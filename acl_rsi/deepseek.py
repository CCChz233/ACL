import fcntl
import json
import os
import re
import ssl
import time
import uuid
from pathlib import Path

import httpx
import truststore
from openai import OpenAI


class BudgetExceeded(RuntimeError):
    def __init__(self, reason: str, details: dict):
        super().__init__(reason)
        self.reason, self.details = reason, details


class ProviderError(RuntimeError):
    """Sanitized provider failure, kept distinct from task/model failure."""
    def __init__(self, error_type: str, status_code=None):
        super().__init__(f"DeepSeek API failed: {error_type}, status={status_code}")
        self.error_type, self.status_code = error_type, status_code


def normalize_json_response(content: str) -> str:
    """Preserve valid JSON even when a string inside it contains a code fence."""
    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        fenced = re.fullmatch(r"\s*```(?:json)?\s*([\s\S]*?)\s*```\s*", content)
        candidate = fenced.group(1) if fenced else content.lstrip()
        try:
            value, _ = json.JSONDecoder().raw_decode(candidate)
        except json.JSONDecodeError:
            return candidate
        # The bridge executes exactly the first leading JSON action. Trailing prose/actions
        # are not executed; the original provider response is retained in the audit log.
        return json.dumps(value) if isinstance(value, (dict, list)) else candidate


def action_tool(role: str) -> dict:
    actions = {
        "analyst": ["digest_many", "report"],
        "digester": ["read_file", "glob", "grep", "bash", "return"],
        "propose": ["list_files", "read_file", "list_traces", "read_trace", "edit_file", "write_file", "done", "abort"],
    }
    if role == "critic":
        properties = {"verdict": {"type": "string", "enum": ["accept", "reject"]},
                      "reasons": {"type": "array", "items": {"type": "string"}},
                      "risk_notes": {"type": "array", "items": {"type": "string"}}}
        required = ["verdict", "reasons", "risk_notes"]
    else:
        properties = {"action": {"type": "string", "enum": actions[role]}}
        for key in ("path", "pattern", "cmd", "old", "new", "content", "summary", "task_id", "reason"):
            properties[key] = {"type": "string"}
        for key in ("offset", "limit", "max_hits", "from_step", "to_step"):
            properties[key] = {"type": "integer"}
        properties["detail"] = {"type": "boolean"}
        properties["requests"] = {"type": "array", "items": {"type": "object", "properties": {
            "task_id": {"type": "string"}, "lens": {"type": "string", "enum": ["failure", "capability_gap", "success"]},
            "questions": {"type": "array", "items": {"type": "string"}}}, "required": ["task_id", "lens"]}}
        properties["digest"] = {"type": "object", "additionalProperties": True}
        for key in ("edits", "failure_modes", "capability_gaps", "success_habits"):
            properties[key] = {"type": "array", "items": {"type": "object", "additionalProperties": True}}
        required = ["action"]
    return {"type": "function", "function": {
        "name": "submit_rrsi_action", "description": "Submit one real RRSI action or review. The runtime executes it; never invent tool results.",
        "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


class UsageLedger:
    """Process- and thread-safe request reservation; failed requests retain their reservation."""

    def __init__(self, path: Path, max_calls: int, max_tokens: int):
        self.path, self.max_calls, self.max_tokens = Path(path), max_calls, max_tokens
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def update(self, fn):
        with self.path.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            state = json.loads(handle.read() or '{"requests": []}')
            result = fn(state)
            handle.seek(0)
            handle.truncate()
            json.dump(state, handle, indent=2)
            handle.flush()
            return result

    def reserve(self, role: str, messages: list, output_tokens: int, tools=None) -> str:
        # UTF-8 byte count plus protocol allowance conservatively bounds visible input.
        reserve = len(json.dumps([messages, tools], ensure_ascii=False).encode()) + output_tokens + 4096

        def change(state):
            rows = state["requests"]
            charged = sum(row["charged_tokens"] for row in rows)
            actual = sum(row.get("usage", {}).get("total_tokens", 0) for row in rows)
            reason = ("call_limit" if len(rows) >= self.max_calls else
                      "token_limit" if actual >= self.max_tokens else
                      "token_reservation" if charged + reserve > self.max_tokens else None)
            if reason:
                raise BudgetExceeded(reason, {"role": role, "calls": len(rows),
                    "max_calls": self.max_calls, "actual_tokens": actual,
                    "charged_tokens": charged, "max_tokens": self.max_tokens,
                    "remaining_charged_tokens": self.max_tokens - charged,
                    "next_request_reserved_tokens": reserve})
            request_id = uuid.uuid4().hex
            rows.append({"id": request_id, "role": role, "status": "reserved", "charged_tokens": reserve,
                         "reserved_tokens": reserve, "time": time.time()})
            return request_id

        return self.update(change)

    def finish(self, request_id: str, usage: dict, model: str) -> None:
        def change(state):
            row = next(row for row in state["requests"] if row["id"] == request_id)
            row.update(status="completed", usage=usage, model=model,
                       charged_tokens=usage["total_tokens"])
        self.update(change)

    def summary(self) -> dict:
        return self.update(lambda state: {
            "calls": len(state["requests"]),
            "completed": sum(row["status"] == "completed" for row in state["requests"]),
            "charged_tokens": sum(row["charged_tokens"] for row in state["requests"]),
            "actual_tokens": sum(row.get("usage", {}).get("total_tokens", 0) for row in state["requests"]),
        })


class DeepSeekClient:
    def __init__(self, cfg: dict, ledger: UsageLedger, role: str, limits: dict):
        if not os.environ.get("DEEPSEEK_API_KEY"):
            raise ValueError("DEEPSEEK_API_KEY is not configured in the environment or .env")
        self.cfg, self.ledger, self.role, self.limits = cfg, ledger, role, limits
        self.client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"], base_url=cfg["api_base"],
            max_retries=0, timeout=120,
            http_client=httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)),
        )

    def complete(self, messages: list, *, tools=None, json_only=False, max_tokens=None, model=None, tool_choice=None):
        max_tokens = min(max_tokens or self.limits["max_output_tokens"], self.limits["max_output_tokens"])
        rid = self.ledger.reserve(self.role, messages, max_tokens, tools)
        kwargs = {"tools": tools} if tools else {}
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if json_only:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self.client.chat.completions.create(
                model=model or self.cfg["model"], messages=messages, max_tokens=max_tokens,
                extra_body={"thinking": {"type": "enabled" if self.cfg.get("thinking") else "disabled"}},
                **kwargs,
            )
        except Exception as exc:
            # Do not serialize SDK exceptions that can contain request credentials.
            raise ProviderError(type(exc).__name__, getattr(exc, "status_code", None)) from None
        if response.usage is None:
            raise ProviderError("MissingUsage")
        self.ledger.finish(rid, response.usage.model_dump(), response.model)
        responses = self.ledger.path.parent / (self.ledger.path.stem + "-responses")
        responses.mkdir(exist_ok=True)
        (responses / f"{rid}.json").write_text(response.model_dump_json(indent=2))
        return response

    def generate(self, prompt, system=None, max_retries=0, json_only=False, model=None,
                 max_tokens=None, cache_prefix=None):
        messages = []
        native = json_only and self.role in {"analyst", "digester", "propose", "critic"}
        if system:
            suffix = ("\nUse submit_rrsi_action exactly once for your next action. Do not simulate [you] or [result] records. "
                      "Only the runtime executes actions and provides real results.") if native else ("\nReturn JSON." if json_only else "")
            messages.append({"role": "system", "content": system + suffix})
        messages.append({"role": "user", "content": "\n\n".join(x for x in (cache_prefix, prompt) if x)})
        response = self.complete(
            messages, json_only=json_only and not native, max_tokens=max_tokens, model=model,
            tools=[action_tool(self.role)] if native else None,
            tool_choice={"type": "function", "function": {"name": "submit_rrsi_action"}} if native else None,
        )
        if native and response.choices[0].message.tool_calls:
            return normalize_json_response(response.choices[0].message.tool_calls[0].function.arguments)
        content = response.choices[0].message.content or ""
        if not content:
            raise RuntimeError("DeepSeek returned empty content")
        if json_only:
            # Let RRSI's role-specific recovery handle genuinely malformed output.
            content = normalize_json_response(content)
        return content


def bind_search_client(cfg: dict, ledger_path: Path) -> UsageLedger:
    """Inject the provider at RRSI's existing role boundaries; upstream code stays intact."""
    import importlib
    ledger = UsageLedger(ledger_path, cfg["search"]["max_calls"], cfg["search"]["max_tokens"])
    for name in ("analyst", "digester", "propose", "critic"):
        module = importlib.import_module(f"rrsi.{name}")
        client = DeepSeekClient(cfg, ledger, name, cfg["search"])
        module.generate = client.generate
        if name == "propose":
            # Upstream assumes a different policy model; this experiment starts with the same model in both roles.
            module.SYSTEM_TMPL = module.SYSTEM_TMPL.replace(
                "is a DIFFERENT\nmodel from you", "is configured independently\nfrom your search role")
    return ledger


import time

from pydantic import BaseModel

from minisweagent.exceptions import FormatError
from minisweagent.models.utils.actions_toolcall import (
    BASH_TOOL, format_toolcall_observation_messages, parse_toolcall_actions,
)

from .deepseek import DeepSeekClient, UsageLedger


class ModelConfig(BaseModel):
    model_name: str
    observation_template: str
    format_error_template: str


class DeepSeekMiniModel:
    """mini-SWE-agent Model protocol with direct, metered DeepSeek API calls."""

    def __init__(self, cfg: dict, templates: dict, ledger_path):
        self.config = ModelConfig(model_name=cfg["model"],
                                  observation_template=templates["observation_template"],
                                  format_error_template=templates["format_error_template"])
        self.ledger = UsageLedger(ledger_path, cfg["target"]["max_calls"], cfg["target"]["max_tokens"])
        self.client = DeepSeekClient(cfg, self.ledger, "target", cfg["target"])

    def query(self, messages: list, **kwargs):
        allowed = {"role", "content", "tool_calls", "tool_call_id", "reasoning_content"}
        prepared = [{key: value for key, value in row.items() if key in allowed and value is not None}
                    for row in messages if row.get("role") != "exit"]
        response = self.client.complete(prepared, tools=[BASH_TOOL])
        extra = {"cost": 0.0, "usage": response.usage.model_dump(), "timestamp": time.time()}
        try:
            actions = parse_toolcall_actions(
                response.choices[0].message.tool_calls or [],
                format_error_template=self.config.format_error_template,
                template_kwargs={"finish_reason": response.choices[0].finish_reason},
            )
        except FormatError as exc:
            exc.messages[0]["extra"].update(extra)
            raise
        message = response.choices[0].message.model_dump(exclude_none=True)
        message["extra"] = {**extra, "actions": actions}
        return message

    def format_message(self, **kwargs):
        return kwargs

    def format_observation_messages(self, message, outputs, template_vars=None):
        return format_toolcall_observation_messages(
            actions=message.get("extra", {}).get("actions", []), outputs=outputs,
            observation_template=self.config.observation_template, template_vars=template_vars,
        )

    def get_template_vars(self, **kwargs):
        return self.config.model_dump()

    def serialize(self):
        return {"info": {"config": {"model": self.config.model_dump()},
                         "usage": self.ledger.summary(), "currency_cost": None,
                         "cost_tracking": "API tokens; currency cost not estimated"}}


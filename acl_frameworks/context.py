"""Allowlisted evidence export and audited filesystem access for optimizers."""
import json
from pathlib import Path
import shutil
import time

from acl_rsi.settings import write_json
from .common import ROOT, read, sha


class EvidenceWorkspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative, *, write=False):
        p = Path(relative)
        if not p.parts or p.is_absolute() or '..' in p.parts or any(s.startswith('.') for s in p.parts):
            raise ValueError('Only public workspace-relative paths are allowed')
        target = (self.root / p).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError('Workspace escape')
        if write and p.parts[0] not in ('candidates', 'reports', 'scratch', 'pending_eval.json'):
            raise ValueError('Evidence and source archives are immutable')
        return target

    def event(self, value):
        with (self.root / 'file-access.jsonl').open('a') as handle:
            handle.write(json.dumps({'time': time.time(), **value}, ensure_ascii=False) + '\n')

    def read(self, relative, offset=0, limit=32000):
        if offset < 0 or not 0 < limit <= 128000:
            raise ValueError('Invalid read bounds')
        path = self.path(relative)
        text = path.read_text()
        value = text[offset:offset+limit]
        self.event({'operation': 'read', 'path': relative, 'sha256': sha(path), 'offset': offset,
                    'returned_chars': len(value), 'total_chars': len(text),
                    'truncated': offset+len(value) < len(text), 'source_kind': Path(relative).parts[0]})
        return value

    def write(self, relative, content):
        path = self.path(relative, write=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.event({'operation': 'write', 'path': relative, 'sha256': sha(path)})

    def glob(self, pattern):
        if Path(pattern).is_absolute() or '..' in Path(pattern).parts:
            raise ValueError('Invalid glob')
        return [str(p.relative_to(self.root)) for p in sorted(self.root.glob(pattern))
                if p.is_file() and not any(s.startswith('.') for s in p.relative_to(self.root).parts)
                and p.resolve().is_relative_to(self.root)]


def export_baseline(root, ids):
    ws = EvidenceWorkspace(root)
    if (ws.root / 'snapshot.json').exists():
        raise ValueError('Snapshot already exists; do not overwrite evidence')
    baseline = ROOT / 'work/verified-mini-50-baseline-v2'
    dataset = {r['instance_id']: r for r in read(ROOT / 'benchmarks/datasets/swe-bench-verified-mini/test.json')}
    from acl_gepa_swe.feedback import record
    rows = []
    for iid in ids:
        if iid not in dataset:
            raise ValueError('Unknown public task')
        source = baseline / 'runs/swe/jobs/base' / iid / 'trial-0'
        grade = record(source, iid, dataset[iid], trace=False)
        messages = []
        for msg in read(source / 'trajectory.json').get('messages', []):
            clean = {k: msg[k] for k in ('role', 'content', 'tool_calls', 'tool_call_id') if k in msg}
            if msg.get('extra', {}).get('actions'):
                clean['extra'] = {'actions': msg['extra']['actions']}
            messages.append(clean)
        folder = ws.root / 'history' / iid
        write_json(folder / 'trajectory.json', {'messages': messages})
        write_json(folder / 'feedback.json', {'resolved': grade['score'], 'stop': grade['stop'],
                    'usage': grade['usage'], 'problem_statement': dataset[iid]['problem_statement']})
        rows.append({'task_id': iid, 'trajectory_sha256': sha(folder / 'trajectory.json'),
                     'feedback_sha256': sha(folder / 'feedback.json')})
    harness = ws.root / 'harness'
    harness.mkdir()
    for name in ('agent.py', 'swebench.yaml', 'LICENSE.md'):
        shutil.copy2(baseline / 'repo/domains/swe/harness' / name, harness / name)
    write_json(ws.root / 'snapshot.json', {'scope': 'historical development evidence; not heldout',
        'feedback': 'public issue, own interactions and binary outcome only', 'tasks': rows,
        'harness': {p.name: sha(p) for p in harness.iterdir()}})
    return ws

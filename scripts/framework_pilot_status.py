"""Read saved pilot status and usage; never launch or retry model work."""
import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def usage(path):
    if not path.exists():
        return {'requests': 0, 'completed': 0, 'known_tokens': 0, 'unknown_usage_requests': 0}
    rows = read(path)['requests']
    return {'requests': len(rows), 'completed': sum(r['status'] == 'completed' for r in rows),
            'known_tokens': sum(r.get('usage', {}).get('total_tokens', 0) for r in rows),
            'unknown_usage_requests': sum('usage' not in r for r in rows),
            'charged_or_reserved_tokens': sum(r['charged_tokens'] for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    args = parser.parse_args()
    result = {}
    for name in ('harnessfix', 'meta-harness'):
        folder = args.work / name
        state = read(folder / 'status.json') if (folder / 'status.json').exists() else {'status': 'pending'}
        state['optimizer'] = usage(folder / 'optimizer-api/usage.json')
        state['target'] = []
        for path in sorted((folder / 'evaluations').glob('*/trials/*/worker.json')):
            grade = path.parent / 'grade.json'
            state['target'].append({'candidate': path.parents[2].name, 'task': path.parent.name,
                'worker_exit': read(path)['exit_status'], 'grade': read(grade) if grade.exists() else None,
                'usage': usage(path.parent / 'usage.json')})
        if (folder / 'result.json').exists():
            state['result'] = read(folder / 'result.json')
        result[name] = state
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

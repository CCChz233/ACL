"""Summarize the completed Mini50 RSI comparison from immutable local evidence."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='configs/mini50-round1-recovery.json')
    parser.add_argument('--output', default='docs/mini50_round1_results.json')
    args = parser.parse_args()
    cfg = read(ROOT / args.config); workspace = ROOT / cfg['workspace']
    baseline_workspace = ROOT / cfg['baseline_workspace']
    ids = cfg['evolve_ids']; source = {row['instance_id']: row for row in read(ROOT / cfg['dataset'])}
    assert len(ids) == len(set(ids)) == 50
    jobs = {}; all_requests = []; stop_reasons = {}; repo_results = {}
    for job, location in [('base', baseline_workspace), ('r0A', workspace)]:
        tasks = []; requests = []; repos = defaultdict(lambda: {'n': 0, 'resolved': 0})
        reasons = Counter(); statuses = Counter(); official = 0
        for iid in ids:
            trial = location / 'runs/swe/jobs' / job / iid / 'trial-0'
            grade = read(trial / 'grade.json'); worker = read(trial / 'worker.json')
            usage = read(trial / 'usage.json')['requests']
            patch = (trial / 'patch.diff').read_bytes()
            assert grade['completed'] and not grade.get('infrastructure_failure'), iid
            assert hashlib.sha256(patch).hexdigest() == grade['patch_sha256'], iid
            if grade.get('report_path'):
                report = Path(grade['report_path']); assert read(report)[iid]['resolved'] == grade['resolved']; official += 1
                report = str(report.relative_to(ROOT))
            else:
                assert not patch and not grade['resolved']; report = None
            calls = len(usage); tokens = sum(row.get('usage', {}).get('total_tokens', 0) for row in usage)
            assert calls <= cfg['target']['max_calls'] and tokens <= cfg['target']['max_tokens']
            assert calls == worker['usage']['calls'] and tokens == worker['usage']['actual_tokens']
            assert all(row['status'] == 'completed' for row in usage)
            assert len(list((trial / 'usage-responses').glob('*.json'))) == calls
            assert (trial / 'trajectory.json').exists()
            statuses[worker['exit_status']] += 1
            reason = worker.get('budget_stop', {}).get('reason')
            if reason: reasons[reason] += 1
            repo = source[iid]['repo']; repos[repo]['n'] += 1; repos[repo]['resolved'] += bool(grade['resolved'])
            tasks.append({'instance_id': iid, 'repo': repo, 'resolved': bool(grade['resolved']),
                          'exit_status': worker['exit_status'], 'budget_stop_reason': reason,
                          'calls': calls, 'actual_tokens': tokens, 'patch_sha256': grade['patch_sha256'],
                          'official_report': report})
            requests.extend(usage)
        assert len({r['id'] for r in requests}) == len(requests)
        jobs[job] = {'n_tasks': 50, 'n_resolved': sum(row['resolved'] for row in tasks),
                     'rate': sum(row['resolved'] for row in tasks) / 50,
                     'calls': len(requests), 'actual_tokens': sum(row['actual_tokens'] for row in tasks),
                     'official_test_reports': official, 'by_repository': dict(repos),
                     'exit_status_counts': dict(statuses), 'budget_stop_counts': dict(reasons), 'tasks': tasks}
        if job != 'base': all_requests.extend(requests)
    old = {row['instance_id']: row for row in jobs['base']['tasks']}
    new = {row['instance_id']: row for row in jobs['r0A']['tasks']}
    transitions = {'newly_resolved': [], 'regressions': [], 'both_resolved': [], 'both_failed': []}
    for iid in ids:
        a, b = old[iid]['resolved'], new[iid]['resolved']
        label = 'both_resolved' if a and b else 'both_failed' if not a and not b else 'newly_resolved' if b else 'regressions'
        transitions[label].append(iid)
    search = read(workspace / 'search_usage.json')['requests']
    assert len(search) <= cfg['search']['max_calls']
    assert all(row['status'] == 'completed' for row in search)
    search_tokens = sum(row.get('usage', {}).get('total_tokens', 0) for row in search)
    assert search_tokens <= cfg['search']['max_tokens']
    assert len({r['id'] for r in all_requests + search}) == len(all_requests) + len(search)
    frontier = read(workspace / 'runs/swe/frontier.json')
    decisions = read(workspace / 'runs/swe/r0/decisions.json')
    proposal = read(workspace / 'runs/swe/r0/A/proposal.json')
    image_mismatches = []
    for iid in ids:
        before = set(read(baseline_workspace / 'images' / f'{iid}.json')['repo_digests'])
        after = set(read(workspace / 'images' / f'{iid}.json')['repo_digests'])
        if not before.intersection(after): image_mismatches.append(iid)
    data = {'status': 'completed', 'config': args.config, 'workspace': cfg['workspace'],
            'rsi_rounds': 1, 'candidate_count': 1, 'baseline_reused': True,
            'evaluations': jobs, 'candidate_gain_percentage_points': round((jobs['r0A']['rate'] - jobs['base']['rate']) * 100, 8),
            'paired_transitions': transitions, 'search_calls_including_failed_first_attempt': len(search),
            'search_actual_tokens_including_failed_first_attempt': search_tokens,
            'search_roles': dict(Counter(row['role'] for row in search)),
            'total_new_api_calls': len(all_requests) + len(search),
            'total_new_actual_tokens': jobs['r0A']['actual_tokens'] + search_tokens,
            'final_selected_job': frontier['incumbent']['job'], 'final_selected_rate': frontier['incumbent']['S'],
            'decisions': decisions, 'mechanism': proposal.get('mechanism'),
            'candidate_commit': read(workspace / 'runs/swe/r0/A/prep.json').get('commit'),
            'image_digest_mismatches': image_mismatches,
            'recovery_protocol': '160-call diagnostic attempt exhausted, then single saved-digest aggregation; total search cap240 calls/2M tokens.',
            'limitations': ['Visible development tasks, not heldout accuracy.', 'One execution per task and one candidate; no repeated-search variance or causal generalization claim.']}
    output = ROOT / args.output; output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: value for key, value in data.items() if key not in ('evaluations', 'paired_transitions', 'decisions', 'limitations')}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

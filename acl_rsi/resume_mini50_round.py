"""Recover a bounded RSI search by aggregating its saved digests without redispatch."""
import json
from pathlib import Path

from .deepseek import DeepSeekClient, UsageLedger, action_tool, normalize_json_response
from .settings import write_json


def aggregate_saved_digests(domain, traces, per_task, round_dir, prior_modes=None, prior_habits=None, model=None):
    """This recovery adapter is explicit: summarize saved evidence once, no new digest loop."""
    from rrsi.analyst import SYSTEM_TMPL
    saved = []
    errors = []
    for path in sorted((round_dir / 'analysis/digests').glob('*.json')):
        digest = json.loads(path.read_text())
        (errors if digest.get('error') else saved).append(digest)
    if not saved:
        raise ValueError('no successful saved digests to recover')
    successes = []
    for iid, rec in traces.items():
        if per_task[iid].mean > 0:
            successes.append({'task_id': iid, 'trace': domain.render_trace(rec, detail=False)})
    tool = action_tool('analyst')
    parameters = tool['function']['parameters']
    parameters['properties']['action']['enum'] = ['report']
    parameters['required'] = ['action', 'failure_modes', 'capability_gaps', 'success_habits']
    context = {'saved_digests': saved, 'unsuccessful_digest_records': errors,
               'successful_baseline_traces': successes,
               'instruction': 'Synthesize the report now. No further digester calls are available. Treat digests as fallible model-generated hypotheses. Claims about gold patches, expected upstream fixes, or hidden tests are unsupported unless directly present in the public trace; do not promote such claims to evidence. Use only trace observations, public issue requirements, known exit status, and external resolved true/false. Generalize mechanisms; do not prescribe issue-specific code fixes.'}
    cfg = domain.cfg
    ledger = UsageLedger(Path(cfg['workspace']) / 'search_usage.json', cfg['search']['max_calls'], cfg['search']['max_tokens'])
    client = DeepSeekClient(cfg, ledger, 'analyst', cfg['search'])
    response = client.complete([
        {'role': 'system', 'content': SYSTEM_TMPL.format(domain_brief=domain.briefs['analyst']) + '\nRECOVERY: Return the final report with submit_rrsi_action. Existing digests are supplied; do not request more.'},
        {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}],
        tools=[tool], tool_choice={'type': 'function', 'function': {'name': 'submit_rrsi_action'}}, model=model)
    calls = response.choices[0].message.tool_calls or []
    raw = calls[0].function.arguments if calls else response.choices[0].message.content or ''
    act = json.loads(normalize_json_response(raw))
    if act.get('action') != 'report':
        raise ValueError('recovery analyst did not return a report')
    report = {key: act.get(key) or [] for key in ('failure_modes', 'capability_gaps', 'success_habits')}
    if not all(isinstance(value, list) for value in report.values()):
        raise ValueError('invalid recovery report fields')
    report['failure_modes'].sort(key=lambda row: -(row.get('n_tasks') or 0))
    report['n_digests'] = len(saved)
    report['recovery'] = {'mode': 'aggregate_existing_digests_without_redispatch', 'successful_saved_digests': len(saved),
                          'failed_saved_digests': len(errors), 'successful_raw_traces': len(successes)}
    write_json(round_dir / 'analysis/recovery_inputs.json', context)
    return report


def main():
    import rrsi.loop
    from .mini50_round import main as run_main
    rrsi.loop.analyze = aggregate_saved_digests
    run_main()


if __name__ == '__main__':
    main()

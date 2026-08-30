"""Structural check: the showcase dataset produces the runbook's numbers.

No network, no model calls. Run: python -m insurance-helper... no — run from
the parent directory:  python -m <pkg>.test_pipeline  or simply
python test_pipeline.py from inside the package directory with the parent on
sys.path. Asserts the deterministic engine and the scripted mock outcomes.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('HELLO_AI_MOCK', '1')

_PKG_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PKG_DIR.parent))
_PKG = _PKG_DIR.name

import importlib

tools = importlib.import_module(f'{_PKG}.tools')
hello_ai = importlib.import_module(f'{_PKG}.hello_ai')
make_prospects = importlib.import_module(f'{_PKG}.make_prospects')


def sheet_text() -> str:
    lines = ['|'.join(make_prospects.HEADER[:-1])]
    for row in make_prospects.ROWS:
        lines.append('|'.join(str(v) for v in row))
    return '\n'.join(lines)


def main() -> None:
    ctx = SimpleNamespace(state={})

    opened = tools.open_batch(sheet_text(), 'prospects.xlsx', ctx)
    assert opened['status'] == 'success', opened
    counts = opened['counts']
    assert counts['total'] == 15, counts
    assert (counts['hot'], counts['warm'], counts['cold']) == (4, 7, 4), counts

    batch = ctx.state[tools.config.BATCH_STATE_KEY]
    by_name = {l['name']: l for l in batch['leads'].values()}
    hots = {n for n, l in by_name.items() if l['priority'] == tools.HOT}
    assert hots == {'Amir Hassan', 'Tan Wei Ming', 'Siti Zulaikha',
                    'Ahmad Faizal'}, hots

    assert by_name['Amir Hassan']['gap_k'] == 980
    assert by_name['Amir Hassan']['policy'] == 'Term S$1M + Child Education Plan'
    assert by_name['Ahmad Faizal']['policy'].startswith('Mortgage-linked Term')
    assert 'CI rider' in by_name['Ahmad Faizal']['policy']
    assert by_name['Wong Kai Jie']['policy'] == 'Retirement / Legacy Plan'
    assert by_name['Nur Farhana']['policy'] == 'Savings + CI starter'
    assert by_name['Lim Mei Ling']['policy'] == 'Health / CI top-up'
    assert counts['combined_gap_sgd_k'] == 8579, counts['combined_gap_sgd_k']

    # Scripted campaign: Hot + Warm = 11 calls, split 4/3/2/2.
    targets = [l for l in batch['leads'].values()
               if l['priority'] in (tools.HOT, tools.WARM)]
    assert len(targets) == 11
    answer = hello_ai._mock_batch(targets)
    details = [r['detail'] for r in answer['results']]
    assert all(d.startswith('[MOCK]') for d in details)
    assert sum('interested —' in d and 'not interested' not in d
               for d in details) == 4, details
    assert sum('call later' in d for d in details) == 3, details
    assert sum('not interested' in d for d in details) == 2, details
    assert sum('no answer' in d for d in details) == 2, details
    assert sum('WhatsApp' in d for d in details) == 5, details

    # The two no-answers stay pending for a scheduled retry, nine are done.
    recorded = tools.record_outreach_results(answer['results'], ctx)
    assert recorded['status'] == 'success', recorded
    assert recorded['counts']['contacted'] == 9, recorded['counts']
    assert recorded['counts']['pending_retry'] == 2, recorded['counts']

    print('test_pipeline: all assertions passed')


if __name__ == '__main__':
    main()

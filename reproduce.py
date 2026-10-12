"""Run the report analysis from public raw files, or redraw existing aggregates."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from settings import RAW, WORK, ROOT


def run(raw, work, download=False, figures_only=False):
    raw, work = raw.resolve(), work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, BIKE_RAW_DIR=str(raw), BIKE_WORK_DIR=str(work), PYTHONUTF8='1')
    commands = []
    if download:
        commands.append('acquire.py')
    if not figures_only:
        commands += ['probe.py', 'robustness.py', 'rebalance.py', 'infer_moves.py', 'write_report.py']
    commands += ['report_figures.py', 'summary_figure.py', 'report_tables.py']
    started = time.monotonic()
    steps = []
    for script in commands:
        print(f'RUN {script}', flush=True)
        t = time.monotonic()
        # One selected interpreter and one shared configuration for every step.
        subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / script)], cwd=ROOT, env=env, check=True)
        steps.append({'script': script, 'seconds': round(time.monotonic()-t, 2)})
    result = {'status': 'passed', 'mode': 'figures-only' if figures_only else 'full',
              'python': sys.version.split()[0], 'steps': steps,
              'seconds': round(time.monotonic()-started, 2)}
    (work/'reproduction_run.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, default=RAW)
    p.add_argument('--work', type=Path, default=WORK)
    p.add_argument('--download', action='store_true', help='Fetch missing public inputs first')
    p.add_argument('--figures-only', action='store_true', help='Use existing verified aggregates')
    a=p.parse_args();run(a.raw, a.work, a.download, a.figures_only)

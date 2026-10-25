"""Bounded local diagnostic of the unchanged multi-context native journey."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

repo = Path(__file__).resolve().parents[1]
folder = Path(os.environ['MGT_DIAGNOSTIC_OUTPUT'])
folder.mkdir(parents=True, exist_ok=True)
source = repo / 'tests/test_multi_game_contexts.py'
original_run = subprocess.run
original_temp = tempfile.TemporaryDirectory
invocation = {}

class RetainedProject(original_temp):
    def cleanup(self):
        self._finalizer.detach()

def compile_only(command, **kwargs):
    if Path(str(command[0])).name == 'test':
        invocation.update(command=command, options=kwargs)
        return subprocess.CompletedProcess(command, 0)
    return original_run(command, **kwargs)

tempfile.TemporaryDirectory = RetainedProject
subprocess.run = compile_only
fixture = source.read_text().replace(
    '            let limit = Date(timeIntervalSinceNow: 30)',
    '            log("probe", "wait.begin line=\\(line)")\n            let limit = Date(timeIntervalSinceNow: 30)',
).replace(
    '            precondition(condition(),',
    '            log("probe", "wait.end line=\\(line)")\n            precondition(condition(),',
)
exec(compile(fixture, str(source), 'exec'), {'__file__': str(source), '__name__': '__main__'})
subprocess.run = original_run
tempfile.TemporaryDirectory = original_temp
options = invocation['options']
options.pop('check')
options.pop('timeout')
options['env']['MGT_PROFILE_OPERATIONS'] = '1'
records = []
for attempt in range(1, 25):
    log = folder / f'multi-context-stress-{attempt:02d}.log'
    started = time.monotonic()
    with log.open('w') as output:
        process = subprocess.Popen(invocation['command'], **options, stdout=output, stderr=subprocess.STDOUT)
        sample = None
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed > 10 and sample is None:
                sample_path = folder / f'multi-context-stress-{attempt:02d}.sample.txt'
                sample = subprocess.Popen(['/usr/bin/sample', str(process.pid), '3', '10', '-file', str(sample_path)], stdout=output, stderr=subprocess.STDOUT)
            if elapsed > 90:
                process.kill()
                process.wait()
                break
            time.sleep(0.1)
        if sample:
            sample.wait(timeout=10)
    record = {'attempt': attempt, 'exitCode': process.returncode, 'seconds': round(time.monotonic() - started, 3), 'log': str(log), 'sampled': sample is not None}
    records.append(record)
    print(json.dumps(record), flush=True)
    (folder / 'multi-context-stress-result.json').write_text(json.dumps({'sourceSHA': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(), 'project': str(options['cwd']), 'operationProfiling': True, 'attempts': records}, indent=2) + '\n')
    if process.returncode:
        break

if any(record['exitCode'] for record in records):
    raise SystemExit(1)

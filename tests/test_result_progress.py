from io import StringIO
import json
import os
import subprocess
import sys
import time

import pytest
from rich.progress import Progress

from bioreport import cli
from bioreport.pdf_parallel import prepared_results
from bioreport.result_progress import ResultProgressReader, report_result_progress


def test_reader_retries_missing_file_and_waits_for_complete_unicode_event(tmp_path):
    path = tmp_path / 'progress.jsonl'
    event = {'kind': 'DEG', 'stage': 'render', 'completed': 1, 'total': 231, 'label': '比较组一'}
    encoded = (json.dumps(event, ensure_ascii=False) + '\n').encode()
    split = encoded.index('比'.encode()) + 1
    with ResultProgressReader(path) as reader:
        assert reader.read() == []
        path.write_bytes(encoded[:split])
        assert reader.read() == []
        with path.open('ab') as output:
            output.write(encoded[split:])
        assert reader.read() == [event]
        assert reader.read() == []


def test_progress_ignores_corrupt_records_and_does_not_break_reports_on_io_failure(tmp_path, monkeypatch):
    path = tmp_path / 'progress.jsonl'
    path.write_text('not json\n[]\n' + '\n'.join(json.dumps(value) for value in [
        {'kind':'DEG','stage':'prepare','completed':True,'total':2},
        {'kind':'DEG','stage':'prepare','completed':3,'total':2},
        {'kind':'other','stage':'prepare','completed':1,'total':2},
    ]) + '\n')
    monkeypatch.setenv('BIOREPORT_PROGRESS_FILE', str(path))
    report_result_progress('DEG','prepare',1,2,'B_vs_A',workers=2)
    with ResultProgressReader(path) as reader:
        assert reader.read() == [{'kind':'DEG','stage':'prepare','completed':1,
                                  'total':2,'label':'B_vs_A','workers':2}]
    monkeypatch.setenv('BIOREPORT_PROGRESS_FILE', str(tmp_path / 'missing' / 'file'))
    report_result_progress('DEG','prepare',2,2,'C_vs_A',workers=2)


def test_parallel_progress_counts_completed_jobs_before_ordered_consumption(tmp_path, monkeypatch):
    path = tmp_path / 'progress.jsonl'
    monkeypatch.setenv('BIOREPORT_PROGRESS_FILE', str(path))

    class Worker:
        def __init__(self, directory):
            pass

        def request(self, job):
            if job['label'] == 'slow':
                deadline = time.monotonic() + 5
                with ResultProgressReader(path) as reader:
                    while time.monotonic() < deadline:
                        if any(row['completed'] == 1 and row['label'] == 'fast' for row in reader.read()):
                            break
                        time.sleep(.01)
                    else:
                        raise AssertionError('Fast result must be reported before slow result is emitted')
            return job['label']

        def stop(self, force=False):
            pass

    monkeypatch.setattr('bioreport.pdf_parallel._Worker', Worker)
    with prepared_results([{'label':'slow'},{'label':'fast'}],2,'DEG') as output:
        assert list(output) == ['slow','fast']
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row['completed'] for row in rows] == [0,1,2]
    assert [row['label'] for row in rows[1:]] == ['fast','slow']


def test_terminal_updates_while_quarto_stdout_is_still_buffered(tmp_path, monkeypatch):
    path = tmp_path / 'progress.jsonl'
    script = '''
import select, sys
from bioreport.result_progress import report_result_progress as report
report('DEG', 'render', 0, 2)
report('DEG', 'prepare', 0, 2, workers=2)
report('DEG', 'prepare', 1, 2, 'B_vs_A', workers=2)
# No stdout until the CLI acknowledges that the live progress was displayed.
if not select.select([sys.stdin], [], [], 5)[0]:
    raise RuntimeError('CLI waited for buffered Quarto output')
sys.stdin.readline()
report('DEG', 'render', 1, 2, 'B_vs_A')
report('DEG', 'prepare', 2, 2, 'C_vs_A', workers=2)
report('DEG', 'render', 2, 2, 'C_vs_A')
print("Cell 23/23: 'pdf-deg'...Done", flush=True)
print('[typst]: Compiling report_pdf.typ to report_pdf.pdf...', flush=True)
'''
    env = os.environ.copy()
    env['BIOREPORT_PROGRESS_FILE'] = str(path)
    process = subprocess.Popen([sys.executable,'-u','-c',script], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    seen = []
    acknowledged = False

    class CaptureProgress(Progress):
        def update(self, task_id, **kwargs):
            nonlocal acknowledged
            super().update(task_id, **kwargs)
            snapshots = [(task.description,task.completed,task.total) for task in self.tasks]
            seen.extend(snapshots)
            if not acknowledged and any('DEG plots' in desc and count == 1 for desc,count,total in snapshots):
                acknowledged = True
                process.stdin.write('displayed\n')
                process.stdin.flush()

    progress = CaptureProgress(disable=True)
    monkeypatch.setattr(cli,'Progress',lambda *args,**kwargs: progress)
    try:
        _, error, finished = cli._stream_quarto_output(process,'pdf',path)
        assert process.wait(timeout=5) == 0
        assert acknowledged and finished and error is None
        assert any('DEG plots' in desc and count == total == 2 for desc,count,total in seen)
        assert any('DEG results' in desc and count == total == 2 for desc,count,total in seen)
        assert len(progress.tasks) == 1
        assert 'compiling document with Typst' in progress.tasks[0].description
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


def test_result_rows_switch_modules_and_skip_empty_preparation(tmp_path, monkeypatch):
    path = tmp_path / 'progress.jsonl'
    monkeypatch.setenv('BIOREPORT_PROGRESS_FILE',str(path))
    report_result_progress('DEG','prepare',2,2,'B_vs_A',workers=2)
    report_result_progress('DEG','render',2,2,'B_vs_A')
    report_result_progress('enrichment','render',0,4)
    report_result_progress('enrichment','prepare',0,0,workers=0)
    report_result_progress('enrichment','render',4,4,'GO B_vs_A DOWN')
    progress = Progress(disable=True)
    monkeypatch.setattr(cli,'Progress',lambda *args,**kwargs: progress)

    class Process:
        stdout = StringIO('')

    cli._stream_quarto_output(Process(),'pdf',path)
    assert not any('DEG' in task.description for task in progress.tasks)
    rows = [task for task in progress.tasks if task.visible and 'Enrichment results' in task.description]
    assert len(rows) == 1 and rows[0].completed == rows[0].total == 4
    assert not any('Enrichment plots' in task.description and task.visible for task in progress.tasks)


def test_cli_scopes_progress_to_the_pdf_render_and_resets_old_events(tmp_path, monkeypatch):
    class StopAfterEnvironment(Exception):
        pass

    captured = {}

    def start(*args, **kwargs):
        captured['progress_file'] = kwargs['env'].get('BIOREPORT_PROGRESS_FILE')
        raise StopAfterEnvironment()

    monkeypatch.setattr(cli.subprocess,'Popen',start)
    monkeypatch.setenv('BIOREPORT_PROGRESS_FILE','/old/run/progress')
    path = tmp_path/'result-progress.jsonl'
    path.write_text('old run')
    with pytest.raises(StopAfterEnvironment):
        cli.render_report({'report':{'output_format':'pdf'}},'config.json',str(tmp_path),tmp_path)
    assert captured['progress_file'] == str(path)
    assert not path.exists()
    with pytest.raises(StopAfterEnvironment):
        cli.render_report({'report':{'output_format':'html'}},'config.json',str(tmp_path),tmp_path)
    assert captured['progress_file'] is None

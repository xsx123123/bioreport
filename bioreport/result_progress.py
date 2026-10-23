"""Small result progress events, independent of Jupyter's captured output."""
import json
import os
from pathlib import Path
from threading import Lock


_write_lock = Lock()


def report_result_progress(kind, stage, completed, total, label='', *, workers=None):
    path = os.environ.get('BIOREPORT_PROGRESS_FILE')
    if not path:
        return
    event = {'kind': kind, 'stage': stage, 'completed': completed, 'total': total, 'label': label}
    if workers is not None:
        event['workers'] = workers
    # Pipe-driver threads publish worker completions; only the owning kernel
    # publishes report output. Progress must never become notebook output.
    with _write_lock:
        try:
            with open(path, 'a', encoding='utf-8') as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        except OSError:
            # Progress is best effort; report generation remains authoritative.
            pass


class ResultProgressReader:
    def __init__(self, path):
        self.path = Path(path) if path is not None else None
        self.stream = None
        self.pending = b''

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.stream is not None:
            self.stream.close()

    def read(self):
        if self.path is None:
            return []
        try:
            if self.stream is None:
                self.stream = self.path.open('rb')
            self.pending += self.stream.read()
        except OSError:
            return []
        lines = self.pending.split(b'\n')
        self.pending = lines.pop()
        events = []
        for line in lines:
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(event, dict):
                continue
            if event.get('kind') not in ('DEG', 'enrichment') or event.get('stage') not in ('prepare', 'render'):
                continue
            completed, total = event.get('completed'), event.get('total')
            if type(completed) is not int or type(total) is not int or not 0 <= completed <= total:
                continue
            if not isinstance(event.get('label', ''), str):
                continue
            events.append(event)
        return events

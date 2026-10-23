"""Bounded PDF preparation in isolated Python processes.

Workers communicate over ordinary pipes, so they also work inside a Jupyter
kernel without sharing its display stream, Matplotlib state, or semaphores.
Only the owning process emits report blocks. No full result matrices cross
the process boundary; workers return SVG paths and bounded table previews.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout
import json
import os
from pathlib import Path
from queue import Queue
import shutil
import subprocess
import sys
import tempfile
from threading import Lock
import time
import traceback


DEFAULT_WORKERS = 8


def worker_count(config, *, use_environment=True):
    value = os.environ.get('BIOREPORT_PDF_WORKERS') if use_environment else None
    if value is None:
        value = config.get('report', {}).get('pdf', {}).get('workers', DEFAULT_WORKERS)
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError('PDF workers must be a positive integer')
    return value


def _json_default(value):
    if hasattr(value, 'item'):
        return value.item()
    raise TypeError(f'Cannot serialize PDF worker value: {type(value).__name__}')


class _Worker:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir()
        self.log_path = directory / 'worker.log'
        self.log = self.log_path.open('w', encoding='utf-8')
        env = os.environ.copy()
        for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                     'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            env[name] = '1'
        env['MPLCONFIGDIR'] = str(directory / 'matplotlib')
        env['MPLBACKEND'] = 'Agg'
        env.pop('BIOREPORT_BLOCK_MANIFEST', None)
        env.pop('BIOREPORT_ASSET_AUDIT_FILE', None)
        env.pop('BIOREPORT_PROGRESS_FILE', None)
        root = str(Path(__file__).resolve().parents[1])
        env['PYTHONPATH'] = os.pathsep.join(filter(None, [root, env.get('PYTHONPATH')]))
        try:
            self.process = subprocess.Popen(
                [sys.executable, '-u', '-m', 'bioreport', '--pdf-worker'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                text=True, encoding='utf-8', bufsize=1, env=env,
            )
        except BaseException:
            self.log.close()
            raise

    def request(self, job):
        try:
            self.process.stdin.write(json.dumps(job, ensure_ascii=False, default=_json_default) + '\n')
            self.process.stdin.flush()
            response = self.process.stdout.readline()
            if not response:
                diagnostic = self.log_path.read_text(encoding='utf-8', errors='replace')[-4000:]
                raise RuntimeError(f"PDF worker exited for {job['label']} without returning a result: {diagnostic}")
            response = json.loads(response)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"PDF worker failed for {job['label']}: {exc}") from exc
        if not response.get('ok'):
            error = response.get('error', {})
            message = f"PDF preparation failed for {job['label']}: {error.get('message', 'unknown error')}"
            exception = {'FileNotFoundError': FileNotFoundError, 'ValueError': ValueError}.get(
                error.get('type'), RuntimeError)
            raise exception(message)
        return response['result']

    def stop(self, force=False):
        process = self.process
        if force and process.poll() is None:
            process.terminate()
        if process.stdin:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()
        self.log.close()


@contextmanager
def prepared_results(jobs, workers, label):
    """Yield in input order, with at most twice the worker count in flight."""
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError('PDF workers must be a positive integer')
    jobs = list(jobs)
    count = min(workers, len(jobs))
    from loguru import logger
    logger.info('PDF {}: {} results, {} worker processes', label, len(jobs), count)
    from .result_progress import report_result_progress
    report_result_progress(label, 'prepare', 0, len(jobs), workers=count)
    completed = 0
    completion_lock = Lock()

    def mark_prepared(job):
        nonlocal completed
        with completion_lock:
            completed += 1
            report_result_progress(label, 'prepare', completed, len(jobs), job['label'], workers=count)
    with tempfile.TemporaryDirectory(prefix='bioreport-pdf-') as temporary:
        root = Path(temporary)
        tasks = [dict(job, output_dir=str(root / f'result-{index:06}'))
                 for index, job in enumerate(jobs)]
        if count <= 1:
            def sequential():
                for job in tasks:
                    try:
                        result = prepare_job(job)
                        mark_prepared(job)
                        yield result
                    finally:
                        shutil.rmtree(job['output_dir'], ignore_errors=True)
            iterator = sequential()
            try:
                yield iterator
            finally:
                iterator.close()
            return
        children = []
        executor = None
        failed = True
        try:
            for index in range(count):
                children.append(_Worker(root / f'worker-{index}'))
            available = Queue()
            for child in children:
                available.put(child)

            def request(job):
                child = available.get()
                try:
                    result = child.request(job)
                    mark_prepared(job)
                    return result
                finally:
                    available.put(child)

            # Threads only drive the subprocess pipes; all plotting happens in
            # the independent Python interpreters, never in these threads.
            executor = ThreadPoolExecutor(max_workers=count, thread_name_prefix='pdf-worker-pipe')

            def ordered():
                remaining = iter(tasks)
                pending = deque()
                for job in remaining:
                    pending.append((job, executor.submit(request, job)))
                    if len(pending) == 2 * count:
                        break
                while pending:
                    job, future = pending.popleft()
                    try:
                        yield future.result()
                    finally:
                        shutil.rmtree(job['output_dir'], ignore_errors=True)
                    next_job = next(remaining, None)
                    if next_job is not None:
                        pending.append((next_job, executor.submit(request, next_job)))

            iterator = ordered()
            try:
                yield iterator
                failed = False
            finally:
                iterator.close()
        finally:
            if executor:
                # Terminate on failure before joining threads blocked in read.
                if failed:
                    for child in children:
                        if child.process.poll() is None:
                            child.process.terminate()
                executor.shutdown(wait=True, cancel_futures=True)
            for child in children:
                child.stop(force=failed)


def _table_preview(frame, limit, sort_by, columns):
    from .utils.pdf_results import ordered_preview
    selected = ordered_preview(frame, sort_by, columns).head(limit)
    clean = selected.astype(object).where(selected.notna(), None)
    return {'columns': list(clean.columns), 'index': clean.index.tolist(),
            'data': clean.values.tolist(), 'total': len(frame), 'limit': limit}


def _export_panels(figure, directory, stem, english):
    from .i18n import localize_figure
    from .utils.print_theme import export_vector, print_panels, UnsupportedTrace
    if english:
        figure = localize_figure(figure)
    panels = []
    for index, (panel, detail) in enumerate(print_panels(figure)):
        path = directory / f'{stem}-{index:03}.svg'
        try:
            export_vector(panel, path)
        except UnsupportedTrace:
            path.write_bytes(panel.to_image(format='svg', scale=4))
        panels.append({'path': str(path), 'detail': detail})
    return panels


def _prepare_deg(job, directory):
    import pandas as pd
    from .utils.pdf_results import apply_gene_annotation, deg_counts, gene_columns, raw_probability_columns
    from omics.rna.analysis.plot_utils import plot_volcano_pvalue
    path = job['path']
    if not path or not Path(path).is_file():
        raise FileNotFoundError(f"Missing DEG result: {job['comparison']}")
    frame = pd.read_csv(path)
    config = job['config']
    deg = config.get('analysis', {}).get('deg', {})
    volcano = config.get('analysis', {}).get('volcano', {})
    fc, p = deg.get('log2fc_threshold', 1.0), deg.get('pvalue_threshold', .05)
    cap, annotate_top = volcano.get('y_axis', {}).get('display_cap', 50), volcano.get('annotate_top', 5)
    up, down = deg_counts(frame, fc, p)
    figure = plot_volcano_pvalue(
        apply_gene_annotation(frame, config), title='', col_logfc='log2FoldChange',
        col_pval='pvalue', col_padj='padj', col_symbol='Symbol', fc_cutoff=fc,
        pval_cutoff=p, display_cap=cap, annotate_top=annotate_top,
    )
    panels = _export_panels(figure, directory, 'volcano', job['english'])
    frame = gene_columns(apply_gene_annotation(raw_probability_columns(path, frame), config))
    limit = max(1, config.get('report', {}).get('pdf', {}).get('deg_rows', 10) // 2)
    tables = []
    for direction, mask in [('Up', frame['log2FoldChange'].gt(fc)),
                            ('Down', frame['log2FoldChange'].lt(-fc))]:
        selected = mask & pd.to_numeric(frame['pvalue'], errors='coerce').lt(p)
        tables.append(dict(_table_preview(frame.loc[selected], limit, 'pvalue',
            ['Gene ID', 'Symbol', 'log2FoldChange', 'pvalue', 'padj']), direction=direction))
    return {'panels': panels, 'tables': tables, 'up': up, 'down': down,
            'fc': fc, 'p': p, 'cap': cap, 'annotate_top': annotate_top}


def _prepare_enrichment(job, directory):
    import pandas as pd
    from .enrichment import EnrichmentResult, select_enrichment_terms
    from .utils.pdf_results import enrichment_chunks, raw_probability_columns
    from omics.rna.analysis.enrichment_plotly import draw_fancy_dotplot
    result = EnrichmentResult(**job['result'])
    frame = result.frame()
    filtered, chosen = select_enrichment_terms(frame, result.cutoff, job['top_n'])
    prepared = {'total': len(frame), 'filtered': len(filtered), 'chosen': len(chosen), 'pieces': []}
    if chosen.empty:
        return prepared
    for part, (start, chunk) in enumerate(enrichment_chunks(chosen)):
        figure, _ = draw_fancy_dotplot(chunk, top_n=None, p_cutoff=None,
            height_num=450, width_num=1000, wrap_width=28)
        figure.update_layout(coloraxis_cmin=float(chosen['p.adjust'].min()),
            coloraxis_cmax=float(chosen['p.adjust'].max()),
            meta={**(figure.layout.meta or {}), 'count_max': int(chosen['Count'].max())})
        prepared['pieces'].append({'start': start, 'count': len(chunk),
            'indices': list(chunk.index),
            'panels': _export_panels(figure, directory, f'enrichment-{part:03}', job['english'])})
    raw = raw_probability_columns(result.path, frame) if result.path else frame
    prepared['table'] = _table_preview(raw.loc[chosen.index], job['top_n'], 'p.adjust',
        ['Description', 'GeneRatio', 'Count', 'p.adjust'])
    return prepared


def prepare_job(job):
    """Prepare one task, also used by workers=1 for identical semantics."""
    directory = Path(job['output_dir'])
    directory.mkdir(parents=True, exist_ok=True)
    previous_language = os.environ.get('BIOREPORT_LANGUAGE')
    os.environ['BIOREPORT_LANGUAGE'] = 'en' if job['english'] else 'zh'
    started = time.perf_counter()
    try:
        prepare = {'deg': _prepare_deg, 'enrichment': _prepare_enrichment}[job['kind']]
        result = prepare(job, directory)
        result.update(worker_pid=os.getpid(), duration_s=time.perf_counter() - started)
        return result
    finally:
        if previous_language is None:
            os.environ.pop('BIOREPORT_LANGUAGE', None)
        else:
            os.environ['BIOREPORT_LANGUAGE'] = previous_language


def worker_main():
    protocol = sys.stdout
    for line in sys.stdin:
        try:
            # Plot helpers may print diagnostics; keep them off the protocol.
            with redirect_stdout(sys.stderr):
                result = prepare_job(json.loads(line))
            response = {'ok': True, 'result': result}
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            response = {'ok': False, 'error': {'type': type(exc).__name__, 'message': str(exc)}}
        protocol.write(json.dumps(response, ensure_ascii=False, default=_json_default) + '\n')
        protocol.flush()

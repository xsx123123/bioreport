from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import pandas as pd
import pytest

from bioreport import cli
from bioreport.config import load_config
from bioreport.enrichment_views import render_enrichment
from bioreport.pdf_parallel import prepared_results, worker_count
from bioreport.pdf_views import render_pdf_deg
from bioreport.utils import render_output


@pytest.mark.parametrize('flag', ['--workers', '-t', '--threads'])
def test_cli_worker_aliases(flag):
    assert cli.parse_args(['run', flag, '4']).workers == 4


@pytest.mark.parametrize('value', ['0', '-1', '1.5', 'eight'])
def test_cli_rejects_invalid_worker_count(value):
    with pytest.raises(SystemExit) as error:
        cli.parse_args(['run', '--workers', value])
    assert error.value.code == 2


@pytest.mark.parametrize('value', [0, -1, 1.5, True, '8'])
def test_schema_rejects_invalid_worker_count(tmp_path, value):
    path = tmp_path / 'report.json'
    path.write_text(json.dumps({'project': {'project_id': 'parallel-test'},
                               'report': {'pdf': {'workers': value}}}))
    with pytest.raises(ValueError, match='report.pdf.workers'):
        load_config(path)


def test_workers_default_config_and_transport_override(monkeypatch):
    monkeypatch.delenv('BIOREPORT_PDF_WORKERS', raising=False)
    assert worker_count({}) == 8
    config = {'report': {'pdf': {'workers': 4}}}
    assert worker_count(config) == 4
    monkeypatch.setenv('BIOREPORT_PDF_WORKERS', '2')
    assert worker_count(config) == 2
    assert worker_count(config, use_environment=False) == 4


def test_cli_override_is_stored_in_resolved_configuration(tmp_path, monkeypatch):
    path = tmp_path / 'report.json'
    path.write_text(json.dumps({'project': {'project_id': 'parallel-cli'},
                               'report': {'modules': ['about'], 'pdf': {'workers': 2}}}))
    monkeypatch.setattr(cli, 'check_quarto_env', lambda: None)
    captured = []
    monkeypatch.setattr(cli, 'render_templates', lambda config, *args: captured.append(config))
    monkeypatch.setattr(sys, 'argv', ['bioreport', 'run', '-c', str(path),
                                     '-o', str(tmp_path / 'output'), '--dry-run', '--workers', '4'])
    cli.main()
    assert captured[0]['report']['pdf']['workers'] == 4


def test_cli_passes_workers_to_quarto_even_when_original_file_differs(tmp_path, monkeypatch):
    class CaptureEnvironment(Exception):
        pass

    captured = {}

    def popen(*args, **kwargs):
        captured.update(kwargs['env'])
        raise CaptureEnvironment()

    monkeypatch.setattr('subprocess.Popen', popen)
    monkeypatch.setenv('BIOREPORT_PDF_WORKERS', '99')
    config = {'report': {'modules': ['about'], 'output_format': 'pdf', 'pdf': {'workers': 4}}}
    with pytest.raises(CaptureEnvironment):
        cli.render_report(config, str(tmp_path / 'original.json'), str(tmp_path / 'output'), tmp_path)
    assert captured['BIOREPORT_PDF_WORKERS'] == '4'


@pytest.fixture
def project(tmp_path):
    deg = tmp_path / 'deg'
    deg.mkdir()
    for name in ['B_vs_A', 'C_vs_A']:
        (deg / f'{name}_DEG.csv').write_text(
            'ENSEMBL,Symbol,log2FoldChange,pvalue,padj\n'
            'g0,old,2,9e-350,9e-349\n'
            'g1,old,-3,1e-400,1e-399\n'
            'g2,old,2,1e-400,1e-399\n'
            'g3,old,1,0.01,0.02\n'
            'g4,old,-2,0.04,0.08\n'
            'g5,old,4,0.8,0.9\n'
        )
    annotation = tmp_path / 'genes.tsv'
    annotation.write_text('gene_id\tgene_name\n' + ''.join(f'g{i}\tSymbol{i}\n' for i in range(6)))
    go = tmp_path / 'go.csv'
    pd.DataFrame({
        'Description': [f'Term {i} ' + 'long functional pathway description ' * 3 for i in range(20)],
        'GeneRatio': ['2/10'] * 20,
        'Count': [2] * 20,
        'p.adjust': [(.001 * (i + 1)) for i in range(20)],
    }).to_csv(go, index=False)
    empty = tmp_path / 'empty.csv'
    pd.DataFrame({'Description': ['not significant', 'invalid ratio', 'negative count'],
                  'GeneRatio': ['2/10', 'invalid', '1/10'], 'Count': [2, 3, -1],
                  'p.adjust': [.9, .001, .002]}).to_csv(empty, index=False)
    kegg = tmp_path / 'kegg.csv'
    kegg.write_text('Description,GeneRatio,Count,p.adjust\nPathway1,2/10,2,1e-400\nPathway2,3/10,3,9e-350\n')
    return {
        'project': {'project_id': 'parallel-test'},
        'report': {'modules': ['results.deg', 'results.enrichment'], 'pdf': {'deg_rows': 4}},
        'input_files': {'deg_dir': str(deg), 'gene_annotation_file': str(annotation)},
        'analysis': {'enrichment': {'top_n': 18}},
        'enrichment': {
            'go': {'contrasts': {
                'B_vs_A': {'UP': {'status': 'available', 'table': str(go)},
                           'DOWN': {'status': 'no_results'}},
                'C_vs_A': {'UP': {'status': 'available', 'table': str(empty)},
                           'DOWN': {'status': 'failed', 'messages': ['upstream failed']}},
            }},
            'kegg': {'contrasts': {
                'B_vs_A': {'UP': {'status': 'available', 'table': str(kegg)},
                           'DOWN': {'status': 'disabled'}},
                'C_vs_A': {'UP': {'status': 'unavailable'},
                           'DOWN': {'status': 'available', 'table': str(kegg)}},
            }},
        },
    }


def normalized_svg(path):
    root = ET.parse(path).getroot()
    for element in list(root):
        if element.tag.rsplit('}', 1)[-1] == 'metadata':
            root.remove(element)
    ids = {node.attrib['id']: f'id{index}' for index, node in enumerate(root.iter()) if 'id' in node.attrib}
    pattern = re.compile('|'.join(re.escape(value) for value in sorted(ids, key=len, reverse=True)))
    for node in root.iter():
        for key, value in node.attrib.items():
            node.attrib[key] = pattern.sub(lambda match: ids[match[0]], value)
    return ET.tostring(root)


@pytest.mark.parametrize('english', [False, True])
def test_serial_and_process_output_have_identical_order_evidence_and_figures(project, tmp_path, monkeypatch, english):
    monkeypatch.delenv('BIOREPORT_PDF_WORKERS', raising=False)
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT', 'pdf')
    monkeypatch.setenv('BIOREPORT_LANGUAGE', 'en' if english else 'zh')
    captures = []
    for workers in [1, 2]:
        output = tmp_path / f'output-{workers}'
        output.mkdir()
        outputs, interpretations = [], []
        manifest = output / 'blocks.jsonl'
        monkeypatch.setenv('BIOREPORT_ASSET_DIR', str(output))
        monkeypatch.setenv('BIOREPORT_BLOCK_MANIFEST', str(manifest))
        monkeypatch.setattr(render_output, '_figure_count', 0)
        monkeypatch.setattr(render_output, '_table_count', 0)
        monkeypatch.setattr(render_output, '_figure_group', None)
        monkeypatch.setattr(render_output, 'display', outputs.append)
        monkeypatch.setattr('IPython.display.display', outputs.append)
        config = deepcopy(project)
        config['report']['pdf']['workers'] = workers
        render_pdf_deg(config, ['B_vs_A', 'C_vs_A'], interpretations.append, english=english)
        render_enrichment(config, ['B_vs_A', 'C_vs_A'], interpretations.append, pdf=True, english=english)
        records = manifest.read_text().replace(str(output), '<assets>')
        text = '\n'.join(item.data for item in outputs).replace(str(output), '<assets>')
        captures.append((records, text, interpretations,
                         [normalized_svg(path) for path in sorted(output.glob('*.svg'))]))
    assert captures[0] == captures[1]
    records = [json.loads(line) for line in captures[0][0].splitlines()]
    deg = [block for block in records if block['type'] == 'figure' and block['content']['kind'] == 'deg']
    assert [block['content'] for block in deg] == [
        {'kind': 'deg', 'comparison': comp, 'up': 2, 'down': 2} for comp in ['B_vs_A', 'C_vs_A']
    ]
    tables = [block for block in records if block['type'] == 'table' and block['content']['kind'] == 'deg']
    assert tables[0]['content']['indices'] == [2, 0]
    assert 'Symbol2' in str(tables[0]['rows']) and '1.00e-400' in str(tables[0]['rows'])
    assert captures[0][2] == ['rna.results.deg__B_vs_A', 'rna.results.deg__C_vs_A',
        'rna.results.enrichment__GO__B_vs_A_UP', 'rna.results.enrichment__KEGG__B_vs_A_UP',
        'rna.results.enrichment__KEGG__C_vs_A_DOWN']
    groups = [block for block in records if block['type'] == 'figure_group']
    assert groups and all(group['figures'] and group['tables'] for group in groups)
    assert ('No significant enrichment' if english else '无显著富集结果') in captures[0][1]
    assert ('No valid terms' if english else '无满足校正后') in captures[0][1]


def test_real_workers_are_isolated_and_are_reaped_after_failure(project, tmp_path, monkeypatch):
    import bioreport.pdf_parallel as parallel
    children = []
    original = parallel._Worker.__init__

    def capture(child, directory):
        original(child, directory)
        children.append(child)

    monkeypatch.setattr(parallel._Worker, '__init__', capture)
    jobs = [{'kind': 'deg', 'label': comp, 'comparison': comp,
             'path': str(tmp_path / 'missing.csv'), 'config': project, 'english': False}
            for comp in ['B_vs_A', 'C_vs_A']]
    with pytest.raises(FileNotFoundError, match='B_vs_A'):
        with prepared_results(jobs, 2, 'failure-test') as results:
            list(results)
    assert len(children) == 2
    assert all(child.process.pid != os.getpid() and child.process.poll() is not None for child in children)
    assert all(not child.directory.exists() for child in children)


def test_parent_numbers_prepared_figures_and_keeps_grouped_table(tmp_path, monkeypatch):
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT', 'pdf')
    monkeypatch.setenv('BIOREPORT_ASSET_DIR', str(tmp_path / 'assets'))
    monkeypatch.setattr(render_output, '_figure_count', 7)
    monkeypatch.setattr(render_output, '_figure_group', None)
    source = tmp_path / 'independent.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"/>')
    blocks, outputs = [], []
    monkeypatch.setattr(render_output, 'record_block', blocks.append)
    monkeypatch.setattr(render_output, 'display', outputs.append)
    with render_output.figure_group('prepared-result'):
        render_output.show_prepared_figure(source, 'Caption', evidence={'kind': 'deg'})
        render_output.show_print_table(pd.DataFrame({'Gene': ['A']}), caption='Preview')
    assert blocks[0].id == 'figure-008'
    assert Path(blocks[0].path).name == 'figure-008.svg'
    assert blocks[-1].id == 'prepared-result'
    assert len(blocks[-1].figures) == len(blocks[-1].tables) == 1
    assert len(outputs) == 1 and '#report-figure-group' in outputs[0].data

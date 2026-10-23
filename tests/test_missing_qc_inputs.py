import json
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bioreport import cli
from bioreport.config import load_config
from bioreport.i18n import localized_config
from bioreport.modules import compose_report, skipped_modules
from bioreport.utils.provenance import build_provenance, write_delivery_manifests


ROOT = Path(__file__).resolve().parents[1]
SCREEN_KEYS = ['fastq_screen_r1_dir', 'fastq_screen_r2_dir']


@pytest.fixture
def staged(tmp_path):
    shutil.copytree(ROOT / 'omics/rna/qmd', tmp_path / 'qmd')
    shutil.copytree(ROOT / 'templates/shared', tmp_path / 'qmd', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'templates/pdf', tmp_path / 'pdf')
    shutil.copytree(ROOT / 'templates/reference', tmp_path / 'reference')
    return tmp_path


@pytest.mark.parametrize('module', ['qc', 'qc.fastp', 'qc.screen', 'qc.qualimap', 'qc.star'])
@pytest.mark.parametrize('configured', [False, True])
def test_validate_tolerates_absent_qc_inputs(tmp_path, monkeypatch, module, configured):
    path = tmp_path / 'report.json'
    path.write_text(json.dumps({
        'project': {'project_id': 'missing-qc'},
        'report': {'modules': [module]},
        'input_files': {key: f'absent/{key}' for key in (
            'fastp_stats_file', 'fastp_report_dir', *SCREEN_KEYS, 'qualimap_dir'
        )} if configured else {},
    }))
    monkeypatch.setattr(sys, 'argv', ['bioreport', 'validate', '-c', str(path)])

    cli.main()

    assert skipped_modules(load_config(path))


def test_invalid_existing_qc_path_still_fails(tmp_path):
    wrong_type = tmp_path / 'r1.txt'
    wrong_type.touch()
    config = {
        'report': {'modules': ['qc.screen']},
        'input_files': {'fastq_screen_r1_dir': str(wrong_type)},
    }
    with pytest.raises(FileNotFoundError, match='Input files are missing'):
        cli.check_input_files(config)


@pytest.mark.parametrize('language', ['zh', 'en'])
@pytest.mark.parametrize('pdf', [False, True])
@pytest.mark.parametrize('modules', [['qc'], ['qc.screen'], ['qc.screen', 'qc.fastp']])
def test_missing_screen_is_replaced_without_hiding_available_qc(staged, language, pdf, modules):
    config = load_config(ROOT / 'tests/report.rna.local.json')
    config['report']['modules'] = modules
    config['input_files']['fastq_screen_r2_dir'] = str(staged / 'absent-r2')
    config = localized_config(config, language)

    document = compose_report(config, staged, pdf=pdf).read_text()

    assert ('this section was skipped' if language == 'en' else '已跳过本节') in document
    assert '`fastq_screen_r2_dir`' in document
    assert 'visualize_fastq_screen_pair' not in document
    assert 'label: fastq-screen-pair' not in document
    assert document.count('label: setup-import-qc') == (0 if modules == ['qc.screen'] else 1)
    if modules != ['qc.screen']:
        assert 'label: fastp-table' in document
    if modules == ['qc']:
        assert 'label: qc-qualimap' in document
        assert 'label: qc-star' in document
    assert skipped_modules(config) == {'rna.qc.screen': ['fastq_screen_r2_dir']}


@pytest.mark.parametrize('language', ['zh', 'en'])
def test_website_qc_page_preserves_missing_data_notice(staged, language):
    config = load_config(ROOT / 'tests/report.rna.local.json')
    config['report'].update(layout='website', output_format='html', modules=['index', 'qc'])
    for key in SCREEN_KEYS:
        config['input_files'].pop(key)
    config = localized_config(config, language)

    pages = compose_report(config, staged, website=True)
    qc = next(page for page in pages if page['id'] == 'rna-qc')
    document = (staged / qc['href']).read_text()

    assert 'visualize_fastq_screen_pair' not in document
    assert 'label: fastp-table' in document
    assert ('this section was skipped' if language == 'en' else '已跳过本节') in document


def test_all_missing_qc_sections_render_notices_and_record_provenance(staged):
    config = {'project': {'project_id': 'missing-qc'}, 'report': {'modules': ['qc']}}

    document = compose_report(config, staged).read_text()
    provenance = build_provenance(config, ['qc'])

    assert document.count('已跳过本节') == 4
    assert 'label: fastp-table' not in document
    assert 'label: qc-qualimap' not in document
    assert 'label: qc-star' not in document
    assert set(provenance['skipped_modules']) == {
        'rna.qc.fastp', 'rna.qc.screen', 'rna.qc.qualimap', 'rna.qc.star'
    }


def test_available_screen_keeps_its_rendering_code(staged):
    config = load_config(ROOT / 'tests/report.rna.local.json')
    config['report']['modules'] = ['qc.screen']

    document = compose_report(config, staged).read_text()

    assert 'visualize_fastq_screen_pair' in document
    assert '已跳过本节' not in document
    assert skipped_modules(config) == {}


@pytest.mark.parametrize('language', ['zh', 'en'])
def test_pdf_methods_exclude_missing_qc_results(tmp_path, monkeypatch, language):
    config = load_config(ROOT / 'tests/report.rna.local.json')
    config['report']['modules'] = ['workflow', 'qc']
    config['input_files']['fastq_screen_r2_dir'] = str(tmp_path / 'absent-r2')
    monkeypatch.setattr('bioreport.config.load_config', lambda: config)
    monkeypatch.setattr('IPython.display.display', lambda *args: None)
    monkeypatch.setattr('bioreport.utils.render_output.show_print_table', lambda *args, **kwargs: None)
    monkeypatch.setattr('bioreport.utils.render_output.typst_note', lambda *args: None)
    source = ROOT / 'omics/rna/qmd' / ('en/pdf' if language == 'en' else 'pdf') / 'workflow.qmd'
    code = next(code for code in re.findall(r'```\{python\}\n(.*?)\n```', source.read_text(), re.S)
                if 'label: pdf-methods' in code)
    namespace = {}

    exec(compile(code, str(source), 'exec'), namespace)

    methods = '\n'.join(namespace['method_details'])
    assert ('Cross-species screening' if language == 'en' else '外源物种污染筛查') not in methods
    assert ('Read filtering and base quality' if language == 'en' else '原始序列过滤与碱基质控') in methods


def test_delivery_manifest_records_skipped_sections(tmp_path, monkeypatch):
    config = {'project': {'project_id': 'missing-qc'}, 'report': {'modules': ['qc']}}
    provenance = build_provenance(config, ['qc'])
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: SimpleNamespace(
        stdout='test-version', stderr='', returncode=0,
    ))

    write_delivery_manifests(config, provenance, tmp_path)

    manifest = json.loads((tmp_path / 'report-manifest.json').read_text())
    assert manifest['skipped_modules'] == provenance['skipped_modules']


def test_ai_does_not_interpret_partial_screen_inputs(tmp_path, monkeypatch):
    r1 = tmp_path / 'r1'
    r1.mkdir()
    (r1 / 'screen.txt').write_text('partial screening results')
    calls = []

    class Interpreter:
        def __init__(self, **kwargs):
            pass

        def execute_inference(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(content='Finding')

    monkeypatch.setattr('bioreport.ai.AIInterpreter', Interpreter)
    from bioreport.pipeline import _run_result_interpretations
    _run_result_interpretations(
        {'input_files': {'fastq_screen_r1_dir': str(r1)}},
        str(tmp_path / 'report.json'), tmp_path / 'templates', {}, 'test', 'mock',
    )

    assert calls == []
    assert not list((tmp_path / 'templates/data/ai_interpretations').glob('*.md'))

"""Omics selection and the real CLI staging boundary must stay in agreement."""
import json
import sys
from pathlib import Path

import pytest

from bioreport import cli
from bioreport.i18n import localized_config
from bioreport.modules import compose_report, select_report_omics, selected_modules
from bioreport.registry import get_registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('omics', ['rna', 'gwas'])
def test_parser_accepts_omics_for_run_and_validate(omics):
    for command in ('run', 'validate'):
        assert cli.parse_args([command, '--omics', omics]).omics == omics


def test_parser_rejects_unknown_omics():
    with pytest.raises(SystemExit) as error:
        cli.parse_args(['run', '--omics', 'unknown'])
    assert error.value.code == 2


@pytest.mark.parametrize(('report', 'requested', 'expected'), [
    ({}, None, 'rna'),
    ({'modules': ['index']}, None, 'rna'),
    ({}, 'gwas', 'gwas'),
    ({'type': 'rna-seq'}, None, 'rna'),
    ({'type': 'gwas'}, None, 'gwas'),
    ({'modules': ['index', 'gwas.qc', 'about']}, None, 'gwas'),
    ({'modules': ['index', 'rna.qc', 'about']}, None, 'rna'),
    ({'sections': ['index', 'workflow']}, 'gwas', 'gwas'),
    ({'modules': ['results.manhattan']}, None, 'gwas'),
])
def test_selection_scopes_defaults_and_short_names(report, requested, expected):
    config = {'report': report}
    assert select_report_omics(config, requested) == expected
    assert all(m in ('about', 'provenance') or m.startswith(expected + '.')
               for m in config['report']['modules'])
    if 'sections' in report:
        assert report['modules'] == ['gwas.index', 'gwas.workflow']


@pytest.mark.parametrize(('report', 'requested'), [
    ({'modules': ['rna.index']}, 'gwas'),
    ({'type': 'rna-seq'}, 'gwas'),
    ({'type': 'gwas', 'modules': ['rna.index']}, None),
    ({'modules': ['rna.index', 'gwas.index']}, None),
    ({'modules': ['results.matrix', 'results.manhattan']}, None),
])
def test_conflicting_omics_are_rejected(report, requested):
    with pytest.raises(ValueError, match='Conflicting omics selection'):
        select_report_omics({'report': report}, requested)


def test_shared_and_custom_pages_do_not_require_an_omics_overlay():
    config = {'report': {'modules': ['about', 'custom.finding'],
                         'module_definitions': {'custom.finding': {'path': 'finding.qmd'}}}}
    assert select_report_omics(config) is None
    assert selected_modules(config) == ['about', 'custom.finding']


@pytest.mark.parametrize('omics', ['rna', 'gwas'])
def test_default_module_validation_only_requires_selected_omics(omics):
    registry = get_registry()
    ids = [m for m in registry.default_modules if m.startswith(omics + '.')]
    inputs = {key: 'example' for m in ids for key in registry.resolve(m).required_inputs}
    config = {'report': {'type': 'rna-seq' if omics == 'rna' else 'gwas'},
              'input_files': inputs}
    assert selected_modules(config) == ids + ['provenance', 'about']


@pytest.mark.parametrize('omics', ['rna', 'gwas'])
@pytest.mark.parametrize('explicit', [False, True])
def test_cli_dry_run_stages_only_the_selected_templates(tmp_path, monkeypatch, omics, explicit):
    inputs = {}
    for key in get_registry().resolve(f'{omics}.index').required_inputs:
        target = tmp_path / key
        target.write_text('{}')
        inputs[key] = str(target)
    config_path = tmp_path / 'report.json'
    config_path.write_text(json.dumps({
        'project': {'project_id': 'omics-test'},
        'report': {'modules': ['index' if explicit else f'{omics}.index'],
                   'output_format': ['html', 'pdf'], 'layout': 'single'},
        'input_files': inputs,
    }))
    output = tmp_path / 'output'
    args = ['bioreport', 'run', '-c', str(config_path), '-o', str(output), '--dry-run']
    if explicit:
        args += ['--omics', omics]
    monkeypatch.setattr(sys, 'argv', args)
    monkeypatch.setattr(cli, 'check_quarto_env', lambda: None)
    checked = []

    def inspect_templates(config, output_dir, template_dir):
        # Exercise actual staging from main, including every colliding path,
        # then compose both formats in both languages from those staged files.
        staged = Path(template_dir)
        source = ROOT / 'omics' / omics / 'qmd'
        for path in source.rglob('*.qmd'):
            assert (staged / 'qmd' / path.relative_to(source)).read_bytes() == path.read_bytes()
        other = 'gwas' if omics == 'rna' else 'rna'
        other_leaf = 'manhattan.qmd' if other == 'gwas' else 'matrix.qmd'
        assert not (staged / 'qmd/modules/results' / other_leaf).exists()
        for lang in ('zh', 'en'):
            for pdf in (False, True):
                document = compose_report(localized_config(config, lang), staged, pdf=pdf).read_text()
                if omics == 'rna':
                    assert 'gwas-index-setup' not in document
                    assert "input_files['project_summary_file']" not in document
                    assert 'sample_file' in document
                else:
                    assert 'gwas' in document
                    assert 'project_summary_file' in document
                checked.append((lang, pdf))

    monkeypatch.setattr(cli, 'render_templates', inspect_templates)
    cli.main()
    assert len(checked) == 4
    assert json.loads(config_path.read_text())['report']['modules'] == [
        'index' if explicit else f'{omics}.index'
    ]


@pytest.mark.parametrize('command', ['run', 'validate'])
def test_cli_rejects_conflict_before_creating_output(tmp_path, monkeypatch, command):
    config_path = tmp_path / 'report.json'
    config_path.write_text(json.dumps({
        'project': {'project_id': 'conflict'},
        'report': {'modules': ['rna.index']},
    }))
    output = tmp_path / 'output'
    monkeypatch.setattr(sys, 'argv', ['bioreport', command, '--omics', 'gwas',
                                     '-c', str(config_path), '-o', str(output)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert not output.exists()


def test_validate_gwas_short_module_names(tmp_path, monkeypatch, capsys):
    for name in ('summary.json', 'qc.tsv'):
        (tmp_path / name).touch()
    config_path = tmp_path / 'report.json'
    config_path.write_text(json.dumps({
        'project': {'project_id': 'gwas-validation'},
        'report': {'modules': ['index']},
        'input_files': {'project_summary_file': 'summary.json', 'qc_final_stats_file': 'qc.tsv'},
    }))
    monkeypatch.setattr(sys, 'argv', ['bioreport', 'validate', '--omics', 'gwas', '-c', str(config_path)])
    cli.main()
    assert 'are valid' in capsys.readouterr().out

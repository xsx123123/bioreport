import json
import sys

import pytest
from rich_argparse import RichHelpFormatter

from bioreport import cli


def invoke_validate(tmp_path, monkeypatch, *, modules=None, inputs=None):
    config = tmp_path / 'report.json'
    config.write_text(json.dumps({
        'project': {'project_id': 'validation-test'},
        'report': {'modules': modules or ['rna.results.matrix']},
        'input_files': inputs or {},
    }))
    monkeypatch.setattr(sys, 'argv', ['bioreport', 'validate', '-c', str(config)])
    cli.main()


def test_validate_resolves_and_checks_input_paths(tmp_path, monkeypatch, capsys):
    (tmp_path / 'matrix.tsv').write_text('gene\tsample\nA\t1\n')
    invoke_validate(tmp_path, monkeypatch, inputs={'tpm_file': 'matrix.tsv'})
    assert 'are valid' in capsys.readouterr().out


@pytest.mark.parametrize('case', ['missing', 'directory', 'unconfigured', 'unknown_module'])
def test_validate_rejects_invalid_inputs(tmp_path, monkeypatch, case):
    inputs = {'tpm_file': 'missing.tsv'}
    modules = None
    if case == 'directory':
        (tmp_path / 'missing.tsv').mkdir()
    elif case == 'unconfigured':
        inputs = {}
    elif case == 'unknown_module':
        modules = ['rna.unknown']
    with pytest.raises(SystemExit) as error:
        invoke_validate(tmp_path, monkeypatch, modules=modules, inputs=inputs)
    assert error.value.code == 1


def test_validate_rejects_file_in_place_of_required_directory(tmp_path, monkeypatch):
    (tmp_path / 'contrasts.csv').touch()
    (tmp_path / 'deg').touch()
    with pytest.raises(SystemExit) as error:
        invoke_validate(tmp_path, monkeypatch, modules=['rna.results.deg'],
                        inputs={'contrasts_file': 'contrasts.csv', 'deg_dir': 'deg'})
    assert error.value.code == 1


@pytest.mark.parametrize('inputs', [
    {},
    {'software_versions_file': 'missing/software_versions.yaml'},
])
def test_validate_requires_existing_software_versions_file(tmp_path, monkeypatch, inputs):
    with pytest.raises(SystemExit) as error:
        invoke_validate(tmp_path, monkeypatch, modules=['rna.workflow'], inputs=inputs)
    assert error.value.code == 1


def test_validate_accepts_existing_software_versions_file(tmp_path, monkeypatch, capsys):
    versions = tmp_path / 'software_versions.yaml'
    versions.write_text('- Software: fastp\n  Version: 1.0.1\n', encoding='utf-8')

    invoke_validate(
        tmp_path, monkeypatch, modules=['rna.workflow'],
        inputs={'software_versions_file': versions.name},
    )

    assert 'are valid' in capsys.readouterr().out


def test_run_rejects_missing_software_versions_file_before_rendering(tmp_path, monkeypatch):
    config = tmp_path / 'report.json'
    config.write_text(json.dumps({
        'project': {'project_id': 'run-validation-test'},
        'report': {'modules': ['rna.workflow']},
        'input_files': {
            'data_dir': str(tmp_path),
            'software_versions_file': 'missing/software_versions.yaml',
        },
    }))
    output = tmp_path / 'output'
    monkeypatch.setattr(sys, 'argv', [
        'bioreport', 'run', '-c', str(config), '-o', str(output), '--dry-run',
    ])

    with pytest.raises(FileNotFoundError, match='Input files are missing'):
        cli.main()


@pytest.mark.parametrize('arguments', [[], ['--help'], ['run', '--help'], ['validate', '--help'], ['runs', '--help']])
def test_rich_help_is_available_for_all_commands(arguments, capsys):
    assert cli.build_parser().formatter_class is RichHelpFormatter
    with pytest.raises(SystemExit) as error:
        cli.parse_args(arguments)
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert 'BioReport' in output
    assert '--config' in output
    assert '--db' in output
    assert 'Reports And Validation' in output

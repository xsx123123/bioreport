from pathlib import Path
import pytest
from bioreport.cli import main
from bioreport.cli import parse_args


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_root_build_context_and_packaged_entrypoint():
    dockerfile = (REPO_ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")

    assert 'COPY pyproject.toml README.md ./' in dockerfile
    for directory in ("bioreport", "omics", "templates", "configs", "examples"):
        assert f"COPY {directory} ./{directory}" in dockerfile
        assert (REPO_ROOT / directory).is_dir()
    assert 'ENTRYPOINT ["bioreport"]' in dockerfile
    assert 'CMD ["--help"]' in dockerfile


def test_console_script_and_docker_entrypoint_share_the_same_command():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")

    assert 'bioreport = "bioreport.cli:main"' in pyproject
    assert 'ENTRYPOINT ["bioreport"]' in dockerfile


def test_init_does_not_require_an_existing_config(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["bioreport", "init"])
    main()
    assert "report.example.json" in capsys.readouterr().out


def test_python_entrypoints_are_consolidated_under_bioreport():
    entrypoints = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "bioreport").rglob("*.py")
        if "if __name__ ==" in path.read_text(encoding="utf-8")
    }

    # The zero-dependency offline launcher is packaged here and copied into
    # delivered website archives, so it is an intentional fourth entrypoint.
    assert entrypoints == {"bioreport/__main__.py", "bioreport/cli.py",
                           "bioreport/api_server.py", "bioreport/serve_report.py"}


@pytest.mark.parametrize("arguments", [[], ["-h"], ["--help"]])
def test_cli_help_exits_cleanly_without_a_config(arguments, capsys):
    with pytest.raises(SystemExit) as result:
        parse_args(arguments)

    assert result.value.code == 0
    output = capsys.readouterr().out
    assert "Usage: bioreport" in output
    assert "Configuration file" in output
    assert "tests/report.rna.local.json" in output

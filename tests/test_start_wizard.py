from pathlib import Path

from thread_room.cli import _parse_agent_selection, _slug, _warn_if_broad_cwd


def test_parse_numbers():
    a = _parse_agent_selection("2 1")
    assert a[0][0] == "codex"
    assert a[1][0] == "mock"


def test_parse_names():
    a = _parse_agent_selection("codex,claude")
    assert [x[0] for x in a] == ["codex", "claude"]


def test_slug():
    assert "hello" in _slug("Hello World!")


def test_home_cwd_warning(capsys):
    _warn_if_broad_cwd(Path.home().resolve())
    assert "home folder" in capsys.readouterr().err


def test_repo_cwd_has_no_warning(tmp_path, capsys):
    _warn_if_broad_cwd(tmp_path)
    assert capsys.readouterr().err == ""

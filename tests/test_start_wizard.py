from thread_room.cli import _parse_agent_selection, _slug


def test_parse_numbers():
    a = _parse_agent_selection("2 1")
    assert a[0][0] == "codex"
    assert a[1][0] == "mock"


def test_parse_names():
    a = _parse_agent_selection("codex,claude")
    assert [x[0] for x in a] == ["codex", "claude"]


def test_slug():
    assert "hello" in _slug("Hello World!")

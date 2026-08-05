import pytest

from thread_room.parser import ParseError, parse_agent_output


def test_json_conclusion():
    out = parse_agent_output(
        '{"conclusion":"hello world","mentions":[],"files_claimed":[]}',
        max_chars=100,
    )
    assert out.conclusion == "hello world"
    assert out.raw_format == "json"


def test_marker_conclusion():
    raw = """:::trace
secret thoughts
:::
:::conclusion
public answer
:::
"""
    out = parse_agent_output(raw, max_chars=100)
    assert out.conclusion == "public answer"
    assert out.raw_format == "markers"


def test_missing_conclusion_fail_closed():
    with pytest.raises(ParseError):
        parse_agent_output("just rambling with no structure", max_chars=100)


def test_empty_fail():
    with pytest.raises(ParseError):
        parse_agent_output("", max_chars=100)


def test_too_long():
    with pytest.raises(ParseError):
        parse_agent_output(
            '{"conclusion":"' + ("x" * 50) + '"}',
            max_chars=10,
        )


def test_no_last_n_fallback():
    # long garbage must not become conclusion
    with pytest.raises(ParseError):
        parse_agent_output("a" * 5000, max_chars=4000)

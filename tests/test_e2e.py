from pathlib import Path

from thread_room.session import Session
from thread_room.store import create_meeting


def test_mention_case_insensitive(tmp_path: Path):
    from thread_room.session import Session
    from thread_room.store import create_meeting

    meeting = create_meeting(
        tmp_path, title="Case", cwd=str(tmp_path), agents=[("grok", "mock")]
    )
    sess = Session.open(meeting)
    msg = sess.say("@Grok hello")
    assert msg.mentions == ["grok"]
    out = sess.pump()
    assert any(m.speaker == "grok" for m in out)


def test_say_pump_export_close(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="E2E", cwd=str(tmp_path))
    sess = Session.open(meeting)
    sess.system("Room opened.", meta={"event": "open"})
    sess.say("Hello @mock please greet")
    assert len(sess.pending) == 1
    out = sess.pump()
    assert any(m.speaker == "mock" and m.type == "utterance" for m in out)
    # conclusion only — short
    mock_msgs = [m for m in sess.store.messages if m.speaker == "mock"]
    assert len(mock_msgs) == 1
    assert "mock" in mock_msgs[0].text.lower() or "Mock" in mock_msgs[0].text
    # trace exists
    traces = list((meeting / "desks" / "mock" / "traces").glob("*.log"))
    assert traces
    exp = sess.export()
    assert exp.is_file()
    body = exp.read_text(encoding="utf-8")
    assert "E2E" in body
    assert "Hello @mock" in body
    sess.close()
    assert sess.store.closed


def test_pending_survives_reopen(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="Reopen", cwd=str(tmp_path))
    s1 = Session.open(meeting)
    s1.say("ping @mock")
    assert s1.pending
    s2 = Session.open(meeting)
    assert any(p.target == "mock" for p in s2.pending)
    out = s2.pump()
    assert any(m.speaker == "mock" for m in out)


def test_parse_fail_system_on_floor(tmp_path: Path):
    meeting = create_meeting(
        tmp_path,
        title="Fail",
        cwd=str(tmp_path),
        agents=[("bad", "mock_fail")],
    )
    sess = Session.open(meeting)
    sess.say("go @bad")
    out = sess.pump()
    assert any(m.type == "system" and m.meta.get("event") == "parse_failed" for m in out)
    # no agent utterance
    assert not any(m.speaker == "bad" and m.type == "utterance" for m in sess.store.messages)

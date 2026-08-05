from pathlib import Path

from thread_room.ownership import PathAssignment
from thread_room.session import Session
from thread_room.store import create_meeting
from thread_room.validate import validate_meeting


def test_validate_ok(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="V", cwd=str(tmp_path))
    sess = Session.open(meeting)
    sess.system("open", meta={"event": "open"})
    sess.say("hi @mock")
    sess.pump()
    r = validate_meeting(meeting)
    assert r.ok, r.errors


def test_validate_missing_room(tmp_path: Path):
    r = validate_meeting(tmp_path)
    assert not r.ok
    assert any("room.yaml" in e for e in r.errors)


def test_validate_after_ownership(tmp_path: Path):
    meeting = create_meeting(
        tmp_path, title="O", cwd=str(tmp_path), agents=[("a", "mock"), ("b", "mock")]
    )
    sess = Session.open(meeting)
    sess.propose_ownership(
        [PathAssignment(["x.py"], "a"), PathAssignment(["y.py"], "b")]
    )
    sess.ratify_ownership()
    r = validate_meeting(meeting)
    assert r.ok, r.errors

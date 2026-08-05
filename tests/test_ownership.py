from pathlib import Path

import pytest

from thread_room.models import make_message
from thread_room.ownership import (
    PathAssignment,
    audit_paths,
    find_overlaps,
    match_owner,
    parse_assign_specs,
    project_state,
)
from thread_room.session import Session
from thread_room.store import StoreError, create_meeting


def test_parse_assign_specs():
    a = parse_assign_specs(["codex:src/a.py,tests/", "claude:docs/SPEC.md"])
    assert a[0].owner == "codex"
    assert a[0].paths == ["src/a.py", "tests/"]
    assert a[1].owner == "claude"


def test_find_overlaps():
    bad = find_overlaps(
        [
            PathAssignment(["src/"], "a"),
            PathAssignment(["src/foo.py"], "b"),
        ]
    )
    assert bad
    good = find_overlaps(
        [
            PathAssignment(["src/a.py"], "a"),
            PathAssignment(["src/b.py"], "b"),
        ]
    )
    assert not good


def test_match_owner_prefix():
    m = {"src/": "codex", "docs/SPEC.md": "claude"}
    assert match_owner(m, "src/foo.py") == "codex"
    assert match_owner(m, "docs/SPEC.md") == "claude"
    assert match_owner(m, "README.md") is None


def test_propose_ratify_phase(tmp_path: Path):
    meeting = create_meeting(
        tmp_path,
        title="Own",
        cwd=str(tmp_path),
        agents=[("codex", "mock"), ("claude", "mock")],
    )
    sess = Session.open(meeting)
    sess.system("open", meta={"event": "open"})
    sess.propose_ownership(
        [
            PathAssignment(["src/a.py"], "codex"),
            PathAssignment(["docs/"], "claude"),
        ]
    )
    with pytest.raises(StoreError):
        sess.set_phase("write")  # not ratified
    sess.ratify_ownership()
    sess.set_phase("write")
    st = sess.ownership_state()
    assert st.phase == "write"
    assert st.owner_for("src/a.py") == "codex"
    assert st.owner_for("docs/x.md") == "claude"


def test_overlap_rejected(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="O", cwd=str(tmp_path))
    sess = Session.open(meeting)
    with pytest.raises(StoreError, match="overlap"):
        sess.propose_ownership(
            [
                PathAssignment(["src/"], "mock"),
                PathAssignment(["src/a.py"], "human"),
            ]
        )


def test_audit_paths():
    from thread_room.ownership import OwnershipState

    st = OwnershipState(ratified_map={"src/": "codex"})
    v = audit_paths(st, speaker="codex", paths=["src/a.py"])
    assert v == []
    v2 = audit_paths(st, speaker="claude", paths=["src/a.py"])
    assert v2
    v3 = audit_paths(st, speaker="codex", paths=["other.py"])
    assert v3


def test_audit_emits_system_on_write_phase(tmp_path: Path, monkeypatch):
    meeting = create_meeting(
        tmp_path, title="A", cwd=str(tmp_path), agents=[("codex", "mock")]
    )
    sess = Session.open(meeting)
    sess.propose_ownership([PathAssignment(["src/only.py"], "codex")])
    sess.ratify_ownership()
    sess.set_phase("write")

    # mock claims a file outside ownership
    from thread_room.adapters import mock as mock_mod

    from thread_room.adapters.base import AdapterResult

    class ClaimBad(mock_mod.MockAdapter):
        def run(self, ctx):
            import json

            body = {
                "conclusion": "I touched secrets.env",
                "mentions": [],
                "files_claimed": ["secrets.env"],
            }
            return AdapterResult(
                stdout=json.dumps(body),
                stderr="",
                exit_code=0,
                duration_ms=1,
            )

    monkeypatch.setattr(
        "thread_room.adapters.registry.get_adapter",
        lambda name: ClaimBad(),
    )
    # re-import path used in session
    import thread_room.session as sess_mod

    monkeypatch.setattr(sess_mod, "get_adapter", lambda name: ClaimBad())

    sess.say("@codex do stuff")
    out = sess.pump()
    assert any(
        m.type == "system" and m.meta.get("event") == "ownership_audit" for m in out
    )


def test_export_has_ownership_section(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="E", cwd=str(tmp_path))
    sess = Session.open(meeting)
    sess.propose_ownership([PathAssignment(["a.py"], "mock")])
    sess.ratify_ownership()
    p = sess.export()
    text = p.read_text(encoding="utf-8")
    assert "Ownership" in text
    assert "a.py" in text

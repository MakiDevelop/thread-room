"""Desks / promote tests — tmux mocked where needed."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from thread_room.desks import (
    DeskError,
    TerminalsState,
    append_side_thread,
    close_desks,
    doctor,
    list_desks,
    load_terminals,
    open_desks,
    read_last_side,
    save_terminals,
)
from thread_room.session import Session
from thread_room.store import create_meeting


def test_promote_to_floor(tmp_path: Path):
    meeting = create_meeting(
        tmp_path, title="P", cwd=str(tmp_path), agents=[("codex", "mock")]
    )
    sess = Session.open(meeting)
    msg = sess.promote(from_speaker="codex", text="Desk conclusion: ship it")
    assert msg.type == "promote"
    assert "ship it" in msg.text
    assert msg.meta.get("from_desk") == "codex"
    assert any(m.type == "promote" for m in sess.store.messages)


def test_promote_unknown_speaker(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="P", cwd=str(tmp_path))
    sess = Session.open(meeting)
    with pytest.raises(Exception):
        sess.promote(from_speaker="nope", text="x")


def test_side_thread_roundtrip(tmp_path: Path):
    meeting = create_meeting(
        tmp_path, title="S", cwd=str(tmp_path), agents=[("mock", "mock")]
    )
    append_side_thread(meeting, "mock", "whisper 1")
    append_side_thread(meeting, "mock", "whisper 2")
    text = read_last_side(meeting, "mock", n=2)
    assert "whisper 1" in text and "whisper 2" in text


def test_open_desks_mocked_tmux(tmp_path: Path):
    meeting = create_meeting(
        tmp_path,
        title="D",
        cwd=str(tmp_path),
        agents=[("codex", "codex_cli"), ("mock", "mock")],
    )
    sess = Session.open(meeting)
    room = sess.room

    calls: list[list[str]] = []

    def fake_tmux(args, check=True):
        from subprocess import CompletedProcess

        calls.append(list(args))
        if args[:1] == ["has-session"]:
            return CompletedProcess(args, 1, "", "")
        return CompletedProcess(args, 0, "", "")

    with patch("thread_room.desks.tmux_available", return_value=True):
        with patch("thread_room.desks._tmux", side_effect=fake_tmux):
            state = open_desks(meeting, room)

    assert state.tmux_session.startswith("tr-")
    assert len(state.desks) == 2
    assert (meeting / ".runtime" / "terminals.json").is_file()
    assert any(c[0] == "new-session" for c in calls)
    assert any(c[0] == "new-window" for c in calls)

    # list
    with patch("thread_room.desks.session_exists", return_value=True):
        text = list_desks(meeting)
    assert "codex" in text and "mock" in text

    # close
    with patch("thread_room.desks.session_exists", return_value=True):
        with patch("thread_room.desks._tmux", side_effect=fake_tmux):
            report = close_desks(meeting)
    assert any("killed" in r or "killing" in r for r in report)
    assert load_terminals(meeting) is None


def test_doctor_orphan_record(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="Doc", cwd=str(tmp_path))
    save_terminals(
        meeting,
        TerminalsState(
            tmux_session="tr-orphan",
            meeting_dir=str(meeting),
            room_id="Doc",
            desks=[],
        ),
    )
    with patch("thread_room.desks.session_exists", return_value=False):
        lines = doctor(meeting)
    assert any("ORPHAN" in ln for ln in lines)


def test_desks_open_requires_tmux(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="X", cwd=str(tmp_path))
    sess = Session.open(meeting)
    with patch("thread_room.desks.tmux_available", return_value=False):
        with pytest.raises(DeskError, match="tmux"):
            open_desks(meeting, sess.room)


def test_session_desks_open_system_event(tmp_path: Path):
    meeting = create_meeting(
        tmp_path, title="E", cwd=str(tmp_path), agents=[("a", "mock")]
    )
    sess = Session.open(meeting)

    def fake_tmux(args, check=True):
        from subprocess import CompletedProcess

        if args[:1] == ["has-session"]:
            return CompletedProcess(args, 1, "", "")
        return CompletedProcess(args, 0, "", "")

    with patch("thread_room.desks.tmux_available", return_value=True):
        with patch("thread_room.desks._tmux", side_effect=fake_tmux):
            sess.desks_open()
    assert any(m.meta.get("event") == "desks_open" for m in sess.store.messages)

"""P3: tmux desks + terminals.json + orphan doctor.

Floor stays headless (pump). Desks are interactive panes for human side-chat.
Side chat is NOT on floor unless promote.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from thread_room.models import RoomConfig, Speaker

TERMINALS_JSON = ".runtime/terminals.json"
SIDE_THREAD = "side-thread.jsonl"


class DeskError(Exception):
    pass


@dataclass
class DeskRecord:
    speaker: str
    window: str
    target: str  # tmux target e.g. session:window
    cmd: list[str]
    cwd: str
    created_at: str
    pid: int | None = None


@dataclass
class TerminalsState:
    tmux_session: str
    meeting_dir: str
    room_id: str
    desks: list[DeskRecord] = field(default_factory=list)
    host_pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tmux_session": self.tmux_session,
            "meeting_dir": self.meeting_dir,
            "room_id": self.room_id,
            "host_pid": self.host_pid,
            "desks": [asdict(d) for d in self.desks],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TerminalsState:
        desks = [
            DeskRecord(
                speaker=str(x["speaker"]),
                window=str(x["window"]),
                target=str(x["target"]),
                cmd=list(x.get("cmd") or []),
                cwd=str(x.get("cwd") or ""),
                created_at=str(x.get("created_at") or ""),
                pid=x.get("pid"),
            )
            for x in (d.get("desks") or [])
            if isinstance(x, dict)
        ]
        return cls(
            tmux_session=str(d.get("tmux_session") or ""),
            meeting_dir=str(d.get("meeting_dir") or ""),
            room_id=str(d.get("room_id") or ""),
            desks=desks,
            host_pid=d.get("host_pid"),
        )


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sanitize_session(room_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", room_id).strip("-")[:40]
    return f"tr-{s or 'room'}"


def terminals_path(meeting_dir: Path) -> Path:
    return meeting_dir / TERMINALS_JSON


def load_terminals(meeting_dir: Path) -> TerminalsState | None:
    p = terminals_path(meeting_dir)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise DeskError(f"corrupt {p}: {e}") from e
    return TerminalsState.from_dict(data)


def save_terminals(meeting_dir: Path, state: TerminalsState) -> Path:
    p = terminals_path(meeting_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return p


def interactive_command(speaker: Speaker) -> list[str]:
    """Command to run inside desk pane (interactive)."""
    adapter = (speaker.adapter or "mock").lower()
    if adapter in ("codex", "codex_cli", "codex-cli"):
        return [os.environ.get("THREAD_ROOM_CODEX_BIN") or "codex"]
    if adapter in ("claude", "claude_code", "claude-code"):
        return [os.environ.get("THREAD_ROOM_CLAUDE_BIN") or "claude"]
    if adapter in ("gemini", "gemini_cli"):
        return [os.environ.get("THREAD_ROOM_GEMINI_BIN") or "gemini"]
    # mock / unknown: shell with banner via bash -lc
    return []


def _banner_script(room: RoomConfig, speaker: Speaker, meeting_dir: Path) -> str:
    desk = meeting_dir / "desks" / speaker.id
    desk.mkdir(parents=True, exist_ok=True)
    (desk / "traces").mkdir(exist_ok=True)
    side = desk / SIDE_THREAD
    return (
        f"clear; "
        f"echo '════════════════════════════════════════'; "
        f"echo ' Thread Room DESK — {speaker.id} ({speaker.display_name})'; "
        f"echo ' Room: {room.id}'; "
        f"echo ' Meeting: {meeting_dir}'; "
        f"echo ' Side chat is NOT on the public floor.'; "
        f"echo ' Promote: thread-room promote -d {meeting_dir} --from {speaker.id} --text \"…\"'; "
        f"echo ' Side log (optional): {side}'; "
        f"echo '════════════════════════════════════════'; "
        f"cd {shlex_quote(str(Path(room.cwd).resolve() if Path(room.cwd).is_dir() else meeting_dir))}; "
        f"exec {os.environ.get('SHELL', '/bin/zsh')} -l"
    )


def shlex_quote(s: str) -> str:
    import shlex

    return shlex.quote(s)


def tmux_available() -> bool:
    return shutil.which("tmux") is not None


def _tmux(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    bin_ = shutil.which("tmux")
    if not bin_:
        raise DeskError("tmux not found on PATH")
    proc = subprocess.run(
        [bin_, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise DeskError(
            f"tmux {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc


def session_exists(name: str) -> bool:
    proc = _tmux(["has-session", "-t", f"={name}"], check=False)
    return proc.returncode == 0


def open_desks(
    meeting_dir: Path,
    room: RoomConfig,
    *,
    attach_hint: bool = True,
) -> TerminalsState:
    """Create tmux session with one window per enabled agent."""
    if not tmux_available():
        raise DeskError("tmux is required for desks (install tmux)")

    meeting_dir = meeting_dir.resolve()
    existing = load_terminals(meeting_dir)
    if existing and session_exists(existing.tmux_session):
        raise DeskError(
            f"desks already open (tmux session {existing.tmux_session!r}); "
            f"use desks close or attach: tmux attach -t {existing.tmux_session}"
        )

    agents = [s for s in room.speakers if s.kind == "agent" and s.enabled]
    if not agents:
        raise DeskError("no enabled agents to open desks for")

    session = _sanitize_session(room.id)
    # kill stale session name if any
    if session_exists(session):
        _tmux(["kill-session", "-t", session], check=False)

    first = agents[0]
    first_cmd = interactive_command(first)
    cwd = Path(room.cwd)
    if not cwd.is_dir():
        cwd = meeting_dir

    # First window: create session
    if first_cmd:
        shell_cmd = (
            f"cd {shlex_quote(str(cwd))} && "
            f"echo 'Thread Room desk: {first.id} | side chat NOT on floor' && "
            f"echo 'promote: thread-room promote -d {shlex_quote(str(meeting_dir))} --from {first.id} --text \"…\"' && "
            f"exec {shlex_quote(first_cmd[0])} "
            + " ".join(shlex_quote(a) for a in first_cmd[1:])
        )
    else:
        shell_cmd = _banner_script(room, first, meeting_dir)

    _tmux(
        [
            "new-session",
            "-d",
            "-s",
            session,
            "-n",
            first.id,
            "-c",
            str(cwd),
            "bash",
            "-lc",
            shell_cmd,
        ]
    )

    desks: list[DeskRecord] = [
        DeskRecord(
            speaker=first.id,
            window=first.id,
            target=f"{session}:{first.id}",
            cmd=first_cmd or ["$SHELL"],
            cwd=str(cwd),
            created_at=_now(),
        )
    ]

    for sp in agents[1:]:
        cmd = interactive_command(sp)
        if cmd:
            shell_cmd = (
                f"cd {shlex_quote(str(cwd))} && "
                f"echo 'Thread Room desk: {sp.id} | side chat NOT on floor' && "
                f"echo 'promote: thread-room promote -d {shlex_quote(str(meeting_dir))} --from {sp.id} --text \"…\"' && "
                f"exec {shlex_quote(cmd[0])} "
                + " ".join(shlex_quote(a) for a in cmd[1:])
            )
        else:
            shell_cmd = _banner_script(room, sp, meeting_dir)
        _tmux(
            [
                "new-window",
                "-t",
                session,
                "-n",
                sp.id,
                "-c",
                str(cwd),
                "bash",
                "-lc",
                shell_cmd,
            ]
        )
        desks.append(
            DeskRecord(
                speaker=sp.id,
                window=sp.id,
                target=f"{session}:{sp.id}",
                cmd=cmd or ["$SHELL"],
                cwd=str(cwd),
                created_at=_now(),
            )
        )

    # select first window
    _tmux(["select-window", "-t", f"{session}:{first.id}"], check=False)

    state = TerminalsState(
        tmux_session=session,
        meeting_dir=str(meeting_dir),
        room_id=room.id,
        desks=desks,
        host_pid=os.getpid(),
    )
    save_terminals(meeting_dir, state)
    return state


def list_desks(meeting_dir: Path) -> str:
    state = load_terminals(meeting_dir)
    if not state:
        return "no terminals.json (desks not opened)"
    alive = session_exists(state.tmux_session)
    lines = [
        f"tmux_session={state.tmux_session} alive={alive}",
        f"room_id={state.room_id}",
    ]
    for d in state.desks:
        lines.append(f"  - {d.speaker}: target={d.target} cmd={' '.join(d.cmd)}")
    if alive:
        lines.append(f"attach: tmux attach -t {state.tmux_session}")
    return "\n".join(lines)


def close_desks(meeting_dir: Path, *, force: bool = False) -> list[str]:
    """Kill tmux session; return human-readable lines of what was closed."""
    state = load_terminals(meeting_dir)
    report: list[str] = []
    if not state:
        report.append("no terminals.json")
        return report
    if session_exists(state.tmux_session):
        if not force:
            # still kill but report panes for confirmation style message
            report.append(f"killing tmux session {state.tmux_session}")
            for d in state.desks:
                report.append(f"  closing desk {d.speaker} ({d.target})")
        _tmux(["kill-session", "-t", state.tmux_session], check=False)
        report.append(f"killed {state.tmux_session}")
    else:
        report.append(f"tmux session {state.tmux_session} already gone")
    # remove terminals.json after close
    p = terminals_path(meeting_dir)
    if p.is_file():
        p.unlink()
        report.append("removed .runtime/terminals.json")
    return report


def doctor(meeting_dir: Path) -> list[str]:
    """List orphan / stale desk state."""
    lines: list[str] = []
    state = load_terminals(meeting_dir)
    if not state:
        # scan for tr-* sessions that might be ours? too broad
        lines.append("no terminals.json for this meeting")
        return lines
    alive = session_exists(state.tmux_session)
    lines.append(f"session={state.tmux_session} alive={alive}")
    if not alive:
        lines.append(
            "ORPHAN RECORD: terminals.json exists but tmux session dead — "
            "run: thread-room desks close -d …  (clears record)"
        )
    else:
        lines.append("session healthy; attach: tmux attach -t " + state.tmux_session)
    for d in state.desks:
        lines.append(f"  desk {d.speaker} → {d.target}")
    return lines


def append_side_thread(
    meeting_dir: Path, speaker: str, text: str, *, role: str = "human"
) -> Path:
    """Optional local side log (not floor)."""
    desk = meeting_dir / "desks" / speaker
    desk.mkdir(parents=True, exist_ok=True)
    path = desk / SIDE_THREAD
    rec = {
        "ts": _now(),
        "role": role,
        "text": text,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def read_last_side(meeting_dir: Path, speaker: str, n: int = 1) -> str:
    path = meeting_dir / "desks" / speaker / SIDE_THREAD
    if not path.is_file():
        raise DeskError(f"no side-thread for {speaker}: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise DeskError("side-thread empty")
    chunk = lines[-n:]
    parts: list[str] = []
    for ln in chunk:
        try:
            o = json.loads(ln)
            parts.append(str(o.get("text", ln)))
        except json.JSONDecodeError:
            parts.append(ln)
    return "\n".join(parts)

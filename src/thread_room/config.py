"""User config + current-meeting pointer."""

from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    raw = os.environ.get("THREAD_ROOM_CONFIG")
    if raw:
        return Path(raw).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "thread-room"
    return Path.home() / ".config" / "thread-room"


def meetings_root() -> Path:
    raw = os.environ.get("THREAD_ROOM_MEETINGS")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "thread-room-meetings"


def current_path_file() -> Path:
    return config_dir() / "current_meeting"


def set_current_meeting(meeting_dir: Path) -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = current_path_file()
    p.write_text(str(meeting_dir.resolve()) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def get_current_meeting() -> Path | None:
    env = os.environ.get("THREAD_ROOM_MEETING")
    if env:
        p = Path(env).expanduser()
        if (p / "room.yaml").is_file():
            return p.resolve()
    f = current_path_file()
    if not f.is_file():
        return None
    text = f.read_text(encoding="utf-8").strip()
    if not text:
        return None
    p = Path(text).expanduser()
    if (p / "room.yaml").is_file():
        return p.resolve()
    return None


def resolve_meeting(cli_dir: str | None) -> Path:
    if cli_dir:
        p = Path(cli_dir).expanduser().resolve()
        if not (p / "room.yaml").is_file():
            raise FileNotFoundError(f"not a meeting dir: {p}")
        return p
    cur = get_current_meeting()
    if cur is None:
        raise FileNotFoundError(
            "no meeting selected — run: thread-room   (or: thr go \"title\")"
        )
    return cur


# Catalog for interactive agent picker
AGENT_CATALOG: list[dict[str, str]] = [
    {
        "id": "mock",
        "adapter": "mock",
        "label": "Mock",
        "desc": "offline test agent (no API)",
    },
    {
        "id": "codex",
        "adapter": "codex_cli",
        "label": "Codex",
        "desc": "OpenAI Codex CLI (codex on PATH)",
    },
    {
        "id": "claude",
        "adapter": "claude_code",
        "label": "Claude",
        "desc": "Claude Code CLI (desk interactive; pump uses mock until adapter lands)",
    },
    {
        "id": "gemini",
        "adapter": "gemini_cli",
        "label": "Gemini",
        "desc": "Gemini CLI (desk interactive; pump uses mock until adapter lands)",
    },
    {
        "id": "grok",
        "adapter": "mock",
        "label": "Grok",
        "desc": "placeholder desk (adapter mock until wired)",
    },
]

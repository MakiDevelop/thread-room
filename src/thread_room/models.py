"""Room config and message models (stdlib only)."""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRP_VERSION = "0.1"

SPEAKER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
MENTION_RE = re.compile(r"@([a-zA-Z0-9_-]{1,64})")


def new_id() -> str:
    return f"{int(time.time() * 1000):x}{secrets.token_hex(8)}"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Policy:
    speak: str = "mention_only"
    floor_output: str = "conclusion_only"
    max_floor_chars: int = 4000
    max_floor_messages_per_turn: int = 1
    max_context_messages: int = 80
    allow_agent_mention: bool = False
    max_agent_chain: int = 0
    write_gate: str = "ownership_audit"  # audit only in v0; not a hard deny gate
    phase: str = "discuss"  # initial only; runtime phase from events


@dataclass
class Speaker:
    id: str
    kind: str  # human | agent | system
    display_name: str
    adapter: str | None = None
    enabled: bool = True


@dataclass
class RoomConfig:
    id: str
    title: str
    created_at: str
    cwd: str
    speakers: list[Speaker]
    policy: Policy = field(default_factory=Policy)
    trp: str = TRP_VERSION
    kind: str = "room"
    path: Path | None = None  # meeting directory

    def speaker_map(self) -> dict[str, Speaker]:
        return {s.id: s for s in self.speakers}

    def human_id(self) -> str:
        for s in self.speakers:
            if s.kind == "human":
                return s.id
        return "human"

    def enabled_agents(self) -> list[Speaker]:
        return [s for s in self.speakers if s.kind == "agent" and s.enabled]


@dataclass
class Message:
    trp: str
    id: str
    ts: str
    room_id: str
    speaker: str
    kind: str
    type: str
    text: str
    mentions: list[str] = field(default_factory=list)
    reply_to: str | None = None
    attachments: list[Any] = field(default_factory=list)
    visibility: str = "floor"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Message:
        return cls(
            trp=str(d.get("trp", TRP_VERSION)),
            id=str(d["id"]),
            ts=str(d["ts"]),
            room_id=str(d["room_id"]),
            speaker=str(d["speaker"]),
            kind=str(d["kind"]),
            type=str(d["type"]),
            text=str(d.get("text", "")),
            mentions=list(d.get("mentions") or []),
            reply_to=d.get("reply_to"),
            attachments=list(d.get("attachments") or []),
            visibility=str(d.get("visibility") or "floor"),
            meta=dict(d.get("meta") or {}),
        )


def extract_mentions(text: str) -> list[str]:
    seen: list[str] = []
    for m in MENTION_RE.findall(text or ""):
        if m not in seen:
            seen.append(m)
    return seen


def make_message(
    room: RoomConfig,
    *,
    speaker: str,
    kind: str,
    type: str,
    text: str,
    mentions: list[str] | None = None,
    reply_to: str | None = None,
    meta: dict[str, Any] | None = None,
    visibility: str = "floor",
) -> Message:
    if mentions is None:
        mentions = extract_mentions(text) if kind == "human" else []
    return Message(
        trp=TRP_VERSION,
        id=new_id(),
        ts=now_iso(),
        room_id=room.id,
        speaker=speaker,
        kind=kind,
        type=type,
        text=text,
        mentions=mentions,
        reply_to=reply_to,
        meta=meta or {},
        visibility=visibility,
    )

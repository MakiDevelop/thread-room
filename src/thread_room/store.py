"""Append-only thread.jsonl store — single-writer per process."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from thread_room.models import TRP_VERSION, Message, Policy, RoomConfig, Speaker, now_iso

ROOM_YAML = "room.yaml"
THREAD_JSONL = "thread.jsonl"


class StoreError(Exception):
    pass


class ThreadStore:
    """Owns thread.jsonl writes for one open room in this process."""

    def __init__(self, meeting_dir: Path) -> None:
        self.meeting_dir = meeting_dir.resolve()
        self.thread_path = self.meeting_dir / THREAD_JSONL
        self.room_path = self.meeting_dir / ROOM_YAML
        self._closed = False
        self._ids: set[str] = set()
        self._messages: list[Message] = []

    def load(self) -> RoomConfig:
        if not self.room_path.is_file():
            raise StoreError(f"missing {self.room_path}")
        room = load_room_yaml(self.room_path)
        room.path = self.meeting_dir
        self._messages = []
        self._ids = set()
        self._closed = False
        if self.thread_path.is_file():
            for msg in read_thread(self.thread_path):
                self._messages.append(msg)
                self._ids.add(msg.id)
                if msg.type == "system" and msg.meta.get("event") == "close":
                    self._closed = True
        return room

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    @property
    def closed(self) -> bool:
        return self._closed

    def append(self, msg: Message) -> Message:
        if self._closed:
            raise StoreError("room is closed; start a new meeting to continue")
        if msg.id in self._ids:
            raise StoreError(f"duplicate message id: {msg.id}")
        if msg.reply_to and msg.reply_to not in self._ids:
            raise StoreError(f"reply_to unknown id: {msg.reply_to}")
        line = json.dumps(msg.to_dict(), ensure_ascii=False, separators=(",", ":"))
        if "\n" in line:
            raise StoreError("message JSON must be single-line")
        self.meeting_dir.mkdir(parents=True, exist_ok=True)
        with self.thread_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._messages.append(msg)
        self._ids.add(msg.id)
        if msg.type == "system" and msg.meta.get("event") == "close":
            self._closed = True
        return msg

    def recent_floor(self, n: int) -> list[Message]:
        floor = [m for m in self._messages if m.visibility != "desk"]
        if n <= 0:
            return floor
        return floor[-n:]


def read_thread(path: Path) -> list[Message]:
    messages: list[Message] = []
    ids: set[str] = set()
    if not path.is_file():
        return messages
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return messages
    for i, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            raise StoreError(f"{path}:{i}: invalid JSON: {e}") from e
        if not isinstance(d, dict):
            raise StoreError(f"{path}:{i}: message must be object")
        for key in ("trp", "id", "ts", "room_id", "speaker", "kind", "type", "text"):
            if key not in d:
                raise StoreError(f"{path}:{i}: missing field {key}")
        msg = Message.from_dict(d)
        if msg.id in ids:
            raise StoreError(f"{path}:{i}: duplicate id {msg.id}")
        if msg.reply_to and msg.reply_to not in ids:
            raise StoreError(f"{path}:{i}: reply_to unknown {msg.reply_to}")
        ids.add(msg.id)
        messages.append(msg)
    return messages


def load_room_yaml(path: Path) -> RoomConfig:
    data = _parse_room_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise StoreError("room.yaml must be a mapping")
    speakers_raw = data.get("speakers") or []
    speakers: list[Speaker] = []
    for s in speakers_raw:
        if not isinstance(s, dict):
            continue
        speakers.append(
            Speaker(
                id=str(s["id"]),
                kind=str(s.get("kind", "agent")),
                display_name=str(s.get("display_name", s["id"])),
                adapter=(str(s["adapter"]) if s.get("adapter") is not None else None),
                enabled=bool(s.get("enabled", True)),
            )
        )
    pol_raw = data.get("policy") or {}
    if not isinstance(pol_raw, dict):
        pol_raw = {}
    policy = Policy(
        speak=str(pol_raw.get("speak", "mention_only")),
        floor_output=str(pol_raw.get("floor_output", "conclusion_only")),
        max_floor_chars=int(pol_raw.get("max_floor_chars", 4000)),
        max_floor_messages_per_turn=int(pol_raw.get("max_floor_messages_per_turn", 1)),
        max_context_messages=int(pol_raw.get("max_context_messages", 80)),
        allow_agent_mention=bool(pol_raw.get("allow_agent_mention", False)),
        max_agent_chain=int(pol_raw.get("max_agent_chain", 0)),
        write_gate=str(pol_raw.get("write_gate", "ownership_audit")),
        phase=str(pol_raw.get("phase", "discuss")),
    )
    return RoomConfig(
        id=str(data["id"]),
        title=str(data.get("title", data["id"])),
        created_at=str(data.get("created_at", "")),
        cwd=str(data.get("cwd", ".")),
        speakers=speakers,
        policy=policy,
        trp=str(data.get("trp", TRP_VERSION)),
        kind=str(data.get("kind", "room")),
    )


def dump_room_yaml(room: RoomConfig) -> str:
    lines = [
        f'trp: "{room.trp}"',
        f"kind: {room.kind}",
        f'id: "{room.id}"',
        f'title: "{_yaml_escape(room.title)}"',
        f'created_at: "{room.created_at}"',
        f'cwd: "{_yaml_escape(room.cwd)}"',
        "policy:",
        f"  speak: {room.policy.speak}",
        f"  floor_output: {room.policy.floor_output}",
        f"  max_floor_chars: {room.policy.max_floor_chars}",
        f"  max_floor_messages_per_turn: {room.policy.max_floor_messages_per_turn}",
        f"  max_context_messages: {room.policy.max_context_messages}",
        f"  allow_agent_mention: {_yaml_bool(room.policy.allow_agent_mention)}",
        f"  max_agent_chain: {room.policy.max_agent_chain}",
        f"  write_gate: {room.policy.write_gate}",
        f"  phase: {room.policy.phase}",
        "speakers:",
    ]
    for s in room.speakers:
        lines.append(f'  - id: "{s.id}"')
        lines.append(f"    kind: {s.kind}")
        lines.append(f'    display_name: "{_yaml_escape(s.display_name)}"')
        if s.adapter:
            lines.append(f"    adapter: {s.adapter}")
        lines.append(f"    enabled: {_yaml_bool(s.enabled)}")
    return "\n".join(lines) + "\n"


def _yaml_bool(v: bool) -> str:
    return "true" if v else "false"


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _parse_room_yaml(text: str) -> dict[str, Any]:
    """Two-level room.yaml: top keys + policy map + speakers list of maps."""
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except ImportError:
        pass

    result: dict[str, Any] = {}
    section: str | None = None
    current_speaker: dict[str, Any] | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        if indent == 0 and line.endswith(":") and ":" == line[-1] and line.count(":") == 1:
            key = line[:-1].strip()
            if key in ("policy", "speakers"):
                section = key
                result[key] = {} if key == "policy" else []
                current_speaker = None
            continue

        if indent == 0 and ":" in line:
            section = None
            current_speaker = None
            k, v = line.split(":", 1)
            result[k.strip()] = _scalar(v.strip())
            continue

        if section == "policy" and indent >= 2 and ":" in line:
            k, v = line.split(":", 1)
            result.setdefault("policy", {})[k.strip()] = _scalar(v.strip())
            continue

        if section == "speakers":
            if line.startswith("- "):
                rest = line[2:].strip()
                current_speaker = {}
                result.setdefault("speakers", []).append(current_speaker)
                if ":" in rest:
                    k, v = rest.split(":", 1)
                    current_speaker[k.strip()] = _scalar(v.strip())
                continue
            if current_speaker is not None and ":" in line:
                k, v = line.split(":", 1)
                current_speaker[k.strip()] = _scalar(v.strip())
            continue

    return result


def _scalar(v: str) -> Any:
    if v == "":
        return ""
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        inner = v[1:-1]
        return inner.replace("\\\\", "\\").replace('\\"', '"')
    if v in ("true", "True", "yes"):
        return True
    if v in ("false", "False", "no"):
        return False
    if v in ("null", "None", "~"):
        return None
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def create_meeting(
    parent: Path,
    *,
    title: str,
    cwd: str,
    room_id: str | None = None,
    human_id: str = "human",
    agents: list[tuple[str, str]] | None = None,
) -> Path:
    """Create meeting dir with room.yaml + empty thread. agents: (id, adapter)."""
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    rid = room_id or f"meeting-{now_iso().replace(':', '').replace('+', 'p')[:17]}"
    folder = "".join(c if c.isalnum() or c in "-_" else "-" for c in rid)
    meeting_dir = parent / folder
    if meeting_dir.exists():
        raise StoreError(f"already exists: {meeting_dir}")
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "desks").mkdir()
    (meeting_dir / ".runtime").mkdir()

    speakers = [
        Speaker(id=human_id, kind="human", display_name=human_id.title()),
    ]
    if agents is None:
        agents = [("mock", "mock")]
    for aid, adapter in agents:
        speakers.append(
            Speaker(
                id=aid,
                kind="agent",
                display_name=aid,
                adapter=adapter,
                enabled=True,
            )
        )

    room = RoomConfig(
        id=rid,
        title=title,
        created_at=now_iso(),
        cwd=str(Path(cwd).resolve()),
        speakers=speakers,
        path=meeting_dir,
    )
    (meeting_dir / ROOM_YAML).write_text(dump_room_yaml(room), encoding="utf-8")
    (meeting_dir / THREAD_JSONL).write_text("", encoding="utf-8")
    return meeting_dir

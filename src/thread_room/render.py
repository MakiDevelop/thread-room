"""Render floor thread for agent prompts and human export."""

from __future__ import annotations

from thread_room.models import Message, RoomConfig


def render_floor_chat(messages: list[Message], *, limit: int | None = None) -> str:
    msgs = messages if limit is None else messages[-limit:]
    lines: list[str] = []
    for m in msgs:
        if m.visibility == "desk":
            continue
        who = m.speaker
        prefix = f"**{m.ts} {who}**"
        if m.type != "utterance":
            prefix += f" · _{m.type}_"
        lines.append(prefix)
        lines.append(m.text)
        lines.append("")
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def build_agent_prompt(
    room: RoomConfig,
    *,
    speaker_id: str,
    display_name: str,
    trigger_text: str,
    floor_messages: list[Message],
) -> str:
    pol = room.policy
    thread = render_floor_chat(floor_messages, limit=pol.max_context_messages)
    return f"""# Thread Room — {room.title}

You are **{display_name}** (id={speaker_id}).
Room id: {room.id}
Phase: {pol.phase}
Write gate (v0 audit only, not hard deny): {pol.write_gate}

## Output contract (mandatory)

Return **only** a single JSON object (no markdown fence) with this shape:

{{"conclusion": "<public reply for the room>", "mentions": [], "files_claimed": []}}

Rules:
- `conclusion` is the ONLY text that will be posted to the public floor.
- Keep conclusion under {pol.max_floor_chars} characters.
- Do not put private reasoning in `conclusion`.
- `mentions` must be an array of speaker ids (ignored unless host allows agent mentions).
- If you cannot answer, still return JSON with a short conclusion stating that.

## Public thread (floor)

{thread if thread.strip() else "(empty)"}

## Current request

{trigger_text}
"""


def export_markdown(room: RoomConfig, messages: list[Message]) -> str:
    parts = [
        f"# {room.title}",
        "",
        f"- id: `{room.id}`",
        f"- created: {room.created_at}",
        f"- cwd: `{room.cwd}`",
        "",
        "## Participants",
        "",
    ]
    for s in room.speakers:
        flag = "" if s.enabled else " (disabled)"
        parts.append(f"- **{s.display_name}** (`{s.id}`, {s.kind}){flag}")
    parts.extend(["", "## Chat", ""])
    for m in messages:
        if m.visibility == "desk":
            continue
        header = f"**{m.ts} {m.speaker}**"
        if m.type != "utterance":
            header += f" · {m.type}"
        parts.append(header)
        parts.append("")
        parts.append(m.text)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"

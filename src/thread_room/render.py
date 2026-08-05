"""Render floor thread for agent prompts and human export."""

from __future__ import annotations

from thread_room.models import Message, RoomConfig
from thread_room.ownership import format_ownership_block, project_state


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
    ownership_block: str | None = None,
    phase: str | None = None,
    ratified_paths: list[str] | None = None,
) -> str:
    pol = room.policy
    ost = project_state(floor_messages, initial_phase=pol.phase)
    phase_s = phase or ost.phase
    own_block = ownership_block
    if own_block is None:
        own_block = format_ownership_block(ost)
    paths = ratified_paths if ratified_paths is not None else ost.paths_for(speaker_id)
    paths_s = ", ".join(f"`{p}`" for p in paths) if paths else "(none ratified for you)"
    thread = render_floor_chat(floor_messages, limit=pol.max_context_messages)
    return f"""# Thread Room — {room.title}

You are **{display_name}** (id={speaker_id}).
Room id: {room.id}
Phase: **{phase_s}**
Write gate: **{pol.write_gate}** (ownership_audit = post-hoc detect only; does not hard-block writes)

## Ratified ownership (all)
{own_block}

## Your ratified paths
{paths_s}

## Output contract (mandatory)

Your **final message** must be a single JSON object (no markdown fence) with this shape:

{{"conclusion": "<public reply for the room>", "mentions": [], "files_claimed": []}}

Rules:
- `conclusion` is the ONLY text that will be posted to the public floor.
- Keep conclusion under {pol.max_floor_chars} characters.
- Do not put chain-of-thought or tool logs in `conclusion`.
- `files_claimed` lists paths you edited (relative to room cwd); required honesty in write phase.
- Phase **{phase_s}**: if discuss, prefer analysis only; if write, only edit your ratified paths.
- If you cannot answer, still return JSON with a short conclusion stating that.

## Public thread (floor)

{thread if thread.strip() else "(empty)"}

## Current request

{trigger_text}
"""


def export_markdown(room: RoomConfig, messages: list[Message]) -> str:
    ost = project_state(messages, initial_phase=room.policy.phase)
    parts = [
        f"# {room.title}",
        "",
        f"- id: `{room.id}`",
        f"- created: {room.created_at}",
        f"- cwd: `{room.cwd}`",
        f"- phase: `{ost.phase}`",
        f"- write_gate: `{room.policy.write_gate}`",
        "",
        "## Participants",
        "",
    ]
    for s in room.speakers:
        flag = "" if s.enabled else " (disabled)"
        parts.append(f"- **{s.display_name}** (`{s.id}`, {s.kind}){flag}")
    parts.extend(["", "## Ownership (ratified)", ""])
    if ost.ratified_map:
        parts.append("| Path | Owner |")
        parts.append("|------|-------|")
        for p, o in sorted(ost.ratified_map.items()):
            parts.append(f"| `{p}` | {o} |")
    else:
        parts.append("_None ratified._")
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

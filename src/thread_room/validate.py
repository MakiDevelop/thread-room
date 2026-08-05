"""Validate a meeting directory (room.yaml + thread.jsonl)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from thread_room.ownership import find_overlaps, project_state
from thread_room.store import (
    ROOM_YAML,
    THREAD_JSONL,
    StoreError,
    ThreadStore,
    load_room_yaml,
    read_thread,
)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_meeting(meeting_dir: Path) -> ValidationResult:
    result = ValidationResult(ok=True)
    meeting_dir = meeting_dir.resolve()

    if not meeting_dir.is_dir():
        result.add_error(f"not a directory: {meeting_dir}")
        return result

    room_path = meeting_dir / ROOM_YAML
    thread_path = meeting_dir / THREAD_JSONL

    if not room_path.is_file():
        result.add_error(f"missing {ROOM_YAML}")
        return result
    if not thread_path.is_file():
        result.add_error(f"missing {THREAD_JSONL}")
        return result

    try:
        room = load_room_yaml(room_path)
    except (StoreError, KeyError, ValueError, TypeError) as e:
        result.add_error(f"room.yaml: {e}")
        return result

    if not room.id:
        result.add_error("room.yaml: empty id")
    if not room.speakers:
        result.add_error("room.yaml: no speakers")
    humans = [s for s in room.speakers if s.kind == "human"]
    if not humans:
        result.add_warning("room.yaml: no human speaker")
    ids = [s.id for s in room.speakers]
    if len(ids) != len(set(ids)):
        result.add_error("room.yaml: duplicate speaker ids")

    try:
        messages = read_thread(thread_path)
    except StoreError as e:
        result.add_error(f"thread.jsonl: {e}")
        return result

    # cross-record
    seen_ids: set[str] = set()
    for i, m in enumerate(messages, 1):
        if m.id in seen_ids:
            result.add_error(f"thread line ~{i}: duplicate id {m.id}")
        seen_ids.add(m.id)
        if m.room_id != room.id:
            result.add_error(
                f"message {m.id}: room_id {m.room_id!r} != room.yaml id {room.id!r}"
            )
        if m.speaker not in ids and m.speaker != "system" and m.kind != "system":
            result.add_warning(
                f"message {m.id}: speaker {m.speaker!r} not in room.yaml speakers"
            )
        if m.kind == "system" and m.speaker != "system":
            result.add_warning(
                f"message {m.id}: kind=system but speaker={m.speaker!r}"
            )
        if m.type == "utterance" and not (m.text or "").strip():
            result.add_warning(f"message {m.id}: empty utterance text")

    # closed then more utterances
    closed_at = None
    for m in messages:
        if m.type == "system" and m.meta.get("event") == "close":
            closed_at = m.id
            continue
        if closed_at and m.type in ("utterance", "ownership", "decision", "promote"):
            result.add_error(
                f"message {m.id}: content after close event ({closed_at})"
            )

    # ownership projection
    try:
        ost = project_state(messages, initial_phase=room.policy.phase)
        # check latest pending/ratified bundles for internal overlap
        for b in ost.bundles:
            if b.consensus == "ratified":
                overs = find_overlaps(b.assignments)
                if overs:
                    result.add_error(
                        f"ownership {b.assignment_id}: overlap in ratified set: "
                        + "; ".join(overs)
                    )
    except Exception as e:
        result.add_error(f"ownership projection: {e}")

    # policy hints
    if room.policy.write_gate not in ("off", "ownership_audit", "ownership_enforced"):
        result.add_warning(
            f"unknown write_gate {room.policy.write_gate!r} "
            "(known: off, ownership_audit, ownership_enforced)"
        )
    if room.policy.floor_output not in (
        "conclusion_only",
        "summary_then_conclusion",
        "full",
    ):
        result.add_warning(f"unusual floor_output {room.policy.floor_output!r}")

    # try full store load
    try:
        ThreadStore(meeting_dir).load()
    except StoreError as e:
        result.add_error(f"store load: {e}")

    return result

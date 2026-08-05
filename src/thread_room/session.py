"""Meeting session logic: say, pump, close (single-writer)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from thread_room.adapters.base import TurnContext
from thread_room.adapters.registry import get_adapter
from thread_room.models import Message, RoomConfig, extract_mentions, make_message
from thread_room.ownership import (
    OwnershipState,
    PathAssignment,
    audit_paths,
    build_ownership_meta,
    find_overlaps,
    format_ownership_block,
    git_status_snapshot,
    project_state,
)
from thread_room.parser import ParseError, parse_agent_output
from thread_room.render import build_agent_prompt, export_markdown
from thread_room.store import StoreError, ThreadStore


@dataclass
class PendingTurn:
    target: str
    trigger_message_id: str
    trigger_text: str
    depth: int = 0


@dataclass
class Session:
    room: RoomConfig
    store: ThreadStore
    pending: list[PendingTurn] = field(default_factory=list)

    @classmethod
    def open(cls, meeting_dir: Path) -> Session:
        store = ThreadStore(meeting_dir)
        room = store.load()
        sess = cls(room=room, store=store)
        sess.pending = _rebuild_pending(room, store.messages)
        return sess

    def ownership_state(self) -> OwnershipState:
        return project_state(
            self.store.messages, initial_phase=self.room.policy.phase
        )

    def propose_ownership(
        self,
        assignments: list[PathAssignment],
        *,
        note: str = "",
        speaker: str | None = None,
    ) -> Message:
        overlaps = find_overlaps(assignments)
        if overlaps:
            raise StoreError("ownership overlap: " + "; ".join(overlaps))
        st = self.ownership_state()
        from thread_room.ownership import _norm, _paths_overlap

        for a in assignments:
            for path in a.paths:
                existing = st.owner_for(path)
                if existing and existing != a.owner:
                    raise StoreError(
                        f"path {path!r} already ratified to {existing!r}"
                    )
                for pref, own in st.ratified_map.items():
                    if own == a.owner:
                        continue
                    if _paths_overlap(_norm(path), pref):
                        raise StoreError(
                            f"path {path!r} overlaps ratified {pref!r} ({own})"
                        )

        human = speaker or self.room.human_id()
        meta = build_ownership_meta(assignments, consensus="pending", note=note)
        lines = [
            f"{a.owner}: {', '.join(a.paths)}" for a in assignments
        ]
        text = "Ownership proposed:\n" + "\n".join(f"- {ln}" for ln in lines)
        if note:
            text += f"\nNote: {note}"
        msg = make_message(
            self.room,
            speaker=human,
            kind="human",
            type="ownership",
            text=text,
            meta=meta,
        )
        self.store.append(msg)
        return msg

    def ratify_ownership(
        self, assignment_id: str | None = None, *, speaker: str | None = None
    ) -> Message:
        st = self.ownership_state()
        if not st.bundles:
            raise StoreError("no ownership proposals to ratify")
        target = None
        if assignment_id:
            for b in st.bundles:
                if b.assignment_id == assignment_id:
                    target = b
                    break
            if target is None:
                raise StoreError(f"unknown assignment_id: {assignment_id}")
        else:
            # latest pending, else latest any
            pending = [b for b in st.bundles if b.consensus != "ratified"]
            target = pending[-1] if pending else st.bundles[-1]
        human = speaker or self.room.human_id()
        # re-emit ownership as ratified + decision
        meta = build_ownership_meta(
            target.assignments,
            consensus="ratified",
            note=target.note,
            assignment_id=target.assignment_id,
        )
        own_msg = make_message(
            self.room,
            speaker=human,
            kind="human",
            type="ownership",
            text=f"Ownership ratified: {target.assignment_id}",
            meta=meta,
        )
        self.store.append(own_msg)
        dec = make_message(
            self.room,
            speaker=human,
            kind="human",
            type="decision",
            text=f"Ratified ownership {target.assignment_id}",
            meta={
                "event": "ratify_ownership",
                "assignment_id": target.assignment_id,
            },
        )
        self.store.append(dec)
        return dec

    def set_phase(self, phase: str, *, speaker: str | None = None) -> Message:
        if phase not in ("discuss", "write"):
            raise StoreError("phase must be discuss|write")
        if phase == "write":
            st = self.ownership_state()
            if not st.ratified_map and self.room.policy.write_gate != "off":
                raise StoreError(
                    "cannot enter write phase without ratified ownership "
                    "(or set write_gate: off)"
                )
        human = speaker or self.room.human_id()
        msg = make_message(
            self.room,
            speaker=human,
            kind="human",
            type="decision",
            text=f"Phase → {phase}",
            meta={"event": "phase", "phase": phase},
        )
        self.store.append(msg)
        return msg

    def say(self, text: str, *, speaker: str | None = None) -> Message:
        human = speaker or self.room.human_id()
        smap = self.room.speaker_map()
        if human not in smap or smap[human].kind != "human":
            # allow explicit human speaker id from config
            if human not in smap:
                raise StoreError(f"unknown speaker: {human}")
        mentions = extract_mentions(text)
        # only keep known agent ids for pump
        valid = []
        for m in mentions:
            sp = smap.get(m)
            if sp and sp.kind == "agent" and sp.enabled:
                valid.append(m)
        msg = make_message(
            self.room,
            speaker=human,
            kind="human",
            type="utterance",
            text=text,
            mentions=valid,
        )
        self.store.append(msg)
        for m in valid:
            self.pending.append(
                PendingTurn(
                    target=m,
                    trigger_message_id=msg.id,
                    trigger_text=text,
                    depth=0,
                )
            )
        return msg

    def pump(self, *, once: bool = False) -> list[Message]:
        """Process pending mentions. Serial. Returns new floor messages."""
        produced: list[Message] = []
        while self.pending:
            turn = self.pending.pop(0)
            out = self._run_agent_turn(turn)
            produced.extend(out)
            if once:
                break
        return produced

    def _run_agent_turn(self, turn: PendingTurn) -> list[Message]:
        smap = self.room.speaker_map()
        sp = smap.get(turn.target)
        if not sp or sp.kind != "agent" or not sp.enabled:
            sys_msg = make_message(
                self.room,
                speaker="system",
                kind="system",
                type="system",
                text=f"skip unknown/disabled agent @{turn.target}",
                meta={
                    "event": "skip",
                    "target": turn.target,
                    "trigger_message_id": turn.trigger_message_id,
                },
            )
            self.store.append(sys_msg)
            return [sys_msg]

        adapter_name = sp.adapter or "mock"
        try:
            adapter = get_adapter(adapter_name)
        except KeyError as e:
            sys_msg = make_message(
                self.room,
                speaker="system",
                kind="system",
                type="system",
                text=f"adapter error for @{turn.target}: {e}",
                meta={
                    "event": "adapter_error",
                    "target": turn.target,
                    "trigger_message_id": turn.trigger_message_id,
                },
            )
            self.store.append(sys_msg)
            return [sys_msg]

        pol = self.room.policy
        ost = self.ownership_state()
        phase = ost.phase
        floor = self.store.recent_floor(pol.max_context_messages)
        prompt = build_agent_prompt(
            self.room,
            speaker_id=sp.id,
            display_name=sp.display_name,
            trigger_text=turn.trigger_text,
            floor_messages=floor,
            ownership_block=format_ownership_block(ost),
            phase=phase,
            ratified_paths=ost.paths_for(sp.id),
        )
        cwd = Path(self.room.cwd)
        if not cwd.is_dir():
            cwd = self.store.meeting_dir

        # save full prompt+stdout under desks
        desk = self.store.meeting_dir / "desks" / sp.id
        traces = desk / "traces"
        traces.mkdir(parents=True, exist_ok=True)

        # Codex timeout default 900s; mock ignores
        timeout = 900 if (sp.adapter or "").startswith("codex") else 120
        before_git = (
            git_status_snapshot(cwd)
            if pol.write_gate == "ownership_audit" and phase == "write"
            else set()
        )
        ctx = TurnContext(
            speaker_id=sp.id,
            display_name=sp.display_name,
            prompt=prompt,
            cwd=cwd,
            room_id=self.room.id,
            phase=phase,
            max_floor_chars=pol.max_floor_chars,
            timeout_sec=timeout,
            work_dir=traces,
            ratified_paths=ost.paths_for(sp.id),
        )

        result = adapter.run(ctx)
        turn_id = turn.trigger_message_id
        trace_path = traces / f"{turn_id}-{sp.id}.log"
        trace_path.write_text(
            f"=== PROMPT ===\n{prompt}\n\n=== STDOUT ===\n{result.stdout}\n\n"
            f"=== STDERR ===\n{result.stderr}\n\n=== EXIT {result.exit_code} ===\n",
            encoding="utf-8",
        )
        try:
            trace_path.chmod(0o600)
        except OSError:
            pass

        if result.exit_code != 0:
            sys_msg = make_message(
                self.room,
                speaker="system",
                kind="system",
                type="system",
                text=(
                    f"@{sp.id} failed (exit {result.exit_code}). "
                    f"Trace: desks/{sp.id}/traces/{trace_path.name}"
                ),
                meta={
                    "event": "agent_failed",
                    "target": sp.id,
                    "exit_code": result.exit_code,
                    "trigger_message_id": turn.trigger_message_id,
                    "trace_path": str(trace_path.relative_to(self.store.meeting_dir)),
                },
            )
            self.store.append(sys_msg)
            return [sys_msg]

        try:
            parsed = parse_agent_output(
                result.stdout, max_chars=pol.max_floor_chars
            )
        except ParseError as e:
            sys_msg = make_message(
                self.room,
                speaker="system",
                kind="system",
                type="system",
                text=(
                    f"@{sp.id} produced no valid public conclusion ({e}). "
                    f"Trace: desks/{sp.id}/traces/{trace_path.name}"
                ),
                meta={
                    "event": "parse_failed",
                    "target": sp.id,
                    "error": str(e),
                    "trigger_message_id": turn.trigger_message_id,
                    "trace_path": str(trace_path.relative_to(self.store.meeting_dir)),
                },
            )
            self.store.append(sys_msg)
            return [sys_msg]

        # agent mentions: only if allowed and depth ok
        new_mentions: list[str] = []
        if pol.allow_agent_mention and turn.depth < pol.max_agent_chain:
            for m in parsed.mentions:
                t = smap.get(m)
                if t and t.kind == "agent" and t.enabled and m != sp.id:
                    new_mentions.append(m)

        utt = make_message(
            self.room,
            speaker=sp.id,
            kind="agent",
            type="utterance",
            text=parsed.conclusion,
            mentions=new_mentions,
            meta={
                "turn_id": turn_id,
                "trigger_message_id": turn.trigger_message_id,
                "floor_output": pol.floor_output,
                "trace_path": str(trace_path.relative_to(self.store.meeting_dir)),
                "duration_ms": result.duration_ms,
                "raw_format": parsed.raw_format,
                "files_claimed": parsed.files_claimed,
                "phase": phase,
            },
        )
        self.store.append(utt)
        out = [utt]

        # ownership_audit: post-hoc path check (does NOT block writes)
        if pol.write_gate == "ownership_audit" and phase == "write":
            after = git_status_snapshot(cwd)
            changed = sorted(after - before_git) if before_git or after else []
            claimed = list(parsed.files_claimed or [])
            paths_to_check = list(dict.fromkeys(claimed + changed))
            if paths_to_check:
                violations = audit_paths(
                    ost, speaker=sp.id, paths=paths_to_check
                )
                if violations:
                    sys_msg = make_message(
                        self.room,
                        speaker="system",
                        kind="system",
                        type="system",
                        text=(
                            f"ownership_audit violation by @{sp.id}: "
                            + "; ".join(violations)
                        ),
                        meta={
                            "event": "ownership_audit",
                            "target": sp.id,
                            "trigger_message_id": turn.trigger_message_id,
                            "violations": violations,
                            "paths_checked": paths_to_check,
                            "note": "audit only — writes were not blocked",
                        },
                    )
                    self.store.append(sys_msg)
                    out.append(sys_msg)

        for m in new_mentions:
            self.pending.append(
                PendingTurn(
                    target=m,
                    trigger_message_id=utt.id,
                    trigger_text=parsed.conclusion,
                    depth=turn.depth + 1,
                )
            )
        return out

    def system(self, text: str, *, meta: dict | None = None) -> Message:
        msg = make_message(
            self.room,
            speaker="system",
            kind="system",
            type="system",
            text=text,
            meta=meta or {},
        )
        self.store.append(msg)
        return msg

    def close(self) -> Message:
        msg = make_message(
            self.room,
            speaker="system",
            kind="system",
            type="system",
            text="Room closed.",
            meta={"event": "close"},
        )
        self.store.append(msg)
        return msg

    def export(self, path: Path | None = None) -> Path:
        out = path or (self.store.meeting_dir / "export.md")
        md = export_markdown(self.room, self.store.messages)
        out.write_text(md, encoding="utf-8")
        return out

    def status_text(self) -> str:
        n = len(self.store.messages)
        pend = ", ".join(p.target for p in self.pending) or "(none)"
        closed = "yes" if self.store.closed else "no"
        ost = self.ownership_state()
        own = (
            ", ".join(f"{p}→{o}" for p, o in sorted(ost.ratified_map.items()))
            or "(none)"
        )
        return (
            f"room={self.room.id} messages={n} closed={closed} "
            f"pending=[{pend}] phase={ost.phase} "
            f"write_gate={self.room.policy.write_gate} ownership=[{own}]"
        )


def _rebuild_pending(room: RoomConfig, messages: list[Message]) -> list[PendingTurn]:
    """Rebuild mention queue from thread so one-shot say/pump works across processes."""
    if any(m.type == "system" and m.meta.get("event") == "close" for m in messages):
        return []
    smap = room.speaker_map()
    pending: list[PendingTurn] = []
    for msg in messages:
        if not msg.mentions:
            continue
        for target in msg.mentions:
            sp = smap.get(target)
            if not sp or sp.kind != "agent" or not sp.enabled:
                continue
            answered = any(
                (
                    (m.speaker == target and m.meta.get("trigger_message_id") == msg.id)
                    or (
                        m.type == "system"
                        and m.meta.get("target") == target
                        and m.meta.get("trigger_message_id") == msg.id
                    )
                )
                for m in messages
            )
            if not answered:
                pending.append(
                    PendingTurn(
                        target=target,
                        trigger_message_id=msg.id,
                        trigger_text=msg.text,
                        depth=0,
                    )
                )
    return pending

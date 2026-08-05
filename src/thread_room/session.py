"""Meeting session logic: say, pump, close (single-writer)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from thread_room.adapters.base import TurnContext
from thread_room.adapters.mock import get_adapter
from thread_room.models import Message, RoomConfig, extract_mentions, make_message
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
        floor = self.store.recent_floor(pol.max_context_messages)
        prompt = build_agent_prompt(
            self.room,
            speaker_id=sp.id,
            display_name=sp.display_name,
            trigger_text=turn.trigger_text,
            floor_messages=floor,
        )
        cwd = Path(self.room.cwd)
        if not cwd.is_dir():
            cwd = self.store.meeting_dir

        ctx = TurnContext(
            speaker_id=sp.id,
            display_name=sp.display_name,
            prompt=prompt,
            cwd=cwd,
            room_id=self.room.id,
            phase=pol.phase,
            max_floor_chars=pol.max_floor_chars,
        )

        # save full prompt+stdout under desks
        desk = self.store.meeting_dir / "desks" / sp.id
        traces = desk / "traces"
        traces.mkdir(parents=True, exist_ok=True)

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
            },
        )
        self.store.append(utt)
        out = [utt]

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
        return (
            f"room={self.room.id} messages={n} closed={closed} "
            f"pending=[{pend}] phase={self.room.policy.phase}"
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

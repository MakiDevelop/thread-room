"""CLI — bare `thread-room` starts interactive meeting wizard."""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

from thread_room import __version__
from thread_room.config import (
    AGENT_CATALOG,
    get_current_meeting,
    meetings_root,
    resolve_meeting,
    set_current_meeting,
)
from thread_room.desks import DeskError, load_terminals, session_exists
from thread_room.ownership import parse_assign_specs
from thread_room.session import Session
from thread_room.store import StoreError, create_meeting


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    # No args → interactive start
    if not argv:
        try:
            _interactive_start()
        except (StoreError, DeskError, FileNotFoundError, ValueError, EOFError, KeyboardInterrupt) as e:
            if isinstance(e, (EOFError, KeyboardInterrupt)):
                print()
                sys.exit(130)
            print(f"thread-room: error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if argv[0] in {"-h", "--help", "help"}:
        _print_help()
        return
    if argv[0] in {"-V", "--version", "version"}:
        print(f"thread-room {__version__}")
        return

    cmd = argv[0]
    rest = argv[1:]
    try:
        handlers = {
            "go": _cmd_go,
            "start": _cmd_go,
            "end": _cmd_end,
            "attach": _cmd_attach,
            "new": _cmd_new,
            "open": _cmd_open,
            "say": _cmd_say,
            "pump": _cmd_pump,
            "export": _cmd_export,
            "close": _cmd_close,
            "status": _cmd_status,
            "ownership": _cmd_ownership,
            "ratify": _cmd_ratify,
            "phase": _cmd_phase,
            "desks": _cmd_desks,
            "promote": _cmd_promote,
            "doctor": _cmd_doctor,
            "validate": _cmd_validate,
            "current": _cmd_current,
            "use": _cmd_use,
        }
        if cmd not in handlers:
            print(f"thread-room: unknown command {cmd!r}", file=sys.stderr)
            _print_help()
            sys.exit(2)
        handlers[cmd](rest)
    except (StoreError, DeskError, FileNotFoundError, ValueError) as e:
        print(f"thread-room: error: {e}", file=sys.stderr)
        sys.exit(1)


def _print_help() -> None:
    cur = get_current_meeting()
    cur_s = str(cur) if cur else "(none — run thread-room with no args)"
    print(
        f"""thread-room {__version__} — multi-agent meetings on the filesystem

  thread-room              # start wizard: title + pick agents + desks
  tr                       # same (after install.sh)

Everyday:
  tr go "Title"            # non-interactive start (flags below)
  tr say "Hello @codex"    # uses current meeting (no -d needed)
  tr pump
  tr attach                # tmux attach to desks
  tr promote --from codex --text "結論"
  tr end                   # desks close + export + close

Current meeting: {cur_s}

Also: new open ownership ratify phase desks status validate doctor use
"""
    )


# ── interactive start (bare thread-room) ──────────────────────────


def _interactive_start() -> None:
    print(f"thread-room {__version__}")
    print("Start a meeting (Ctrl-C to cancel)\n")

    title = _prompt("Title", "Meeting")
    cwd = _prompt("Working directory (repo)", str(Path.cwd()))
    cwd_path = Path(cwd).expanduser().resolve()
    if not cwd_path.is_dir():
        raise ValueError(f"not a directory: {cwd_path}")

    print("\nAgents — pick numbers (space/comma separated), or names:\n")
    for i, a in enumerate(AGENT_CATALOG, 1):
        print(f"  {i}) {a['label']:8}  {a['desc']}")
    print()
    sel = _prompt("Selection", "1")
    agents = _parse_agent_selection(sel)
    if not agents:
        raise ValueError("pick at least one agent")

    desks_ans = _prompt("Open tmux desks now? [Y/n]", "Y").strip().lower()
    open_desks = desks_ans not in ("n", "no", "0")

    parent = meetings_root()
    parent.mkdir(parents=True, exist_ok=True)
    room_id = _slug(title)

    path = create_meeting(
        parent,
        title=title,
        cwd=str(cwd_path),
        room_id=room_id,
        agents=agents,
    )
    sess = Session.open(path)
    sess.system("Room opened.", meta={"event": "open"})
    set_current_meeting(path)

    print(f"\nMeeting: {path}")
    print(f"Agents:  {', '.join(a[0] for a in agents)}")

    if open_desks:
        try:
            state = sess.desks_open()
            print(f"tmux:    {state.tmux_session}")
            print(f"\n  tmux attach -t {state.tmux_session}")
            print("  (or: tr attach)\n")
        except DeskError as e:
            print(f"desks skipped: {e}")
            print("Continue with: tr open   or   tr say \"@mock hi\"\n")
    else:
        print("\nNext: tr open   or   tr say \"@mock hi\" && tr pump\n")

    # drop into REPL
    _repl_loop(sess)


def _prompt(label: str, default: str) -> str:
    try:
        raw = input(f"{label} [{default}]: ").strip()
    except EOFError:
        return default
    return raw if raw else default


def _parse_agent_selection(sel: str) -> list[tuple[str, str]]:
    """Return list of (id, adapter) from '1 2' or 'codex mock'."""
    tokens = re.split(r"[\s,]+", sel.strip())
    tokens = [t for t in tokens if t]
    if not tokens:
        return [("mock", "mock")]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    by_id = {a["id"]: a for a in AGENT_CATALOG}
    by_label = {a["label"].lower(): a for a in AGENT_CATALOG}
    for t in tokens:
        if t.isdigit():
            i = int(t)
            if 1 <= i <= len(AGENT_CATALOG):
                a = AGENT_CATALOG[i - 1]
            else:
                raise ValueError(f"invalid agent number: {t}")
        else:
            key = t.lower().replace("-", "_")
            a = by_id.get(key) or by_label.get(key)
            if not a:
                # allow id:adapter freeform
                if ":" in t:
                    aid, adapter = t.split(":", 1)
                    if aid not in seen:
                        out.append((aid, adapter))
                        seen.add(aid)
                    continue
                raise ValueError(f"unknown agent: {t}")
        if a["id"] not in seen:
            out.append((a["id"], a["adapter"]))
            seen.add(a["id"])
    return out


def _slug(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.strip()).strip("-").lower()
    return (s or "meeting")[:48]


# ── go / end / attach shortcuts ─────────────────────────────────


def _cmd_go(argv: list[str]) -> None:
    """Non-interactive start: tr go "Title" [--agents 1,2|codex,mock] [--no-desks]"""
    p = argparse.ArgumentParser(prog="thread-room go")
    p.add_argument("title", nargs="?", default="Meeting")
    p.add_argument("--cwd", default=str(Path.cwd()))
    p.add_argument(
        "--agents",
        default="1",
        help="numbers and/or names, e.g. 2,1 or codex,mock (default: mock)",
    )
    p.add_argument("--no-desks", action="store_true")
    p.add_argument("--id", default=None, dest="room_id")
    args = p.parse_args(argv)
    agents = _parse_agent_selection(args.agents)
    parent = meetings_root()
    parent.mkdir(parents=True, exist_ok=True)
    path = create_meeting(
        parent,
        title=args.title,
        cwd=str(Path(args.cwd).expanduser().resolve()),
        room_id=args.room_id or _slug(args.title),
        agents=agents,
    )
    sess = Session.open(path)
    sess.system("Room opened.", meta={"event": "open"})
    set_current_meeting(path)
    print(path)
    if not args.no_desks:
        try:
            state = sess.desks_open()
            print(f"tmux attach -t {state.tmux_session}")
        except DeskError as e:
            print(f"desks: {e}", file=sys.stderr)


def _cmd_end(argv: list[str]) -> None:
    path = _meeting_from_argv(argv)
    sess = Session.open(path)
    try:
        for line in sess.desks_close():
            print(line)
    except DeskError as e:
        print(f"desks: {e}")
    if not sess.store.closed:
        sess.close()
    exp = sess.export()
    print(f"ended export={exp}")


def _cmd_attach(argv: list[str]) -> None:
    path = _meeting_from_argv(argv)
    st = load_terminals(path)
    if not st or not session_exists(st.tmux_session):
        raise FileNotFoundError("no live desks; run: tr   or   tr desks open")
    # exec tmux attach
    import os

    os.execvp("tmux", ["tmux", "attach", "-t", st.tmux_session])


def _cmd_current(argv: list[str]) -> None:
    cur = get_current_meeting()
    print(cur if cur else "(none)")


def _cmd_use(argv: list[str]) -> None:
    if not argv:
        raise ValueError("usage: thread-room use MEETING_DIR")
    p = Path(argv[0]).expanduser().resolve()
    if not (p / "room.yaml").is_file():
        raise FileNotFoundError(f"not a meeting: {p}")
    set_current_meeting(p)
    print(f"current={p}")


def _meeting_from_argv(argv: list[str]) -> Path:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-d", "--dir", dest="meeting")
    args, _ = p.parse_known_args(argv)
    return resolve_meeting(args.meeting)


def _meeting_dir(argv: list[str]) -> tuple[Path, list[str]]:
    """-d optional: fall back to current meeting."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-d", "--dir", dest="meeting")
    args, rest = p.parse_known_args(argv)
    path = resolve_meeting(args.meeting)
    set_current_meeting(path)
    return path, rest


# ── original commands ( -d optional ) ───────────────────────────


def _cmd_new(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="thread-room new")
    p.add_argument("--title", required=True)
    p.add_argument("--cwd", default=".")
    p.add_argument("--dir", default=None, help="parent dir (default: ~/thread-room-meetings)")
    p.add_argument("--id", default=None, dest="room_id")
    p.add_argument("--agent", action="append", default=[])
    args = p.parse_args(argv)
    agents: list[tuple[str, str]] = []
    for a in args.agent:
        if ":" in a:
            aid, adapter = a.split(":", 1)
        else:
            aid, adapter = a, "mock"
        agents.append((aid, adapter))
    if not agents:
        agents = [("mock", "mock")]
    parent = Path(args.dir) if args.dir else meetings_root()
    path = create_meeting(
        parent,
        title=args.title,
        cwd=args.cwd,
        room_id=args.room_id,
        agents=agents,
    )
    sess = Session.open(path)
    sess.system("Room opened.", meta={"event": "open"})
    set_current_meeting(path)
    print(path)


def _cmd_say(argv: list[str]) -> None:
    path, rest = _meeting_dir(argv)
    if not rest:
        raise ValueError("usage: thread-room say [-d DIR] TEXT")
    text = " ".join(rest)
    sess = Session.open(path)
    msg = sess.say(text)
    print(f"ok id={msg.id} mentions={msg.mentions}")


def _cmd_pump(argv: list[str]) -> None:
    path, rest = _meeting_dir(argv)
    once = "--once" in rest
    sess = Session.open(path)
    produced = sess.pump(once=once)
    if not produced:
        print("(no pending)")
    for m in produced:
        print(f"{m.type}\t{m.speaker}\t{m.text[:200]}")


def _cmd_ownership(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="thread-room ownership")
    p.add_argument("-d", "--dir", dest="meeting", default=None)
    p.add_argument("--assign", action="append", required=True)
    p.add_argument("--note", default="")
    args = p.parse_args(argv)
    path = resolve_meeting(args.meeting)
    set_current_meeting(path)
    assignments = parse_assign_specs(args.assign)
    sess = Session.open(path)
    msg = sess.propose_ownership(assignments, note=args.note)
    print(f"ok ownership proposed assignment_id={msg.meta.get('assignment_id')}")


def _cmd_ratify(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="thread-room ratify")
    p.add_argument("-d", "--dir", dest="meeting", default=None)
    p.add_argument("--id", dest="assignment_id", default=None)
    args = p.parse_args(argv)
    path = resolve_meeting(args.meeting)
    set_current_meeting(path)
    sess = Session.open(path)
    msg = sess.ratify_ownership(args.assignment_id)
    print(f"ok ratified assignment_id={msg.meta.get('assignment_id')}")


def _cmd_phase(argv: list[str]) -> None:
    path, rest = _meeting_dir(argv)
    if not rest or rest[0] not in ("discuss", "write"):
        raise ValueError("usage: thread-room phase [-d DIR] discuss|write")
    sess = Session.open(path)
    msg = sess.set_phase(rest[0])
    print(f"ok phase={msg.meta.get('phase')}")


def _cmd_export(argv: list[str]) -> None:
    path, rest = _meeting_dir(argv)
    out = None
    if "-o" in rest:
        i = rest.index("-o")
        out = Path(rest[i + 1])
    sess = Session.open(path)
    print(sess.export(out))


def _cmd_close(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    sess = Session.open(path)
    try:
        for line in sess.desks_close():
            print(line)
    except DeskError as e:
        print(f"desks: {e}")
    if sess.store.closed:
        print("already closed")
        return
    sess.close()
    print(f"closed export={sess.export()}")


def _cmd_desks(argv: list[str]) -> None:
    if not argv or argv[0] not in ("open", "list", "close", "doctor"):
        raise ValueError("usage: thread-room desks open|list|close|doctor [-d DIR]")
    sub = argv[0]
    path, _ = _meeting_dir(argv[1:])
    sess = Session.open(path)
    if sub == "open":
        state = sess.desks_open()
        print(f"ok tmux_session={state.tmux_session}")
        print(f"attach: tmux attach -t {state.tmux_session}")
        return
    if sub == "list":
        from thread_room.desks import list_desks

        print(list_desks(path))
        return
    if sub == "close":
        for line in sess.desks_close():
            print(line)
        return
    if sub == "doctor":
        from thread_room.desks import doctor

        print("\n".join(doctor(path)))


def _cmd_promote(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="thread-room promote")
    p.add_argument("-d", "--dir", dest="meeting", default=None)
    p.add_argument("--from", required=True, dest="from_speaker")
    p.add_argument("--text", default=None)
    p.add_argument("--file", default=None, dest="file_path")
    p.add_argument("--last-side", nargs="?", const=1, type=int, default=None)
    args = p.parse_args(argv)
    path = resolve_meeting(args.meeting)
    set_current_meeting(path)
    if args.text is not None:
        text = args.text
    elif args.file_path:
        text = Path(args.file_path).read_text(encoding="utf-8")
    elif args.last_side is not None:
        from thread_room.desks import read_last_side

        text = read_last_side(path, args.from_speaker, n=args.last_side)
    else:
        raise ValueError("promote requires --text, --file, or --last-side")
    sess = Session.open(path)
    msg = sess.promote(from_speaker=args.from_speaker, text=text)
    print(f"ok promote id={msg.id} from={args.from_speaker}")


def _cmd_doctor(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    from thread_room.desks import doctor

    print("\n".join(doctor(path)))


def _cmd_validate(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    from thread_room.validate import validate_meeting

    result = validate_meeting(path)
    for w in result.warnings:
        print(f"warning: {w}")
    for e in result.errors:
        print(f"error: {e}")
    if result.ok:
        print(f"ok: {path.resolve()}")
        sys.exit(0)
    print(f"invalid: {len(result.errors)} error(s)")
    sys.exit(1)


def _cmd_status(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    sess = Session.open(path)
    print(sess.status_text())
    print(f"path={path.resolve()}")


def _cmd_open(argv: list[str]) -> None:
    if argv:
        meeting = Path(argv[0]).expanduser().resolve()
    else:
        meeting = resolve_meeting(None)
    if not (meeting / "room.yaml").is_file():
        raise FileNotFoundError(f"not a meeting dir: {meeting}")
    set_current_meeting(meeting)
    sess = Session.open(meeting)
    print(f"thread-room open: {meeting}")
    print(sess.status_text())
    _repl_loop(sess)


def _repl_loop(sess: Session) -> None:
    print("Type help · quit ends REPL (meeting stays open)")
    while True:
        try:
            line = input("room> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        try:
            if line in {"quit", "exit", "q"}:
                break
            _repl_line(sess, line)
        except (StoreError, DeskError, ValueError, KeyError) as e:
            print(f"error: {e}")
        if sess.store.closed:
            print("room closed")
            break


def _repl_line(sess: Session, line: str) -> None:
    if line in {"help", "?"}:
        print(
            "say | pump | ownership | ratify | phase | desks open|list|close | "
            "promote from ID text… | attach | export | status | thread | end | help"
        )
        return
    if line == "status":
        print(sess.status_text())
        return
    if line == "thread":
        from thread_room.render import render_floor_chat

        print(render_floor_chat(sess.store.messages) or "(empty)")
        return
    if line == "attach":
        st = load_terminals(sess.store.meeting_dir)
        if not st or not session_exists(st.tmux_session):
            print("no live desks")
            return
        import os

        os.execvp("tmux", ["tmux", "attach", "-t", st.tmux_session])
    if line in {"end", "close"}:
        try:
            for ln in sess.desks_close():
                print(ln)
        except DeskError as e:
            print(f"desks: {e}")
        if not sess.store.closed:
            sess.close()
        print(f"export={sess.export()}")
        return
    if line == "pump" or line.startswith("pump "):
        once = "once" in line.split()
        produced = sess.pump(once=once)
        if not produced:
            print("(no pending)")
        for m in produced:
            print(f"[{m.speaker}/{m.type}] {m.text}")
        return
    if line == "export" or line.startswith("export "):
        parts = shlex.split(line)
        out = Path(parts[1]) if len(parts) > 1 else None
        print(f"wrote {sess.export(out)}")
        return
    if line.startswith("ownership "):
        msg = sess.propose_ownership(parse_assign_specs(line.split()[1:]))
        print(f"proposed {msg.meta.get('assignment_id')}")
        return
    if line == "ratify" or line.startswith("ratify "):
        parts = line.split()
        msg = sess.ratify_ownership(parts[1] if len(parts) > 1 else None)
        print(f"ratified {msg.meta.get('assignment_id')}")
        return
    if line.startswith("phase "):
        print(f"phase={sess.set_phase(line.split(None, 1)[1].strip()).meta.get('phase')}")
        return
    if line.startswith("desks "):
        sub = line.split(None, 1)[1].strip()
        if sub == "open":
            st = sess.desks_open()
            print(f"tmux attach -t {st.tmux_session}")
        elif sub == "list":
            from thread_room.desks import list_desks

            print(list_desks(sess.store.meeting_dir))
        elif sub == "close":
            for ln in sess.desks_close():
                print(ln)
        else:
            print("desks open|list|close")
        return
    if line.startswith("promote "):
        parts = line.split(None, 3)
        if len(parts) < 4 or parts[1] != "from":
            print("usage: promote from SPEAKER text…")
            return
        msg = sess.promote(from_speaker=parts[2], text=parts[3])
        print(f"promoted {msg.id}")
        return
    if line.startswith("say "):
        print(f"ok mentions={sess.say(line[4:]).mentions}")
        return
    if line.startswith("@"):
        print(f"ok mentions={sess.say(line).mentions}")
        return
    # bare text → say
    print(f"ok mentions={sess.say(line).mentions}")


if __name__ == "__main__":
    main()

"""CLI entrypoint — new / open REPL / one-shot commands."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from thread_room import __version__
from thread_room.desks import DeskError
from thread_room.ownership import parse_assign_specs
from thread_room.session import Session
from thread_room.store import StoreError, create_meeting


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help", "help"}:
        _print_help()
        return
    if argv[0] in {"-V", "--version", "version"}:
        print(f"thread-room {__version__}")
        return

    cmd = argv[0]
    rest = argv[1:]
    try:
        if cmd == "new":
            _cmd_new(rest)
        elif cmd == "open":
            _cmd_open(rest)
        elif cmd == "say":
            _cmd_say(rest)
        elif cmd == "pump":
            _cmd_pump(rest)
        elif cmd == "export":
            _cmd_export(rest)
        elif cmd == "close":
            _cmd_close(rest)
        elif cmd == "status":
            _cmd_status(rest)
        elif cmd == "ownership":
            _cmd_ownership(rest)
        elif cmd == "ratify":
            _cmd_ratify(rest)
        elif cmd == "phase":
            _cmd_phase(rest)
        elif cmd == "desks":
            _cmd_desks(rest)
        elif cmd == "promote":
            _cmd_promote(rest)
        elif cmd == "doctor":
            _cmd_doctor(rest)
        else:
            print(f"thread-room: unknown command {cmd!r}", file=sys.stderr)
            _print_help()
            sys.exit(2)
    except (StoreError, DeskError, FileNotFoundError, ValueError) as e:
        print(f"thread-room: error: {e}", file=sys.stderr)
        sys.exit(1)


def _print_help() -> None:
    print(
        f"""thread-room {__version__} — multi-agent meetings on the filesystem

Commands:
  new         --title TITLE [--cwd DIR] [--dir PARENT] [--id ID] [--agent id:adapter]
  open        [MEETING_DIR]          Interactive REPL (recommended single-writer)
  say         -d MEETING_DIR TEXT
  pump        -d MEETING_DIR [--once]
  ownership   -d MEETING_DIR --assign owner:path[,path…] [--assign …] [--note TEXT]
  ratify      -d MEETING_DIR [--id ASSIGNMENT_ID]
  phase       -d MEETING_DIR discuss|write
  desks       open|list|close|doctor -d MEETING_DIR
  promote     -d MEETING_DIR --from SPEAKER (--text T | --file F | --last-side [N])
  export      -d MEETING_DIR [-o FILE]
  close       -d MEETING_DIR   (also closes desks if open)
  status      -d MEETING_DIR
  doctor      -d MEETING_DIR

REPL:
  say | pump | ownership … | ratify | phase | desks open|list|close
  promote from SPEAKER text… | export | status | thread | close | quit

Ownership (P2): propose → ratify → phase write; audit is post-hoc only.
Desks (P3): tmux one window per agent; side chat not on floor until promote.
Adapters: mock | codex_cli
"""
    )


def _cmd_new(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="thread-room new")
    p.add_argument("--title", required=True)
    p.add_argument("--cwd", default=".")
    p.add_argument("--dir", default=".", help="parent directory for meeting folder")
    p.add_argument("--id", default=None, dest="room_id")
    p.add_argument(
        "--agent",
        action="append",
        default=[],
        help="agent as id[:adapter], default mock:mock",
    )
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
    path = create_meeting(
        Path(args.dir),
        title=args.title,
        cwd=args.cwd,
        room_id=args.room_id,
        agents=agents,
    )
    sess = Session.open(path)
    sess.system("Room opened.", meta={"event": "open"})
    print(path)


def _meeting_dir(argv: list[str]) -> tuple[Path, list[str]]:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-d", "--dir", dest="meeting")
    args, rest = p.parse_known_args(argv)
    if not args.meeting:
        raise ValueError("missing -d/--dir MEETING_DIR")
    return Path(args.meeting), rest


def _cmd_say(argv: list[str]) -> None:
    path, rest = _meeting_dir(argv)
    if not rest:
        raise ValueError("usage: thread-room say -d DIR TEXT")
    text = " ".join(rest)
    sess = Session.open(path)
    msg = sess.say(text)
    print(f"ok id={msg.id} mentions={msg.mentions}")


def _cmd_pump(argv: list[str]) -> None:
    path, rest = _meeting_dir(argv)
    once = "--once" in rest
    sess = Session.open(path)
    produced = sess.pump(once=once)
    for m in produced:
        print(f"{m.type}\t{m.speaker}\t{m.text[:200]}")


def _cmd_ownership(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="thread-room ownership")
    p.add_argument("-d", "--dir", required=True, dest="meeting")
    p.add_argument(
        "--assign",
        action="append",
        required=True,
        help="owner:path[,path…] (repeatable)",
    )
    p.add_argument("--note", default="")
    args = p.parse_args(argv)
    assignments = parse_assign_specs(args.assign)
    sess = Session.open(Path(args.meeting))
    msg = sess.propose_ownership(assignments, note=args.note)
    aid = msg.meta.get("assignment_id")
    print(f"ok ownership proposed assignment_id={aid}")


def _cmd_ratify(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="thread-room ratify")
    p.add_argument("-d", "--dir", required=True, dest="meeting")
    p.add_argument("--id", dest="assignment_id", default=None)
    args = p.parse_args(argv)
    sess = Session.open(Path(args.meeting))
    msg = sess.ratify_ownership(args.assignment_id)
    print(f"ok ratified assignment_id={msg.meta.get('assignment_id')}")


def _cmd_phase(argv: list[str]) -> None:
    path, rest = _meeting_dir(argv)
    if not rest or rest[0] not in ("discuss", "write"):
        raise ValueError("usage: thread-room phase -d DIR discuss|write")
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
    pth = sess.export(out)
    print(pth)


def _cmd_close(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    sess = Session.open(path)
    try:
        for line in sess.desks_close():
            print(line)
    except Exception as e:
        if type(e).__name__ != "DeskError":
            raise
        print(f"desks: {e}")
    if sess.store.closed:
        print("already closed")
        return
    sess.close()
    exp = sess.export()
    print(f"closed export={exp}")


def _cmd_desks(argv: list[str]) -> None:
    if not argv or argv[0] not in ("open", "list", "close", "doctor"):
        raise ValueError("usage: thread-room desks open|list|close|doctor -d DIR")
    sub = argv[0]
    path, _ = _meeting_dir(argv[1:])
    sess = Session.open(path)
    if sub == "open":
        state = sess.desks_open()
        print(f"ok tmux_session={state.tmux_session}")
        for d in state.desks:
            print(f"  desk {d.speaker} → {d.target}")
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
    p.add_argument("-d", "--dir", required=True, dest="meeting")
    p.add_argument("--from", required=True, dest="from_speaker")
    p.add_argument("--text", default=None)
    p.add_argument("--file", default=None, dest="file_path")
    p.add_argument(
        "--last-side",
        nargs="?",
        const=1,
        type=int,
        default=None,
        help="promote last N lines from desks/<id>/side-thread.jsonl",
    )
    args = p.parse_args(argv)
    text: str
    if args.text is not None:
        text = args.text
    elif args.file_path:
        text = Path(args.file_path).read_text(encoding="utf-8")
    elif args.last_side is not None:
        from thread_room.desks import read_last_side

        text = read_last_side(Path(args.meeting), args.from_speaker, n=args.last_side)
    else:
        raise ValueError("promote requires --text, --file, or --last-side")
    sess = Session.open(Path(args.meeting))
    msg = sess.promote(from_speaker=args.from_speaker, text=text)
    print(f"ok promote id={msg.id} from={args.from_speaker}")


def _cmd_doctor(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    from thread_room.desks import doctor

    print("\n".join(doctor(path)))


def _cmd_status(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    sess = Session.open(path)
    print(sess.status_text())
    print(f"path={path.resolve()}")


def _cmd_open(argv: list[str]) -> None:
    meeting = Path(argv[0]) if argv else Path(".")
    if not (meeting / "room.yaml").is_file():
        raise FileNotFoundError(f"not a meeting dir (no room.yaml): {meeting}")
    sess = Session.open(meeting)
    print(f"thread-room open: {meeting.resolve()}")
    print(sess.status_text())
    print("Type 'help' for commands.")
    while True:
        try:
            line = input("room> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        try:
            _repl_line(sess, line)
        except (StoreError, ValueError, KeyError) as e:
            print(f"error: {e}")
        if sess.store.closed:
            print("room closed; exiting REPL")
            break


def _repl_line(sess: Session, line: str) -> None:
    if line in {"help", "?"}:
        print(
            "say | pump | ownership owner:paths … | ratify | phase discuss|write | "
            "desks open|list|close | promote from SPEAKER text… | "
            "export | status | thread | close | quit"
        )
        return
    if line in {"quit", "exit", "q"}:
        raise SystemExit(0)
    if line == "status":
        print(sess.status_text())
        return
    if line == "thread":
        from thread_room.render import render_floor_chat

        print(render_floor_chat(sess.store.messages) or "(empty)")
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
        p = sess.export(out)
        print(f"wrote {p}")
        return
    if line == "close":
        sess.close()
        p = sess.export()
        print(f"closed; export {p}")
        return
    if line.startswith("ownership "):
        specs = line.split()[1:]
        assignments = parse_assign_specs(specs)
        msg = sess.propose_ownership(assignments)
        print(f"proposed assignment_id={msg.meta.get('assignment_id')}")
        return
    if line == "ratify" or line.startswith("ratify "):
        parts = line.split()
        aid = parts[1] if len(parts) > 1 else None
        msg = sess.ratify_ownership(aid)
        print(f"ratified {msg.meta.get('assignment_id')}")
        return
    if line.startswith("phase "):
        ph = line.split(None, 1)[1].strip()
        msg = sess.set_phase(ph)
        print(f"phase={msg.meta.get('phase')}")
        return
    if line.startswith("desks "):
        sub = line.split(None, 1)[1].strip()
        if sub == "open":
            st = sess.desks_open()
            print(f"tmux={st.tmux_session} attach: tmux attach -t {st.tmux_session}")
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
        # promote from SPEAKER text…
        parts = line.split(None, 3)
        if len(parts) < 4 or parts[1] != "from":
            print("usage: promote from SPEAKER text…")
            return
        msg = sess.promote(from_speaker=parts[2], text=parts[3])
        print(f"promoted id={msg.id}")
        return
    if line.startswith("say "):
        msg = sess.say(line[4:])
        print(f"ok mentions={msg.mentions}")
        return
    if line.startswith("@"):
        msg = sess.say(line)
        print(f"ok mentions={msg.mentions}")
        return
    print("unknown command; try 'help'")


if __name__ == "__main__":
    main()

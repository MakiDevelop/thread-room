"""CLI entrypoint — P0: new / open REPL / one-shot commands."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from thread_room import __version__
from thread_room.models import make_message
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
        else:
            print(f"thread-room: unknown command {cmd!r}", file=sys.stderr)
            _print_help()
            sys.exit(2)
    except (StoreError, FileNotFoundError, ValueError) as e:
        print(f"thread-room: error: {e}", file=sys.stderr)
        sys.exit(1)


def _print_help() -> None:
    print(
        f"""thread-room {__version__} — multi-agent meetings on the filesystem

Commands:
  new    --title TITLE [--cwd DIR] [--dir PARENT] [--id ID]
  open   [MEETING_DIR]          Interactive REPL (recommended single-writer)
  say    -d MEETING_DIR TEXT    Append human utterance (and queue @mentions)
  pump   -d MEETING_DIR [--once]
  export -d MEETING_DIR [-o FILE]
  close  -d MEETING_DIR
  status -d MEETING_DIR

REPL (inside open):
  say <text> | pump | pump once | export | status | thread | close | help | quit

Notes:
  - Floor SSOT is thread.jsonl; agent traces under desks/<id>/traces/
  - Missing conclusion → system event on floor (fail closed)
  - P0 adapters: mock only
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
    """Parse -d/--dir MEETING and return (path, remaining)."""
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
        print(f"{m.type}\t{m.speaker}\t{m.text[:120]}")


def _cmd_export(argv: list[str]) -> None:
    path, rest = _meeting_dir(argv)
    out = None
    if "-o" in rest:
        i = rest.index("-o")
        out = Path(rest[i + 1])
    sess = Session.open(path)
    p = sess.export(out)
    print(p)


def _cmd_close(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    sess = Session.open(path)
    if sess.store.closed:
        print("already closed")
        return
    sess.close()
    exp = sess.export()
    print(f"closed export={exp}")


def _cmd_status(argv: list[str]) -> None:
    path, _ = _meeting_dir(argv)
    sess = Session.open(path)
    print(sess.status_text())
    print(f"path={path.resolve()}")


def _cmd_open(argv: list[str]) -> None:
    meeting = Path(argv[0]) if argv else Path(".")
    if not (meeting / "room.yaml").is_file():
        # allow opening parent if only one meeting? require explicit
        raise FileNotFoundError(f"not a meeting dir (no room.yaml): {meeting}")
    sess = Session.open(meeting)
    print(f"thread-room open: {meeting.resolve()}")
    print(sess.status_text())
    print("Type 'help' for commands. Single-writer REPL — avoid concurrent CLI say/pump.")
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
            "say <text> | pump | pump once | export [path] | status | thread | "
            "close | quit"
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
        once = line.strip() == "pump once" or line.endswith(" --once")
        produced = sess.pump(once=once)
        if not produced:
            print("(no pending)")
        for m in produced:
            print(f"[{m.speaker}] {m.text}")
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
    if line.startswith("say "):
        text = line[4:]
        msg = sess.say(text)
        print(f"ok mentions={msg.mentions}")
        return
    if line.startswith("@"):
        # shorthand: treat as say
        msg = sess.say(line)
        print(f"ok mentions={msg.mentions}")
        return
    print("unknown command; try 'help'")


if __name__ == "__main__":
    main()

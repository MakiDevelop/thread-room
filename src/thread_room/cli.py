"""CLI entrypoint — P0 scaffold (implementation pending)."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(
            """thread-room — multi-agent meetings on the filesystem

Usage (planned):
  thread-room new --title TITLE --cwd DIR
  thread-room open [DIR]     # interactive REPL (single writer)
  thread-room export [-o FILE]
  thread-room --version

Status: scaffold only — P0 not implemented yet.
See README.md and docs/TRP.md.
"""
        )
        return
    if args[0] in {"-V", "--version", "version"}:
        from thread_room import __version__

        print(f"thread-room {__version__}")
        return
    print(
        f"thread-room: command {args[0]!r} not implemented yet (scaffold 0.0.1).",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

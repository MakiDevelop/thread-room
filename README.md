# Thread Room

**Multi-agent + human meetings on the filesystem.**  
One folder, one `thread.jsonl` (like a LINE group chat), pluggable CLI agents.

> **Status:** P0 working (`0.1.0`) — mock agent, REPL, export. Real CLI adapters next.

## Install

```bash
cd thread-room
python3 -m pip install -e ".[dev]"
thread-room --version
```

## Quick start

```bash
# create a meeting (prints path)
thread-room new --title "Demo" --cwd . --dir ./meetings --id demo-1

# one-shot flow
thread-room say -d ./meetings/demo-1 "Hello @mock — introduce yourself"
thread-room pump -d ./meetings/demo-1
thread-room export -d ./meetings/demo-1
thread-room close -d ./meetings/demo-1

# or interactive single-writer REPL (recommended)
thread-room open ./meetings/demo-1
# room> say Hello @mock
# room> pump
# room> thread
# room> export
# room> close
```

## Layout

```text
meeting-dir/
  room.yaml
  thread.jsonl          # public floor (SSOT)
  export.md
  desks/<agent>/traces/ # full prompt+stdout (private; gitignored pattern)
```

## P0 behavior (council-reviewed)

| Feature | Behavior |
|---------|----------|
| Human UI | CLI |
| Speak | `@mention` queues agent turns |
| Floor output | **conclusion only** (JSON `{"conclusion":…}` or `:::conclusion`) |
| Parse failure | **fail closed** → `system` event on floor (no last-N fallback) |
| Writer | Prefer **one** `open` REPL; one-shot cmds also ok if not concurrent |
| Adapters | `mock` only |
| Write gate | named `ownership_audit` in config; hard enforce not in P0 |

## Protocol

See [docs/TRP.md](docs/TRP.md). Room transcripts are **lossy by design** — not a RED/compliance audit log.

## Roadmap

| Phase | Scope |
|-------|--------|
| **P0** | ✅ mock, store, pump, export, fail-visible |
| **P1** | Codex adapter (read-only discuss), real conclusion contract |
| **P2** | ownership audit |
| **P3** | tmux desks + promote |
| **P4** | polish / PyPI |

## License

MIT — see [LICENSE](LICENSE).

# Thread Room

**Multi-agent + human meetings on the filesystem.**  
One folder, one `thread.jsonl` (like a LINE group chat), pluggable CLI agents, optional tmux desks.

[![CI](https://github.com/MakiDevelop/thread-room/actions/workflows/ci.yml/badge.svg)](https://github.com/MakiDevelop/thread-room/actions/workflows/ci.yml)

> **Status:** **0.5.0** (P0–P4) — usable beta. Protocol: [TRP](docs/TRP.md).

## Install

```bash
# from source (recommended while pre-PyPI / latest main)
git clone https://github.com/MakiDevelop/thread-room.git
cd thread-room
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
thread-room --version

# after PyPI publish:
# pip install thread-room
```

## Quick start

```bash
thread-room new --title "Demo" --cwd . --dir ./meetings --id demo-1
thread-room say -d ./meetings/demo-1 "Hello @mock — introduce yourself"
thread-room pump -d ./meetings/demo-1
thread-room validate -d ./meetings/demo-1
thread-room export -d ./meetings/demo-1
thread-room close -d ./meetings/demo-1
```

Interactive single-writer REPL:

```bash
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
  thread.jsonl              # public floor (SSOT)
  export.md
  desks/<agent>/traces/     # private full I/O (gitignored pattern)
  desks/<agent>/side-thread.jsonl   # optional desk log
  .runtime/terminals.json   # tmux desk map
```

## Features

| Area | Behavior |
|------|----------|
| Human UI | **CLI** (+ optional tmux desks) |
| Speak | `@mention` queues agent turns (`mention_only`) |
| Floor | **conclusion only** — JSON `{"conclusion":…}` or `:::conclusion` |
| Parse fail | **fail closed** → `system` on floor (no last-N fallback) |
| Adapters | `mock`, `codex` / `codex_cli` |
| Codex sandbox | discuss → `read-only`; write → `workspace-write` |
| Ownership | propose → ratify → `phase write`; **audit** is post-hoc only |
| Desks | tmux one window per agent; promote to floor explicitly |
| Validate | `thread-room validate -d DIR` |

### Ownership

```bash
thread-room ownership -d ./meetings/c1 \
  --assign 'codex:src/foo.py,tests/' \
  --assign 'claude:docs/'
thread-room ratify -d ./meetings/c1
thread-room phase -d ./meetings/c1 write
```

### Desks (needs `tmux`)

```bash
thread-room desks open -d ./meetings/c1
tmux attach -t tr-c1
thread-room promote -d ./meetings/c1 --from codex --text "Ship option A"
thread-room desks close -d ./meetings/c1
```

### Codex agent

```bash
thread-room new --title "Codex meet" --cwd . --dir ./meetings --id c1 \
  --agent codex:codex_cli
thread-room say -d ./meetings/c1 "@codex Summarize ownership_audit in one sentence."
thread-room pump -d ./meetings/c1   # may take a while
```

Env: `THREAD_ROOM_CODEX_BIN`, `THREAD_ROOM_CODEX_TIMEOUT` (default 900s).

## Protocol (TRP)

See **[docs/TRP.md](docs/TRP.md)**.

Room transcripts are **lossy by design** (conclusions on floor; traces/side-chat on desks).  
**Do not use as a compliance or RED audit log.**

## Roadmap

| Phase | Status |
|-------|--------|
| P0 store / mock / export | ✅ |
| P1 Codex adapter | ✅ |
| P2 ownership audit | ✅ |
| P3 desks + promote | ✅ |
| P4 polish / packaging / CI | ✅ |

## Development

```bash
pip install -e ".[dev]"
pytest -q
# optional: ruff check src tests
python -m build && twine check dist/*
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/PUBLISHING.md](docs/PUBLISHING.md).

## License

MIT — [LICENSE](LICENSE).

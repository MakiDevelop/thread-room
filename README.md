# Thread Room

**Multi-agent + human meetings on the filesystem.**  
One folder, one `thread.jsonl` (like a LINE group chat), pluggable CLI agents.

> **Status:** P1 (`0.2.0`) — mock + **Codex** adapter (`read-only` in discuss).

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

## Behavior (council-reviewed)

| Feature | Behavior |
|---------|----------|
| Human UI | CLI |
| Speak | `@mention` queues agent turns |
| Floor output | **conclusion only** (JSON `{"conclusion":…}` or `:::conclusion`) |
| Parse failure | **fail closed** → `system` event on floor (no last-N fallback) |
| Writer | Prefer **one** `open` REPL; one-shot cmds also ok if not concurrent |
| Adapters | `mock`, **`codex` / `codex_cli`** |
| Codex sandbox | `discuss` → `--sandbox read-only`; `write` → `workspace-write` |
| Write gate | `ownership_audit` named only; hard enforce not yet |

### Codex meeting example

```bash
# requires `codex` on PATH (or THREAD_ROOM_CODEX_BIN)
thread-room new --title "Codex meet" --cwd . --dir ./meetings --id c1 \
  --agent mock:mock --agent codex:codex_cli

thread-room say -d ./meetings/c1 "@codex In one sentence: what is ownership_audit?"
thread-room pump -d ./meetings/c1
thread-room export -d ./meetings/c1
```

**Governance note (Maki lab):** if you use Claude Code hooks that only allow `council-dispatch` to spawn Codex, you must allowlist `thread-room` or run pump outside that hook — see council C1 decision.

## Protocol

See [docs/TRP.md](docs/TRP.md). Room transcripts are **lossy by design** — not a RED/compliance audit log.

## Roadmap

| Phase | Scope |
|-------|--------|
| **P0** | ✅ mock, store, pump, export, fail-visible |
| **P1** | ✅ Codex adapter (`read-only` discuss, schema + last-message) |
| **P2** | ownership audit |
| **P3** | tmux desks + promote |
| **P4** | polish / PyPI |

## License

MIT — see [LICENSE](LICENSE).

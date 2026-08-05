# Thread Room

**Multi-agent + human meetings on the filesystem.**  
One folder, one `thread.jsonl` (like a LINE group chat), pluggable CLI agents, optional per-agent terminal desks.

> Status: **early scaffold** — public repo for design & implementation.  
> Protocol draft: [docs/TRP.md](docs/TRP.md)  
> Design origin: Maki lab council session `2026-08-05-thread-room-design-review`

## What it is

| Surface | Role |
|---------|------|
| **Floor** | Public `thread.jsonl` — shared meeting timeline |
| **Desk** | Optional per-agent terminal — side chat & full traces stay here |
| **Host** | CLI (`thread-room`) — human runs the meeting |

**Defaults (Chair preferences):**

- Human UI: **CLI**
- Speak policy: **mention_only**
- Floor output: **conclusion only** (reasoning stays on desk)
- Write code: **agree ownership first**, then edit disjoint paths (no file locks)
- No always-on daemon

## Not File-I/O RFP

Classic multi-CLI “briefing → answer files” is a **batch tender**.  
Thread Room is a **round-table + side desks** with a durable chat log.

## Quick mental model

```text
meeting-2026-08-05-foo/
  room.yaml          # who is in the room, policy
  thread.jsonl       # public SSOT (group chat)
  desks/<agent>/     # traces / optional side-thread
  export.md          # human-readable export
```

## Install (planned)

```bash
# not published yet — local editable install once package exists
pip install -e .
thread-room --help
```

## Roadmap (from design review)

| Phase | Scope |
|-------|--------|
| **P0** | REPL host, mock agent, jsonl store, export, fail-visible |
| **P1** | Real adapter (Codex first), conclusion contract |
| **P2** | Ownership audit (honest name; hard enforce later) |
| **P3** | `desks open` (tmux), promote |
| **P4** | Spec freeze, docs polish |

## Related

- Does **not** replace offline council File I/O for RED/ratify audit trails.
- Room transcripts are **lossy by design** (conclusions on floor; traces on desks). Do not use as a compliance log.

## License

[MIT](LICENSE) — see LICENSE file.

## Contributing

Issues and design notes welcome once P0 lands. Breaking changes expected before `0.1.0`.

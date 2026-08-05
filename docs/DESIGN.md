# Design overview

Thread Room is a **host** for multi-agent + human meetings using filesystem SSOT.

## Surfaces

| Surface | Role |
|---------|------|
| **Floor** | `thread.jsonl` — public timeline |
| **Desk** | Optional tmux interactive pane per agent |
| **Host** | `thread-room` CLI |

## Phases delivered

| Phase | Deliverable |
|-------|-------------|
| P0 | store, mock pump, export, REPL |
| P1 | Codex adapter, structured conclusion |
| P2 | ownership propose/ratify/phase, audit |
| P3 | desks, promote, doctor |
| P4 | validate, CI, packaging docs |

## Non-goals (still)

- Always-on daemon / auto router
- Shared model KV cache across vendors
- Hard write enforcement by default (`ownership_enforced` reserved)
- Using floor transcript as RED compliance evidence

## Historical design notes

Longer design drafts may live outside this repo (agent-council session).  
Stable contracts for implementers: [TRP.md](./TRP.md), this file, and the CLI `--help`.

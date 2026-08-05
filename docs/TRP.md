# Thread Room Protocol (TRP) v0.1 — Draft

> **Status:** draft for implementers. Semantic contract only.  
> Adapter CLI matrices, tmux, and host enforcement mechanisms are **not** part of the protocol — they belong in host config.

## Principles

1. **Thread is SSOT** for the public meeting timeline (`thread.jsonl`).
2. **Append-only** — corrections are new events, not rewrites.
3. **Speakers are pluggable** — humans and agents share the same message envelope.
4. **Floor ≠ Desk** — public floor vs private desk side-chat / traces.
5. **Lossy by design** — hosts may put only conclusions on the floor; full reasoning may stay on desks.  
   **Do not use a Room transcript as a compliance or RED audit log.**

## Room directory

```text
meeting-<id>/
  room.yaml
  thread.jsonl
  export.md          # optional host export
  desks/<speaker>/   # optional private surfaces
  .runtime/          # host cache (not protocol SSOT)
```

## Message envelope (`thread.jsonl` — one JSON object per line)

Required fields:

| Field | Type | Notes |
|-------|------|--------|
| `trp` | string | Protocol version, e.g. `"0.1"` |
| `id` | string | Unique id (ULID/UUID recommended) |
| `ts` | string | ISO-8601 timestamp |
| `room_id` | string | Matches room id |
| `speaker` | string | Speaker id |
| `kind` | string | `human` \| `agent` \| `system` |
| `type` | string | See types below |
| `text` | string | Body (may be empty if attachments-only later) |

Optional: `mentions` (string[]), `reply_to`, `attachments`, `visibility` (`floor`\|`desk`\|`promoted`), `meta` (object).

### Types (v0)

| type | Purpose |
|------|---------|
| `utterance` | Normal speech / public conclusion |
| `system` | Room open/close, errors, gate notices — **failures must be visible** |
| `ownership` | Path assignment proposals / status |
| `decision` | Human ratify |
| `dissent` | Explicit disagreement |
| `summary` | Compression (reserved) |
| `tool_note` | Short tool note |
| `correction` | Supersede meaning without deleting history |
| `promote` | Desk content brought to floor (or meta on utterance) |

## Speak policies (host)

Recommended default: **`mention_only`** (only @'d agents run).  
`round_robin` / `free` are out of v0 host scope for router risk.

## Floor output

Recommended default: **`conclusion_only`** — public messages carry conclusions; private traces stay on desks.  
Missing/invalid conclusion → **fail closed** (system event, no fake utterance). Hosts must not fallback to “last N characters of stdout”.

## Ownership

Meetings that write code should **ratify disjoint path sets** before writes.  
Protocol defines the `ownership` / `decision` event shapes; enforcement is host-specific:

- `ownership_audit` — detect after the fact  
- `ownership_enforced` — host applies only validated patches / rollbacks  

Overlapping ratified paths for the same path are an error.

## What is NOT in TRP

- Concrete `claude` / `codex` / `gemini` argv matrices (they rot)
- How desks are opened (tmux, Terminal.app, …)
- Network RPC (optional future A2A bridging is out of band)

## Versioning

Breaking envelope changes bump `trp` minor or major per semver discussion in host releases.

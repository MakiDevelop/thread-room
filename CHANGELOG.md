# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] — 2026-08-05

### Added

- Bare `thread-room` interactive wizard: title + agent picker + optional desks
- `install.sh` → `~/.local/bin/thread-room` and alias `thr` (not `tr`)
- Current-meeting pointer (no `-d` for everyday commands)
- Shortcuts: `go`, `end`, `attach`, `use`, `current`

## [0.5.0] — 2026-08-05

### Added

- `thread-room validate -d DIR` — room.yaml + thread.jsonl + ownership checks
- GitHub Actions CI (pytest on Python 3.12)
- `CHANGELOG.md`, `CONTRIBUTING.md`, `docs/PUBLISHING.md`
- `py.typed` marker for type checkers
- Packaging polish for src layout + package data (`conclusion.schema.json`)

### Changed

- README reorganized for install / quick start / full feature map
- TRP status clarified as implementable v0.1 (lossy-by-design warning retained)

## [0.4.0] — 2026-08-05

### Added

- P3: tmux desks (`desks open|list|close`), `promote`, `doctor`
- `.runtime/terminals.json`; optional `side-thread.jsonl`

## [0.3.0] — 2026-08-05

### Added

- P2: `ownership` propose, `ratify`, `phase discuss|write`
- `ownership_audit` post-hoc violations on floor (not hard deny)

## [0.2.0] — 2026-08-05

### Added

- P1: Codex adapter (`codex_cli`) with discuss `read-only` sandbox
- Conclusion JSON schema + `--output-last-message` integration

## [0.1.0] — 2026-08-05

### Added

- P0: `new` / `say` / `pump` / `export` / `close` / REPL `open`
- Mock adapter, strict conclusion parse (fail closed)
- Append-only `thread.jsonl` store

## [0.0.1] — 2026-08-05

### Added

- Public repo scaffold, TRP draft, MIT license

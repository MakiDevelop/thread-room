# Thread Room

**Multi-agent + human meetings on the filesystem.**  
Type `thread-room` → pick agents → start. Optional tmux desks.

[![CI](https://github.com/MakiDevelop/thread-room/actions/workflows/ci.yml/badge.svg)](https://github.com/MakiDevelop/thread-room/actions/workflows/ci.yml)

## Install (one shot)

```bash
# from a clone
git clone https://github.com/MakiDevelop/thread-room.git
cd thread-room
./install.sh

# or remote
curl -fsSL https://raw.githubusercontent.com/MakiDevelop/thread-room/main/install.sh | bash
```

Adds `thread-room` and short alias **`thr`** to `~/.local/bin`  
(ensure `export PATH="$HOME/.local/bin:$PATH"`).

> Do **not** use alias name `tr` — that shadows the system `/usr/bin/tr` tool.

## Use

```bash
thread-room
```

Then:

1. **Title**
2. **Working directory** (repo path)
3. **Pick agents** by number or name:

```text
  1) Mock      offline test
  2) Codex     OpenAI Codex CLI
  3) Claude    Claude Code
  4) Gemini    Gemini CLI
  5) Grok      placeholder desk
```

Example selection: `2 3` or `codex,claude`

4. **Open tmux desks?** `Y` / `n`
5. Drop into the meeting REPL (`room>`)

### Everyday after start

No `cd`, no `.venv`, no `-d` (uses **current** meeting):

```bash
thr say "Hello @codex …"
thr pump
thr attach                 # tmux → agent desks
thr promote --from codex --text "結論：採用 A"
thr end                    # close desks + export + close
```

### Non-interactive

```bash
thr go "Sprint review" --agents 2,3
thr go "Quick" --agents mock --no-desks
```

## Layout

```text
~/thread-room-meetings/<id>/
  room.yaml
  thread.jsonl
  desks/…
```

Current meeting pointer: `~/.config/thread-room/current_meeting`

## Docs

- Protocol: [docs/TRP.md](docs/TRP.md)
- Publish: [docs/PUBLISHING.md](docs/PUBLISHING.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)

## License

MIT

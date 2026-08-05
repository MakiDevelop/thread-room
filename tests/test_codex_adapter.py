"""Codex adapter unit tests — subprocess mocked (no live Codex required)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from thread_room.adapters.base import TurnContext
from thread_room.adapters.codex import CodexAdapter, _normalize_last_message
from thread_room.adapters.registry import get_adapter
from thread_room.parser import parse_agent_output


def _ctx(tmp_path: Path, phase: str = "discuss") -> TurnContext:
    work = tmp_path / "traces"
    work.mkdir()
    return TurnContext(
        speaker_id="codex",
        display_name="Codex",
        prompt="hello",
        cwd=tmp_path,
        room_id="r1",
        phase=phase,
        max_floor_chars=4000,
        timeout_sec=30,
        work_dir=work,
    )


def test_registry_codex():
    a = get_adapter("codex")
    assert a.name == "codex_cli"
    assert get_adapter("codex_cli").name == "codex_cli"


def test_normalize_json_last_message():
    raw = json.dumps({"conclusion": "ok", "mentions": [], "files_claimed": []})
    out = _normalize_last_message(raw)
    p = parse_agent_output(out, max_chars=100)
    assert p.conclusion == "ok"


def test_normalize_plain_last_message():
    out = _normalize_last_message("plain answer")
    p = parse_agent_output(out, max_chars=100)
    assert p.conclusion == "plain answer"


def test_codex_uses_read_only_in_discuss(tmp_path: Path):
    adapter = CodexAdapter(binary="codex", timeout_sec=30)
    ctx = _ctx(tmp_path, phase="discuss")
    last = ctx.work_dir / "codex-last-codex.txt"
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = ""
    fake.stderr = ""

    def run_side_effect(cmd, **kwargs):
        # write last message as codex would
        last.write_text(
            json.dumps({"conclusion": "from codex", "mentions": [], "files_claimed": []}),
            encoding="utf-8",
        )
        assert cmd[0] == "codex" or cmd[0].endswith("codex")
        assert "exec" in cmd
        assert "--sandbox" in cmd
        i = cmd.index("--sandbox")
        assert cmd[i + 1] == "read-only"
        assert "-" in cmd  # stdin prompt
        assert kwargs.get("input") == "hello"
        return fake

    with patch("thread_room.adapters.codex.subprocess.run", side_effect=run_side_effect):
        with patch("thread_room.adapters.codex.shutil.which", return_value="codex"):
            result = adapter.run(ctx)

    assert result.exit_code == 0
    parsed = parse_agent_output(result.stdout, max_chars=4000)
    assert parsed.conclusion == "from codex"


def test_codex_uses_workspace_write_in_write_phase(tmp_path: Path):
    adapter = CodexAdapter(binary="codex", timeout_sec=30)
    ctx = _ctx(tmp_path, phase="write")
    last = ctx.work_dir / "codex-last-codex.txt"
    fake = MagicMock(returncode=0, stdout="", stderr="")

    def run_side_effect(cmd, **kwargs):
        last.write_text(
            json.dumps({"conclusion": "wrote", "mentions": [], "files_claimed": ["a.py"]}),
            encoding="utf-8",
        )
        i = cmd.index("--sandbox")
        assert cmd[i + 1] == "workspace-write"
        return fake

    with patch("thread_room.adapters.codex.subprocess.run", side_effect=run_side_effect):
        with patch("thread_room.adapters.codex.shutil.which", return_value="codex"):
            result = adapter.run(ctx)
    assert "wrote" in result.stdout


def test_codex_timeout(tmp_path: Path):
    import subprocess as sp

    adapter = CodexAdapter(binary="codex", timeout_sec=1)
    ctx = _ctx(tmp_path)

    with patch(
        "thread_room.adapters.codex.subprocess.run",
        side_effect=sp.TimeoutExpired(cmd=["codex"], timeout=1),
    ):
        with patch("thread_room.adapters.codex.shutil.which", return_value="codex"):
            result = adapter.run(ctx)
    assert result.exit_code == 124
    assert "timeout" in result.stderr.lower()


def test_codex_missing_binary(tmp_path: Path):
    adapter = CodexAdapter(binary="codex-not-installed-xyz", timeout_sec=5)
    ctx = _ctx(tmp_path)
    with patch("thread_room.adapters.codex.shutil.which", return_value=None):
        with patch(
            "thread_room.adapters.codex.subprocess.run",
            side_effect=FileNotFoundError(),
        ):
            result = adapter.run(ctx)
    assert result.exit_code == 127

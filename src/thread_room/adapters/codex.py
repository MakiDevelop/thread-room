"""Codex CLI adapter (P1).

Uses argv-only subprocess (no shell). Aligns with council-dispatch lessons:
- prompt via stdin when using '-'
- sandbox: read-only in discuss, workspace-write in write
- --output-schema + --output-last-message for structured conclusion
- timeout default 900s
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from thread_room.adapters.base import AdapterResult, TurnContext

# Package data first; repo schemas/ for docs; else inline
_PKG_SCHEMA = Path(__file__).resolve().parent.parent / "data" / "conclusion.schema.json"
_REPO_SCHEMA = Path(__file__).resolve().parents[3] / "schemas" / "conclusion.schema.json"


class CodexAdapter:
    name = "codex_cli"

    def __init__(
        self,
        *,
        binary: str | None = None,
        timeout_sec: int = 900,
        sandbox_discuss: str = "read-only",
        sandbox_write: str = "workspace-write",
        schema_path: Path | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        self.binary = binary or os.environ.get("THREAD_ROOM_CODEX_BIN") or "codex"
        self.timeout_sec = int(
            os.environ.get("THREAD_ROOM_CODEX_TIMEOUT", str(timeout_sec))
        )
        self.sandbox_discuss = sandbox_discuss
        self.sandbox_write = sandbox_write
        if schema_path is not None:
            self.schema_path = schema_path
        elif _PKG_SCHEMA.is_file():
            self.schema_path = _PKG_SCHEMA
        elif _REPO_SCHEMA.is_file():
            self.schema_path = _REPO_SCHEMA
        else:
            self.schema_path = Path()  # trigger inline write
        self.extra_args = list(extra_args or [])

    def run(self, ctx: TurnContext) -> AdapterResult:
        t0 = time.perf_counter()
        bin_path = shutil.which(self.binary) or self.binary
        sandbox = (
            self.sandbox_discuss
            if ctx.phase in ("discuss", "plan", "")
            else self.sandbox_write
        )
        timeout = ctx.timeout_sec if ctx.timeout_sec > 0 else self.timeout_sec

        # Work dir for schema + last message (caller may pass work_dir via cwd parent)
        work = ctx.work_dir if ctx.work_dir is not None else ctx.cwd
        work.mkdir(parents=True, exist_ok=True)
        schema = self.schema_path
        if not schema.is_file():
            schema = work / "conclusion.schema.json"
            schema.write_text(_INLINE_SCHEMA, encoding="utf-8")
        last_msg = work / f"codex-last-{ctx.speaker_id}.txt"

        cmd: list[str] = [
            bin_path,
            "exec",
            "--sandbox",
            sandbox,
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "-C",
            str(ctx.cwd),
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(last_msg),
            *self.extra_args,
            "-",  # read prompt from stdin
        ]

        try:
            proc = subprocess.run(
                cmd,
                input=ctx.prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ctx.cwd),
                env=_filtered_env(),
                check=False,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            code = proc.returncode
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else f"timeout after {timeout}s"
            if not stderr:
                stderr = f"timeout after {timeout}s"
            code = 124
        except FileNotFoundError:
            return AdapterResult(
                stdout="",
                stderr=f"codex binary not found: {bin_path}",
                exit_code=127,
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )

        # Prefer last-message file as public payload source
        if last_msg.is_file():
            try:
                last = last_msg.read_text(encoding="utf-8").strip()
            except OSError:
                last = ""
            if last:
                # If last message is already JSON conclusion, use as stdout for parser
                # else wrap as conclusion JSON for fail-open-to-parse path
                stdout_for_parse = _normalize_last_message(last)
                # Keep raw streams in result for traces: combine
                combined = (
                    f"=== codex stdout ===\n{stdout}\n\n"
                    f"=== last message ===\n{last}\n"
                )
                ms = int((time.perf_counter() - t0) * 1000)
                return AdapterResult(
                    stdout=stdout_for_parse,
                    stderr=stderr + "\n" + combined if stderr else combined,
                    exit_code=code,
                    duration_ms=ms,
                )

        ms = int((time.perf_counter() - t0) * 1000)
        return AdapterResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=code,
            duration_ms=ms,
        )


def _normalize_last_message(last: str) -> str:
    """Ensure parser sees JSON with conclusion or marker block."""
    s = last.strip()
    if not s:
        return s
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "conclusion" in obj:
            return json.dumps(obj, ensure_ascii=False)
        if isinstance(obj, dict) and "message" in obj and isinstance(obj["message"], str):
            return json.dumps(
                {"conclusion": obj["message"], "mentions": [], "files_claimed": []},
                ensure_ascii=False,
            )
    except json.JSONDecodeError:
        pass
    # Plain text last message → wrap as conclusion (still structured)
    return json.dumps(
        {"conclusion": s, "mentions": [], "files_claimed": []},
        ensure_ascii=False,
    )


def _filtered_env() -> dict[str, str]:
    """Inherit env but drop empty noise; argv-only — no shell."""
    return {k: v for k, v in os.environ.items() if v is not None}


_INLINE_SCHEMA = """{
  "type": "object",
  "required": ["conclusion"],
  "additionalProperties": false,
  "properties": {
    "conclusion": {"type": "string", "minLength": 1},
    "mentions": {"type": "array", "items": {"type": "string"}},
    "files_claimed": {"type": "array", "items": {"type": "string"}}
  }
}
"""

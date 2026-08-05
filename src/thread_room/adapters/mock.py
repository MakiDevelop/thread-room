"""Mock adapter — deterministic, no network."""

from __future__ import annotations

import json
import time

from thread_room.adapters.base import AdapterResult, TurnContext


class MockAdapter:
    name = "mock"

    def run(self, ctx: TurnContext) -> AdapterResult:
        t0 = time.perf_counter()
        # Produce valid JSON conclusion (preferred contract)
        body = {
            "conclusion": (
                f"[mock:{ctx.speaker_id}] Acknowledged. "
                f"Public conclusion only — room={ctx.room_id}, phase={ctx.phase}."
            ),
            "mentions": [],
            "files_claimed": [],
        }
        # Also include marker form in "trace" for humans reading raw (not required)
        stdout = json.dumps(body, ensure_ascii=False)
        # Simulate reading prompt (length only)
        _ = len(ctx.prompt)
        ms = int((time.perf_counter() - t0) * 1000)
        return AdapterResult(stdout=stdout, stderr="", exit_code=0, duration_ms=ms)


class MockFailAdapter:
    """Always fails — for tests."""

    name = "mock_fail"

    def run(self, ctx: TurnContext) -> AdapterResult:
        return AdapterResult(
            stdout="thinking without conclusion markers…",
            stderr="mock failure",
            exit_code=0,
            duration_ms=1,
        )


# get_adapter lives in registry.py (P1+)

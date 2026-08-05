"""Parse agent public conclusion — fail closed, no last-N fallback."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


class ParseError(Exception):
    pass


@dataclass
class ParsedOutput:
    conclusion: str
    mentions: list[str]
    files_claimed: list[str]
    raw_format: str  # json | markers


_CONCLUSION_BLOCK = re.compile(
    r":::conclusion\s*\n(.*?)(?:\n:::|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_TRACE_BLOCK = re.compile(
    r":::trace\s*\n(.*?)(?:\n:::|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def parse_agent_output(stdout: str, *, max_chars: int) -> ParsedOutput:
    """Extract public conclusion from adapter stdout.

    Accepts either:
      1) A single JSON object with key \"conclusion\"
      2) Marker blocks :::conclusion ... :::

    Missing/invalid conclusion raises ParseError (fail closed).
    """
    text = (stdout or "").strip()
    if not text:
        raise ParseError("empty adapter stdout")

    # Try JSON (whole stdout or last JSON object line)
    parsed = _try_json(text)
    if parsed is not None:
        conclusion = parsed.conclusion.strip()
        if not conclusion:
            raise ParseError("JSON conclusion is empty")
        if len(conclusion) > max_chars:
            raise ParseError(
                f"conclusion exceeds max_floor_chars ({len(conclusion)} > {max_chars})"
            )
        return parsed

    m = _CONCLUSION_BLOCK.search(text)
    if not m:
        raise ParseError("no :::conclusion block and no JSON conclusion object")
    conclusion = m.group(1).strip()
    if not conclusion:
        raise ParseError("empty :::conclusion block")
    if len(conclusion) > max_chars:
        raise ParseError(
            f"conclusion exceeds max_floor_chars ({len(conclusion)} > {max_chars})"
        )
    return ParsedOutput(
        conclusion=conclusion,
        mentions=[],
        files_claimed=[],
        raw_format="markers",
    )


def _try_json(text: str) -> ParsedOutput | None:
    candidates = [text]
    # also try last non-empty line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        candidates.append(lines[-1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if "conclusion" not in obj:
            continue
        conclusion = obj.get("conclusion")
        if not isinstance(conclusion, str):
            raise ParseError("JSON conclusion must be a string")
        mentions = obj.get("mentions") or []
        files = obj.get("files_claimed") or obj.get("files") or []
        if not isinstance(mentions, list) or not all(isinstance(x, str) for x in mentions):
            raise ParseError("JSON mentions must be string array")
        if not isinstance(files, list) or not all(isinstance(x, str) for x in files):
            raise ParseError("JSON files_claimed must be string array")
        return ParsedOutput(
            conclusion=conclusion,
            mentions=list(mentions),
            files_claimed=list(files),
            raw_format="json",
        )
    return None

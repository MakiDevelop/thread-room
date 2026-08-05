"""Ownership projection + audit (P2).

Honest model:
- ownership_audit: detect after a turn; never claims to block writes
- ownership_enforced: reserved (not implemented in P2)

State is projected from floor events (ownership + decision), not room.yaml.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from thread_room.models import Message, new_id


@dataclass
class PathAssignment:
    paths: list[str]
    owner: str
    status: str = "proposed"  # proposed | accepted | ratified | done


@dataclass
class OwnershipBundle:
    assignment_id: str
    assignments: list[PathAssignment]
    consensus: str  # pending | ratified
    note: str = ""
    message_id: str | None = None


@dataclass
class OwnershipState:
    """Latest ratified map + all bundles."""

    bundles: list[OwnershipBundle] = field(default_factory=list)
    # path_or_prefix -> owner (only ratified)
    ratified_map: dict[str, str] = field(default_factory=dict)
    phase: str = "discuss"  # projected from decision/system events + initial

    def owner_for(self, path: str) -> str | None:
        return match_owner(self.ratified_map, path)

    def paths_for(self, owner: str) -> list[str]:
        return sorted(p for p, o in self.ratified_map.items() if o == owner)


def match_owner(ratified_map: dict[str, str], path: str) -> str | None:
    """Longest-prefix match. Paths normalized with forward slashes."""
    p = _norm(path)
    best: str | None = None
    best_len = -1
    for prefix, owner in ratified_map.items():
        pref = _norm(prefix)
        if p == pref or p.startswith(pref.rstrip("/") + "/") or (
            pref.endswith("/") and p.startswith(pref)
        ):
            if len(pref) > best_len:
                best = owner
                best_len = len(pref)
        # also: assignment is a file equal
        if pref == p:
            return owner
    return best


def _norm(path: str) -> str:
    p = path.strip().replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def find_overlaps(assignments: list[PathAssignment]) -> list[str]:
    """Return human-readable overlap errors among proposed/ratified sets."""
    # Expand pairwise: if two prefixes can both match same conceptual path
    errors: list[str] = []
    items: list[tuple[str, str]] = []
    for a in assignments:
        for path in a.paths:
            items.append((_norm(path), a.owner))
    for i, (p1, o1) in enumerate(items):
        for p2, o2 in items[i + 1 :]:
            if o1 == o2:
                continue
            if _paths_overlap(p1, p2):
                errors.append(f"{p1!r} ({o1}) overlaps {p2!r} ({o2})")
    return errors


def _paths_overlap(a: str, b: str) -> bool:
    if a == b:
        return True
    a_dir = a if a.endswith("/") else a + "/"
    b_dir = b if b.endswith("/") else b + "/"
    return a.startswith(b_dir) or b.startswith(a_dir) or a == b or b == a


def project_state(messages: list[Message], *, initial_phase: str = "discuss") -> OwnershipState:
    state = OwnershipState(phase=initial_phase)
    for msg in messages:
        if msg.type == "ownership":
            bundle = bundle_from_message(msg)
            if bundle:
                state.bundles.append(bundle)
                if bundle.consensus == "ratified":
                    _apply_ratified(state, bundle)
        elif msg.type == "decision":
            meta = msg.meta or {}
            if meta.get("event") == "ratify_ownership":
                aid = meta.get("assignment_id")
                for b in reversed(state.bundles):
                    if aid is None or b.assignment_id == aid:
                        b.consensus = "ratified"
                        for a in b.assignments:
                            a.status = "ratified"
                        _apply_ratified(state, b)
                        break
            if meta.get("event") == "phase":
                ph = str(meta.get("phase", ""))
                if ph in ("discuss", "write", "closed"):
                    state.phase = ph
        elif msg.type == "system" and msg.meta.get("event") == "phase":
            ph = str(msg.meta.get("phase", ""))
            if ph in ("discuss", "write", "closed"):
                state.phase = ph
        elif msg.type == "system" and msg.meta.get("event") == "close":
            state.phase = "closed"
    return state


def _apply_ratified(state: OwnershipState, bundle: OwnershipBundle) -> None:
    for a in bundle.assignments:
        for path in a.paths:
            state.ratified_map[_norm(path)] = a.owner


def bundle_from_message(msg: Message) -> OwnershipBundle | None:
    meta = msg.meta or {}
    raw = meta.get("assignments")
    if not isinstance(raw, list):
        return None
    assignments: list[PathAssignment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        paths = item.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        owner = str(item.get("owner", ""))
        if not owner or not paths:
            continue
        assignments.append(
            PathAssignment(
                paths=[str(p) for p in paths],
                owner=owner,
                status=str(item.get("status", meta.get("consensus", "proposed"))),
            )
        )
    if not assignments:
        return None
    return OwnershipBundle(
        assignment_id=str(meta.get("assignment_id") or msg.id),
        assignments=assignments,
        consensus=str(meta.get("consensus", "pending")),
        note=str(meta.get("note", "")),
        message_id=msg.id,
    )


def build_ownership_meta(
    assignments: list[PathAssignment],
    *,
    consensus: str = "pending",
    note: str = "",
    assignment_id: str | None = None,
) -> dict[str, Any]:
    aid = assignment_id or new_id()
    return {
        "assignment_id": aid,
        "consensus": consensus,
        "note": note,
        "assignments": [
            {
                "paths": list(a.paths),
                "owner": a.owner,
                "status": a.status if consensus != "ratified" else "ratified",
            }
            for a in assignments
        ],
    }


def parse_assign_specs(specs: list[str]) -> list[PathAssignment]:
    """Parse CLI --assign owner:path1,path2 or owner=path1,path2."""
    out: list[PathAssignment] = []
    for spec in specs:
        spec = spec.strip()
        if not spec:
            continue
        if ":" in spec:
            owner, paths_s = spec.split(":", 1)
        elif "=" in spec:
            owner, paths_s = spec.split("=", 1)
        else:
            raise ValueError(f"assign must be owner:path[,path…], got {spec!r}")
        owner = owner.strip()
        paths = [p.strip() for p in re.split(r"[,;]", paths_s) if p.strip()]
        if not owner or not paths:
            raise ValueError(f"invalid assign: {spec!r}")
        out.append(PathAssignment(paths=paths, owner=owner, status="proposed"))
    if not out:
        raise ValueError("no assignments")
    return out


def format_ownership_block(state: OwnershipState) -> str:
    if not state.ratified_map:
        return "(no ratified ownership yet — phase should stay discuss until ratify)"
    lines = [f"- `{p}` → **{o}**" for p, o in sorted(state.ratified_map.items())]
    return "\n".join(lines)


def git_changed_paths(cwd: Path, before: set[str] | None = None) -> set[str]:
    """Return changed paths in cwd via git status. Empty if not a git repo."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), "status", "--porcelain", "-uall"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode != 0:
        return set()
    paths: set[str] = set()
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        # XY PATH or XY ORIG -> PATH
        rest = line[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        paths.add(_norm(rest))
    if before is not None:
        return paths - before
    return paths


def git_status_snapshot(cwd: Path) -> set[str]:
    return git_changed_paths(cwd, before=None)


def audit_paths(
    state: OwnershipState,
    *,
    speaker: str,
    paths: list[str],
) -> list[str]:
    """Return list of violation descriptions (empty if ok).

    Audit only: does not prevent writes.
    """
    if not state.ratified_map:
        # no map → no violations under audit mode (nothing to compare)
        return []
    violations: list[str] = []
    for path in paths:
        owner = state.owner_for(path)
        if owner is None:
            violations.append(f"{path!r} not under any ratified prefix (speaker={speaker})")
        elif owner != speaker:
            violations.append(
                f"{path!r} owned by {owner!r}, not {speaker!r}"
            )
    return violations

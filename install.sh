#!/usr/bin/env bash
# install.sh — install thread-room ONLY (never touch agent CLIs)
#
# HARD RULES (do not break existing agent tooling):
#   - Only write under: $PREFIX/share/thread-room/  and  $PREFIX/bin/{thread-room,thr}
#   - NEVER overwrite/replace: claude, codex, gemini, agy, ollama, python, tr, …
#   - NEVER use short alias "tr" (shadows /usr/bin/tr)
#   - Short alias is "thr" only
#
# Usage:
#   ./install.sh
#   curl -fsSL https://raw.githubusercontent.com/MakiDevelop/thread-room/main/install.sh | bash

set -euo pipefail

REPO_URL="${THREAD_ROOM_REPO:-https://github.com/MakiDevelop/thread-room.git}"
BRANCH="${THREAD_ROOM_BRANCH:-main}"
PREFIX="${THREAD_ROOM_PREFIX:-$HOME/.local}"
SHARE="${PREFIX}/share/thread-room"
VENV="${SHARE}/venv"
SRC="${SHARE}/src"
BIN="${PREFIX}/bin"

# Names we must NEVER install or replace under $BIN
PROTECTED_NAMES=(
  tr claude codex gemini agy ollama python python3 pip pip3
  git gh tmux node npm npx
)

info() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "need '$1' on PATH"
}

is_protected() {
  local name="$1" p
  for p in "${PROTECTED_NAMES[@]}"; do
    [[ "$name" == "$p" ]] && return 0
  done
  return 1
}

# Safe symlink: only create/replace if target is ours (thread-room) or missing
safe_link() {
  local dest="$1" src="$2" name
  name="$(basename "$dest")"
  if is_protected "$name"; then
    die "refusing to install protected name: $name (would affect existing tools)"
  fi
  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ -L "$dest" ]]; then
      local cur
      cur="$(readlink "$dest" 2>/dev/null || true)"
      if [[ "$cur" == *thread-room* ]]; then
        ln -sfn "$src" "$dest"
        return 0
      fi
      die "refusing to overwrite existing $dest (not a thread-room link: $cur)"
    fi
    die "refusing to overwrite existing file $dest"
  fi
  ln -sfn "$src" "$dest"
}

need_cmd python3
need_cmd git

# Snapshot protected tool paths before install (for post-check)
declare -A BEFORE=()
for name in claude codex gemini; do
  BEFORE[$name]="$(command -v "$name" 2>/dev/null || true)"
done
BEFORE[tr]="$(command -v tr 2>/dev/null || true)"

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' \
  || die "Python >= 3.12 required (found ${PY_VER})"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/pyproject.toml" ]] && grep -q 'name = "thread-room"' "${SCRIPT_DIR}/pyproject.toml" 2>/dev/null; then
  SRC="${SCRIPT_DIR}"
  info "Installing from local checkout: ${SRC}"
else
  info "Cloning ${REPO_URL} (${BRANCH}) → ${SRC}"
  mkdir -p "${SHARE}"
  if [[ -d "${SRC}/.git" ]]; then
    git -C "${SRC}" fetch --depth 1 origin "${BRANCH}"
    git -C "${SRC}" checkout -q FETCH_HEAD || git -C "${SRC}" checkout -q "${BRANCH}"
    git -C "${SRC}" pull --ff-only origin "${BRANCH}" 2>/dev/null || true
  else
    # only remove our own src tree, never anything else
    if [[ -d "${SRC}" ]]; then
      rm -rf "${SRC}"
    fi
    git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${SRC}"
  fi
fi

info "Creating isolated venv at ${VENV} (does not touch system Python agents)"
python3 -m venv "${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
python -m pip install -U pip setuptools wheel >/dev/null
info "Installing thread-room into venv only"
python -m pip install -e "${SRC}" >/dev/null

mkdir -p "${BIN}"

# ONLY these two names on PATH
safe_link "${BIN}/thread-room" "${VENV}/bin/thread-room"
safe_link "${BIN}/thr" "${VENV}/bin/thread-room"

# Clean up bad legacy alias if we once installed it
if [[ -L "${BIN}/tr" ]]; then
  target="$(readlink "${BIN}/tr" 2>/dev/null || true)"
  if [[ "${target}" == *thread-room* ]]; then
    rm -f "${BIN}/tr"
    info "Removed legacy ${BIN}/tr (was shadowing /usr/bin/tr)"
  fi
fi

MEETINGS="${THREAD_ROOM_MEETINGS:-$HOME/thread-room-meetings}"
mkdir -p "${MEETINGS}"

# ── Post-install isolation checks ──────────────────────────────
info "Verifying isolation (existing agent CLIs must be unchanged)"
fail=0

# tr must not be thread-room
tr_path="$(command -v tr 2>/dev/null || true)"
if [[ -n "$tr_path" ]] && [[ "$(readlink "$tr_path" 2>/dev/null || true)" == *thread-room* ]]; then
  warn "tr still points at thread-room: $tr_path"
  fail=1
fi
if [[ -L "${BIN}/tr" ]] && [[ "$(readlink "${BIN}/tr")" == *thread-room* ]]; then
  warn "still have ${BIN}/tr → thread-room"
  fail=1
fi

# protected names must not be our links
for name in claude codex gemini; do
  p="${BIN}/${name}"
  if [[ -L "$p" ]]; then
    t="$(readlink "$p" 2>/dev/null || true)"
    if [[ "$t" == *thread-room* ]]; then
      warn "REFUSING state: $p points at thread-room ($t)"
      fail=1
    fi
  fi
  after="$(command -v "$name" 2>/dev/null || true)"
  # only warn if we changed path when they existed before
  if [[ -n "${BEFORE[$name]:-}" && -n "$after" && "${BEFORE[$name]}" != "$after" ]]; then
    # PATH order can change without us overwriting; only fail if BIN name is ours
    if [[ -L "${BIN}/${name}" ]] && [[ "$(readlink "${BIN}/${name}")" == *thread-room* ]]; then
      warn "$name resolution changed and BIN link is thread-room"
      fail=1
    fi
  fi
done

# our binaries work
"${BIN}/thread-room" --version >/dev/null || die "thread-room binary broken after install"
"${BIN}/thr" --version >/dev/null || die "thr binary broken after install"

if [[ "$fail" -ne 0 ]]; then
  die "isolation check failed — fix above before using (agent CLIs must stay untouched)"
fi

PATH_OK=0
case ":${PATH}:" in
  *":${BIN}:"*) PATH_OK=1 ;;
esac

info "OK — thread-room isolated install complete"
echo
echo "Installed (only these names):"
echo "  ${BIN}/thread-room"
echo "  ${BIN}/thr"
echo "Isolated venv: ${VENV}"
echo "Meetings dir:  ${MEETINGS}"
echo
echo "Unchanged by design: claude, codex, gemini, /usr/bin/tr, …"
echo

if [[ "${PATH_OK}" -ne 1 ]]; then
  echo "Add to ~/.zshrc if needed:"
  echo "  export PATH=\"${BIN}:\$PATH\""
  echo
fi

cat <<'EOF'
Usage:
  thread-room          # interactive: title + pick agents
  thr go "Title"       # one-shot
  thr say "…@codex"
  thr pump
  thr end
EOF

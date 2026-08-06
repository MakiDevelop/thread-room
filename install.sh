#!/usr/bin/env bash
# install.sh — one-shot install of thread-room onto PATH
#
# Usage:
#   ./install.sh
#   curl -fsSL https://raw.githubusercontent.com/MakiDevelop/thread-room/main/install.sh | bash
#
# After install you should have:
#   thread-room   (and short alias: thr — NOT "tr", which would shadow /usr/bin/tr)
# on PATH (typically ~/.local/bin).

set -euo pipefail

REPO_URL="${THREAD_ROOM_REPO:-https://github.com/MakiDevelop/thread-room.git}"
BRANCH="${THREAD_ROOM_BRANCH:-main}"
PREFIX="${THREAD_ROOM_PREFIX:-$HOME/.local}"
SHARE="${PREFIX}/share/thread-room"
VENV="${SHARE}/venv"
SRC="${SHARE}/src"
BIN="${PREFIX}/bin"

info() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "need '$1' on PATH"
}

need_cmd python3
need_cmd git

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' \
  || die "Python >= 3.12 required (found ${PY_VER})"

# Resolve source: running from a checkout, or clone into SHARE/src
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
    rm -rf "${SRC}"
    git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${SRC}"
  fi
fi

info "Creating venv at ${VENV}"
python3 -m venv "${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
python -m pip install -U pip setuptools wheel >/dev/null
info "Installing thread-room (editable from ${SRC})"
python -m pip install -e "${SRC}" >/dev/null

mkdir -p "${BIN}"
ln -sfn "${VENV}/bin/thread-room" "${BIN}/thread-room"
# Use thr, never tr — tr is a standard Unix tool (/usr/bin/tr)
ln -sfn "${VENV}/bin/thread-room" "${BIN}/thr"
# Remove mistaken legacy alias if present
if [[ -L "${BIN}/tr" ]]; then
  target="$(readlink "${BIN}/tr" 2>/dev/null || true)"
  if [[ "${target}" == *thread-room* ]]; then
    rm -f "${BIN}/tr"
    info "Removed legacy alias ${BIN}/tr (was shadowing /usr/bin/tr)"
  fi
fi

# Default meetings root
MEETINGS="${THREAD_ROOM_MEETINGS:-$HOME/thread-room-meetings}"
mkdir -p "${MEETINGS}"

# PATH hint
PATH_OK=0
case ":${PATH}:" in
  *":${BIN}:"*) PATH_OK=1 ;;
esac

info "Installed thread-room $(${BIN}/thread-room --version 2>/dev/null | awk '{print $2}')"
echo
echo "Commands on PATH:"
echo "  ${BIN}/thread-room"
echo "  ${BIN}/thr         # short alias (not 'tr' — that is a system tool)"
echo "Meetings default dir: ${MEETINGS}"
echo

if [[ "${PATH_OK}" -ne 1 ]]; then
  echo "Add this to your shell rc (~/.zshrc or ~/.bashrc):"
  echo "  export PATH=\"${BIN}:\$PATH\""
  echo
  echo "Then:  source ~/.zshrc"
  echo
fi

cat <<'EOF'
Quick use (no cd, no .venv):

  thread-room                     # interactive start: pick agents
  thr go "My meeting"             # or short alias thr
  thr say "Hello @codex …"
  thr pump
  thr attach
  thr end

EOF

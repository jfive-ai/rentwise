#!/usr/bin/env bash
#
# build-mac.sh — package the RentWise Expo Universal app as a macOS .app
# bundle by exporting the Expo web build and wrapping it in a tiny Electron
# shell.
#
# Phase 8 PR-A. We tried Mac Catalyst via `expo run:ios --device "Mac"` first
# (the issue's preferred path) but the Expo + RN 0.76 + Pod stack we're on
# only produces "Designed for iPad" iOS-platform .app bundles, which Finder
# refuses to launch on macOS ("incorrect executable format"). Real Mac
# Catalyst would require enabling SUPPORTS_MACCATALYST=YES in the Pods
# project and re-jigging hermes-engine and several pods that don't ship
# Catalyst-compatible binaries — far more invasive than the issue's
# "lightest lift" remit.
#
# Electron is the issue's documented fallback. It produces a real macOS .app
# we can drop into /Applications, reuses 100% of the existing Expo web build
# (same TypeScript source, same PWA hooks), and adds zero coupling to React
# Native iOS internals.
#
# Usage:
#   ./scripts/build-mac.sh                   # build into apps/desktop/build
#   ./scripts/build-mac.sh --install         # also copy RentWise.app -> /Applications
#   ./scripts/build-mac.sh --clean           # remove generated apps/desktop/build first
#
# Prereqs (one-time):
#   - macOS (this script will refuse to run anywhere else).
#   - Node + npm (already required for `apps/web` dev).
#   - That's it. Electron installs its own runtime via npm.

set -euo pipefail

# ------------------------------------------------------------------ helpers
log() { printf '\033[1;34m[build-mac]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[build-mac]\033[0m %s\n' "$*" >&2; }

die() {
  err "$*"
  exit 1
}

# ----------------------------------------------------------- platform check
if [[ "$(uname -s)" != "Darwin" ]]; then
  die "This script must run on macOS (detected: $(uname -s))."
fi

# ------------------------------------------------------------- tool checks
command -v node >/dev/null 2>&1 || die "node is required. Install Node 20+."
command -v npm  >/dev/null 2>&1 || die "npm is required."

# ------------------------------------------------------------- locate repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WEB_DIR="${REPO_ROOT}/apps/web"
DESKTOP_DIR="${REPO_ROOT}/apps/desktop"
WEB_DIST="${WEB_DIR}/dist"
DESKTOP_BUILD="${DESKTOP_DIR}/build"

# ----------------------------------------------------------- argument parse
DO_CLEAN=0
DO_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --clean) DO_CLEAN=1 ;;
    --install) DO_INSTALL=1 ;;
    -h|--help)
      sed -n '1,32p' "$0"
      exit 0
      ;;
    *) die "Unknown argument: $arg (try --help)" ;;
  esac
done

# --------------------------------------------------------------- workflow
if [[ "${DO_CLEAN}" -eq 1 ]]; then
  log "Cleaning previous build artifacts…"
  rm -rf "${DESKTOP_BUILD}" "${WEB_DIST}"
fi

# 1) Make sure JS deps are installed in apps/web (so `expo export` works)
#    and apps/desktop (so electron-builder is available).
if [[ ! -d "${WEB_DIR}/node_modules" ]]; then
  log "Installing apps/web dependencies (npm install)…"
  ( cd "${WEB_DIR}" && npm install )
fi

if [[ ! -d "${DESKTOP_DIR}/node_modules" ]]; then
  log "Installing apps/desktop dependencies (npm install)…"
  ( cd "${DESKTOP_DIR}" && npm install )
fi

# 2) Build the static web bundle. Idempotent — re-running just rewrites dist/.
log "Exporting Expo web build (apps/web/dist)…"
( cd "${WEB_DIR}" && npx expo export -p web )

[[ -f "${WEB_DIST}/index.html" ]] || die "Expected ${WEB_DIST}/index.html after export."

# 3) Package with electron-builder. We target arm64 only — the build script
#    is gated to Apple Silicon Macs, and a personal-use install doesn't need
#    a fat universal binary.
log "Packaging Electron .app (arm64, unsigned)…"
( cd "${DESKTOP_DIR}" && npm run --silent build:mac )

# Locate the produced .app under apps/desktop/build/.
APP_PATH="$(/usr/bin/find "${DESKTOP_BUILD}" -maxdepth 4 -name 'RentWise.app' -type d | head -n1 || true)"
[[ -n "${APP_PATH}" ]] || die "Build succeeded but RentWise.app was not found under ${DESKTOP_BUILD}."

log "Built: ${APP_PATH}"

if [[ "${DO_INSTALL}" -eq 1 ]]; then
  DEST="/Applications/RentWise.app"
  log "Installing to ${DEST} (will overwrite if present)…"
  rm -rf "${DEST}"
  cp -R "${APP_PATH}" "${DEST}"
  log "Installed. Open it with: open ${DEST}"
  log "First launch: macOS will warn about an unsigned app. Right-click → Open → Open Anyway."
else
  log "To install:  cp -R \"${APP_PATH}\" /Applications/RentWise.app"
  log "Or re-run:   ./scripts/build-mac.sh --install"
fi

log "Done."

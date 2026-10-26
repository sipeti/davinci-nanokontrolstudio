#!/usr/bin/env bash
# Reversible nanoKONTROL Studio / Resolve installation (macOS Bash 3.2).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
HS="$HOME/.hammerspoon"
BASE="$HOME/Library/Application Support/NK Scene2"
FORCE=0
DRY=0
fail() { printf 'NK_INSTALL=BLOCKED: %s\n' "$*" >&2; exit 1; }
usage() {
  echo 'Usage: sh install.command [--dry-run] [--force]'
  echo 'Backs up existing Hammerspoon files; never resets Korg calibration.'
  echo 'Stop any Scene 2 session before installing.'
}
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY=1 ;;
    --force) FORCE=1 ;;
    *) fail "unknown argument $arg" ;;
  esac
done
[ "$(uname -s)" = Darwin ] || fail "macOS required"
RUNTIME="fairlight_mcu_bridge.py fairlight_mcu_continuous.py scene2_audio_roundtrip_probe.py scene2_clip_gain_8rotary.py scene2_combined_bench.py scene2_continuous_clip_gain.py scene2_live_pickup_readonly.py scene2_soft_takeover.py"
for name in nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua scene2_session_menu.lua; do
  [ -f "$ROOT/$name" ] || fail "missing $name"
done
for name in $RUNTIME; do
  [ -f "$ROOT/scripts/$name" ] || fail "missing scripts/$name"
done
[ -f "$ROOT/requirements-scene2.txt" ] || fail "missing MIDI requirements"
if pgrep -fl 'scene2_combined_bench.py|scene2_continuous_clip_gain.py|fairlight_mcu_continuous.py' >/dev/null 2>&1; then
  fail "Scene 2 running: use NK JOG STOP first"
fi
PYTHON="$(printenv NK_RESOLVE_PYTHON 2>/dev/null || true)"
if [ -z "$PYTHON" ]; then
  for path in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "$path" ]; then PYTHON="$path"; break; fi
  done
fi
[ -x "$PYTHON" ] || fail "Python 3.10+ not found (install Homebrew Python)"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 10)' ||
  fail "Python 3.10+ required"
# Preserve unknown user edits unless the operator explicitly opts in.
for name in nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua scene2_session_menu.lua; do
  if [ -f "$HS/$name" ] && ! cmp -s "$ROOT/$name" "$HS/$name"; then
    [ "$FORCE" = 1 ] ||
      fail "$name differs; review changes, then install with --force (backup always created)"
  fi
done
if [ "$DRY" = 1 ]; then
  printf 'NK_INSTALL=DRY_RUN; python=%s; target=%s\n' "$PYTHON" "$HS"
  exit 0
fi
command -v shasum >/dev/null || fail "shasum unavailable"
# Prepare MIDI Python BEFORE changing any Hammerspoon files.
mkdir -p "$BASE"
VENV="$BASE/venv"
if [ ! -x "$VENV/bin/python3" ]; then "$PYTHON" -m venv "$VENV"; fi
"$VENV/bin/python3" -m pip install -r "$ROOT/requirements-scene2.txt" ||
  fail "MIDI dependency install failed, live Hammerspoon untouched"
"$VENV/bin/python3" -c 'import mido, rtmidi' ||
  fail "MIDI dependencies unavailable"
STAMP="$(date +%Y%m%d-%H%M%S)-$$"
BACK="$BASE/backups/$STAMP"
mkdir -p "$BACK/before" "$BACK/absent" "$BACK/after" "$HS"
checksum() { shasum -a 256 "$1" | awk '{print $1}'; }
snapshot() {
  if [ -f "$2" ]; then cp -p "$2" "$BACK/before/$1"
  else touch "$BACK/absent/$1"; fi
}
for name in nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua scene2_session_menu.lua init.lua; do
  snapshot "$name" "$HS/$name"
done
snapshot resolve-python.path "$BASE/resolve-python.path"
if [ -d "$BASE/scripts" ]; then
  cp -R "$BASE/scripts" "$BACK/before/scripts"
else
  touch "$BACK/absent/scripts"
fi
mkdir -p "$BASE/scripts"
for name in nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua scene2_session_menu.lua; do
  cp -p "$ROOT/$name" "$HS/$name.nk-new.$$"
  mv -f "$HS/$name.nk-new.$$" "$HS/$name"
  checksum "$HS/$name" > "$BACK/after/$name.sha256"
done
for name in $RUNTIME; do
  cp -p "$ROOT/scripts/$name" "$BASE/scripts/$name"
  checksum "$BASE/scripts/$name" > "$BACK/after/script-$name.sha256"
done
printf '%s\n' "$PYTHON" > "$BASE/resolve-python.path"
checksum "$BASE/resolve-python.path" > "$BACK/after/resolve-python.path.sha256"
LINE='require("nanokontrol_resolve21")'
if [ ! -f "$HS/init.lua" ]; then
  printf '%s\n' "$LINE" > "$HS/init.lua"
elif ! grep -Fq "$LINE" "$HS/init.lua" &&
     ! grep -Fq "require('nanokontrol_resolve21')" "$HS/init.lua"; then
  printf '\n-- Korg nanoKONTROL Studio / DaVinci Resolve\n%s\n' "$LINE" >> "$HS/init.lua"
fi
checksum "$HS/init.lua" > "$BACK/after/init.lua.sha256"
# Only advertise a complete install after every copy succeeded.
printf '%s\n' "$BACK" > "$BASE/active-backup"
printf 'NK_INSTALL=PASS\nBACKUP=%s\n' "$BACK"
echo 'Hammerspoon > Reload Config. Scene 2 starts automatically with Resolve.'
echo 'NK JOG > Scene 2: AUTOMATIKUS / SZUNET controls auto-session.'
echo 'No Korg relearn and no hardware rewrite.'

#!/usr/bin/env bash
# Install only the already-accepted Scene 2 menu, with backup and fail-closed
# checks. No launch, no Hammerspoon settings changes, no Git merge.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
HS="$HOME/.hammerspoon"
BASE="$HOME/Library/Application Support/NK Scene2"
VENV="$BASE/venv"
OLD_MAIN="030d42d62bf7b3ef6c6e920b32524d83253eedaa"
OLD_BRIDGE="76b4005464150cb02ffd63e2816b63b05ac943f6"

fail() { printf 'SCENE2_INSTALL=BLOCKED: %s\n' "$*" >&2; exit 1; }
sha() { git hash-object "$1"; }

[[ -f "$ROOT/nanokontrol_resolve21.lua" ]] || fail "staged main Lua missing"
[[ -f "$ROOT/scene2_clip_gain_bridge.lua" ]] || fail "staged bridge Lua missing"
[[ -f "$ROOT/scene2_session_menu.lua" ]] || fail "staged menu helper missing"
[[ -f "$ROOT/scripts/scene2_combined_bench.py" ]] || fail "staged Python missing"
[[ -f "$HS/nanokontrol_resolve21.lua" ]] || fail "live Hammerspoon controller missing"
[[ -f "$HS/scene2_clip_gain_bridge.lua" ]] || fail "live bridge missing"
[[ -x /opt/homebrew/bin/python3 ]] || fail "Resolve Python missing"
command -v git >/dev/null || fail "git unavailable"

# Refuse to overwrite unexpected local Hammerspoon changes. The exact
# original controller was previously accepted by physical Scene 1 tests.
LIVE_MAIN="$(sha "$HS/nanokontrol_resolve21.lua")"
STAGED_MAIN="$(sha "$ROOT/nanokontrol_resolve21.lua")"
[[ "$LIVE_MAIN" == "$OLD_MAIN" || "$LIVE_MAIN" == "$STAGED_MAIN" ]] ||
  fail "live controller modified (sha=$LIVE_MAIN); review diff before install"
LIVE_BRIDGE="$(sha "$HS/scene2_clip_gain_bridge.lua")"
STAGED_BRIDGE="$(sha "$ROOT/scene2_clip_gain_bridge.lua")"
[[ "$LIVE_BRIDGE" == "$OLD_BRIDGE" || "$LIVE_BRIDGE" == "$STAGED_BRIDGE" ]] ||
  fail "live bridge modified; review before install"
if [[ -f "$HS/scene2_session_menu.lua" ]]; then
  [[ "$(sha "$HS/scene2_session_menu.lua")" == "$(sha "$ROOT/scene2_session_menu.lua")" ]] ||
    fail "existing session menu modified; review before install"
fi

if pgrep -fl 'scene2_combined_bench.py|fairlight_mcu_continuous.py|scene2_continuous_clip_gain.py' >/dev/null; then
  fail "a Scene 2 Python worker is still running; stop it first"
fi

# Verify the staged Python implementation before ANY Hammerspoon replacement.
printf 'SCENE2_INSTALL=TESTS\n'
(cd "$ROOT" && /opt/homebrew/bin/python3 -m unittest discover -s tests -p 'test_scene2_*.py') ||
  fail "offline tests failed"
if command -v luac >/dev/null; then
  luac -p "$ROOT/nanokontrol_resolve21.lua" "$ROOT/scene2_clip_gain_bridge.lua" "$ROOT/scene2_session_menu.lua" ||
    fail "Lua syntax failed"
fi

# A durable venv survives reboot; the previously working /tmp venv does not.
mkdir -p "$BASE"
if [[ ! -x "$VENV/bin/python3" ]]; then
  /opt/homebrew/bin/python3 -m venv "$VENV"
fi
if ! "$VENV/bin/python3" -c 'import mido, rtmidi' >/dev/null 2>&1; then
  if [[ -x /tmp/nk-mcu-venv/bin/python3 ]]; then
    /tmp/nk-mcu-venv/bin/python3 -m pip freeze > "$BASE/mcu-requirements.txt"
    "$VENV/bin/python3" -m pip install -r "$BASE/mcu-requirements.txt"
  else
    "$VENV/bin/python3" -m pip install mido python-rtmidi
  fi
fi
"$VENV/bin/python3" -c 'import mido, rtmidi; print("SCENE2_INSTALL=MCU_PYTHON_OK")' ||
  fail "persistent MCU Python unavailable"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACK="$BASE/backups/$STAMP"
mkdir -p "$BACK"
cp -p "$HS/nanokontrol_resolve21.lua" "$BACK/"
cp -p "$HS/scene2_clip_gain_bridge.lua" "$BACK/"
if [[ -f "$HS/scene2_session_menu.lua" ]]; then
  cp -p "$HS/scene2_session_menu.lua" "$BACK/"
else
  touch "$BACK/session_menu_was_absent"
fi
if [[ -d "$BASE/scripts" ]]; then
  mkdir -p "$BACK/scripts"
  cp -R "$BASE/scripts/." "$BACK/scripts/"
fi

mkdir -p "$BASE/scripts"
cp -R "$ROOT/scripts/." "$BASE/scripts/"
for name in nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua scene2_session_menu.lua; do
  cp -p "$ROOT/$name" "$HS/$name.nk-new.$$"
  mv -f "$HS/$name.nk-new.$$" "$HS/$name"
  [[ "$(sha "$HS/$name")" == "$(sha "$ROOT/$name")" ]] ||
    fail "installed Lua checksum mismatch: $name; restore from $BACK"
done

printf 'SCENE2_INSTALL=PASS\nBACKUP=%s\n' "$BACK"
printf '%s\n' 'NEXT: Hammerspoon menu -> Reload Config. NK JOG -> Scene 2 TEST: START.'
printf '%s\n' 'START prompts for the named TEST project; never starts automatically.'

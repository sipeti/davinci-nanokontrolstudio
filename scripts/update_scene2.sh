#!/usr/bin/env bash
# Upgrade the installed controller from THIS source snapshot, then restart it.
# No background service, device rewrite or automatic Git pull.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
BASE="$HOME/Library/Application Support/NK Scene2"
HS="$HOME/.hammerspoon"
ACK="$HOME/Library/Caches/nk-scene2-update-paused"
fail() { printf 'NK_UPDATE=BLOCKED: %s\n' "$*" >&2; exit 1; }
usage() {
  echo 'Usage: sh ./update.command [--dry-run]'
  echo 'Installs this checkout, backs up the previous version and restarts Hammerspoon.'
  echo 'Requires the newer NK controller URL hooks; see docs/INSTALL.md for one-time upgrade.'
}
DRY=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY=1 ;;
    *) fail "unknown argument: $arg" ;;
  esac
done
[ "$(uname -s)" = Darwin ] || fail "macOS required"
if [ "$DRY" = 1 ]; then
  exec /bin/sh "$ROOT/install.command" --dry-run --force
fi
workers_running() {
  pgrep -fl 'scene2_combined_bench.py|scene2_continuous_clip_gain.py|fairlight_mcu_continuous.py' >/dev/null 2>&1
}
hs_running=0
if pgrep -x Hammerspoon >/dev/null 2>&1; then hs_running=1; fi
if [ "$hs_running" = 1 ]; then
  [ -f "$HS/nanokontrol_resolve21.lua" ] &&
    grep -Fq 'nk-controller-pause-for-update' "$HS/nanokontrol_resolve21.lua" ||
    fail "installed controller predates auto-update; pause it once, run install.command --force, then Reload Config"
  rm -f "$ACK"
  trap 'rm -f "$ACK"' EXIT
  open -g 'hammerspoon://nk-controller-pause-for-update' ||
    fail "could not request Hammerspoon pause"
  i=0
  while [ ! -f "$ACK" ]; do
    [ "$i" -lt 40 ] ||
      fail "no pause acknowledgement; return to confirmed bank A1-A8 and retry"
    sleep 0.25
    i=$((i+1))
  done
fi
# Wait for the MCU supervisor to finish cleaning up TOUCH and button state.
i=0
while workers_running; do
  [ "$i" -lt 60 ] ||
    fail "Scene 2 workers still running; installation was not started"
  sleep 0.25
  i=$((i+1))
done
/bin/sh "$ROOT/install.command" --force
for file in nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua scene2_session_menu.lua; do
  cmp -s "$ROOT/$file" "$HS/$file" ||
    fail "verification failed: $file"
done
for file in fairlight_mcu_bridge.py fairlight_mcu_continuous.py scene2_combined_bench.py scene2_continuous_clip_gain.py; do
  cmp -s "$ROOT/scripts/$file" "$BASE/scripts/$file" ||
    fail "verification failed: $file"
done
if [ "$hs_running" = 1 ]; then
  open -g 'hammerspoon://nk-controller-restart' ||
    fail "files updated, but automatic restart request failed; use Hammerspoon > Reload Config"
  echo 'NK_UPDATE=PASS; restart requested via Hammerspoon'
else
  echo 'NK_UPDATE=PASS; Hammerspoon is not running; it will load on next login/launch'
fi

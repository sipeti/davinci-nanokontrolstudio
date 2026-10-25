#!/usr/bin/env bash
# Restore pre-install state; never deletes user calibration, venv or backups.
set -euo pipefail
BASE="$HOME/Library/Application Support/NK Scene2"
HS="$HOME/.hammerspoon"
fail() { printf 'NK_UNINSTALL=BLOCKED: %s\n' "$*" >&2; exit 1; }
if [ "$#" = 1 ] && [ "$1" = --help ]; then
  echo 'Usage: sh uninstall.command'
  echo 'Restores the prior Hammerspoon files; refuses files modified since install.'
  exit 0
fi
[ "$#" = 0 ] || fail "unexpected arguments"
[ -f "$BASE/active-backup" ] || fail "active install record missing"
BACK="$(cat "$BASE/active-backup")"
case "$BACK" in "$BASE"/backups/*) ;; *) fail "unexpected backup path";; esac
[ -d "$BACK/after" ] || fail "incomplete backup"
if pgrep -fl 'scene2_combined_bench.py|scene2_continuous_clip_gain.py|fairlight_mcu_continuous.py' >/dev/null 2>&1; then
  fail "Scene 2 active: STOP via NK JOG first"
fi
checksum() { shasum -a 256 "$1" | awk '{print $1}'; }
verify() {
  [ -f "$1" ] && [ -f "$2" ] ||
    fail "installed file/manifest missing: $1"
  [ "$(checksum "$1")" = "$(cat "$2")" ] ||
    fail "user-modified file: $1; preserve edits and restore manually"
}
# Verify ALL installed items before changing ANY Hammerspoon file.
for name in nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua scene2_session_menu.lua init.lua; do
  verify "$HS/$name" "$BACK/after/$name.sha256"
done
verify "$BASE/resolve-python.path" "$BACK/after/resolve-python.path.sha256"
for manifest in "$BACK"/after/script-*.sha256; do
  [ -e "$manifest" ] || continue
  name="$(basename "$manifest" .sha256 | sed 's/^script-//')"
  verify "$BASE/scripts/$name" "$manifest"
done
restore() {
  if [ -f "$BACK/before/$1" ]; then cp -p "$BACK/before/$1" "$2"
  elif [ -f "$BACK/absent/$1" ]; then rm -f "$2"
  else fail "missing original backup: $1"; fi
}
for name in nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua scene2_session_menu.lua init.lua; do
  restore "$name" "$HS/$name"
done
restore resolve-python.path "$BASE/resolve-python.path"
# Move installed scripts into the backup rather than deleting user content.
if [ -d "$BASE/scripts" ]; then
  mv "$BASE/scripts" "$BACK/installed-scripts"
fi
if [ -d "$BACK/before/scripts" ]; then
  cp -R "$BACK/before/scripts" "$BASE/scripts"
elif [ ! -f "$BACK/absent/scripts" ]; then
  fail "original scripts state unavailable"
fi
rm -f "$BASE/active-backup"
printf 'NK_UNINSTALL=PASS\nRESTORED_FROM=%s\n' "$BACK"
echo 'Hammerspoon -> Reload Config. hs.settings and Korg scene data remain intact.'

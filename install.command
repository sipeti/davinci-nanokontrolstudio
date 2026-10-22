#!/bin/sh
set -eu
SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DST_DIR="$HOME/.hammerspoon"
mkdir -p "$DST_DIR"
TARGET="$DST_DIR/nanokontrol_resolve21.lua"
if [ -f "$TARGET" ] && ! cmp -s "$SRC_DIR/nanokontrol_resolve21.lua" "$TARGET"; then
  cp "$TARGET" "$TARGET.backup.$(date +%Y%m%d-%H%M%S)"
fi
cp "$SRC_DIR/nanokontrol_resolve21.lua" "$TARGET"
INIT="$DST_DIR/init.lua"
LINE='require("nanokontrol_resolve21")'
if [ -f "$INIT" ]; then
  if ! grep -Fq "$LINE" "$INIT"; then
    cp "$INIT" "$INIT.backup.$(date +%Y%m%d-%H%M%S)"
    printf '\n-- KORG nanoKONTROL Studio - DaVinci Resolve 21\n%s\n' "$LINE" >> "$INIT"
  fi
else
  printf '%s\n' "$LINE" > "$INIT"
fi
printf '\nINSTALLED v1.2: %s\n' "$TARGET"
printf 'Saved MIDI bindings preserved in Hammerspoon hs.settings.\n'
printf 'Use Hammerspoon -> Reload Config; NK menu: learn SELECT 5 only; existing 24 bindings stay.\n'

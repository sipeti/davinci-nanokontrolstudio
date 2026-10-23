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
printf '\nINSTALLED v1.3 CLEAN: %s\n' "$TARGET"
printf 'Existing MIDI settings backed by hs.settings; clean setup is committed only after 28/28.\n'
printf 'Hammerspoon -> Reload Config; NK menu -> TELJES UJRABETANITAS (28 lepes).\n'

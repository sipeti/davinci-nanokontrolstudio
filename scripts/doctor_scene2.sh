#!/usr/bin/env bash
# Read-only MIDI / Python / Hammerspoon preflight (no Resolve writes).
set -u
BASE="$HOME/Library/Application Support/NK Scene2"
HS="$HOME/.hammerspoon"
echo '== nanoKONTROL Studio / Resolve 21 doctor (read-only) =='
for file in "$HS/init.lua" "$HS/nanokontrol_resolve21.lua" \
  "$HS/scene2_clip_gain_bridge.lua" "$HS/scene2_session_menu.lua" \
  "$BASE/scripts/scene2_combined_bench.py" \
  "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"; do
  if [ -e "$file" ]; then printf 'OK: %s\n' "$file"
  else printf 'MISSING: %s\n' "$file"; fi
done
if [ -x "$BASE/venv/bin/python3" ]; then
  "$BASE/venv/bin/python3" - <<'PY'
import sys
print("Python:", sys.version.split()[0])
try:
    import mido, rtmidi
    print("MIDI dependencies: OK")
    names = mido.get_input_names() + mido.get_output_names()
    for p in ("IAC Driver NK FL From Resolve", "IAC Driver NK FL To Resolve"):
        print("MIDI port", repr(p), ":", "OK" if p in names else "MISSING")
except Exception as exc:
    print("MIDI check unavailable:", type(exc).__name__, str(exc))
PY
else
  echo 'MISSING: MIDI Python venv'
fi
echo 'No MIDI is sent and no Resolve project is changed by this command.'

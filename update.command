#!/bin/sh
set -eu
SRC="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec /bin/bash "$SRC/scripts/update_scene2.sh" "$@"

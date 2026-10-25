#!/bin/sh
set -eu
SRC="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec /bin/bash "$SRC/scripts/install_scene2_menu.sh" "$@"

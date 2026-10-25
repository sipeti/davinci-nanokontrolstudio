#!/bin/sh
set -eu
SRC="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec /bin/bash "$SRC/scripts/doctor_scene2.sh" "$@"

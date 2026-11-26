#!/bin/sh
# Build native standalone JS8 modem on the device. Network required once.
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
REPO='https://github.com/jfrancis42/gfsk8-modem-clean.git'
REV='bd6457e0bd4c3a10e74d1c1aaa5e86f67565168a'
BASE="${HOME}/.cache/pocketjs8-lite"
SRC="${BASE}/gfsk8-modem-clean"
SELF=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
[ -f "$SELF/native/modem.cpp" ] || { echo 'Missing native/modem.cpp' >&2; exit 1; }
for c in git cmake c++ make; do
    command -v "$c" >/dev/null || { echo "Missing $c. Install git cmake build-essential." >&2; exit 1; }
done
if [ ! -d "$SRC/.git" ]; then
    mkdir -p "$BASE"
    git clone "$REPO" "$SRC"
fi
cd "$SRC"
git fetch --depth=1 origin "$REV"
git checkout --detach "$REV"
[ "$(git rev-parse HEAD)" = "$REV" ] || { echo 'Upstream revision mismatch' >&2; exit 1; }
# -O1 and single-job build reduce peak compiler RAM on a 512 MiB Zero.
cmake -S . -B "$BASE/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS_RELEASE='-O1 -DNDEBUG'
cmake --build "$BASE/build" --parallel 1
ctest --test-dir "$BASE/build" --output-on-failure
mkdir -p "${HOME}/.local/bin"
c++ -std=c++20 -O1 -DNDEBUG -pthread -I "$SRC/include" -I "$SRC/src" \
    "$SELF/native/modem.cpp" "$BASE/build/libgfsk8modem.a" "$BASE/build/libkissfft.a" \
    -o "${HOME}/.local/bin/pocketjs8-lite-modem"
"${HOME}/.local/bin/pocketjs8-lite-modem" version
printf 'Built %s\n' "${HOME}/.local/bin/pocketjs8-lite-modem"
printf 'If compilation was killed by the OOM killer, add temporary build swap and rerun.\n'

#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cat >"$tmp/a" <<'LOG'
# main
0 0 0 main OUT 12FC AA 1234
1 1 0 main OUT 00FC BB 1234
2 2 0 main IN 00FD EE 1234
3 3 0 main OUT 00FE CC 1234
# 取りこぼし: 0件 / 総イベント数: 4件
# sub
LOG
cat >"$tmp/b" <<'LOG'
# main
0 0 0 main OUT 00FC BB 1234
1 1 0 main OUT 00FE DD 1234
2 2 0 main OUT 00FF EE 1234
# 取りこぼし: 0件 / 総イベント数: 3件
# sub
LOG
cat >"$tmp/expected" <<'LOG'
port FC out-count=2 1 last=same
port FE out-count=1 1 last=differ
port FF out-count=0 1 last=none
LOG
python3 "$repo/tools/b63_port_last.py" "$tmp/a" "$tmp/b" >"$tmp/out"
diff -u "$tmp/expected" "$tmp/out"
sed 's/取りこぼし: 0件/取りこぼし: 1件/' "$tmp/a" >"$tmp/dropped"
if python3 "$repo/tools/b63_port_last.py" "$tmp/dropped" "$tmp/b" >"$tmp/out" 2>/dev/null; then exit 1; fi
[[ ! -s "$tmp/out" ]]
printf 'OK: B63 自己検査\n'

#!/usr/bin/env bash
# 公式ROMなし。実Z80上で媒体全体の差、事前エラー、名前の大小を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
CORE="$(find_l3_core)"
[ -n "$CORE" ] || { printf 'NG コアなし\n' >&2; exit 1; }
ensure_l3_frontend
WORK="$(mktemp -d "${TMPDIR:-/tmp}/l4-killname-z80.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
run_one() {
  local arm="$1" fault="$2" out="$WORK/$1-$2" log="$WORK/$1-$2.memlog"
  python3 "$REPO/tools/l4_killname_z80_selftest.py" "$out" "$arm" "$fault" || return 1
  "$REPO/tools/harness/frontend/q88measure" --core "$CORE" --rom-dir "$out" --frames 30 \
    --mem-write-log "$log" --mem-write-range E300-E304 >"$out/stdout" 2>"$out/stderr" || return 1
  python3 - "$log" <<'PY'
import re,sys
last={}
for line in open(sys.argv[1],encoding='utf-8',errors='replace'):
    m=re.match(r'\s*\d+\s+\d+\s+[0-9A-Fa-f]{4}\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})',line)
    if m:last[m[1].upper()]=m[2].upper()
print(last.get('E304','00'),last.get('E303','00'))
PY
}
for arm in K-1 K-2 K-3 K-4 N-1 N-2 N-3 N-4 N-5 N-6 chain late unused deleted drive1 upper boundary same short; do
  read -r pass fail <<<"$(run_one "$arm" normal)"
  [ "$pass/$fail" = 01/00 ] || { printf 'NG %s (%s/%s)\n' "$arm" "$pass" "$fail" >&2; exit 1; }
done
for control in K-1:release N-1:tail N-4:protect K-1:prompt; do
  read -r pass fail <<<"$(run_one "${control%:*}" "${control#*:}")"
  [ "$pass" != 01 ] && [ "$fail" != 00 ] || { printf 'NG 陰性対照 %s\n' "$control" >&2; exit 1; }
done
python3 "$REPO/tools/l4_killname_integration_selftest.py" "$WORK" "$CORE"
printf 'OK KILL/NAME Z80: 19腕、鎖・全媒体比較・ERR53/65/73/61・大小・陰性対照4件\n'

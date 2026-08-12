#!/usr/bin/env bash
# cmp_fdc_sectors.py の検出力を、合成ログだけで確認する。

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$REPO/tools/cmp_fdc_sectors.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

write_log() {
  local dst="$1" second_r="$2"
  cat >"$dst" <<EOF
# main
# seq clock frame cpu kind port value pc
1 5 0 main IN 00FE 00 1000
2 6 0 main OUT 00FF 00 1001
3 100 0 main OUT 0031 00 1002
# sub
# seq clock frame cpu kind port value pc
1 10 0 sub OUT 00FB 46 0100
2 11 0 sub OUT 00FB 00 0101
3 12 0 sub OUT 00FB 01 0101
4 13 0 sub OUT 00FB 00 0101
5 14 0 sub OUT 00FB 02 0101
6 15 0 sub OUT 00FB 01 0101
7 16 0 sub OUT 00FB 08 0101
8 17 0 sub OUT 00FB 2A 0101
9 18 0 sub OUT 00FB FF 0101
10 30 0 sub OUT 00FB 46 0100
11 31 0 sub OUT 00FB 00 0101
12 32 0 sub OUT 00FB 01 0101
13 33 0 sub OUT 00FB 00 0101
14 34 0 sub OUT 00FB ${second_r} 0101
15 35 0 sub OUT 00FB 01 0101
16 36 0 sub OUT 00FB 08 0101
17 37 0 sub OUT 00FB 2A 0101
18 38 0 sub OUT 00FB FF 0101
EOF
}

write_log "$WORK/reference.iolog.txt" 03
write_log "$WORK/same.iolog.txt" 03
write_log "$WORK/changed.iolog.txt" 04

same_out="$WORK/same.out"
if ! python3 "$TOOL" "$WORK/reference.iolog.txt" "$WORK/same.iolog.txt" \
    --divergence-index 3 >"$same_out" 2>&1; then
  echo "NG: 同一座標列を一致と判定できない"
  exit 1
fi
grep -q '^基準側抽出件数: 2$' "$same_out" || {
  echo "NG: 既知入力から非0件を抽出できない"; exit 1;
}
grep -q '^混成側抽出件数: 2$' "$same_out" || {
  echo "NG: 対象側の抽出件数が不正"; exit 1;
}
grep -q '^座標列の一致プレフィックス長: 2$' "$same_out" || {
  echo "NG: 同一座標列の一致長が不正"; exit 1;
}

changed_out="$WORK/changed.out"
set +e
python3 "$TOOL" "$WORK/reference.iolog.txt" "$WORK/changed.iolog.txt" \
    --divergence-index 3 >"$changed_out" 2>&1
changed_rc=$?
set -e
if [ "$changed_rc" -ne 1 ]; then
  echo "NG: 意図的な座標不一致を不一致rcで検出できない"
  exit 1
fi
grep -q '^座標列の一致プレフィックス長: 1$' "$changed_out" || {
  echo "NG: 意図的不一致の直前までの一致長が不正"; exit 1;
}
grep -q '^最初の不一致位置: 2$' "$changed_out" || {
  echo "NG: 意図的不一致の位置を正しく検出できない"; exit 1;
}
grep -q '^不一致種別: 座標が違う$' "$changed_out" || {
  echo "NG: 意図的不一致の種別が不正"; exit 1;
}
grep -q '^分岐点3との位置関係: 前$' "$changed_out" || {
  echo "NG: 分岐点前後の判定が不正"; exit 1;
}

echo "cmp_fdc_sectors selftest: OK（非0件抽出・意図的不一致位置の検出）"

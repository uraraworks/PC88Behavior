#!/usr/bin/env bash
# tools/make_l3_testdisk_selftest.sh — 規則生成D88の生成器の自己検査（公式環境不要）。
# m7lh で --data-crc-error を足したときに作った。確かめること:
#   1. 同じ引数で2回作るとバイト一致する（決定論性）
#   2. --data-crc-error の版と通常版は、全セクタ見出しの状態バイト(オフセット8)だけが違い、
#      CRC版はすべて0xB0、通常版はすべて0x00である
#   3. 陰性対照: 検査2の期待を1つずらすと不一致として落ちる（検査に検出力がある）
# 生成物は自作の規則生成データで、ROM・ディスク由来のバイトを含まない。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
ok() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng() { printf '  \033[31mNG\033[0m   %s\n' "$1"; rc=1; }
rc=0
G=(--cylinders 40 --double-sided --sectors-per-track 16)
python3 "$REPO/tools/make_l3_testdisk.py" "$W/a.d88" "${G[@]}" >/dev/null
python3 "$REPO/tools/make_l3_testdisk.py" "$W/b.d88" "${G[@]}" >/dev/null
python3 "$REPO/tools/make_l3_testdisk.py" "$W/c.d88" "${G[@]}" --data-crc-error >/dev/null
cmp -s "$W/a.d88" "$W/b.d88" && ok "同じ引数で2回作るとバイト一致" || ng "同じ引数で作ってもバイト一致しない"
check() {  # $1 = CRC版に期待する状態値
python3 - "$W/a.d88" "$W/c.d88" "$1" <<'PY'
import sys, struct
a = open(sys.argv[1], "rb").read(); b = open(sys.argv[2], "rb").read(); want = int(sys.argv[3], 0)
pos = set()
for off in struct.unpack_from("<164I", a, 32):
    if not off: continue
    p = off; n = struct.unpack_from("<H", a, p + 4)[0]
    for _ in range(n):
        pos.add(p + 8); p += 16 + struct.unpack_from("<H", a, p + 14)[0]
diff = {i for i in range(len(a)) if a[i] != b[i]}
print(f"  （違うバイト {len(diff)} 個 / セクタ数 {len(pos)}）")
sys.exit(0 if (len(a) == len(b) and diff == pos and all(b[i] == want for i in pos) and all(a[i] == 0 for i in pos)) else 1)
PY
}
check 0xB0 && ok "CRC版は全セクタの状態バイトだけが0xB0で、他は通常版と一致" || ng "CRC版の違いが状態バイトだけではない"
check 0xB1 && ng "陰性対照: 期待をずらしても一致してしまった（検査に検出力が無い）" || ok "陰性対照: 期待をずらすと不一致として落ちる"
[ "$rc" -eq 0 ] && echo "make_l3_testdisk_selftest: OK（全項目）" || echo "make_l3_testdisk_selftest: 失敗あり"
exit "$rc"

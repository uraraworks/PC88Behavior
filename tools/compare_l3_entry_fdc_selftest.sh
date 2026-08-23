#!/usr/bin/env bash
# compare_l3_entry_fdc.py のunit/head・結果ステータス分類自己検査。
# 入力は公開μPD765形式から作った合成ログだけで、公式データは含まない。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/compare_l3_entry_fdc.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

make_log() {
  local path="$1" unit="$2" status="$3"
  python3 - "$path" "$unit" "$status" <<'EOF'
import sys
path, unit, status = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
events = [
    ("OUT", 0x04), ("OUT", unit), ("IN", status),
]
with open(path, "w", encoding="utf-8") as fp:
    fp.write("# 合成FDCログ（公式データ不使用）\n")
    fp.write("core      : (テスト用ダミー)\nframes    : 800\n\n")
    fp.write("# main\n# seq clock frame cpu kind port value pc\n\n")
    fp.write("# sub\n# seq clock frame cpu kind port value pc\n")
    for seq, (kind, value) in enumerate(events, 1):
        fp.write(f"{seq:6d} {seq:6d} 700 sub {kind:<4} 00FB {value:02X} 0100\n")
EOF
}

# B/head0、READY、WRITE PROTECTEDを表す公開分類用の合成値。
make_log "$WORK/base.txt" 1 97
make_log "$WORK/same.txt" 1 97
# 故障注入1: unitだけAへ変える。
make_log "$WORK/bad-unit.txt" 0 96
# 故障注入2: WRITE PROTECTEDだけ落とす。
make_log "$WORK/bad-status.txt" 1 33

if out="$(python3 "$CHECK" --official "$WORK/base.txt" --mixed "$WORK/same.txt" \
      --after-frame 700 2>&1)" \
   && printf '%s\n' "$out" | grep -q '公式入口区間unit/head分類:.*B/head0' \
   && printf '%s\n' "$out" | grep -q '入口区間のunit/head差: なし' \
   && printf '%s\n' "$out" | grep -q '入口区間の結果ステータス差: なし'; then
  ok "同じunit/head・結果分類を全長一致と判定"
else
  ng "同じ合成ログの分類が一致しない"
fi

out="$(python3 "$CHECK" --official "$WORK/base.txt" --mixed "$WORK/bad-unit.txt" \
      --after-frame 700 2>&1)"
if printf '%s\n' "$out" | grep -q '最初のunit/head差: コマンド1件目' \
   && printf '%s\n' "$out" | grep -q '公式=B/head0、混成=A/head0'; then
  ok "故障注入したunit差を位置と公開分類で検出"
else
  ng "unit差を検出できない"
fi

out="$(python3 "$CHECK" --official "$WORK/base.txt" --mixed "$WORK/bad-status.txt" \
      --after-frame 700 2>&1)"
if printf '%s\n' "$out" | grep -q '最初の結果ステータス差: コマンド1件目' \
   && printf '%s\n' "$out" | grep -q 'WRITE PROTECTED'; then
  ok "故障注入したST3分類差を位置と公開ビット名で検出"
else
  ng "ST3分類差を検出できない"
fi

if printf '%s\n' "$out" | grep -Eq '0x|=[0-9A-Fa-f]{2}([、,/]|$)'; then
  ng "分類出力へ結果バイト値が漏れた"
else
  ok "分類出力に結果バイト値を出さない"
fi

exit "$rc"

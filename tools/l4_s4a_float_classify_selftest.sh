#!/usr/bin/env bash
# tools/l4_s4a_float_classify_selftest.sh — tools/l4_s4a_float_classify.py 自体を
# 検査する自己検査（陰性対照つき）。
#
# l4-s4a事前登録「本文を出さない取り扱い」節の指示どおり、新しく書いた分類器
# （集合外の文字コードを標準出力へ一切出さない設計）を、測定に使う前に
# わざと壊して検出できることを確かめる（tools/redact_iolog_selftest.sh・
# tools/screen_content_leak_selftest.sh と同じ作法）。公式ROM不要。
# フィクスチャは全て自作の合成VRAM写し(3000バイト)で、公式データは一切
# 使わない。
#
# 使い方: tools/l4_s4a_float_classify_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLASSIFY="$SCRIPT_DIR/l4_s4a_float_classify.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 合成VRAM写しを作る道具 ------------------------------------------------
# ROWS=25, STRIDE=120 (char80+attr40)。row/colを指定して1バイトだけ書き換える。
python3 - "$WORK" <<'PYEOF'
import sys
ROWS, STRIDE, COLS = 25, 120, 80

def blank_dump():
    return bytearray(b'\x20' * (ROWS * STRIDE))

def poke(buf, row, col, code):
    buf[row * STRIDE + col] = code

work = sys.argv[1]

# --- ケース1: 陽性対照(numeric)。origin=row6、出力row=row7に "1.5"、Ok行=row8 ---
before1 = blank_dump()
after1 = blank_dump()
poke(after1, 6, 0, ord('x'))          # 打った行が変化した印(内容は問わない)
poke(after1, 7, 1, ord('1'))
poke(after1, 7, 2, ord('.'))
poke(after1, 7, 3, ord('5'))
poke(after1, 8, 0, ord('O'))          # Ok行の印(境界に使うだけ、集合外でよい)
with open(f"{work}/pos_before.bin", "wb") as f:
    f.write(before1)
with open(f"{work}/pos_after.bin", "wb") as f:
    f.write(after1)

# --- ケース2: 陰性対照(集合外コード混入)。出力row(7)に '?'(0x3F)を混ぜる ---
before2 = blank_dump()
after2 = blank_dump()
poke(after2, 6, 0, ord('x'))
poke(after2, 7, 1, ord('1'))
poke(after2, 7, 2, ord('?'))          # 集合外
poke(after2, 8, 0, ord('O'))
with open(f"{work}/neg_before.bin", "wb") as f:
    f.write(before2)
with open(f"{work}/neg_after.bin", "wb") as f:
    f.write(after2)

# --- ケース3: 陰性対照その2(押す前が空白でなかった=コードが読めないセル) ---
before3 = blank_dump()
poke(before3, 7, 1, ord('a'))          # 事前から非空白(前の画面の残り、という想定)
after3 = blank_dump()
poke(after3, 6, 0, ord('x'))
poke(after3, 7, 1, ord('9'))           # 変化はしたが押す前が空白でないので読めない
poke(after3, 8, 0, ord('O'))
with open(f"{work}/unreadable_before.bin", "wb") as f:
    f.write(before3)
with open(f"{work}/unreadable_after.bin", "wb") as f:
    f.write(after3)
PYEOF

# --- 検査1: 陽性対照が numeric_output と分類され、セルが正しく出る ---
OUT_POS="$(python3 "$CLASSIFY" --before "$WORK/pos_before.bin" --after "$WORK/pos_after.bin")"
if echo "$OUT_POS" | grep -q '"classification":"numeric_output"'; then
  pass "陽性対照: numeric_output に分類された"
else
  fail "陽性対照: numeric_output に分類されなかった ($OUT_POS)"
fi
# セルは相対行1・相対桁1-3にコード 0x31('1')0x2E('.')0x35('5') が乗るはず。
if echo "$OUT_POS" | grep -q '"cells":\[\[1,1,49\],\[1,2,46\],\[1,3,53\]\]'; then
  pass "陽性対照: セルの並びが期待どおり"
else
  fail "陽性対照: セルの並びが期待と違う ($OUT_POS)"
fi

# --- 検査2: 陰性対照(集合外コード)が non_numeric_output に分類され、
#     コード(0x3Fや文字'?')が一切出力に現れない ---
OUT_NEG="$(python3 "$CLASSIFY" --before "$WORK/neg_before.bin" --after "$WORK/neg_after.bin")"
if echo "$OUT_NEG" | grep -q '"classification":"non_numeric_output"'; then
  pass "陰性対照: non_numeric_output に分類された(検出できた)"
else
  fail "陰性対照: non_numeric_output に分類されなかった(検出できていない)"
fi
if echo "$OUT_NEG" | grep -qi '"cells"'; then
  fail "陰性対照: cells キーが出力に含まれてしまった(コード漏れの疑い)"
else
  pass "陰性対照: cells キーが出力に含まれない"
fi
if echo "$OUT_NEG" | grep -q '3[Ff]' ; then
  fail "陰性対照: 集合外コード(0x3F相当の16進表記)が出力に現れた"
else
  pass "陰性対照: 集合外コードの16進表記が出力に現れない"
fi

# --- 検査3: 押す前が空白でなかった(コードが読めない)セルが混じると
#     安全側で non_numeric_output になり、コードも出さない ---
OUT_UNREAD="$(python3 "$CLASSIFY" --before "$WORK/unreadable_before.bin" --after "$WORK/unreadable_after.bin")"
if echo "$OUT_UNREAD" | grep -q '"classification":"non_numeric_output"'; then
  pass "コード不明セル: non_numeric_output に安全側で倒れた"
else
  fail "コード不明セル: numeric_output のままになってしまった(安全側になっていない)"
fi
if echo "$OUT_UNREAD" | grep -qi '"cells"'; then
  fail "コード不明セル: cells キーが出力に含まれてしまった"
else
  pass "コード不明セル: cells キーが出力に含まれない"
fi

# --- 検査4: --range-only を指定すると、numeric_output でも cells を出さない ---
OUT_RANGE="$(python3 "$CLASSIFY" --before "$WORK/pos_before.bin" --after "$WORK/pos_after.bin" --range-only)"
if echo "$OUT_RANGE" | grep -q '"classification":"numeric_output"'; then
  pass "--range-only: 分類自体は numeric_output のまま"
else
  fail "--range-only: 分類が変わってしまった ($OUT_RANGE)"
fi
if echo "$OUT_RANGE" | grep -qi '"cells"'; then
  fail "--range-only: cells キーが出力に含まれてしまった"
else
  pass "--range-only: cells キーが出力に含まれない(件数・範囲だけ)"
fi
if echo "$OUT_RANGE" | grep -q '"row_summary"'; then
  pass "--range-only: row_summary(件数・範囲)は出力される"
else
  fail "--range-only: row_summary が出力されない"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "失敗あり"
fi
exit "$FAIL"

#!/usr/bin/env bash
# tools/l4_list_classify_selftest.sh — tools/l4_list_classify.py 自体を
# 検査する自己検査（陽性対照・陰性対照・故障注入つき）。
#
# l4-s5a事前登録（別担当が並行で作成中）の指示どおり、新しく書いた
# 分類器（行番号で始まる表示可能ASCIIの行だけコードを出す設計）を、
# 測定に使う前にわざと壊して検出できることを確かめる
# （tools/l4_s4a_float_classify_selftest.sh・tools/redact_iolog_
# selftest.sh・tools/screen_content_leak_selftest.sh と同じ作法）。
# 公式ROM不要。フィクスチャは全て自作の合成VRAM写し(3000バイト)で、
# 公式データは一切使わない。
#
# 使い方: tools/l4_list_classify_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLASSIFY="$SCRIPT_DIR/l4_list_classify.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 合成VRAM写しを作る ----------------------------------------------
# row6=打った行(origin)・row7=list_line候補(数字始まり・全ASCII)・
# row8=other_line候補(英字始まり)・row9=other_line候補(数字始まりだが
# 範囲外バイトを1つ含む)・row10=Ok行。
python3 - "$WORK" <<'PYEOF'
import sys
ROWS, STRIDE, COLS = 25, 120, 80

def blank_dump():
    return bytearray(b'\x20' * (ROWS * STRIDE))

def poke(buf, row, col, code):
    buf[row * STRIDE + col] = code

def poke_str(buf, row, col, s):
    for i, ch in enumerate(s):
        poke(buf, row, col + i, ord(ch))

work = sys.argv[1]

before = blank_dump()
after = blank_dump()

# 打った行(origin)の印
poke_str(after, 6, 0, "list")

# list_line候補: "12 REM HELLO"(数字始まり・全ASCII)
poke_str(after, 7, 0, "12 REM HELLO")

# other_line候補(1): 英字始まり
poke_str(after, 8, 0, "REM ONLY")

# other_line候補(2): 数字始まりだが範囲外バイト(0x01)を1つ含む
poke_str(after, 9, 0, "5 X")
poke(after, 9, 10, 0x01)

# Ok行の印
poke_str(after, 10, 0, "Ok")

with open(f"{work}/before.bin", "wb") as f:
    f.write(bytes(before))
with open(f"{work}/after.bin", "wb") as f:
    f.write(bytes(after))
PYEOF

OUT="$(python3 "$CLASSIFY" --before "$WORK/before.bin" --after "$WORK/after.bin")"

# --- 検査1: 原点・Ok相対行 ------------------------------------------
if echo "$OUT" | grep -q '"origin_row0":6'; then
  pass "検査1a: origin_row0が6(打った行)と一致"
else
  fail "検査1a: origin_row0が期待値と違う ($OUT)"
fi
if echo "$OUT" | grep -q '"ok_relative_row":4'; then
  pass "検査1b: ok_relative_rowが4(row10-row6)と一致"
else
  fail "検査1b: ok_relative_rowが期待値と違う ($OUT)"
fi

# --- 検査2: 陽性対照(row7、相対行1) list_lineに分類されコードが出る ---
if echo "$OUT" | grep -q '"classification":"list_line".*"relative_row":1\|"relative_row":1,"row_summary".*"classification":"list_line"'; then
  pass "検査2a: 陽性対照(相対行1)がlist_lineに分類された(緩い形式チェック)"
else
  # 形式に依存しない厳密チェック: python側で判定する
  python3 - "$OUT" <<'PYEOF'
import json, sys
d = json.loads(sys.argv[1])
line1 = [l for l in d["lines"] if l["relative_row"] == 1][0]
assert line1["classification"] == "list_line", line1["classification"]
print("PYOK")
PYEOF
  if [ $? -eq 0 ]; then
    pass "検査2a: 陽性対照(相対行1)がlist_lineに分類された"
  else
    fail "検査2a: 陽性対照(相対行1)の分類がlist_lineでない"
  fi
fi
# コード49='1' 50='2' が相対行1に出ていること(先頭の"12"の'1','2')
if echo "$OUT" | grep -q '\[1,0,49\]' && echo "$OUT" | grep -q '\[1,1,50\]'; then
  pass "検査2b: 陽性対照のコード(相対桁0='1'・桁1='2')が出力に含まれる"
else
  fail "検査2b: 陽性対照のコードが出力に含まれない($OUT)"
fi

# --- 検査3: 陰性対照(row8、英字始まり) other_lineでコードが一切出ない ---
python3 - "$OUT" > "$WORK/line2.json" <<'PYEOF'
import json, sys
d = json.loads(sys.argv[1])
line2 = [l for l in d["lines"] if l["relative_row"] == 2][0]
print(json.dumps(line2, separators=(',',':')))
PYEOF
LINE2="$(cat "$WORK/line2.json")"
if echo "$LINE2" | grep -q '"classification":"other_line"'; then
  pass "検査3a: 陰性対照(英字始まり、相対行2)がother_lineに分類された"
else
  fail "検査3a: 陰性対照(英字始まり)がother_lineに分類されなかった ($LINE2)"
fi
if echo "$LINE2" | grep -qi '"cells"'; then
  fail "検査3b: 陰性対照(英字始まり)にcellsキーが含まれてしまった(コード漏れ)"
else
  pass "検査3b: 陰性対照(英字始まり)にcellsキーが含まれない"
fi
# "REM ONLY"の文字コード(R=82,E=69,M=77...)が出力全体に一切現れないこと
if echo "$OUT" | grep -q '\[2,[0-9]*,82\]\|\[2,[0-9]*,69\]\|\[2,[0-9]*,77\]'; then
  fail "検査3c: 陰性対照(英字始まり)の文字コードが出力全体に現れた"
else
  pass "検査3c: 陰性対照(英字始まり)の文字コードが出力全体のどこにも現れない"
fi

# --- 検査4: 陰性対照(row9、数字始まりだが範囲外バイトを含む) ---------
python3 - "$OUT" > "$WORK/line3.json" <<'PYEOF'
import json, sys
d = json.loads(sys.argv[1])
line3 = [l for l in d["lines"] if l["relative_row"] == 3][0]
print(json.dumps(line3, separators=(',',':')))
PYEOF
LINE3="$(cat "$WORK/line3.json")"
if echo "$LINE3" | grep -q '"classification":"other_line"'; then
  pass "検査4a: 陰性対照(数字始まり+範囲外バイト、相対行3)がother_lineに分類された"
else
  fail "検査4a: 陰性対照(数字始まり+範囲外バイト)がother_lineに分類されなかった ($LINE3)"
fi
if echo "$LINE3" | grep -qi '"cells"'; then
  fail "検査4b: 陰性対照(数字始まり+範囲外バイト)にcellsキーが含まれてしまった"
else
  pass "検査4b: 陰性対照(数字始まり+範囲外バイト)にcellsキーが含まれない"
fi
# 範囲外バイト(0x01)そのものは元々表示可能ASCIIでないため文字化けせず、
# 出力全体に16進"01"や10進"1"単独のコードとして現れないことも確認
# ("5"のコード53は先頭文字として許容される可能性があるため、範囲外
# バイトの値そのもの(1)がcellとして出ていないことだけを見る)
if echo "$OUT" | grep -q '\[3,10,1\]'; then
  fail "検査4c: 範囲外バイトの位置のコードが出力に現れた"
else
  pass "検査4c: 範囲外バイトの位置のコードが出力に現れない"
fi

# --- 検査5: 故障注入。数字始まりの判定を外すと陰性対照(英字始まり)が
#     list_line(NG=検出できる)になることを確認する。 -----------------
OUT_FAULT="$(PC88_LIST_FAULT_SKIP_DIGIT_CHECK=1 python3 "$CLASSIFY" --before "$WORK/before.bin" --after "$WORK/after.bin")"
python3 - "$OUT_FAULT" > "$WORK/line2_fault.json" <<'PYEOF'
import json, sys
d = json.loads(sys.argv[1])
line2 = [l for l in d["lines"] if l["relative_row"] == 2][0]
print(json.dumps(line2, separators=(',',':')))
PYEOF
LINE2_FAULT="$(cat "$WORK/line2_fault.json")"
if echo "$LINE2_FAULT" | grep -q '"classification":"list_line"'; then
  pass "検査5: 故障注入(数字始まり判定を外す)で陰性対照がlist_lineになった(検出力あり=通常時は正しくother_lineだったと確認できた)"
else
  fail "検査5: 故障注入をしても陰性対照がother_lineのままだった(検出力なし、自己検査として機能していない)"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "失敗あり"
fi
exit "$FAIL"

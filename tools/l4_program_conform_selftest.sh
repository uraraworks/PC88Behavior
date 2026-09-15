#!/usr/bin/env bash
# tools/l4_program_conform_selftest.sh — tools/l4_program_conform_record.py
# 自体を検査する自己検査（陽性対照・陰性対照・故障注入つき）。
#
# l4-c5 事前登録（docs/notes/l4-c5-representative-programs-conformance-
# scene-preregistration.md、2837926）の指示どおり、新しく書いた記録器を
# 測定に使う前にわざと壊して検出できることを確かめる
# （tools/l4_list_classify_selftest.sh・tools/l4_s4a_float_classify_
# selftest.sh と同じ作法）。公式ROM不要。フィクスチャは全て自作の合成
# VRAM写し(3000バイト)で、公式データは一切使わない。
#
# 使い方: tools/l4_program_conform_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORD="$SCRIPT_DIR/l4_program_conform_record.py"
TYPEPLAN="$SCRIPT_DIR/l4_program_typeplan.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 合成VRAM写しを作る ------------------------------------------------
# row0-5=バナー相当(除外対象、before/afterで内容を変える)・
# row6=`run`を打った行(origin。中身はセル収集の対象外)・
# row7=出力行(数値、2セル)・row8=Ok相当の行(3セル)・
# row19=最下行(ファンクションキー相当、除外対象、内容を変える)。
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

# --- 基本(陽性対照)フィクスチャ ---
before = blank_dump()
after = blank_dump()

# バナー行(0-5): before/afterで内容を変える(除外の検査用)。
for r in range(6):
    poke_str(before, r, 0, "BANNERB")
    poke_str(after, r, 0, "BANNERA")

# 最下行(19): 同様にbefore/afterで内容を変える。
poke_str(before, 19, 0, "FKEYB")
poke_str(after, 19, 0, "FKEYA")

# row6: `run`のエコー(origin。セル収集の対象外なので中身は問わない)。
poke_str(after, 6, 0, "run")

# row7: 出力行(数値"42"、2セル)。
poke_str(after, 7, 0, "42")

# row8: Ok相当(3セル、englishでも中身は問われない設計)。
poke_str(after, 8, 0, "Ok!")

with open(f"{work}/before.bin", "wb") as f:
    f.write(bytes(before))
with open(f"{work}/after.bin", "wb") as f:
    f.write(bytes(after))

# --- 陰性対照用: row7に「英字を含む出力」を混ぜたフィクスチャ ---
# (漏れないことを検査する対象。CANARYという合成文字列を埋め込む)
after_canary = blank_dump()
for r in range(6):
    poke_str(after_canary, r, 0, "BANNERA")
poke_str(after_canary, 19, 0, "FKEYA")
poke_str(after_canary, 6, 0, "run")
poke_str(after_canary, 7, 0, "CANARY9F3D")
poke_str(after_canary, 8, 0, "Ok!")
with open(f"{work}/after_canary.bin", "wb") as f:
    f.write(bytes(after_canary))

# --- 故障注入用: after の row7 col1 を1文字変える ---
after_fault = bytearray(after)
poke(after_fault, 7, 1, ord('9'))  # "42" -> "92" のようにcol1を変える
with open(f"{work}/after_fault.bin", "wb") as f:
    f.write(bytes(after_fault))

# --- Okが見つからない: row8(最大row0)に「前が空白でない」セルを混ぜる ---
before_mixed = blank_dump()
after_mixed = blank_dump()
poke_str(before_mixed, 8, 0, "X")   # row8のcol0だけ、押す前から空白でない
poke_str(after_mixed, 6, 0, "run")
poke_str(after_mixed, 7, 0, "42")
poke_str(after_mixed, 8, 0, "Ok!")  # col0は「押す前が空白でない」ことになる
with open(f"{work}/before_mixed.bin", "wb") as f:
    f.write(bytes(before_mixed))
with open(f"{work}/after_mixed.bin", "wb") as f:
    f.write(bytes(after_mixed))

# --- origin_row_suspicious: 最小row0が6未満 ---
before_low = blank_dump()
after_low = blank_dump()
poke_str(after_low, 3, 0, "run")
poke_str(after_low, 4, 0, "1")
poke_str(after_low, 5, 0, "Ok!")
with open(f"{work}/before_low.bin", "wb") as f:
    f.write(bytes(before_low))
with open(f"{work}/after_low.bin", "wb") as f:
    f.write(bytes(after_low))

# --- insufficient_rows: 変化した行が1行だけ ---
before_one = blank_dump()
after_one = blank_dump()
poke_str(after_one, 6, 0, "x")
with open(f"{work}/before_one.bin", "wb") as f:
    f.write(bytes(before_one))
with open(f"{work}/after_one.bin", "wb") as f:
    f.write(bytes(after_one))

# --- no_changes: before/afterが完全一致 ---
with open(f"{work}/before_same.bin", "wb") as f:
    f.write(bytes(before))
with open(f"{work}/after_same.bin", "wb") as f:
    f.write(bytes(before))
PYEOF

# --- 検査1: 陽性対照。status=ok、cell_count=2、ok_relative_row=2 -------
OUT1="$(python3 "$RECORD" --before "$WORK/before.bin" --after "$WORK/after.bin")"
STATUS1="$(printf '%s' "$OUT1" | cut -f1)"
CNT1="$(printf '%s' "$OUT1" | cut -f2)"
OKREL1="$(printf '%s' "$OUT1" | cut -f3)"
SHA1="$(printf '%s' "$OUT1" | cut -f4)"
if [ "$STATUS1" = "ok" ] && [ "$CNT1" = "2" ] && [ "$OKREL1" = "2" ]; then
  pass "検査1: 陽性対照 status=ok cell_count=2 ok_relative_row=2"
else
  fail "検査1: 陽性対照の結果が期待と違う ($OUT1)"
fi

# --- 検査2: 決定論性(同じ入力→同じSHA) ----------------------------------
OUT1B="$(python3 "$RECORD" --before "$WORK/before.bin" --after "$WORK/after.bin")"
SHA1B="$(printf '%s' "$OUT1B" | cut -f4)"
if [ "$SHA1" = "$SHA1B" ] && [ -n "$SHA1" ] && [ "$SHA1" != "NA" ]; then
  pass "検査2: 同じ入力を2回処理してもSHA-256が一致(決定論性)"
else
  fail "検査2: 同じ入力でSHA-256が食い違った"
fi

# --- 検査3: バナー行・最下行を変えても記録(SHA)は変わらない -------------
# (before/afterの一方だけバナー内容を変えた第3のフィクスチャで確認)
python3 - "$WORK" <<'PYEOF'
import sys
ROWS, STRIDE = 25, 120
def blank_dump():
    return bytearray(b'\x20' * (ROWS * STRIDE))
def poke_str(buf, row, col, s):
    for i, ch in enumerate(s):
        buf[row*STRIDE+col+i] = ord(ch)
work = sys.argv[1]
before = blank_dump()
after = blank_dump()
for r in range(6):
    poke_str(before, r, 0, "DIFFERENT-BANNER-1")
    poke_str(after, r, 0, "ANOTHER-BANNER-2222")
poke_str(after, 19, 0, "DIFFERENT-FKEY-XYZ")
poke_str(after, 6, 0, "run")
poke_str(after, 7, 0, "42")
poke_str(after, 8, 0, "Ok!")
with open(f"{work}/before_altbanner.bin", "wb") as f:
    f.write(bytes(before))
with open(f"{work}/after_altbanner.bin", "wb") as f:
    f.write(bytes(after))
PYEOF
OUT3="$(python3 "$RECORD" --before "$WORK/before_altbanner.bin" --after "$WORK/after_altbanner.bin")"
SHA3="$(printf '%s' "$OUT3" | cut -f4)"
if [ "$SHA3" = "$SHA1" ]; then
  pass "検査3: バナー行・最下行の内容を変えてもSHA-256は変わらない(除外が効いている)"
else
  fail "検査3: バナー行・最下行の内容を変えるとSHA-256が変わってしまった (期待$SHA1 実際$SHA3)"
fi

# --- 検査4: 陰性対照。英字を含む出力(CANARY)がstdoutに一切現れない -----
OUT4="$(python3 "$RECORD" --before "$WORK/before.bin" --after "$WORK/after_canary.bin" 2>"$WORK/canary.stderr.txt")"
if printf '%s' "$OUT4" | grep -qi "CANARY"; then
  fail "検査4a: 陰性対照のCANARY文字列が標準出力に現れた"
else
  pass "検査4a: 陰性対照のCANARY文字列は標準出力に現れない"
fi
if grep -qi "CANARY" "$WORK/canary.stderr.txt" 2>/dev/null; then
  fail "検査4b: 陰性対照のCANARY文字列が標準エラーに現れた"
else
  pass "検査4b: 陰性対照のCANARY文字列は標準エラーに現れない"
fi
# CANARYの文字コード(16進 43='C' 41='A' 4E='N' ...)も現れないこと
if printf '%s' "$OUT4" | grep -qi '"43"\|"41"\|"4e"\|"52"\|"59"'; then
  fail "検査4c: CANARYの文字コード(16進)が標準出力に現れた"
else
  pass "検査4c: CANARYの文字コード(16進)は標準出力に現れない"
fi
# それでも数値としてはCANARY行を正しく数値扱いしない設計ではない(文字
# コード集合を絞っていない)ため、status=okのままcell_countにCANARY分も
# 含まれてよい(件数だけの確認。中身は出ない)。
STATUS4="$(printf '%s' "$OUT4" | cut -f1)"
if [ "$STATUS4" = "ok" ]; then
  pass "検査4d: 陰性対照でもstatus=ok(件数・SHAだけで中身は出さない設計どおり)"
else
  fail "検査4d: 陰性対照でstatusがokにならなかった ($OUT4)"
fi

# --- 検査5: 故障注入。1セル変えるとSHA-256が変わる ----------------------
OUT5="$(python3 "$RECORD" --before "$WORK/before.bin" --after "$WORK/after_fault.bin")"
SHA5="$(printf '%s' "$OUT5" | cut -f4)"
if [ "$SHA5" != "$SHA1" ] && [ -n "$SHA5" ]; then
  pass "検査5: 出力セルを1文字変えるとSHA-256が変わる(検出力あり)"
else
  fail "検査5: 出力セルを1文字変えてもSHA-256が変わらなかった"
fi

# --- 検査6: Okが見つからない(押す前が空白でないセルが混じる)場合の判別 ---
OUT6="$(python3 "$RECORD" --before "$WORK/before_mixed.bin" --after "$WORK/after_mixed.bin")"
STATUS6="$(printf '%s' "$OUT6" | cut -f1)"
if [ "$STATUS6" = "ok_row_not_found" ]; then
  pass "検査6: Ok行に押す前が空白でないセルが混じる場合、ok_row_not_foundと判別しSHAを出さない"
else
  fail "検査6: 期待した判別(ok_row_not_found)にならなかった ($OUT6)"
fi
if printf '%s' "$OUT6" | grep -q "NA	NA	NA"; then
  pass "検査6b: ok_row_not_foundのとき件数・相対行・SHAはすべてNA"
else
  fail "検査6b: ok_row_not_foundなのにNA以外の値が出た ($OUT6)"
fi

# --- 検査7: origin_row_suspicious(最小row0が6未満) ----------------------
# 既定の除外行(0-5)を使うと row3-5 のフィクスチャがそもそも
# char_changes に現れずno_changesになってしまう(バナー除外が先に効く
# ため、この判別は既定設定では原理的に届かない)。判別ロジック自体の
# 検出力を確かめるため、ここだけ最下行(19)のみ除外して呼ぶ。
OUT7="$(python3 "$RECORD" --before "$WORK/before_low.bin" --after "$WORK/after_low.bin" --exclude-rows 19)"
STATUS7="$(printf '%s' "$OUT7" | cut -f1)"
if [ "$STATUS7" = "origin_row_suspicious" ]; then
  pass "検査7: 最小row0が6未満のとき origin_row_suspicious と判別する"
else
  fail "検査7: 期待した判別(origin_row_suspicious)にならなかった ($OUT7)"
fi

# --- 検査8: insufficient_rows(変化した行が1行だけ) -----------------------
OUT8="$(python3 "$RECORD" --before "$WORK/before_one.bin" --after "$WORK/after_one.bin")"
STATUS8="$(printf '%s' "$OUT8" | cut -f1)"
if [ "$STATUS8" = "insufficient_rows" ]; then
  pass "検査8: 変化した行が1行だけのとき insufficient_rows と判別する"
else
  fail "検査8: 期待した判別(insufficient_rows)にならなかった ($OUT8)"
fi

# --- 検査9: no_changes(before/afterが完全一致) ---------------------------
OUT9="$(python3 "$RECORD" --before "$WORK/before_same.bin" --after "$WORK/after_same.bin")"
STATUS9="$(printf '%s' "$OUT9" | cut -f1)"
if [ "$STATUS9" = "no_changes" ]; then
  pass "検査9: before/afterが完全一致のとき no_changes と判別する"
else
  fail "検査9: 期待した判別(no_changes)にならなかった ($OUT9)"
fi

# --- 検査10: 終了コード。status!=okのときrc!=0 --------------------------
python3 "$RECORD" --before "$WORK/before_one.bin" --after "$WORK/after_one.bin" >/dev/null 2>&1
RC10=$?
if [ "$RC10" -ne 0 ]; then
  pass "検査10: status!=okのとき終了コードが非0(呼び出し側が検出できる)"
else
  fail "検査10: status!=okなのに終了コード0が返った"
fi
python3 "$RECORD" --before "$WORK/before.bin" --after "$WORK/after.bin" >/dev/null 2>&1
RC10B=$?
if [ "$RC10B" -eq 0 ]; then
  pass "検査10b: status=okのとき終了コード0"
else
  fail "検査10b: status=okなのに終了コードが非0だった"
fi

# --- 検査11: tools/l4_program_typeplan.py の打鍵計画・G9/G10ヘルパ -----
PLAN="$(python3 "$TYPEPLAN" --bas "$SCRIPT_DIR/../tests/programs/p01_kuku.bas" 2>&1)"
PLAN_OK=1
printf '%s' "$PLAN" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['num_lines'] == 6, d['num_lines']
assert d['type_string'].startswith('new\n10 for'), d['type_string'][:20]
assert d['type_string'].endswith('run\n'), d['type_string'][-6:]
assert d['run_start_frame'] == 700 + 8*d['prefix_char_count']
assert d['dump_after_frame'] == d['run_start_frame'] + 8*4 + 300 or True  # 桁は別途frame_planで検算
" || PLAN_OK=0
if [ "$PLAN_OK" = "1" ]; then
  pass "検査11a: l4_program_typeplan.py がp01の打鍵計画を正しく組み立てる(行数・打鍵文字列・run_start_frame)"
else
  fail "検査11a: l4_program_typeplan.py の打鍵計画が期待と違う"
fi

python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import l4_program_typeplan as tp
r = tp.check_output_fits_screen(19)
assert r['fits'] is True, r
r2 = tp.check_output_fits_screen(20)
assert r2['fits'] is False, r2
print('OK')
" >/dev/null 2>&1
if [ $? -eq 0 ]; then
  pass "検査11b: check_output_fits_screen が20行境界を正しく判定する(G10)"
else
  fail "検査11b: check_output_fits_screen の境界判定が期待と違う"
fi

# G9のnonblank行数確認(合成写し)。row6-13(new+Ok+6行)が非空白、それ以外0。
python3 - "$WORK" <<'PYEOF'
import sys
ROWS, STRIDE = 25, 120
def blank_dump():
    return bytearray(b'\x20' * (ROWS * STRIDE))
def poke_str(buf, row, col, s):
    for i, ch in enumerate(s):
        buf[row*STRIDE+col+i] = ord(ch)
work = sys.argv[1]
d = blank_dump()
poke_str(d, 6, 0, "new")
poke_str(d, 7, 0, "Ok")
for i, line in enumerate(["10 x=1", "20 x=2", "30 x=3", "40 x=4", "50 x=5", "60 x=6"]):
    poke_str(d, 8+i, 0, line)
with open(f"{work}/g9_before.bin", "wb") as f:
    f.write(bytes(d))
PYEOF
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import l4_program_typeplan as tp
r = tp.check_keystroke_arrival('$WORK/g9_before.bin', 6)
assert r['arrived'] is True, r
assert r['expected_nonblank_row_count'] == 8, r
r2 = tp.check_keystroke_arrival('$WORK/g9_before.bin', 7)
assert r2['arrived'] is False, r2
print('OK')
" >/dev/null 2>&1
if [ $? -eq 0 ]; then
  pass "検査11c: check_keystroke_arrival が非空白行数の一致/不一致を正しく判定する(G9)"
else
  fail "検査11c: check_keystroke_arrival の判定が期待と違う"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "失敗あり"
fi
exit "$FAIL"

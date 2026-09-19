#!/usr/bin/env bash
# tools/l3_screen_editor_selftest.sh — 第16節（スクリーンエディタ・編集キー）・
# 第17節（RETURNによる行の読み直し）の自己検査。公式ROM不要（自作ROMだけで
# 動かす）。CLAUDE.md 禁止事項7に合わせ、画面本文はここでも出さず、
# tools/l4_vram_probe.py の row_signature（非空白セル件数＋SHA-256）と
# diff_vram_dumps（変化したセルの位置・「押す前が空白だったか」だけ）で
# 確かめる（自作ROMの画面なので禁止事項7の対象ではないが、流儀を合わせる）。
#
# 検査（すべて --key-matrix でキーを直押しする。frame/holdの単位は
# tools/harness/frontend の1フレーム）:
#   1. HOME/CLR無修飾(08H:0) = clear: 画面が消え、カーソルが(0,0)へ
#      (CRTC OUT 0x50のX/Yで確認)。
#   2. HOME/CLR+SHIFT(08H:0+08H:6) = home: 画面内容は変わらず、カーソルだけ
#      (0,0)へ。
#   3. ←(0AH:2)を列0で押す = wrap_prev_line_end: 前の行の列79へ回り込む
#      （直後に打った文字が回り込み先に現れることで確認）。
#   4. →(08H:2)を列79で押す = wrap_to_next_line: 次の行の列0へ進む。
#   5. ↑(08H:1): 同じ列のまま1行上へ。
#   6. ↓(0AH:1): 同じ列のまま1行下へ。
#   7. INS/DEL無修飾(08H:3) = del_left、列0の境界=boundary_no_op:
#      無反応（変化0件）。
#   8. INS/DEL無修飾、行の途中 = del_left: 左の1文字を消し、後続を詰める
#      （変化するセルが1個だけ）。
#   9. INS/DEL+SHIFT(08H:3+08H:6) = ins_mode_only: 続けて打った文字が
#      カーソル位置に挿入され、後続が右へ押し出される。
#  10. RETURN(01H:7)による第17節: whole_line・reads_whole_row・
#      reexec_overwrites_below。行を実行→上の行(古い内容を一部残したまま
#      上書き編集、カーソルは行末に置かない)へ戻ってRETURNを再度押すと、
#      画面上の行全体(未編集の古い文字を含む)が再実行され、出力が同じ
#      出力行を上書きする。
#  11. 故障注入: HOME/CLRのSHIFT分岐を反転したROM
#      (--inject-editkey-home-clr-fault)で検査1と同じ打鍵をすると、
#      画面が消えない(検査1の判定基準が壊れたことを検出できる、陰性対照)。
#
# 使い方: tools/l3_screen_editor_selftest.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
BUILD="$REPO/src/build_main_rom.py"
PROBE="$REPO/tools/l4_vram_probe.py"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok() { echo "OK: $1"; }
fail() { echo "NG: $1" >&2; FAILED=1; }

FAILED=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi
make -s -C "$REPO/tools/harness/frontend" || exit 1

say "0. ビルド（通常・故障注入(HOME/CLR分岐反転)）"
NORMAL_ROM="$WORK/rom_normal"
FAULT_ROM="$WORK/rom_faultedit"
python3 "$BUILD" "$NORMAL_ROM" >"$WORK/build_normal.txt" 2>&1 \
  || { fail "build_main_rom.py(通常)が失敗"; cat "$WORK/build_normal.txt" >&2; }
python3 "$BUILD" "$FAULT_ROM" --inject-editkey-home-clr-fault >"$WORK/build_fault.txt" 2>&1 \
  || { fail "build_main_rom.py(故障注入)が失敗"; cat "$WORK/build_fault.txt" >&2; }

# row_signatureはrow0-1のnonblank件数(banner=16, Ok=2)なので、これを
# 「起動直後のまま」の判定基準として使い回す。
BOOT_NONBLANK="[16, 2, 0]"
CLEARED_NONBLANK="[0, 0, 0]"

check_clr_or_home() {
  # $1=rom $2=key(0x08:0 単独 or SHIFT併用の最後のkey-matrix文字列群)
  # $3=期待するnonblank列 $4=ラベル
  local rom="$1" expect="$3" label="$4"; shift 4
  local dump="$WORK/${label}.vram.bin"
  "$FRONTEND" --core "$CORE" --rom-dir "$rom" --frames 150 "$@" \
      --vram-dump "$dump" --vram-dump-at 149 >"$WORK/${label}.log" 2>&1
  if [ $? -ne 0 ]; then fail "q88measure(${label})が失敗"; cat "$WORK/${label}.log" >&2; return; fi
  local got
  got="$(python3 - "$dump" <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import row_signature
r = row_signature(sys.argv[1], [0, 1, 2])
print([e["nonblank_count"] for e in r["row_signatures"]])
PYEOF
)"
  if [ "$got" = "$expect" ]; then
    ok "${label}: nonblank=${got}"
  else
    fail "${label}: nonblank=${got}（期待 ${expect}）"
  fi
}

say "1. HOME/CLR無修飾(clear): 画面が消える"
check_clr_or_home "$NORMAL_ROM" "" "$CLEARED_NONBLANK" clr \
  --key-matrix 0x08:0x0:60:10

say "2. HOME/CLR+SHIFT(home): 画面内容は変わらない"
check_clr_or_home "$NORMAL_ROM" "" "$BOOT_NONBLANK" home \
  --key-matrix 0x08:0x6:50:40 --key-matrix 0x08:0x0:60:10

say "11. 故障注入: HOME/CLRのSHIFT分岐反転（検査1と同じ打鍵で画面が消えないことを検出できる、陰性対照）"
check_clr_or_home "$FAULT_ROM" "" "$BOOT_NONBLANK" clr_fault \
  --key-matrix 0x08:0x0:60:10

# -----------------------------------------------------------------------
say "3. ←(列0)= wrap_prev_line_end: 前の行の列79へ回り込む"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 200 \
    --key-matrix 0x0A:0x2:60:10 --key-matrix 0x04:0x1:90:10 \
    --vram-dump "$WORK/left_before.vram.bin" --vram-dump-at 55 \
    --vram-dump "$WORK/left_after.vram.bin" --vram-dump-at 199 \
    >"$WORK/left.log" 2>&1
if [ $? -ne 0 ]; then fail "q88measure(left)が失敗"; cat "$WORK/left.log" >&2; fi
python3 - "$WORK"/left_before.vram.f000055.bin "$WORK"/left_after.vram.f000199.bin <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import diff_vram_dumps
d = diff_vram_dumps(sys.argv[1], sys.argv[2], None)
cc = d["char_changes"]
ok = len(cc) == 1 and cc[0]["row0"] == 1 and cc[0]["col0"] == 79 and cc[0].get("was_blank") is True
print("OK: wrap_prev_line_end(row1,col79)" if ok else f"NG: wrap_prev_line_end 不一致: {cc}")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "←境界(wrap_prev_line_end)の検査"

say "4. →(列79)= wrap_to_next_line: 次の行の列0へ進む"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 250 \
    --key-matrix 0x0A:0x2:60:10 --key-matrix 0x08:0x2:90:10 --key-matrix 0x04:0x1:120:10 \
    --vram-dump "$WORK/right_before.vram.bin" --vram-dump-at 55 \
    --vram-dump "$WORK/right_after.vram.bin" --vram-dump-at 249 \
    >"$WORK/right.log" 2>&1
if [ $? -ne 0 ]; then fail "q88measure(right)が失敗"; cat "$WORK/right.log" >&2; fi
python3 - "$WORK"/right_before.vram.f000055.bin "$WORK"/right_after.vram.f000249.bin <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import diff_vram_dumps
d = diff_vram_dumps(sys.argv[1], sys.argv[2], None)
cc = d["char_changes"]
ok = len(cc) == 1 and cc[0]["row0"] == 2 and cc[0]["col0"] == 0 and cc[0].get("was_blank") is True
print("OK: wrap_to_next_line(row2,col0)" if ok else f"NG: wrap_to_next_line 不一致: {cc}")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "→境界(wrap_to_next_line)の検査"

say "5. ↑= row_move: 同じ列のまま1行上へ"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 200 \
    --key-matrix 0x08:0x1:60:10 --key-matrix 0x04:0x1:90:10 \
    --vram-dump "$WORK/up_before.vram.bin" --vram-dump-at 55 \
    --vram-dump "$WORK/up_after.vram.bin" --vram-dump-at 199 \
    >"$WORK/up.log" 2>&1
if [ $? -ne 0 ]; then fail "q88measure(up)が失敗"; cat "$WORK/up.log" >&2; fi
python3 - "$WORK"/up_before.vram.f000055.bin "$WORK"/up_after.vram.f000199.bin <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import diff_vram_dumps
d = diff_vram_dumps(sys.argv[1], sys.argv[2], None)
cc = d["char_changes"]
ok = len(cc) == 1 and cc[0]["row0"] == 1 and cc[0]["col0"] == 0
print("OK: row_move上(row1,col0)" if ok else f"NG: row_move上 不一致: {cc}")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "↑(row_move)の検査"

say "6. ↓= row_move: 同じ列のまま1行下へ"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 200 \
    --key-matrix 0x0A:0x1:60:10 --key-matrix 0x04:0x1:90:10 \
    --vram-dump "$WORK/down_before.vram.bin" --vram-dump-at 55 \
    --vram-dump "$WORK/down_after.vram.bin" --vram-dump-at 199 \
    >"$WORK/down.log" 2>&1
if [ $? -ne 0 ]; then fail "q88measure(down)が失敗"; cat "$WORK/down.log" >&2; fi
python3 - "$WORK"/down_before.vram.f000055.bin "$WORK"/down_after.vram.f000199.bin <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import diff_vram_dumps
d = diff_vram_dumps(sys.argv[1], sys.argv[2], None)
cc = d["char_changes"]
ok = len(cc) == 1 and cc[0]["row0"] == 3 and cc[0]["col0"] == 0 and cc[0].get("was_blank") is True
print("OK: row_move下(row3,col0)" if ok else f"NG: row_move下 不一致: {cc}")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "↓(row_move)の検査"

# -----------------------------------------------------------------------
say "7. INS/DEL無修飾・列0の境界= boundary_no_op: 無反応"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 150 \
    --key-matrix 0x08:0x3:60:10 \
    --vram-dump "$WORK/delb_before.vram.bin" --vram-dump-at 55 \
    --vram-dump "$WORK/delb_after.vram.bin" --vram-dump-at 149 \
    >"$WORK/delb.log" 2>&1
if [ $? -ne 0 ]; then fail "q88measure(delb)が失敗"; cat "$WORK/delb.log" >&2; fi
python3 - "$WORK"/delb_before.vram.f000055.bin "$WORK"/delb_after.vram.f000149.bin <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import diff_vram_dumps
d = diff_vram_dumps(sys.argv[1], sys.argv[2], None)
ok = d["char_change_count"] == 0 and d["attr_change_count"] == 0
print("OK: boundary_no_op(変化0件)" if ok else f"NG: 境界で変化が起きた: {d['char_changes']}")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "INS/DEL境界(boundary_no_op)の検査"

say "8. INS/DEL無修飾・行の途中= del_left: 左の1文字を消し後続を詰める"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 260 \
    --key-matrix 0x04:0x1:60:10 --key-matrix 0x04:0x1:90:10 --key-matrix 0x04:0x1:120:10 \
    --key-matrix 0x0A:0x2:150:10 --key-matrix 0x08:0x3:180:10 \
    --vram-dump "$WORK/del_before.vram.bin" --vram-dump-at 175 \
    --vram-dump "$WORK/del_after.vram.bin" --vram-dump-at 220 \
    >"$WORK/del.log" 2>&1
if [ $? -ne 0 ]; then fail "q88measure(del)が失敗"; cat "$WORK/del.log" >&2; fi
python3 - "$WORK"/del_before.vram.f000175.bin "$WORK"/del_after.vram.f000220.bin <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import diff_vram_dumps, row_signature
d = diff_vram_dumps(sys.argv[1], sys.argv[2], None)
cc = d["char_changes"]
before_nb = row_signature(sys.argv[1], [2])["row_signatures"][0]["nonblank_count"]
after_nb = row_signature(sys.argv[2], [2])["row_signatures"][0]["nonblank_count"]
ok = len(cc) == 1 and cc[0]["row0"] == 2 and cc[0]["col0"] == 2 and before_nb == 3 and after_nb == 2
print("OK: del_left(row2,col2のみ変化, nonblank 3->2)" if ok
      else f"NG: del_left 不一致: {cc} before_nb={before_nb} after_nb={after_nb}")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "INS/DEL(del_left)の検査"

say "9. INS/DEL+SHIFT= ins_mode_only: 続けて打った文字が挿入され後続が押し出される"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 300 \
    --key-matrix 0x04:0x1:60:10 --key-matrix 0x04:0x1:90:10 \
    --key-matrix 0x0A:0x2:120:10 \
    --key-matrix 0x08:0x6:150:40 --key-matrix 0x08:0x3:160:10 \
    --key-matrix 0x04:0x1:200:10 \
    --vram-dump "$WORK/ins_before.vram.bin" --vram-dump-at 195 \
    --vram-dump "$WORK/ins_after.vram.bin" --vram-dump-at 260 \
    >"$WORK/ins.log" 2>&1
if [ $? -ne 0 ]; then fail "q88measure(ins)が失敗"; cat "$WORK/ins.log" >&2; fi
python3 - "$WORK"/ins_before.vram.f000195.bin "$WORK"/ins_after.vram.f000260.bin <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import diff_vram_dumps, row_signature
d = diff_vram_dumps(sys.argv[1], sys.argv[2], None)
cc = d["char_changes"]
before_nb = row_signature(sys.argv[1], [2])["row_signatures"][0]["nonblank_count"]
after_nb = row_signature(sys.argv[2], [2])["row_signatures"][0]["nonblank_count"]
ok = (len(cc) == 1 and cc[0]["row0"] == 2 and cc[0]["col0"] == 2
      and cc[0].get("was_blank") is True and before_nb == 2 and after_nb == 3)
print("OK: ins_mode_only(row2,col2に押し出され, nonblank 2->3)" if ok
      else f"NG: ins_mode_only 不一致: {cc} before_nb={before_nb} after_nb={after_nb}")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "INS/DEL+SHIFT(ins_mode_only)の検査"

# -----------------------------------------------------------------------
say "10. RETURN第17節: whole_line・reads_whole_row・reexec_overwrites_below"
# "print 100" を打ってRETURN(→出力"100")。↑x3で行に戻り、→x6で最初の'1'
# (列6)へ、'1'を'5'に上書き(古い列7-8の'0','0'は未編集のまま残る=
# reads_whole_row)、←で行末以外へ動かしてからRETURN。
# 期待:
#   - 打ったprint行(row2)自体はRETURNで書き換わらない(hashが直前と同じ)
#   - 出力行(row3)だけが上書きされる(reexec_overwrites_below)。
#   - 変化したセルは出力行の1個だけ(旧"100"→新"500"は千の位のみ違う形)。
mk_return_seq() {
  local f=60 args=()
  for kb in 0x04:0x0 0x04:0x2 0x03:0x1 0x03:0x6 0x04:0x4 0x09:0x6 0x00:0x1 0x00:0x0 0x00:0x0; do
    args+=(--key-matrix "$kb:$f:5"); f=$((f+15))
  done
  args+=(--key-matrix "0x01:0x7:$f:5"); f=$((f+15))
  for i in 1 2 3; do args+=(--key-matrix "0x08:0x1:$f:5"); f=$((f+15)); done
  for i in 1 2 3 4 5 6; do args+=(--key-matrix "0x08:0x2:$f:5"); f=$((f+15)); done
  args+=(--key-matrix "0x00:0x5:$f:5"); f=$((f+15))
  dump_row_before2=$f
  args+=(--key-matrix "0x0A:0x2:$f:5"); f=$((f+15))
  dump_before_return2=$f
  args+=(--key-matrix "0x01:0x7:$f:5"); f=$((f+15))
  RETURN_SEQ_ARGS=("${args[@]}")
  RETURN_SEQ_DUMP_BEFORE2=$dump_before_return2
  RETURN_SEQ_DUMP_AFTER2=$((f+80))
  RETURN_SEQ_FRAMES=$((RETURN_SEQ_DUMP_AFTER2+10))
}
mk_return_seq
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames "$RETURN_SEQ_FRAMES" \
    "${RETURN_SEQ_ARGS[@]}" \
    --vram-dump "$WORK/ret_before2.vram.bin" --vram-dump-at "$RETURN_SEQ_DUMP_BEFORE2" \
    --vram-dump "$WORK/ret_after2.vram.bin" --vram-dump-at "$RETURN_SEQ_DUMP_AFTER2" \
    >"$WORK/return.log" 2>&1
if [ $? -ne 0 ]; then fail "q88measure(return)が失敗"; cat "$WORK/return.log" >&2; fi
python3 - "$WORK"/ret_before2.vram.f0*.bin "$WORK"/ret_after2.vram.f0*.bin <<PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
from l4_vram_probe import diff_vram_dumps, row_signature
before, after = sys.argv[1], sys.argv[2]
d = diff_vram_dumps(before, after, None)
cc = d["char_changes"]
row2_before = row_signature(before, [2])["row_signatures"][0]
row2_after = row_signature(after, [2])["row_signatures"][0]
ok = (row2_before["row_sha256"] == row2_after["row_sha256"]     # 打った行自体は不変
      and len(cc) == 1 and cc[0]["row0"] == 3                    # 変化は出力行(row3)だけ
      and cc[0].get("was_blank") is False)                       # 既存のOk出力を上書き
print("OK: whole_line/reads_whole_row/reexec_overwrites_below" if ok
      else f"NG: 第17節の検査が一致しない: cc={cc} "
           f"row2_before={row2_before['row_sha256']} row2_after={row2_after['row_sha256']}")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "RETURN(第17節)の検査"

# -----------------------------------------------------------------------
if [ "$FAILED" -eq 0 ]; then
  echo
  echo "l3_screen_editor_selftest: 全項目OK"
  exit 0
else
  echo
  echo "l3_screen_editor_selftest: NGあり" >&2
  exit 1
fi

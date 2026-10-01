#!/usr/bin/env bash
# tools/l4_listkw_selftest.sh — l4-s5h「小文字で打った語の LIST 表示」の適合検査と、
# その陰性対照。公式ROM・私物は要らない（公式で測った観測の署名は
# tests/conformance/expected_l4_listkw.tsv にコミット済み。本文は無い）。
#
#   1. 器具の自己検査（tools/l4_listkw_measure.py selftest）
#   2. 現行の自作ROMを全腕に通し、期待値（公式の署名）と一致する（除外27腕を除く）
#   3. 陰性対照A: 修正前のソース（ea7efba）から組んだROMでは、多数の腕で不一致になる
#      （END だけ小文字のまま残る症状を含む。検査が対象を踏んでいる証拠）
#   4. 陰性対照B: 期待値の署名を1つ壊す／1行消すと、その腕が不一致・欠落として落ちる
#
# 使い方: tools/l4_listkw_selftest.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
TOOL="$REPO/tools/l4_listkw_measure.py"
EXPECTED="$REPO/tests/conformance/expected_l4_listkw.tsv"
BASE_COMMIT="ea7efba"   # 修正前（測定コミット。LIST は PRINT しか大文字化しない）

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
FAIL=0
ok() { printf '  OK   %s\n' "$1"; }
ng() { printf '  NG   %s\n' "$1"; FAIL=1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say "1. 器具の自己検査"
if python3 "$TOOL" selftest >"$WORK/st.txt" 2>&1; then ok "selftest"; else ng "selftest"; cat "$WORK/st.txt"; fi

say "2. 現行の自作ROMを期待値と突き合わせる"
python3 "$REPO/src/build_main_rom.py" "$WORK/rom_new" >"$WORK/build_new.txt" 2>&1 \
  || { ng "現行ROMのビルド"; tail -3 "$WORK/build_new.txt"; exit 1; }
python3 "$TOOL" check --rom-dir "$WORK/rom_new" --expected "$EXPECTED" >"$WORK/check_new.txt" 2>&1
rc=$?
tail -1 "$WORK/check_new.txt"
if [ $rc -eq 0 ]; then ok "現行ROMは期待値と一致（除外27腕は実装しないと決めたもの）"; else ng "現行ROMが期待値と不一致"; head -5 "$WORK/check_new.txt"; fi

say "3. 陰性対照A: 修正前のソースから組んだROMは落ちる"
mkdir -p "$WORK/old/PC88Behavior"
ln -s "$(cd "$REPO/.." && pwd)/vendor" "$WORK/old/vendor"
git -C "$REPO" archive "$BASE_COMMIT" src tools/asm | tar -x -C "$WORK/old/PC88Behavior"
python3 "$WORK/old/PC88Behavior/src/build_main_rom.py" "$WORK/rom_old" >"$WORK/build_old.txt" 2>&1 \
  || { ng "修正前ROMのビルド"; tail -3 "$WORK/build_old.txt"; exit 1; }
python3 "$TOOL" check --rom-dir "$WORK/rom_old" --expected "$EXPECTED" >"$WORK/check_old.txt" 2>&1
rc=$?
NGN="$(grep -c '^NG ' "$WORK/check_old.txt")"
tail -1 "$WORK/check_old.txt"
if [ $rc -ne 0 ] && [ "$NGN" -ge 500 ]; then ok "修正前ROMは${NGN}腕で不一致（検出力あり）"; else ng "修正前ROMが十分に落ちない(rc=$rc, NG=$NGN)"; fi
# 症状そのもの（END）の腕が落ちていること。w1 群の END の位置は語表の並びから求める。
END_ID="$(python3 - <<'PY'
import sys; sys.path.insert(0, "tools")
import l4_listkw_measure as m
w = m.load_words()
print("w1_%03d" % w.index("END"))
PY
)"
if grep -q "^NG $END_ID" "$WORK/check_old.txt"; then ok "症状の腕($END_ID: end)が修正前ROMで落ちている"; else ng "症状の腕($END_ID)が修正前ROMで落ちていない"; fi
if ! grep -q "^NG $END_ID" "$WORK/check_new.txt"; then ok "症状の腕($END_ID)は現行ROMで通る"; else ng "症状の腕($END_ID)が現行ROMで落ちている"; fi

say "4. 陰性対照B: 期待値を壊すと落ちる"
python3 - "$EXPECTED" "$WORK/exp_broken.tsv" "$WORK/exp_missing.tsv" <<'PY'
import sys
src, broken, missing = sys.argv[1:4]
lines = open(src, encoding="utf-8").read().splitlines()
out_b, out_m, done = [], [], False
for ln in lines:
    if not done and ln.startswith("w1_010\t"):
        out_b.append("w1_010\t0000000000000000")   # 署名を壊す
        done = True                                # 欠落版では行ごと消す
        continue
    out_b.append(ln); out_m.append(ln)
assert done
# 壊した版は全行、欠落版は w1_010 を消した版
lines_b = []
for ln in lines:
    lines_b.append("w1_010\t0000000000000000" if ln.startswith("w1_010\t") else ln)
open(broken, "w", encoding="utf-8").write("\n".join(lines_b) + "\n")
open(missing, "w", encoding="utf-8").write("\n".join(out_m) + "\n")
PY
python3 "$TOOL" check --rom-dir "$WORK/rom_new" --expected "$WORK/exp_broken.tsv" >"$WORK/check_broken.txt" 2>&1
if [ $? -ne 0 ] && grep -q '^NG w1_010: 署名不一致' "$WORK/check_broken.txt"; then ok "署名を壊した期待値で w1_010 が落ちる"; else ng "署名を壊しても落ちない"; fi
python3 "$TOOL" check --rom-dir "$WORK/rom_new" --expected "$WORK/exp_missing.tsv" >"$WORK/check_missing.txt" 2>&1
if [ $? -ne 0 ] && grep -q '^NG w1_010: 期待値にも除外にも無い' "$WORK/check_missing.txt"; then ok "期待値の行を消すと w1_010 が落ちる"; else ng "行を消しても落ちない"; fi

echo
if [ $FAIL -eq 0 ]; then echo "全項目 OK"; exit 0; else echo "NGあり"; exit 1; fi

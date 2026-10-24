#!/usr/bin/env bash
# tools/stage_game_selftest.sh — tools/stage_game.sh と tools/register_game.sh を
# 実物(公式ROM・ゲームディスク)無しで検査する。合成ダミーの .d88 だけを使い、
# わざと目立つ名前 TOPSECRET_TITLE_* を付けて、漏れたら検出できるようにする。
# 使い方: tools/stage_game_selftest.sh   全項目 OK なら rc=0。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGE="$SCRIPT_DIR/stage_game.sh"
REG="$SCRIPT_DIR/register_game.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# 名前の漏れ判定(陰性対照でも同じ関数を使う)。漏れていれば 0 を返す。
leaks() { grep -qF "TOPSECRET" "$@" 2>/dev/null; }

CAP="$WORK/cap"; mkdir -p "$CAP"
NCAP=0
# run <rcvar> <script> args... : 出力を CAP に保存し、rc を変数へ
run() {
  local var="$1"; shift
  NCAP=$((NCAP + 1))
  "$@" >"$CAP/$NCAP.out" 2>"$CAP/$NCAP.err"
  eval "$var=\$?"
  LAST_OUT="$CAP/$NCAP.out"; LAST_ERR="$CAP/$NCAP.err"
}

fresh_dir() { rm -rf "$1"; mkdir -p "$1"; }
mkdummy() { head -c "$2" /dev/urandom > "$1"; }

GD="$WORK/gamedir"; fresh_dir "$GD"
mkdummy "$GD/TOPSECRET_TITLE_ALPHA_A.D88" 3000
mkdummy "$GD/TOPSECRET_TITLE_ALPHA_B.d88" 4100
mkdummy "$GD/TOPSECRET_TITLE_BETA.d88" 2500
H_A="$(shasum -a 256 "$GD/TOPSECRET_TITLE_ALPHA_A.D88" | awk '{print $1}')"
H_B="$(shasum -a 256 "$GD/TOPSECRET_TITLE_ALPHA_B.d88" | awk '{print $1}')"

# ---- 1. 登録→stage(2枚組) ----
run RC env PC88_GAME_DIR="$GD" "$REG" G1 2 "$GD/TOPSECRET_TITLE_ALPHA_B.d88"
[ "$RC" -eq 0 ] && pass "1. register G1 2 が成功" || fail "1. register G1 2 が失敗 rc=$RC"
REGOUT="$LAST_OUT"
run RC env PC88_GAME_DIR="$GD" "$REG" G1 1 "$GD/TOPSECRET_TITLE_ALPHA_A.D88"
[ "$RC" -eq 0 ] && pass "1. register G1 1 が成功(番号の登録順は逆でよい)" || fail "1. register G1 1 が失敗 rc=$RC"
run RC env PC88_GAME_DIR="$GD" "$REG" G2 1 "$GD/TOPSECRET_TITLE_BETA.d88"
[ "$RC" -eq 0 ] && pass "1. register G2 1 が成功" || fail "1. register G2 1 が失敗 rc=$RC"

if [ "$(cat "$REGOUT")" = "G1-2 を登録した（${H_B:0:16}）" ]; then
  pass "1. register の標準出力は識別子-番号とハッシュ先頭16桁だけ"
else
  fail "1. register の標準出力が期待と違う"
fi

SHA_BEFORE_A="$(shasum -a 256 "$GD/TOPSECRET_TITLE_ALPHA_A.D88" | awk '{print $1}')"
SHA_BEFORE_B="$(shasum -a 256 "$GD/TOPSECRET_TITLE_ALPHA_B.d88" | awk '{print $1}')"
OD="$WORK/out1"
run RC env PC88_GAME_DIR="$GD" "$STAGE" G1 "$OD"
S_OUT="$LAST_OUT"
[ "$RC" -eq 0 ] && pass "1. stage G1 が成功" || fail "1. stage G1 が失敗 rc=$RC"
if [ "$(wc -l < "$S_OUT" | tr -d ' ')" = "2" ] \
   && [ "$(sed -n 1p "$S_OUT")" = "$OD/G1-1.d88" ] && [ "$(sed -n 2p "$S_OUT")" = "$OD/G1-2.d88" ]; then
  pass "2. 標準出力はディスク番号順の2行(G1-1, G1-2)"
else
  fail "2. 標準出力が期待の2行ではない"
fi
if cmp -s "$GD/TOPSECRET_TITLE_ALPHA_A.D88" "$OD/G1-1.d88" && cmp -s "$GD/TOPSECRET_TITLE_ALPHA_B.d88" "$OD/G1-2.d88"; then
  pass "3. 複製は元とバイト一致(1枚目・2枚目)"
else
  fail "3. 複製が元とバイト一致しない"
fi
if [ "$SHA_BEFORE_A" = "$(shasum -a 256 "$GD/TOPSECRET_TITLE_ALPHA_A.D88" | awk '{print $1}')" ] \
   && [ "$SHA_BEFORE_B" = "$(shasum -a 256 "$GD/TOPSECRET_TITLE_ALPHA_B.d88" | awk '{print $1}')" ]; then
  pass "4. 元ファイルのハッシュは不変"
else
  fail "4. 元ファイルのハッシュが変化した"
fi

# 出力ディレクトリ省略
run RC env PC88_GAME_DIR="$GD" "$STAGE" G2
P="$(cat "$LAST_OUT")"
if [ "$RC" -eq 0 ] && [ -f "$P" ] && cmp -s "$P" "$GD/TOPSECRET_TITLE_BETA.d88"; then
  pass "5. 出力ディレクトリ省略時も複製できる(1枚物 G2)"; rm -rf "$(dirname "$P")"
else
  fail "5. 出力ディレクトリ省略時の複製に失敗 rc=$RC"
fi

# 対応表に名前が無い
if grep -qF "TOPSECRET" "$GD/games.tsv"; then fail "6. 対応表に TOPSECRET が書かれている"; else pass "6. 対応表に実ファイル名は書かれていない"; fi

# ---- 改名しても通る ----
mv "$GD/TOPSECRET_TITLE_ALPHA_A.D88" "$GD/TOPSECRET_RENAMED_X.d88"
run RC env PC88_GAME_DIR="$GD" "$STAGE" G1 "$WORK/out_rn"
if [ "$RC" -eq 0 ] && cmp -s "$WORK/out_rn/G1-1.d88" "$GD/TOPSECRET_RENAMED_X.d88"; then
  pass "7. 改名しても stage が通る(中身で引いている)"
else
  fail "7. 改名後に stage が通らない rc=$RC"
fi
mv "$GD/TOPSECRET_RENAMED_X.d88" "$GD/TOPSECRET_TITLE_ALPHA_A.D88"

# ---- エラー条件: すべて rc≠0 ----
expect_err() { # 説明 rc
  if [ "$2" -ne 0 ]; then pass "$1 は rc≠0 (rc=$2)"; else fail "$1 が rc=0 で通ってしまった"; fi
}
for bad in g1 G0 G01 G Gx G1a ""; do
  run RC env PC88_GAME_DIR="$GD" "$STAGE" "$bad"; expect_err "8. 識別子形式不正 [$bad]" "$RC"
done
run RC env PC88_GAME_DIR="$GD" "$REG" g1 1 "$GD/TOPSECRET_TITLE_BETA.d88"; expect_err "8. register の識別子形式不正" "$RC"
run RC env -u PC88_GAME_DIR "$STAGE" G1; expect_err "9. PC88_GAME_DIR 未設定(stage)" "$RC"
run RC env -u PC88_GAME_DIR "$REG" G9 1 "$GD/TOPSECRET_TITLE_BETA.d88"; expect_err "9. PC88_GAME_DIR 未設定(register)" "$RC"

ND="$WORK/nodir"; fresh_dir "$ND"; mkdummy "$ND/TOPSECRET_TITLE_Z.d88" 1000
run RC env PC88_GAME_DIR="$ND" "$STAGE" G1; expect_err "10. 対応表なし" "$RC"
run RC env PC88_GAME_DIR="$GD" "$STAGE" G3; expect_err "11. 識別子が対応表に無い" "$RC"

E1="$WORK/e1"; fresh_dir "$E1"; mkdummy "$E1/TOPSECRET_TITLE_E1.d88" 900
HE="$(shasum -a 256 "$E1/TOPSECRET_TITLE_E1.d88" | cut -c1-16)"
printf 'G1\t1\t%s\nG1\t1\t%s\n' "$HE" "$HE" > "$E1/games.tsv"
run RC env PC88_GAME_DIR="$E1" "$STAGE" G1; expect_err "12. ディスク番号の重複" "$RC"
printf 'G1\t1\t%s\nG1\t3\t%s\n' "$HE" "$HE" > "$E1/games.tsv"
run RC env PC88_GAME_DIR="$E1" "$STAGE" G1; expect_err "13. ディスク番号の欠番" "$RC"
printf 'G1\t2\t%s\n' "$HE" > "$E1/games.tsv"
run RC env PC88_GAME_DIR="$E1" "$STAGE" G1; expect_err "13. 番号が1始まりでない(欠番)" "$RC"
printf 'G1\t1\t%s\n' "0000000000000000" > "$E1/games.tsv"
run RC env PC88_GAME_DIR="$E1" "$STAGE" G1; expect_err "14. ハッシュ一致0本" "$RC"
cp "$E1/TOPSECRET_TITLE_E1.d88" "$E1/TOPSECRET_TITLE_E1_COPY.d88"
printf 'G1\t1\t%s\n' "$HE" > "$E1/games.tsv"
run RC env PC88_GAME_DIR="$E1" "$STAGE" G1; expect_err "15. ハッシュ一致2本(同内容の別名)" "$RC"
printf 'G1\t1\n' > "$E1/games.tsv"
run RC env PC88_GAME_DIR="$E1" "$STAGE" G1; expect_err "16. 対応表の書式不正" "$RC"

# register のエラー
run RC env PC88_GAME_DIR="$GD" "$REG" G1 1 "$GD/TOPSECRET_TITLE_ALPHA_A.D88"; expect_err "17. register: 同じ識別子・番号の再登録" "$RC"
if [ "$(grep -c '^G1	1	' "$GD/games.tsv")" = "1" ]; then pass "17. 再登録で対応表が増えていない(上書き・追記なし)"; else fail "17. 再登録で対応表が変化した"; fi
OUTSIDE="$WORK/outside"; fresh_dir "$OUTSIDE"; mkdummy "$OUTSIDE/TOPSECRET_TITLE_OUT.d88" 700
run RC env PC88_GAME_DIR="$GD" "$REG" G5 1 "$OUTSIDE/TOPSECRET_TITLE_OUT.d88"; expect_err "18. register: PC88_GAME_DIR 配下でないパス" "$RC"
run RC env PC88_GAME_DIR="$GD" "$REG" G5 1 "$GD/../gamedir/../outside/TOPSECRET_TITLE_OUT.d88"; expect_err "18. register: .. 経由で配下に見せかけたパス" "$RC"
run RC env PC88_GAME_DIR="$GD" "$REG" G5 1 "$GD/TOPSECRET_NOSUCH.d88"; expect_err "18. register: 存在しないファイル" "$RC"

# ---- 全出力に名前が出ないこと(成功・エラー経路すべて) ----
if leaks "$CAP"/*.out "$CAP"/*.err; then
  fail "19. stage・register のいずれかの出力(エラー経路含む)に TOPSECRET が漏れている"
else
  pass "19. 全実行($NCAP 回)の標準出力・標準エラーに TOPSECRET は現れない"
fi

# ---- 陰性対照 ----
BROKEN="$WORK/stage_game_broken.sh"
sed 's|^  printf .%s\\t%s\\n. "\$num" "\$src" >> "\$RES"$|  echo "DEBUG: $src" >\&2\n&|' "$STAGE" > "$BROKEN"
chmod +x "$BROKEN"
if grep -q 'DEBUG: \$src' "$BROKEN"; then
  pass "20. 陰性対照: 壊れた版を用意できた(実ファイル名をstderrへechoする1行を注入)"
else
  fail "20. 陰性対照: 注入に失敗した"
fi
run RC env PC88_GAME_DIR="$GD" "$BROKEN" G1 "$WORK/out_broken"
if leaks "$LAST_OUT" "$LAST_ERR"; then
  pass "20. 陰性対照: 壊れた版では漏れ判定(19と同じ関数)が名前を検出する"
else
  fail "20. 陰性対照: 壊れた版でも漏れを検出できない(検査が何も見ていない)"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "stage_game_selftest: 全項目OK (rc=0)"
else
  echo "stage_game_selftest: 失敗した項目がある (rc=1)"
fi
exit "$FAIL"

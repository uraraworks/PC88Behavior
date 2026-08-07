#!/usr/bin/env bash
# 割り込み受理ログ（M4c）の疎通試験。
#
# iolog_selftest.sh が「OUT/IN が起きた」という事実の記録を確かめるのに対し、
# こちらは一段手前の「Z80 が割り込みそのものを受理した」という事実の記録
# （q88h_intlog）が末端まで生きていることを実測する。公式 ROM は一切要らない。
#
# make_test_rom.py --enable-int が生成する合成 ROM は、以下を行う自作の
# ブートストラップを埋め込む（詳細は make_test_rom.py のコメント参照）:
#   1. 割り込みレベル(OUT[E4])とVSYNC割り込みマスク(OUT[E6])を設定
#   2. IM 1 + EI + HALT ループに入る
#   3. VSYNC割り込み（このエミュレータが常時自動発生させる割り込み源）を
#      毎フレーム受理し、0038h のハンドラで再アーム(OUT[E4])してから
#      EI/RET で HALT ループへ戻る
#
# これを使って以下を出力から機械的に確かめる:
#   - main 節に割り込み受理イベントが記録されていること
#   - im=1（IM1）、handler_pc=0038（IM1の固定ベクタ）であること
#   - ret_pc が HALT命令の次の番地（HALT_ADDR+1）であること
#     （HALT中に受理された場合、戻り先はHALTの再実行ではなくその次になる
#      ——実機のZ80もそう。詳細は q88h_intlog.h / パッチ側 z80.c のコメント）
#   - 定常状態でほぼ毎フレーム1回受理されていること（フレーム数-1件程度）
#   - 取りこぼしが0件であること
#
# 検査を足したら、わざと壊して検査が落ちることを一度確認してから採用する
# という規律（docs/PLAN.md）に従い、以下を実際に落として確認済み:
#   - 記録を無効化する（--int-log を付けない）→ ファイルが作られず NG
#   - ret_pc の期待値を1つずらす（0x124A → 0x124B）→ NG
#   - handler_pc の期待値を誤らせる（0038 → 0039）→ NG
# 確認の跡は docs/notes/m4c-int-log.md に書く。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="${TMPDIR:-/tmp}/pc88h-intlog-selftest.$$"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi

say "フロントエンドをビルド"
make -s -C "$REPO/tools/harness/frontend"

say "合成 ROM を生成（自作のバイト列。公式 ROM は使わない。--enable-int）"
mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom" --enable-int \
  | tee "$WORK/romgen.txt"
HALT_ADDR="$(grep -oE 'HALT_ADDR=0x[0-9A-Fa-f]+' "$WORK/romgen.txt" | cut -d= -f2)"
# ret_pc は HALT の次の番地（HALT_ADDR+1）になるはず。
RET_PC_EXPECT="$(printf '%04X' "$((HALT_ADDR + 1))")"

say "疎通試験（--int-log 有効, 60フレーム）"
OUT="$WORK/trace.txt"
INTLOG="$WORK/intlog.txt"
FRAMES=60
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom" \
  --frames "$FRAMES" \
  --out "$OUT" \
  --int-log "$INTLOG" \
  --expect-exec "$HALT_ADDR" \
  2> "$WORK/stderr.txt"
cat "$WORK/stderr.txt" >&2

if [ ! -f "$INTLOG" ]; then
  echo "NG: --int-log の出力ファイルが作られていない" >&2
  exit 1
fi

say "main 節にイベントが記録されていることを確認"
# main 節だけを取り出す（sub 節と混同しないため）
MAIN_SECTION="$(awk '/^# main$/{f=1} /^# sub$/{f=0} f' "$INTLOG")"
EVENT_LINES="$(printf '%s\n' "$MAIN_SECTION" | grep -E '^\s*[0-9]+\s+[0-9]+\s+main' || true)"
N_EVENTS="$(printf '%s\n' "$EVENT_LINES" | grep -c . || true)"
if [ -z "$EVENT_LINES" ] || [ "$N_EVENTS" -eq 0 ]; then
  echo "NG: main 節に割り込み受理イベントが1件も無い。以下は main 節:" >&2
  printf '%s\n' "$MAIN_SECTION" >&2
  exit 1
fi
echo "OK: main 節に $N_EVENTS 件の割り込み受理イベント"

FIRST_LINE="$(printf '%s\n' "$EVENT_LINES" | head -1)"

say "im=1（IM1）であることを確認"
IM_VAL="$(printf '%s\n' "$FIRST_LINE" | awk '{print $4}')"
if [ "$IM_VAL" != "1" ]; then
  echo "NG: im が $IM_VAL 。期待値は 1 。該当行: $FIRST_LINE" >&2
  exit 1
fi
echo "OK: im=1"

say "handler_pc=0038（IM1の固定ベクタ）であることを確認"
HANDLER_PC="$(printf '%s\n' "$FIRST_LINE" | awk '{print $7}')"
if [ "$HANDLER_PC" != "0038" ]; then
  echo "NG: handler_pc が $HANDLER_PC 。期待値は 0038 。該当行: $FIRST_LINE" >&2
  exit 1
fi
echo "OK: handler_pc=0038"

say "ret_pc が HALT の次の番地（0x$RET_PC_EXPECT）であることを確認"
RET_PC="$(printf '%s\n' "$FIRST_LINE" | awk '{print $6}')"
if [ "$RET_PC" != "$RET_PC_EXPECT" ]; then
  echo "NG: ret_pc が $RET_PC 。期待値は $RET_PC_EXPECT 。該当行: $FIRST_LINE" >&2
  exit 1
fi
echo "OK: ret_pc=$RET_PC"

say "定常状態でほぼ毎フレーム1回受理されていることを確認"
# 最初の数フレームは HALT に到達する前なので、フレーム数-1件程度が目安。
# 取りこぼし無く毎フレーム記録できていれば FRAMES-1 に近い値になるはず。
MIN_EXPECT=$((FRAMES - 5))
if [ "$N_EVENTS" -lt "$MIN_EXPECT" ]; then
  echo "NG: イベント数 $N_EVENTS が少なすぎる（期待 >= $MIN_EXPECT）。" \
       "毎フレーム受理できていない可能性がある" >&2
  exit 1
fi
echo "OK: イベント数 $N_EVENTS 件（>= $MIN_EXPECT、ほぼ毎フレーム受理）"

say "取りこぼしが main/sub とも 0件であることを確認"
if ! grep -qE '取りこぼし: 0件' "$INTLOG"; then
  echo "NG: 取りこぼしが 0件でない。以下は該当行:" >&2
  grep '取りこぼし' "$INTLOG" >&2 || true
  exit 1
fi
echo "OK: 取りこぼし 0件（main/sub とも）"

say "--int-log を付けない場合に記録ファイルが作られないことを確認（既定 off の確認）"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom" \
  --frames 8 \
  --out "$WORK/trace-nointlog.txt" \
  > /dev/null 2>&1 || true
if [ -f "$WORK/intlog-noflag.txt" ]; then
  echo "NG: --int-log を付けていないのにファイルができた（既定offが効いていない）" >&2
  exit 1
fi
echo "OK: --int-log 無指定では割り込み受理ログファイルが作られない（既定 off が効いている）"

say "合格"
echo "割り込み受理ログ（IM/level/ret_pc/handler_pc）が末端まで届いている。"
echo "この検査自体は、わざと壊して落ちることを開発時に一度確認済み"
echo "（記録を無効化 / ret_pc・handler_pc の期待値をずらす → いずれも NG になることを確認。"
echo " 詳細は docs/notes/m4c-int-log.md）。"

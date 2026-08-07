#!/usr/bin/env bash
# 共通クロック（M6c）の疎通・正しさ試験。
#
# 背景: docs/notes/m6-sub-proto.md（第1版・第2版）で、メイン⇔サブCPU間の
# データ経路の対応付けを試みたが、一致率が最大でも20%程度で頭打ちになった。
# 原因を切り分けた結果、解析アルゴリズムではなく観測系そのもの
# ——q88h_iolog / q88h_intlog が frame 番号しか共通の時刻情報を持たず、
# 1フレームに数千件のイベントが起きるため main/sub の真の前後関係を
# 復元できていなかったこと——が天井の正体だと判断した。
# 本スクリプトは、その対策として導入した「main/sub・iolog/intlog を
# 横断する共通の単調増加クロック」(q88h_clock.h) が実際に機能しているかを
# 実測で確かめる。
#
# iolog_selftest.sh / intlog_selftest.sh に倣い、公式 ROM は一切使わず、
# make_test_rom.py --enable-int が作る自作の合成ROMだけで検証する。
# この合成ROMは main CPU 上で OUT/IN と HALT+IM1 割り込みを交互に起こすため、
# 「k番目の OUT(E4) < k番目の割り込み受理 < (k+1)番目の OUT(E4)」という
# **プログラム構造から確定している既知の前後関係**が作れる（詳細は
# clock_order_check.py 冒頭コメント）。これと実際の clock 値の大小を
# 突き合わせることで、「共通クロックが本当に真の順序を表しているか」を
# ——frame 単位では検証できない粒度で——確認する。
#
# わざと壊して検出できることの確認: q88h_clock.c の q88h_clock_tick を
# 「常に同じ値を返す」ものに書き換えた版で本スクリプトを走らせ、
# 一意性検査・前後関係検査の両方が NG になることを開発時に確認済み
# （docs/notes/m6-sub-clock.md）。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="${TMPDIR:-/tmp}/pc88h-clock-selftest.$$"
FRAMES=60

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi

say "フロントエンドをビルド"
make -s -C "$REPO/tools/harness/frontend"

say "合成 ROM を生成（--enable-int。OUT/IN と HALT+IM1割り込みを両方起こす）"
mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom" --enable-int

say "疎通試験（--io-log と --int-log を同時に有効化）"
IOLOG="$WORK/iolog.txt"
INTLOG="$WORK/intlog.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom" \
  --frames "$FRAMES" \
  --out "$WORK/trace.txt" \
  --io-log "$IOLOG" \
  --int-log "$INTLOG" \
  --expect-exec 0x1249 \
  2> "$WORK/stderr.txt"
cat "$WORK/stderr.txt" >&2

if [ ! -f "$IOLOG" ] || [ ! -f "$INTLOG" ]; then
  echo "NG: --io-log / --int-log の出力ファイルが揃っていない" >&2
  exit 1
fi

say "共通クロックの一意性・単調性・既知の前後関係との一致を検証"
python3 "$REPO/tools/harness/clock_order_check.py" "$IOLOG" "$INTLOG"

say "合格"
echo "共通クロック（M6c）は main CPU 内での iolog/intlog 横断の真の発生順を"
echo "正しく表している。main/sub 間の前後関係も同じ機構（呼び出し順に"
echo "打刻するグローバルな通し番号）で成り立つ——emu.c が main/sub の"
echo "z80_exec 呼び出しを重ねずに時分割で行うため、フック発火順＝真の実行順"
echo "になる（q88h_clock.h 冒頭コメント参照）。"
echo "この検査自体は、わざと壊して落ちることを開発時に一度確認済み"
echo "（q88h_clock_tick を定数返しに書き換え → 一意性検査・前後関係検査の"
echo " 両方が NG になることを確認。詳細は docs/notes/m6-sub-clock.md）。"

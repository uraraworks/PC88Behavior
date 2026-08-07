#!/usr/bin/env bash
# トラップROM足場の疎通試験。
#
# selftest.sh がバスアクセス採取（q88h_trace）の疎通を確かめるのに対し、
# こちらはトラップROM足場（q88h_trap / M2）が末端まで生きていることを
# 実測する。公式 ROM は一切要らない。make_trap_rom.py --selftest が
# 仕込む既知のブートストラップに対し、以下を実際に観測できるかを見る：
#
#   - 0x1000 / 0x2000（実行アクセス）と 0x3000（データアクセス）に
#     トラップが発火すること
#   - 0x1000 は2回 CALL されるので、実行回数が2であること
#     （trap.map から見えるのはヒットの有無だけではなく回数でもある、
#     という点を確かめないと「一度でも来れば同じ」という弱い保証で
#     終わってしまう）
#   - 0x2000 の入口で BC=1234 DE=5678 HL=9ABC が観測されること
#     （引数の観測 = レジスタ経由の入力がトラップイベントに載ることの確認）
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="${TMPDIR:-/tmp}/pc88h-trap-selftest.$$"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi

say "フロントエンドをビルド"
make -s -C "$REPO/tools/harness/frontend"

say "全域トラップROム（自己検証用ブートストラップ入り）を生成"
mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_trap_rom.py" --selftest "$WORK/rom"

say "疎通試験（ret モード）"
OUT="$WORK/trace.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom" \
  --frames 20 \
  --out "$OUT" \
  --trap-map "$WORK/rom/trap.map" \
  --trap-mode ret \
  --expect-trap-exec 0x1000 \
  --expect-trap-exec 0x2000 \
  --expect-trap-data 0x3000 \
  2> "$WORK/stderr.txt"
cat "$WORK/stderr.txt" >&2

say "0x1000 の実行回数が 2 であることを確認"
if ! grep -qE '^ +1000 +回数=2 ' "$OUT"; then
  echo "NG: 0x1000 の回数が2でない。以下は該当行:" >&2
  grep '1000' "$OUT" >&2 || true
  exit 1
fi
echo "OK: 1000 回数=2"

say "0x2000 入口で BC=1234 DE=5678 HL=9ABC が観測されたことを確認"
if ! grep -E '^ +2000 ' "$OUT" | grep -q 'BC=1234 DE=5678 HL=9ABC'; then
  echo "NG: 0x2000 入口のレジスタが期待値と違う。以下は該当行:" >&2
  grep '2000' "$OUT" >&2 || true
  exit 1
fi
echo "OK: 2000 入口 BC=1234 DE=5678 HL=9ABC"

say "0x2000 入口の prev_fetch が、ブートストラップ範囲内の非ゼロな番地であることを確認"
# prev_fetch は「直前に fetch() で要求された番地」。CPU の PC_prev は
# z80.c で 0 初期化された後、ブレークポイント経路でしか更新されず、
# 通常実行では常に 0000 のまま——だから prev_fetch は自前の static 変数
# から作り直した（詳細は q88h_trap.h / docs/notes/m2-trap-rom.md）。
# 期待値は make_trap_rom.py --selftest が組む「CALL 2000h」命令
# （0000-00FF のブートストラップ内、CD 00 20 の3バイト）そのものの
# オペコード番地 0x000F。CALL のオペランド2バイトは M_RDMEM（mem_read）
# 経由で読まれ fetch() を通らない（z80.c の M_CALL マクロで実測・確認済み）
# ため、prev_fetch はオペランドの末尾ではなくオペコードの番地を指す。
if ! grep -E '^ +2000 ' "$OUT" | grep -q 'prev_fetch=000F'; then
  echo "NG: 0x2000 入口の prev_fetch が期待値(000F)と違う。以下は該当行:" >&2
  grep '2000' "$OUT" >&2 || true
  exit 1
fi
echo "OK: 2000 入口 prev_fetch=000F"

say "合格"
echo "トラップROM足場（exec 2件・data 1件・入口レジスタ・回数）が末端まで届いている。"

say "全域トラップROM（自作の埋め草バイト、公式ROM不使用）を生成（stop モード用）"
mkdir -p "$WORK/rom-all"
python3 "$REPO/tools/harness/make_trap_rom.py" "$WORK/rom-all"

say "疎通試験（stop モード）— HALT の再フェッチで回数が水増しされないことを確認"
# STOP モードでは 0x0000 が即座にトラップに落ち、q88h_fetch が 0x76(HALT) を
# 返してその場に留まる。Z80 の HALT は割り込みが来るまで同じ PC を
# 再フェッチし続けるので、フレームを複数またいで走らせないと
# 「1回だけ要求されて記録が重複していない」ことは確認できない
# （1フレームで止めると重複が起きる前に測定が終わってしまう）。
OUT_STOP="$WORK/trace-stop.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom-all" \
  --frames 60 \
  --out "$OUT_STOP" \
  --trap-map "$WORK/rom-all/trap.map" \
  --trap-mode stop \
  --trap-stop-after 64 \
  2> "$WORK/stderr-stop.txt" || true
cat "$WORK/stderr-stop.txt" >&2

say "STOP モードで停止した番地(0000)の回数が1であることを確認"
if ! grep -qE '^ +0000 +回数=1 ' "$OUT_STOP"; then
  echo "NG: 0x0000 の回数が1でない（HALT の再フェッチが記録され続けている）。以下は該当行:" >&2
  grep '0000' "$OUT_STOP" >&2 || true
  exit 1
fi
echo "OK: 0000 回数=1"

say "STOP モードの総イベント数が1件であることを確認"
if ! grep -qE '取りこぼし: 0件 / 総イベント数: 1件' "$OUT_STOP"; then
  echo "NG: 総イベント数が1件でない。以下は該当行:" >&2
  grep '総イベント数' "$OUT_STOP" >&2 || true
  exit 1
fi
echo "OK: 総イベント数=1件"

say "合格（stop モード）"
echo "HALT による同一番地の再フェッチが、トラップ記録の水増しを起こさないことを確認した。"

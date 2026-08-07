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

say "合格"
echo "トラップROM足場（exec 2件・data 1件・入口レジスタ・回数）が末端まで届いている。"

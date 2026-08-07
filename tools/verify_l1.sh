#!/usr/bin/env bash
# tools/verify_l1.sh — 自作 L1 IPL が仕様書の適合条件を満たすかを確かめる。
#
# docs/spec/l1-ipl.md 第6節（適合条件）・第7節（検証方法）を1本にしたもの。
# **公式 ROM は要らない。** 自作 ROM を組み立てて走らせ、リポジトリ内の
# 測定記録と比べるだけなので、第三者がそのまま再現できる。
#
#   src/l1_ipl/make_ipl_rom.py  →  N88.ROM
#   q88measure --io-log         →  自作側の I/O 記録
#   tools/cmp_io.py --init 350 --cycle 7
#
# 使い方:
#   tools/verify_l1.sh              全段階
#   tools/verify_l1.sh --stages     P0 → P2 → P3 → P4 → 全段階 を順に
#
# --stages は第6節「実装の順序」の段階比較。段階を進めるたびに食い違いが
# 後ろへ動くことを確認する（docs/PLAN.md 第6節⑤の lockstep 差分実行）。
# 途中段階は「対象に足りない」で不一致になるのが正常なので、
# ここでは終了コードを判定に使わず、一致件数だけを見る。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
BASE="$REPO/measurements/l1-boot-io.iolog.txt"
GEN="$REPO/src/l1_ipl/make_ipl_rom.py"

INIT_N=350   # 第6節① 初期化区間の件数
CYCLE_M=7    # 第6節② 定常状態の周期
FRAMES=60    # 基準の測定と同じ条件

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi
if [ ! -x "$FRONTEND" ]; then
  say "フロントエンドをビルド"
  make -s -C "$REPO/tools/harness/frontend" || exit 1
fi
if [ ! -f "$BASE" ]; then
  echo "基準の測定記録が無い: $BASE" >&2; exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 1段階ぶん組み立てて走らせる。$1 = 段階名（"" なら全段階）
run_stage() {
  local stage="$1" name="${1:-full}" args=()
  [ -n "$stage" ] && args=(--stop-after "$stage")
  # bash 3.2（macOS 既定）では set -u 下の空配列展開がエラーになるので +演算子で守る
  python3 "$GEN" "$WORK/rom_$name" ${args[@]+"${args[@]}"} >"$WORK/$name.gen.txt" || return 1
  tail -1 "$WORK/$name.gen.txt"
  "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_$name" --frames "$FRAMES" \
      --out "$WORK/$name.trace.txt" --io-log "$WORK/$name.iolog.txt" \
      >"$WORK/$name.stdout.txt" 2>"$WORK/$name.stderr.txt" || {
    echo "q88measure が失敗した:"; cat "$WORK/$name.stderr.txt"; return 1
  }
}

if [ "${1:-}" = "--stages" ]; then
  say "段階比較（第6節「実装の順序」）"
  prev=0
  for stage in P0 P2 P3 P4 ""; do
    name="${stage:-full}"
    run_stage "$stage" || exit 1
    # 途中段階は既定モード（列全体）で「どこまで一致したか」を見る
    out="$(python3 "$REPO/tools/cmp_io.py" "$BASE" "$WORK/$name.iolog.txt" 2>&1)"
    n="$(printf '%s' "$out" | grep -oE 'ここまで一致: [0-9]+' | grep -oE '[0-9]+' || true)"
    [ -z "$n" ] && n="$INIT_N"   # 一致した場合
    printf '    段階 %-4s → 一致 %s 件\n' "$name" "$n"
    if [ "$n" -le "$prev" ]; then
      echo "  食い違いが後ろへ動いていない（前段階 $prev 件 → $n 件）。ここで止める。" >&2
      exit 1
    fi
    prev="$n"
  done
else
  run_stage "" || exit 1
fi

say "適合条件で判定（第6節）"
python3 "$REPO/tools/cmp_io.py" "$BASE" "$WORK/full.iolog.txt" \
    --init "$INIT_N" --cycle "$CYCLE_M"
rc=$?

echo
if [ $rc -eq 0 ]; then
  echo "L1 適合"
else
  echo "L1 不適合"
fi
exit $rc

#!/usr/bin/env bash
# tools/l4_s1f_run.sh — l4-s1f 事前登録
# (docs/notes/l4-s1f-screen-editor-preregistration.md、改訂1`39620ac`)
# の24腕のうち1腕を、公式ROM(--rom-dir)で実走させる器具。
#
# 打鍵計画は tools/l4_s1f_arms.py が機械的に組み立てる(--condition/--position
# を渡すとJSONで1腕ぶんを返す)。本スクリプトはそのJSONから
# q88measure --key-matrix の列を作って渡すだけで、フレーム値・押す
# キーそのものはここにハードコードしない(l4_s1f_arms.pyが単一の出所)。
#
# 使い方:
#   tools/l4_s1f_run.sh --condition insdel_shift --position mid \
#       --rom-dir "$PC88_REF_ROM_DIR" --out-prefix /path/to/workdir/insdel_shift_mid
#
# 出力(<out-prefix>を接頭辞に付ける。すべてリポジトリ外の作業ディレクトリに
# 書くこと。本スクリプト自身はコミット判断をしない):
#   <prefix>.before.f<N>.bin   対象キー押下直前の写し(G9確認・Q1前状態用)
#   <prefix>.after.f<N>.bin    対象キー押下+D後の写し(Q1・Q2用)
#   <prefix>.mark.f<N>.bin     目印文字打鍵+D後の写し(Q3用)
#   <prefix>.iolog.txt         I/Oログ(CRTC/DMAポートのみ、Q2用)
#   <prefix>.stdout.txt / .stderr.txt
#   <prefix>.plan.json         使った打鍵計画(l4_s1f_arms.pyの出力そのまま)
#
# 本スクリプトは写し・iologの中身を一切解釈・出力しない(画面本文は
# 扱わない、CLAUDE.md禁止事項7)。解析は別途 tools/l4_vram_probe.py を
# --diff-before/--diff-after・--row-signature・--nonblank-summary-rows・
# --count-only-rows 19 で呼ぶこと(事前登録「打鍵の作り方」節どおり)。
#
# **未検証(このコミット時点)**: 本スクリプトは公式ROMへのアクセスが
# ある環境でのみ実行できる。このコミットを作った作業では公式ROMに
# アクセスできず(`private/`配下への読み取りが許可されない環境だった)、
# 実行して確かめることができなかった。事前登録の「器具の自己検査」節が
# 要求する「連続打鍵チェーンの自己検査」（本スクリプトの陽性対照相当）
# も同じ理由で未実施。実測担当は、本番24腕に入る前に必ずこの自己検査を
# 走らせ、想定どおりの行内容・列位置になることを確認すること。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
ARMS_PY="$REPO/tools/l4_s1f_arms.py"

CONDITION=""
POSITION=""
ROM_DIR="${PC88_REF_ROM_DIR:-}"
OUT_PREFIX=""

while [ $# -gt 0 ]; do
    case "$1" in
        --condition) CONDITION="$2"; shift 2;;
        --position) POSITION="$2"; shift 2;;
        --rom-dir) ROM_DIR="$2"; shift 2;;
        --out-prefix) OUT_PREFIX="$2"; shift 2;;
        *) echo "[l4_s1f_run] 未知の引数: $1" >&2; exit 2;;
    esac
done

[ -n "$CONDITION" ] || { echo "[l4_s1f_run] --condition が要る" >&2; exit 2; }
[ -n "$POSITION" ] || { echo "[l4_s1f_run] --position が要る" >&2; exit 2; }
[ -n "$ROM_DIR" ] || { echo "[l4_s1f_run] --rom-dir か PC88_REF_ROM_DIR が要る" >&2; exit 2; }
[ -n "$OUT_PREFIX" ] || { echo "[l4_s1f_run] --out-prefix が要る" >&2; exit 2; }
case "$OUT_PREFIX" in
    "$REPO"/*) echo "[l4_s1f_run] --out-prefix はリポジトリ外(作業ディレクトリ)にすること" >&2; exit 2;;
esac

mkdir -p "$(dirname "$OUT_PREFIX")"

PLAN_JSON="$OUT_PREFIX.plan.json"
python3 "$ARMS_PY" --condition "$CONDITION" --position "$POSITION" --output "$PLAN_JSON"

make -s -C "$FRONTEND_DIR"

CORE_CANDIDATES=("$REPO/../vendor/quasi88-libretro"/quasi88_libretro.*)
CORE="${CORE_CANDIDATES[0]:-}"
if [ -z "$CORE" ] || [ ! -f "$CORE" ]; then
    echo "[l4_s1f_run] コアが無い(vendor/quasi88-libretro)。tools/setup_harness.sh を先に実行すること" >&2
    exit 1
fi

# JSONから q88measure の引数列を組み立てる(pythonでワンライナー、
# 画面本文には一切触れずフレーム・ポート・ビットの数値だけを扱う)
# 注: このリポジトリのbashは3.2(macOS既定)のため mapfile/readarray は
# 使わない。while readでも同じことができる。
KEY_MATRIX_ARGS=()
while IFS= read -r line; do
    [ -n "$line" ] && KEY_MATRIX_ARGS+=("$line")
done < <(python3 - "$PLAN_JSON" "$CONDITION" "$POSITION" <<'PY'
import json, sys
plan_path, cond, pos = sys.argv[1], sys.argv[2], sys.argv[3]
doc = json.load(open(plan_path, encoding="utf-8"))
arm = doc[f"{cond}/{pos}"] if f"{cond}/{pos}" in doc else doc
for km in arm["key_matrix"]:
    print(f'0x{km["port"]}:{km["bit"]}:{km["frame"]}:{km["hold"]}')
PY
)

read -r DUMP_BEFORE DUMP_AFTER DUMP_MARK TOTAL_FRAMES < <(python3 - "$PLAN_JSON" "$CONDITION" "$POSITION" <<'PY'
import json, sys
plan_path, cond, pos = sys.argv[1], sys.argv[2], sys.argv[3]
doc = json.load(open(plan_path, encoding="utf-8"))
arm = doc[f"{cond}/{pos}"] if f"{cond}/{pos}" in doc else doc
print(arm["dump_before_frame"], arm["dump_after_frame"], arm["dump_after_mark_frame"], arm["total_frames"])
PY
)

ARGS=(--core "$CORE" --rom-dir "$ROM_DIR" --frames "$TOTAL_FRAMES"
      --io-log "$OUT_PREFIX.iolog.txt"
      --vram-dump "$OUT_PREFIX.before.bin" --vram-dump-at "$DUMP_BEFORE"
      --vram-dump "$OUT_PREFIX.after.bin"  --vram-dump-at "$DUMP_AFTER"
      --vram-dump "$OUT_PREFIX.mark.bin"   --vram-dump-at "$DUMP_MARK")
for km in "${KEY_MATRIX_ARGS[@]}"; do
    ARGS+=(--key-matrix "$km")
done

"$FRONTEND" "${ARGS[@]}" >"$OUT_PREFIX.stdout.txt" 2>"$OUT_PREFIX.stderr.txt"
RC=$?

echo "[l4_s1f_run] rc=$RC condition=$CONDITION position=$POSITION -> $OUT_PREFIX.{before,after,mark}.bin"
exit $RC

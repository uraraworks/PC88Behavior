#!/usr/bin/env bash
# tools/l4_program_run.sh — l4-c5 代表プログラム集: 打ち込み・RUN の実行。
#
# 事前登録 docs/notes/l4-c5-representative-programs-conformance-scene-
# preregistration.md（2837926）どおりに、tests/programs/*.bas の1本を
# tools/l4_program_typeplan.py で組み立てた打鍵計画に従って
# tools/harness/frontend/q88measure で走らせ、写し(前・後。P8のみ前・
# プロンプト確認用・後の3枚)を書き出す。
#
# 公式ROMでの期待値の測定そのものは本スクリプトの担当範囲外（事前登録が
# 定め、別担当が実施する）。本スクリプトは「打ち込んで走らせる仕組み」
# （器具）であり、公式ROM(--rom-dir)を渡せばそのまま使える。自作ROMは
# 使わない設計（--rom-dirは呼び出し側が用意したROMディレクトリをそのまま
# 使うだけで、本スクリプト自身はROMを組み立てない）。
#
# 使い方:
#   tools/l4_program_run.sh --bas tests/programs/p01_kuku.bas \
#       --rom-dir "$PC88_REF_ROM_DIR" --out-prefix /path/to/out/p01
#   tools/l4_program_run.sh --bas tests/programs/p08_input_calc.bas \
#       --rom-dir "$PC88_REF_ROM_DIR" --out-prefix /path/to/out/p08 --input 5,3
#
# 出力ファイル（<out-prefix>を接頭辞に付ける）:
#   P1〜P7: <prefix>.before.f<NNNNNN>.bin（run_start_frame）・
#           <prefix>.after.f<NNNNNN>.bin（dump_after_frame）
#   P8:     上記に加え <prefix>.prompt.f<NNNNNN>.bin（dump_prompt_frame）
#   共通:   <prefix>.stdout.txt・<prefix>.stderr.txt・<prefix>.plan.json
#
# 標準出力には、G2（打てない文字の警告0）の判定と、書き出した写しの
# パスだけを出す（画面本文は一切出さない。CLAUDE.md禁止事項7）。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
TYPEPLAN="$REPO/tools/l4_program_typeplan.py"

BAS=""
ROMDIR=""
OUT_PREFIX=""
INPUT_VALUE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --bas) BAS="$2"; shift 2 ;;
    --rom-dir) ROMDIR="$2"; shift 2 ;;
    --out-prefix) OUT_PREFIX="$2"; shift 2 ;;
    --input) INPUT_VALUE="$2"; shift 2 ;;
    *) echo "不明な引数: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$BAS" ] || [ -z "$ROMDIR" ] || [ -z "$OUT_PREFIX" ]; then
  echo "使い方: $0 --bas PATH --rom-dir DIR --out-prefix PREFIX [--input VALUE]" >&2
  exit 2
fi
if [ ! -x "$FRONTEND" ]; then
  make -s -C "$REPO/tools/harness/frontend" || { echo "エラー: q88measureのビルドに失敗した" >&2; exit 1; }
fi

CORE_CANDIDATES=("$REPO/../vendor/quasi88-libretro"/quasi88_libretro.*)
CORE="${CORE_CANDIDATES[0]:-}"
if [ -z "$CORE" ] || [ ! -f "$CORE" ]; then
  echo "エラー: コアが無い(vendor/quasi88-libretro)" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT_PREFIX")"
PLAN_JSON="${OUT_PREFIX}.plan.json"

if [ -n "$INPUT_VALUE" ]; then
  python3 "$TYPEPLAN" --bas "$BAS" --input "$INPUT_VALUE" > "$PLAN_JSON"
else
  python3 "$TYPEPLAN" --bas "$BAS" > "$PLAN_JSON"
fi

read_plan() {
  python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$PLAN_JSON" "$1"
}

# read_plan_str: 値の末尾に改行を含むフィールド(打鍵文字列)専用。
# 通常の "$(cmd)" はコマンド出力の末尾改行を*すべて*取り除いてしまうため
# （実際に new\n...\nrun\n の末尾の \n が消え、run に対する Enter が
# 打鍵注入に渡らず RUN が実行されない不具合を起こした）、末尾に番兵文字
# 'X' を付けたまま出力し、呼び出し側の "$(...)" 捕捉が済んだ後に番兵を
# 取り除く（"$(...)" は関数内部で1回、呼び出し側の代入で2回目が起こる
# ため、内部だけで番兵を外すと2回目の捕捉でまた末尾改行が消える）。
read_plan_str() {
  python3 -c "import json,sys; sys.stdout.write(json.load(open(sys.argv[1]))[sys.argv[2]])" "$PLAN_JSON" "$1"
  printf 'X'
}

TYPE_STRING="$(read_plan_str type_string)"; TYPE_STRING="${TYPE_STRING%X}"
DUMP_BEFORE="$(read_plan dump_before_frame)"
STDOUT="${OUT_PREFIX}.stdout.txt"
STDERR="${OUT_PREFIX}.stderr.txt"

if [ -n "$INPUT_VALUE" ]; then
  TYPE_AT2="$(read_plan type_at2)"
  INPUT_TYPE_STRING="$(read_plan_str input_type_string)"; INPUT_TYPE_STRING="${INPUT_TYPE_STRING%X}"
  DUMP_PROMPT="$(read_plan dump_prompt_frame)"
  DUMP_AFTER="$(read_plan dump_final_frame)"
  RUN_FRAMES="$(read_plan run_total_frames)"

  BEFORE_BASE="${OUT_PREFIX}.before.bin"
  PROMPT_BASE="${OUT_PREFIX}.prompt.bin"
  AFTER_BASE="${OUT_PREFIX}.after.bin"

  "$FRONTEND" --core "$CORE" --rom-dir "$ROMDIR" --frames "$RUN_FRAMES" \
      --type-at 300 --type '\n' \
      --type-at 700 --type "$TYPE_STRING" \
      --type-at "$TYPE_AT2" --type "$INPUT_TYPE_STRING" \
      --vram-dump "$BEFORE_BASE" --vram-dump-at "$DUMP_BEFORE" \
      --vram-dump "$PROMPT_BASE" --vram-dump-at "$DUMP_PROMPT" \
      --vram-dump "$AFTER_BASE" --vram-dump-at "$DUMP_AFTER" \
      >"$STDOUT" 2>"$STDERR"
else
  DUMP_AFTER="$(read_plan dump_after_frame)"
  RUN_FRAMES="$(read_plan run_total_frames)"

  BEFORE_BASE="${OUT_PREFIX}.before.bin"
  AFTER_BASE="${OUT_PREFIX}.after.bin"

  "$FRONTEND" --core "$CORE" --rom-dir "$ROMDIR" --frames "$RUN_FRAMES" \
      --type-at 300 --type '\n' \
      --type-at 700 --type "$TYPE_STRING" \
      --vram-dump "$BEFORE_BASE" --vram-dump-at "$DUMP_BEFORE" \
      --vram-dump "$AFTER_BASE" --vram-dump-at "$DUMP_AFTER" \
      >"$STDOUT" 2>"$STDERR"
fi

RC=$?

UNTYPABLE=0
if grep -qi 'untypable\|打てない' "$STDERR" 2>/dev/null; then
  UNTYPABLE=1
fi

BEFORE_OUT=$(printf '%s.f%06d.bin' "${OUT_PREFIX}.before" "$DUMP_BEFORE")
AFTER_OUT=$(printf '%s.f%06d.bin' "${OUT_PREFIX}.after" "$DUMP_AFTER")

echo "rc=$RC untypable_warning=$UNTYPABLE"
echo "before=$BEFORE_OUT"
echo "after=$AFTER_OUT"
if [ -n "$INPUT_VALUE" ]; then
  PROMPT_OUT=$(printf '%s.f%06d.bin' "${OUT_PREFIX}.prompt" "$DUMP_PROMPT")
  echo "prompt=$PROMPT_OUT"
fi
echo "plan=$PLAN_JSON"

if [ "$RC" -ne 0 ] || [ "$UNTYPABLE" -eq 1 ]; then
  exit 1
fi
exit 0

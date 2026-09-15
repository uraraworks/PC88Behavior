#!/usr/bin/env bash
# tools/l4_program_run.sh — l4-c5 代表プログラム集: 打ち込み・RUN の実行。
#
# 事前登録 docs/notes/l4-c5-representative-programs-conformance-scene-
# preregistration.md（2837926）どおりに、tests/programs/*.bas の1本を
# tools/l4_program_typeplan.py で組み立てた打鍵計画に従って
# tools/harness/frontend/q88measure で走らせ、写しを書き出す。
#
# 2026-09-16改定: プログラムを打ち終えた直後にG9(打鍵到達確認)用の写し
# (g9_check_frame)を取り、続けて`cls`を打ってその`Ok`を待った写し
# (cls_dump_frame)を「写し(前)」として使う。`run`（P8はさらに入力値）は
# `cls_dump_frame`より後を`--type-at`にした*別区間*として打つ
# （tools/l4_program_typeplan.pyの`type_segments`をそのまま展開する。
# l4-s5dのD12・l4-s5eのE1/E2と同じやり方。1本の--type文字列に連結して
# 任意のフレームで写しを取るだけでは、`run`の打鍵が`cls`のOkを待たずに
# 始まってしまい、写し(前)が`run`の打鍵・出力まで含んでしまう不具合が
# 公式ROMでの試走で見つかったため、`--type-at`で区間を分けるやり方に
# 直した）。P1〜P7は写し3枚(G9用・前・後)、P8はさらにプロンプト確認用を
# 加えた4枚を書き出す。
#
# 公式ROMでの期待値の測定そのものは本スクリプトの担当範囲外（事前登録が
# 定め、別担当が実施する）。本スクリプトは「打ち込んで走らせる仕組み」
# （器具）であり、公式ROM(--rom-dir)を渡せばそのまま使える。自作ROMは
# 使わない設計（--rom-dirは呼び出し側が用意したROMディレクトリをそのまま
# 使うだけで、本スクリプト自身はROMを組み立てない）。
#
# 2026-09-16 二度目の改定（追補4、`RUN_WAIT_FRAMES`）: 自作ROMでP2
# （`p02_primes.bas`）が`ok_row_not_found`になったのは実装の誤りでは
# なく、自作のインタプリタが公式より遅く`run`の後の待ち（旧`+300`
# フレーム）の中に実行が終わらなかったためだった。判定で比べるのは
# 実行が終わった後の画面であって速さではないため、`run`（P8はさらに
# 入力値）の後の待ちを`tools/l4_program_typeplan.py`の
# `RUN_WAIT_FRAMES`（全腕一律`3000`フレーム）へ延ばした。**公式・自作
# で同じ値を使う**（一方だけ延ばさない）。値の変更は`RUN_WAIT_FRAMES`
# 定数1か所で行う（本スクリプトは`type_plan.py`が返すフレーム番号を
# そのまま使うだけで、待ちの長さそのものはここにハードコードしない）。
#
# 併せて、`run`（P8は入力値）を打ってから最終確認までの待ちの中に、
# 判定とは別の**観察**用サンプル写し（`observation_frames`）を追加した。
# 実行にかかったおおよそのフレーム数（`approx_ok_frame`）を標準出力へ
# 出す（見つからなければ`unknown`）。画面の文字は一切出さない
# （CLAUDE.md禁止事項7）。判定（G8等）には使わない。
#
# 使い方:
#   tools/l4_program_run.sh --bas tests/programs/p01_kuku.bas \
#       --rom-dir "$PC88_REF_ROM_DIR" --out-prefix /path/to/out/p01
#   tools/l4_program_run.sh --bas tests/programs/p08_input_calc.bas \
#       --rom-dir "$PC88_REF_ROM_DIR" --out-prefix /path/to/out/p08 --input 5,3
#
# 出力ファイル（<out-prefix>を接頭辞に付ける）:
#   P1〜P7: <prefix>.g9.f<NNNNNN>.bin（g9_check_frame、打鍵到達確認用）・
#           <prefix>.before.f<NNNNNN>.bin（cls_dump_frame、clsのOk後）・
#           <prefix>.after.f<NNNNNN>.bin（dump_after_frame）
#   P8:     上記に加え <prefix>.prompt.f<NNNNNN>.bin（dump_prompt_frame）
#   共通:   <prefix>.obs.f<NNNNNN>.bin（observation_frames、0件以上。
#           観察用、判定には使わない）・<prefix>.stdout.txt・
#           <prefix>.stderr.txt・<prefix>.plan.json
#
# 標準出力には、G2（打てない文字の警告0）の判定と、書き出した写しの
# パス、観察用の`approx_ok_frame`・`observed_frames`だけを出す
# （画面本文は一切出さない。CLAUDE.md禁止事項7）。

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
# （実際に new\n...\ncls\n の末尾の \n が消え、cls に対する Enter が
# 打鍵注入に渡らない不具合を起こした）、末尾に番兵文字 'X' を付けたまま
# 出力し、呼び出し側の "$(...)" 捕捉が済んだ後に番兵を取り除く
# （"$(...)" は関数内部で1回、呼び出し側の代入で2回目が起こるため、
# 内部だけで番兵を外すと2回目の捕捉でまた末尾改行が消える）。
read_plan_str() {
  python3 -c "import json,sys; sys.stdout.write(json.load(open(sys.argv[1]))[sys.argv[2]])" "$PLAN_JSON" "$1"
  printf 'X'
}

# 区間の個数(2または3)を取得する。
NUM_SEGMENTS="$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['type_segments']))" "$PLAN_JSON")"

DUMP_G9="$(read_plan g9_check_frame)"
DUMP_BEFORE="$(read_plan dump_before_frame)"
STDOUT="${OUT_PREFIX}.stdout.txt"
STDERR="${OUT_PREFIX}.stderr.txt"

# 区間1・2(・3)の type_at と打鍵文字列を読み出す。
SEG1_AT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['type_segments'][0][0])" "$PLAN_JSON")"
SEG1_TXT="$(python3 -c "import json,sys; sys.stdout.write(json.load(open(sys.argv[1]))['type_segments'][0][1])" "$PLAN_JSON"; printf 'X')"; SEG1_TXT="${SEG1_TXT%X}"
SEG2_AT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['type_segments'][1][0])" "$PLAN_JSON")"
SEG2_TXT="$(python3 -c "import json,sys; sys.stdout.write(json.load(open(sys.argv[1]))['type_segments'][1][1])" "$PLAN_JSON"; printf 'X')"; SEG2_TXT="${SEG2_TXT%X}"

if [ "$NUM_SEGMENTS" -ge 3 ]; then
  SEG3_AT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['type_segments'][2][0])" "$PLAN_JSON")"
  SEG3_TXT="$(python3 -c "import json,sys; sys.stdout.write(json.load(open(sys.argv[1]))['type_segments'][2][1])" "$PLAN_JSON"; printf 'X')"; SEG3_TXT="${SEG3_TXT%X}"
fi

# 観察用(observation_frames、判定には使わない)のサンプルフレーム。
# 同じベース名を使い回すと、フロントエンドが拡張子の直前へフレーム番号
# を差し込んで別ファイルにする(vram_out_path()と同じ規約。既存の
# g9/before/after/promptと同じ扱い)。
OBS_FRAMES="$(python3 -c "import json,sys; print(' '.join(str(x) for x in json.load(open(sys.argv[1])).get('observation_frames', [])))" "$PLAN_JSON")"
OBS_BASE="${OUT_PREFIX}.obs.bin"
OBS_ARGS=()
for f in $OBS_FRAMES; do
  OBS_ARGS+=(--vram-dump "$OBS_BASE" --vram-dump-at "$f")
done

if [ -n "$INPUT_VALUE" ]; then
  DUMP_PROMPT="$(read_plan dump_prompt_frame)"
  DUMP_AFTER="$(read_plan dump_final_frame)"
  RUN_FRAMES="$(read_plan run_total_frames)"

  G9_BASE="${OUT_PREFIX}.g9.bin"
  BEFORE_BASE="${OUT_PREFIX}.before.bin"
  PROMPT_BASE="${OUT_PREFIX}.prompt.bin"
  AFTER_BASE="${OUT_PREFIX}.after.bin"

  "$FRONTEND" --core "$CORE" --rom-dir "$ROMDIR" --frames "$RUN_FRAMES" \
      --type-at 300 --type '\n' \
      --type-at "$SEG1_AT" --type "$SEG1_TXT" \
      --type-at "$SEG2_AT" --type "$SEG2_TXT" \
      --type-at "$SEG3_AT" --type "$SEG3_TXT" \
      --vram-dump "$G9_BASE" --vram-dump-at "$DUMP_G9" \
      --vram-dump "$BEFORE_BASE" --vram-dump-at "$DUMP_BEFORE" \
      --vram-dump "$PROMPT_BASE" --vram-dump-at "$DUMP_PROMPT" \
      --vram-dump "$AFTER_BASE" --vram-dump-at "$DUMP_AFTER" \
      "${OBS_ARGS[@]+"${OBS_ARGS[@]}"}" \
      >"$STDOUT" 2>"$STDERR"
else
  DUMP_AFTER="$(read_plan dump_after_frame)"
  RUN_FRAMES="$(read_plan run_total_frames)"

  G9_BASE="${OUT_PREFIX}.g9.bin"
  BEFORE_BASE="${OUT_PREFIX}.before.bin"
  AFTER_BASE="${OUT_PREFIX}.after.bin"

  "$FRONTEND" --core "$CORE" --rom-dir "$ROMDIR" --frames "$RUN_FRAMES" \
      --type-at 300 --type '\n' \
      --type-at "$SEG1_AT" --type "$SEG1_TXT" \
      --type-at "$SEG2_AT" --type "$SEG2_TXT" \
      --vram-dump "$G9_BASE" --vram-dump-at "$DUMP_G9" \
      --vram-dump "$BEFORE_BASE" --vram-dump-at "$DUMP_BEFORE" \
      --vram-dump "$AFTER_BASE" --vram-dump-at "$DUMP_AFTER" \
      "${OBS_ARGS[@]+"${OBS_ARGS[@]}"}" \
      >"$STDOUT" 2>"$STDERR"
fi

RC=$?

UNTYPABLE=0
if grep -qi 'untypable\|打てない' "$STDERR" 2>/dev/null; then
  UNTYPABLE=1
fi

G9_OUT=$(printf '%s.f%06d.bin' "${OUT_PREFIX}.g9" "$DUMP_G9")
BEFORE_OUT=$(printf '%s.f%06d.bin' "${OUT_PREFIX}.before" "$DUMP_BEFORE")
AFTER_OUT=$(printf '%s.f%06d.bin' "${OUT_PREFIX}.after" "$DUMP_AFTER")

echo "rc=$RC untypable_warning=$UNTYPABLE"
echo "g9=$G9_OUT"
echo "before=$BEFORE_OUT"
echo "after=$AFTER_OUT"
if [ -n "$INPUT_VALUE" ]; then
  PROMPT_OUT=$(printf '%s.f%06d.bin' "${OUT_PREFIX}.prompt" "$DUMP_PROMPT")
  echo "prompt=$PROMPT_OUT"
fi
echo "plan=$PLAN_JSON"

# 観察用: run(P8は入力値)を打ってからdump_final(最終確認)までの待ちの
# 中で、最初に「写し(前)との差分がstatus=okになった」観察用サンプルの
# フレーム番号をapprox_ok_frameとして出す（判定には使わない。見つから
# なければunknown。画面の文字は一切出さない。CLAUDE.md禁止事項7）。
OBS_COUNT=0
for f in $OBS_FRAMES; do OBS_COUNT=$((OBS_COUNT + 1)); done
APPROX_OK_FRAME="unknown"
if [ "$RC" -eq 0 ] && [ "$UNTYPABLE" -eq 0 ] && [ "$OBS_COUNT" -gt 0 ]; then
  APPROX_OK_FRAME="$(OBS_FRAMES_ENV="$OBS_FRAMES" python3 -c "
import os, sys
sys.path.insert(0, '$REPO/tools')
import l4_program_conform_record as pcr
before = '$BEFORE_OUT'
obs_prefix = '${OUT_PREFIX}.obs'
found = 'unknown'
for tok in os.environ['OBS_FRAMES_ENV'].split():
    f = int(tok)
    path = '%s.f%06d.bin' % (obs_prefix, f)
    if not os.path.exists(path):
        continue
    result = pcr.build_record(before, path, {19})
    if result.get('status') == 'ok':
        found = str(f)
        break
print(found)
" 2>/dev/null)"
  [ -n "$APPROX_OK_FRAME" ] || APPROX_OK_FRAME="unknown"
fi
echo "approx_ok_frame=$APPROX_OK_FRAME"
echo "observed_frames=$OBS_COUNT"

if [ "$RC" -ne 0 ] || [ "$UNTYPABLE" -eq 1 ]; then
  exit 1
fi
exit 0

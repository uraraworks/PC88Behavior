#!/usr/bin/env bash
# 自作ROMの SAVE ,A を m6f-j の固定観測に照合する。公式環境の腕は明示指定のみ。
# local の J-1 像を残す場合は PC88_SAVE_CONFORM_WORK を未使用パスに設定する。
# official-readback はその runs/J-1/drive2.d88 を SAVE_CONFORM_J1_IMAGE に渡す。
# 公式環境なしの2モードは「未実施」、終了コード3。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-local}"
case "$MODE" in local|official-readback|hybrid) ;; *) printf 'NG モード\n' >&2; exit 2;; esac
EXPECTED="${SAVE_CONFORM_EXPECTED:-$REPO/tools/save_conform_expected.tsv}"
FRONTEND="${SAVE_CONFORM_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
CHECK="$REPO/tools/save_conform_check.py"
python3 "$CHECK" validate "$EXPECTED" >/dev/null || exit 2

if [ "$MODE" != local ]; then
  if [ -z "${PC88_REF_ROM_DIR:-}" ] || [ -z "${PC88_REF_DISK_DIR:-}" ] ||
     [ ! -d "$PC88_REF_ROM_DIR" ] || [ ! -f "$PC88_REF_DISK_DIR/N88_FE.D88" ] ||
     [ ! -f "$PC88_REF_ROM_DIR/DISK.ROM" ]; then
    printf '%s\t未実施\t公式環境なし\n' "$MODE"
    exit 3
  fi
fi
if [ "$MODE" = official-readback ] && [ ! -f "${SAVE_CONFORM_J1_IMAGE:-}" ]; then
  printf 'NG J-1像なし\n' >&2; exit 2
fi

if [ -n "${PC88_SAVE_CONFORM_WORK:-}" ]; then
  WORK="$PC88_SAVE_CONFORM_WORK"
  [ ! -e "$WORK" ] || { printf 'NG 作業先が存在\n' >&2; exit 2; }
  mkdir -p "$WORK" || exit 2
  KEEP=1
else
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/save-conform.XXXXXX")" || exit 2
  KEEP=0
fi
trap '[ "$KEEP" -eq 1 ] || rm -rf "$WORK"' EXIT
mkdir "$WORK/rom" "$WORK/media" "$WORK/runs" || exit 2
if [ "$MODE" = official-readback ]; then
  :
elif [ -n "${SAVE_CONFORM_TEST_ROM_DIR:-}" ]; then
  cp -R "$SAVE_CONFORM_TEST_ROM_DIR"/. "$WORK/rom"/ || exit 2
else
  python3 "$REPO/src/build_main_rom.py" "$WORK/rom" >"$WORK/build.out" 2>"$WORK/build.err" || exit 2
fi
if [ "$MODE" = hybrid ]; then
  cp "$PC88_REF_ROM_DIR/DISK.ROM" "$WORK/rom/DISK.ROM" || exit 2
fi
if [ "$MODE" = official-readback ]; then
  for name in N88.ROM N88_0.ROM N88_1.ROM N88_2.ROM N88_3.ROM DISK.ROM; do
    cp "$PC88_REF_ROM_DIR/$name" "$WORK/rom/$name" || exit 2
  done
fi
if [ -n "${SAVE_CONFORM_CORE:-}" ]; then
  CORE="$SAVE_CONFORM_CORE"
else
  source "$REPO/tools/lib_l3_measure.sh"
  CORE="$(find_l3_core)"
  [ -n "$CORE" ] || { printf 'NG コアなし\n' >&2; exit 2; }
  if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
    ensure_l3_frontend || exit 2
  fi
fi
[ -x "$FRONTEND" ] || { printf 'NG フロントエンドなし\n' >&2; exit 2; }

if [ "$MODE" = official-readback ]; then
  run="$WORK/runs/readback"; mkdir "$run" || exit 2
  cp "$PC88_REF_DISK_DIR/N88_FE.D88" "$run/drive1.d88" || exit 2
  cp "$SAVE_CONFORM_J1_IMAGE" "$run/drive2.d88" || exit 2
  python3 "$CHECK" verify-j1-image "$EXPECTED" "$run/drive2.d88" \
    >"$run/image-check.out" 2>"$run/image-check.err" || { printf 'J-1像\tNG\n'; exit 1; }
  before_hash="$(shasum -a 256 "$run/drive1.d88" | cut -d' ' -f1)"
  image_hash="$(shasum -a 256 "$run/drive2.d88" | cut -d' ' -f1)"
  rc=0
  /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" \
    --core "$CORE" --rom-dir "$WORK/rom" --disk "$run/drive1.d88" \
    --disk2 "$run/drive2.d88" --frames 11000 --screen-signature-only \
    --screen-signature-at list:6000 --screen-signature-at list_late:6300 \
    --screen-signature-at files:10000 --screen-signature-at files_late:10300 \
    --out "$run/signatures.tsv" --type-at 300 --type '\n' \
    --type-at 700 --type 'cls:load "2:qsb"\n' \
    --type-at 4000 --type 'cls:list\n' \
    --type-at 7000 --type 'cls:files 2\n' \
    >"$run/stdout.txt" 2>"$run/stderr.txt" || rc=$?
  [ "$before_hash" = "$(shasum -a 256 "$run/drive1.d88" | cut -d' ' -f1)" ] || rc=1
  [ "$image_hash" = "$(shasum -a 256 "$run/drive2.d88" | cut -d' ' -f1)" ] || rc=1
  [ "$rc" -eq 0 ] || { printf 'official-readback\tNG\n'; exit 1; }
  python3 "$REPO/tools/save_conform_readback.py" "$run/signatures.tsv"
  exit $?
fi

python3 "$REPO/tools/make_m6fj_disk.py" "$WORK/media" >"$WORK/media.out" 2>"$WORK/media.err" || exit 2
ARMS=(J-1 J-2 J-3 J-4 J-5 J-6)
[ "$MODE" = hybrid ] && ARMS=(J-1 J-D1)
overall=0
for arm in "${ARMS[@]}"; do
  run="$WORK/runs/$arm"; mkdir "$run" || exit 2
  # J-D1: ドライブ1（D=0）へのSAVE。自作B0をドライブ1に置き、J-1と同じ期待値で
  # 読み戻す（新しい公式署名は作らない）。公式sub＋自作mainの書き込み送信の検査。
  earm="$arm"; [ "$arm" = J-D1 ] && earm=J-1
  case "$arm" in
    J-1|J-6|J-D1) media=B0;; J-2) media=B1;; J-3) media=B2;; J-4) media=BP;; J-5) media=BF;;
  esac
  if [ "$arm" = J-D1 ]; then
    cp "$WORK/media/B0.d88" "$run/drive1.d88" || exit 2
  elif [ "$MODE" = hybrid ]; then
    cp "$PC88_REF_DISK_DIR/N88_FE.D88" "$run/drive1.d88" || exit 2
    disk1_hash="$(shasum -a 256 "$run/drive1.d88" | cut -d' ' -f1)"
  else
    cp "$WORK/media/B0.d88" "$run/drive1.d88" || exit 2
  fi
  cp "$WORK/media/$media.d88" "$run/before.d88" || exit 2
  if [ "$arm" = J-D1 ]; then
    # hybrid の J-D1 はドライブ2に別媒体(B1)を挿し、書き込み先Dの誤りで
    # そちらへ書かれたら「もう一方のドライブ不変」の検査で落とす。
    if [ "$MODE" = hybrid ]; then
      cp "$WORK/media/B1.d88" "$run/drive2.d88" || exit 2
      disk2_hash="$(shasum -a 256 "$run/drive2.d88" | cut -d' ' -f1)"
    fi
  elif [ "$arm" != J-6 ]; then cp "$run/before.d88" "$run/drive2.d88" || exit 2; fi
  command="$(python3 - "$REPO/tools" "$earm" <<'PY'
import sys
sys.path.insert(0,sys.argv[1])
import m6fj_script
sys.stdout.write(m6fj_script.keystrokes(sys.argv[2]).replace('\n','\\n'))
PY
)" || exit 2
  [ "$arm" = J-D1 ] && command="${command/\"2:/\"1:}"
  args=(--core "$CORE" --rom-dir "$WORK/rom" --disk "$run/drive1.d88"
    --save-to-disk-image --frames 8000 --screen-signature-only
    --screen-signature-at baseline:600 --screen-signature-at final:7700
    --screen-signature-at late:8000 --out "$run/signatures.tsv"
    --type-at 300 --type '\n' --type-at 700 --type "$command")
  if [ "$arm" = J-6 ]; then
    cp "$run/before.d88" "$run/drive2.d88" || exit 2
    args+=(--expect-disk2-empty --insert-disk2 "$run/drive2.d88"
      --insert-disk2-at 1200 --screen-signature-at preinsert:1100)
  elif [ "$arm" != J-D1 ] || [ "$MODE" = hybrid ]; then
    args+=(--disk2 "$run/drive2.d88")
  fi
  rc=0
  SAVE_CONFORM_ARM="$arm" SAVE_CONFORM_EXPECTED_FOR_FAKE="$EXPECTED" \
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" "${args[@]}" \
    >"$run/stdout.txt" 2>"$run/stderr.txt" || rc=$?
  # 段ごとの結果を $run/stage.txt に残す（どの判定で落ちたかを後から示すため）。
  fe_rc=$rc; other_state=na; compare_state=skipped
  if [ "$MODE" = hybrid ]; then
    other_state=ok
    if [ "$arm" = J-D1 ]; then other_now="$(shasum -a 256 "$run/drive2.d88" | cut -d' ' -f1)"; other_ref="$disk2_hash"
    else other_now="$(shasum -a 256 "$run/drive1.d88" | cut -d' ' -f1)"; other_ref="$disk1_hash"; fi
    [ "$other_now" = "$other_ref" ] || { other_state=changed; rc=1; }
  fi
  if [ "$fe_rc" -eq 0 ] && [ -s "$run/signatures.tsv" ]; then
    img="$run/drive2.d88"; [ "$arm" = J-D1 ] && img="$run/drive1.d88"
    if python3 "$CHECK" compare "$EXPECTED" "$earm" "$img" \
        "$run/signatures.tsv" "$run/before.d88" >"$run/compare.out" 2>"$run/compare.err"; then
      compare_state=ok
    else compare_state=ng; rc=1; fi
  else
    rc=1
  fi
  printf 'frontend_rc=%s\nother_drive=%s\ncompare=%s\n' "$fe_rc" "$other_state" "$compare_state" >"$run/stage.txt"
  if [ "$rc" -eq 0 ]; then printf '%s\tOK\n' "$arm"; else printf '%s\tNG\n' "$arm"; overall=1; fi
done
exit "$overall"

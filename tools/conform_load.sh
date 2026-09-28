#!/usr/bin/env bash
# 自作ROM・自作媒体によるLOAD適合試験。観測は署名のみ。
# 自作ROMはディスク起動しない。公式測定時のドライブ1参照媒体の交換は
# 行わず、最初からドライブ1にも自作媒体を入れる（conform_files.shと同じ）。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED="${LOAD_CONFORM_EXPECTED:-$REPO/tools/load_conform_expected.tsv}"
FRONTEND="${LOAD_CONFORM_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
CHECK="$REPO/tools/load_conform_check.py"
KEEP=0
if [ -n "${PC88_LOAD_CONFORM_WORK:-}" ]; then
  WORK="$PC88_LOAD_CONFORM_WORK"
  [ ! -e "$WORK" ] || { printf 'NG 作業先が存在\n' >&2; exit 2; }
  mkdir -p "$WORK" || exit 2
  KEEP=1
else
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/load-conform.XXXXXX")" || exit 2
fi
trap '[ "$KEEP" -eq 1 ] || rm -rf "$WORK"' EXIT
python3 "$CHECK" validate "$EXPECTED" >"$WORK/validate.out" 2>"$WORK/validate.err" || {
  printf 'NG 期待値形式\n' >&2; exit 2;
}
mkdir "$WORK/rom" "$WORK/base" "$WORK/add2" "$WORK/runs" || exit 2
if [ -n "${LOAD_CONFORM_TEST_ROM_DIR:-}" ]; then
  cp -R "$LOAD_CONFORM_TEST_ROM_DIR"/. "$WORK/rom"/ || exit 2
else
  python3 "$REPO/src/build_main_rom.py" "$WORK/rom" >"$WORK/build.out" 2>"$WORK/build.err" || {
    printf 'NG 自作ROM構築\n' >&2; exit 2;
  }
fi
python3 "$REPO/tools/make_m6fi_disk.py" "$WORK/base" >"$WORK/base.out" 2>"$WORK/base.err" || exit 2
python3 "$REPO/tools/make_m6fi_add2_disk.py" "$WORK/add2" >"$WORK/add2.out" 2>"$WORK/add2.err" || exit 2
if [ -n "${LOAD_CONFORM_CORE:-}" ]; then
  CORE="$LOAD_CONFORM_CORE"
else
  source "$REPO/tools/lib_l3_measure.sh"
  CORE="$(find_l3_core)"
  [ -n "$CORE" ] || { printf 'NG コアなし\n' >&2; exit 2; }
  if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
    ensure_l3_frontend || exit 2
  fi
fi
[ -x "$FRONTEND" ] || { printf 'NG フロントエンドなし\n' >&2; exit 2; }
ARMS=(I-1 I-2 I-3 E-1 "I-4'" "E-2'" E-3 E-3m)
overall=0
for arm in "${ARMS[@]}"; do
  dir="$WORK/base"
  case "$arm" in "I-4'"|"E-2'"|E-3|E-3m) dir="$WORK/add2";; esac
  safe="${arm//\'/p}"
  run="$WORK/runs/$safe"
  mkdir "$run" || exit 2
  cp "$WORK/base/ascii.d88" "$run/drive1.d88" || exit 2
  command="$(python3 - "$dir/manifest.json" "$arm" <<'PY'
import json,sys
doc=json.load(open(sys.argv[1],encoding='ascii'))
sys.stdout.write(next(a['command'] for a in doc['arms'] if a['id']==sys.argv[2]))
PY
)" || exit 2
  args=(--core "$CORE" --rom-dir "$WORK/rom" --disk "$run/drive1.d88"
    --disk2 "$dir/ascii.d88" --frames 8000 --screen-signature-only
    --screen-signature-at baseline:600 --screen-signature-at final:7700
    --screen-signature-at late:8000 --out "$run/signatures.tsv"
    --type-at 300 --type $'\n' --type-at 500 --type $'CLS\n'
    --type-at 700 --type "$command"$'\n')
  case "$arm" in
    I-1|I-2|I-3|E-3)
      args+=(--screen-signature-at load:3300 --screen-signature-at load_late:3600
        --type-at 4000 --type $'CLS:LIST\n') ;;
  esac
  rc=0
  LOAD_CONFORM_ARM="$arm" LOAD_CONFORM_EXPECTED_FOR_FAKE="$EXPECTED" \
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" "${args[@]}" \
    >"$run/stdout.txt" 2>"$run/stderr.txt" || rc=$?
  if [ "$rc" -ne 0 ] || [ ! -s "$run/signatures.tsv" ]; then
    printf '%s\tNG\t不一致行数=-\t最初の不一致行番号=-\n' "$arm"
    overall=1
    continue
  fi
  rc=0
  python3 "$CHECK" compare --expected "$EXPECTED" --arm "$arm" \
    --report "$run/signatures.tsv" >"$run/compare.out" 2>"$run/compare.err" || rc=$?
  if [ "$rc" -eq 0 ]; then
    printf '%s\tOK\n' "$arm"
  else
    if [ "$rc" -eq 1 ]; then
      IFS=$'\t' read -r _ count row <"$run/compare.out"
    else
      count=- row=-
    fi
    printf '%s\tNG\t不一致行数=%s\t最初の不一致行番号=%s\n' "$arm" "$count" "$row"
    overall=1
  fi
done
exit "$overall"

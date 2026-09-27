#!/usr/bin/env bash
# 自作main ROMの FILES を、m6f-eで凍結した行署名だけと照合する。
# 公式ROM・公式ディスクは使わない。自作ROMはディスク起動しないため、
# 公式測定のD/E腕にあった「参照diskAを外してD1へ交換」は行わず、最初から
# ドライブ1へ自作D1を入れる。ドライブ2は各腕の自作媒体（D/E腕はD2）。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED="${FILES_CONFORM_EXPECTED:-$REPO/tools/files_conform_expected.tsv}"
CHECK="$REPO/tools/files_conform_check.py"
FRONTEND="${FILES_CONFORM_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
KEEP_WORK=0
if [ -n "${PC88_FILES_CONFORM_WORK:-}" ]; then
  WORK="$PC88_FILES_CONFORM_WORK"
  [ ! -e "$WORK" ] || { printf 'エラー: 作業先が既に存在する\n' >&2; exit 2; }
  mkdir -p "$WORK" || exit 2
  KEEP_WORK=1
else
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/files-conform.XXXXXX")"
fi
trap '[ "$KEEP_WORK" -eq 1 ] || rm -rf "$WORK"' EXIT

python3 "$CHECK" validate "$EXPECTED" >"$WORK/expected-check.out" \
  2>"$WORK/expected-check.err" || {
    printf 'エラー: 期待値TSVが不正\n' >&2
    exit 2
  }

mkdir "$WORK/rom" "$WORK/base" "$WORK/add2" "$WORK/add3" "$WORK/runs" || exit 2
if [ -n "${FILES_CONFORM_TEST_ROM_DIR:-}" ]; then
  cp -R "$FILES_CONFORM_TEST_ROM_DIR"/. "$WORK/rom"/ || exit 2
else
  python3 "$REPO/src/build_main_rom.py" "$WORK/rom" \
    >"$WORK/build.out" 2>"$WORK/build.err" || {
      printf 'エラー: 自作ROMの構築に失敗\n' >&2
      exit 2
    }
fi
python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/base" \
  >"$WORK/base.out" 2>"$WORK/base.err" || exit 2
python3 "$REPO/tools/make_m6fe_disk.py" --addendum2 "$WORK/add2" \
  >"$WORK/add2.out" 2>"$WORK/add2.err" || exit 2
python3 "$REPO/tools/make_m6fe_disk.py" --addendum3 "$WORK/add3" \
  >"$WORK/add3.out" 2>"$WORK/add3.err" || exit 2

if [ -n "${FILES_CONFORM_CORE:-}" ]; then
  CORE="$FILES_CONFORM_CORE"
else
  # 既存m6f-eドライバと同じq88measure/core探索を使う。
  source "$REPO/tools/lib_l3_measure.sh"
  CORE="$(find_l3_core)"
  [ -n "$CORE" ] || { printf 'エラー: q88measure用コアが無い\n' >&2; exit 2; }
  if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
    ensure_l3_frontend || exit 2
  fi
fi
[ -x "$FRONTEND" ] || { printf 'エラー: フロントエンドが実行不可\n' >&2; exit 2; }

ARMS=(L0 L1 L4 L5 L6 L11 L96 D-omit D-1 D-2 D-expr E-0 E-3 E-str N-wait
      L80 L85 L90 L95 "L96'" L81 L86 L91 "L90'")

command_for_arm() {
  case "$1" in
    L*|N-wait) printf '%s' 'CLS:FILES 2\n' ;;
    D-omit) printf '%s' 'CLS:FILES\n' ;;
    D-1) printf '%s' 'CLS:FILES 1\n' ;;
    D-2) printf '%s' 'CLS:FILES 2\n' ;;
    D-expr) printf '%s' 'CLS:FILES 1+1\n' ;;
    E-0) printf '%s' '10 ON ERROR GOTO 100\n20 FILES 0\n30 END\n100 CLS:PRINT ERR\n110 RESUME 30\nRUN\n' ;;
    E-3) printf '%s' '10 ON ERROR GOTO 100\n20 FILES 3\n30 END\n100 CLS:PRINT ERR\n110 RESUME 30\nRUN\n' ;;
    E-str) printf '%s' '10 ON ERROR GOTO 100\n20 FILES "B:"\n30 END\n100 CLS:PRINT ERR\n110 RESUME 30\nRUN\n' ;;
    *) return 1 ;;
  esac
}

disk2_for_arm() {
  case "$1" in
    L0|L1|L4|L5|L6|L11|L96) printf '%s/%s.d88' "$WORK/base" "$1" ;;
    D-*|E-*|N-wait) printf '%s' "$WORK/base/D2.d88" ;;
    L80|L85|L90|L95) printf '%s/%s.d88' "$WORK/add2" "$1" ;;
    "L96'") printf '%s' "$WORK/add2/L96p.d88" ;;
    L81|L86|L91) printf '%s/%s.d88' "$WORK/add3" "$1" ;;
    "L90'") printf '%s' "$WORK/add3/L90p.d88" ;;
    *) return 1 ;;
  esac
}

overall=0
for arm in "${ARMS[@]}"; do
  safe_arm="${arm//\'/p}"
  run_dir="$WORK/runs/$safe_arm"
  mkdir "$run_dir" || exit 2
  cp "$WORK/base/D1.d88" "$run_dir/drive1.d88" || exit 2
  disk2="$(disk2_for_arm "$arm")" || exit 2
  command="$(command_for_arm "$arm")" || exit 2
  frames=8000
  case "$arm" in L96|L80|L85|L90|L95|"L96'"|L81|L86|L91|"L90'") frames=12000;; esac
  [ "$arm" = N-wait ] && frames=4000
  report="$run_dir/signatures.tsv"
  qargs=(--core "$CORE" --rom-dir "$WORK/rom" --disk "$run_dir/drive1.d88"
    --frames "$frames" --screen-signature-only --screen-signature-at baseline:600
    --screen-signature-at "final:$((frames - 300))" --screen-signature-at "late:$frames"
    --out "$report" --type-at 300 --type '\n' --type-at 500 --type 'CLS\n'
    --type-at 700 --type "$command")
  if [ "$arm" = N-wait ]; then
    qargs+=(--expect-disk2-empty --insert-disk2 "$WORK/base/L1.d88" --insert-disk2-at 1200
      --screen-signature-at preinsert:1100)
  else
    qargs+=(--disk2 "$disk2")
  fi

  run_rc=0
  FILES_CONFORM_ARM="$arm" FILES_CONFORM_EXPECTED_FOR_FAKE="$EXPECTED" \
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" "${qargs[@]}" \
    >"$run_dir/stdout.txt" 2>"$run_dir/stderr.txt" || run_rc=$?
  if [ "$run_rc" -ne 0 ] || [ ! -s "$report" ]; then
    printf '%s\tNG\t不一致行数=-\t最初の不一致行番号=-\n' "$arm"
    overall=1
    continue
  fi
  compare_out="$run_dir/compare.out"
  compare_rc=0
  python3 "$CHECK" compare --expected "$EXPECTED" --arm "$arm" --report "$report" \
    >"$compare_out" 2>"$run_dir/compare.err" || compare_rc=$?
  if [ "$compare_rc" -eq 0 ]; then
    printf '%s\tOK\n' "$arm"
  elif [ "$compare_rc" -eq 1 ]; then
    IFS=$'\t' read -r _ mismatch_count first_row <"$compare_out"
    printf '%s\tNG\t不一致行数=%s\t最初の不一致行番号=%s\n' \
      "$arm" "$mismatch_count" "$first_row"
    overall=1
  else
    printf '%s\tNG\t不一致行数=-\t最初の不一致行番号=-\n' "$arm"
    overall=1
  fi
done

exit "$overall"

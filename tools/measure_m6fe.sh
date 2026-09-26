#!/usr/bin/env bash
# m6f-e 器具D: 15腕×2走の測定ドライバ。
# 公式ROM・参照diskAは環境変数からだけ受け取る。画面は q88measure の
# --screen-signature-only でプロセス内署名化し、本文を一切保存しない。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="${M6FE_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
SUPPORT="$REPO/tools/m6fe_measure_support.py"
WORK_TARGET="${PC88_M6FE_WORK:-}"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-driver.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

emit_gate_failure() {
  python3 - "$1" <<'PY'
import json, sys
failed = [item for item in sys.argv[1].split() if item]
print(json.dumps({"judgment":"gate_failed","failed_gates":failed,
                  "frontend_launch_count":0}, sort_keys=True, separators=(",",":")))
PY
  exit 1
}

if [ -z "$WORK_TARGET" ]; then
  printf '%s\n' '{"frontend_launch_count":0,"judgment":"gate_failed","reason":"PC88_M6FE_WORK_missing"}'
  exit 1
fi

G0=1; G1=1; G2=1; G3=1; G4=1; G5=1; G6=1; G7=1; G8=1

# G0: このドライバが読むレビュー入力を許可リスト化する。自己検査では末尾へ
# 禁止名を注入し、同じ検査経路を陰性対照にする。
REVIEW_INPUTS="CLAUDE.md docs/notes/m6f-e-files-display-preregistration.md docs/notes/m6f-e-addendum1-cls-baseline.md docs/spec/l4-basic.md tools/measure_m6fd.sh tools/measure_m6fd_driver_selftest.sh tools/measure_m6fd_add1.sh tools/measure_m6fd_add1_driver_selftest.sh tools/make_m6fe_disk.py tools/make_m6fe_disk_selftest.sh tools/check_m6fe_disk.py tools/predict_m6fe.py tools/derive_m6fe.py tools/judge_m6fe.py tools/check_m6fe_candidates.py tools/compare_screen_signatures.py tools/m6fe_predict_derive_selftest.sh tools/screen_signature_selftest.sh tools/screen_signature_live_selftest.sh tools/check_l3_entry_screen.py tools/m6fc_fdc_by_drive.py tools/analyze_main_to_sub.py tools/analyze_write_path.py tools/lib_m6f_measure.sh tools/lib_l3_measure.sh tools/harness/insert_disk2_selftest.sh tools/harness/swap_disk1_selftest.sh tools/harness/frontend/main.c tools/harness/frontend/screen_signature.h tools/run_all_selftests.sh tools/run_all_selftests_selftest.sh"
if [ -n "${M6FE_TEST_FORBIDDEN_INPUT:-}" ]; then REVIEW_INPUTS="$REVIEW_INPUTS $M6FE_TEST_FORBIDDEN_INPUT"; fi
case " $REVIEW_INPUTS " in
  *" private/"*|*" vendor/"*|*"make_n88_blank_disk.py"*|*"make_n88_blank_disk_selftest.py"*|*"m7eb"*|*" image.c"*) G0=0 ;;
esac
if [ "${M6FE_TEST_FAST_GATES:-0}" != 1 ]; then
  "$REPO/tools/check_cleanroom.sh" >"$STAGE/g0.out" 2>"$STAGE/g0.err" || G0=0
fi

# G1・G5・G6の自己検査は測定前に各1回だけ実行する。
if [ "${M6FE_TEST_FAST_GATES:-0}" != 1 ]; then
  "$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$STAGE/g1a.out" 2>"$STAGE/g1a.err" || G1=0
  "$REPO/tools/make_m6fe_disk_selftest.sh" >"$STAGE/g1b.out" 2>"$STAGE/g1b.err" || G1=0
fi

python3 "$REPO/tools/make_m6fe_disk.py" "$STAGE/media" \
  >"$STAGE/generate.out" 2>"$STAGE/generate.err" || G2=0
if [ "$G2" -eq 1 ]; then
  python3 "$REPO/tools/check_m6fe_disk.py" "$STAGE/media/manifest.json" \
    --image-dir "$STAGE/media" --json >"$STAGE/g2.out" 2>"$STAGE/g2.err" || G2=0
fi

# G3はmanifest凍結、G4は候補表再生成・欠落重複までをそれぞれ確認する。
if [ "$G2" -eq 1 ]; then
  python3 - "$STAGE/media/manifest.json" "$REPO/tools/m6fe_frozen.tsv" <<'PY' \
    >"$STAGE/g3.out" 2>"$STAGE/g3.err" || G3=0
import hashlib, pathlib, sys
manifest, frozen = map(pathlib.Path, sys.argv[1:])
values = dict(line.split("\t") for line in frozen.read_text(encoding="ascii").splitlines())
raise SystemExit(0 if hashlib.sha256(manifest.read_bytes()).hexdigest() == values["manifest_sha256"] else 1)
PY
  python3 "$REPO/tools/check_m6fe_candidates.py" "$STAGE/media/manifest.json" \
    >"$STAGE/g4.out" 2>"$STAGE/g4.err" || G4=0
else
  G3=0; G4=0
fi

if [ "${M6FE_TEST_FAST_GATES:-0}" != 1 ]; then
  "$REPO/tools/screen_signature_selftest.sh" >"$STAGE/g5a.out" 2>"$STAGE/g5a.err" || G5=0
  "$REPO/tools/m6fe_predict_derive_selftest.sh" >"$STAGE/g5b.out" 2>"$STAGE/g5b.err" || G5=0
  # 同じ1回の自己検査に、正例/故障検出(G5)と漏えい陰性対照(G6)が含まれる。
  [ "$G5" -eq 1 ] || G6=0
fi

# G7: ドライブ1実行中差し替え口（--swap-disk1/--swap-disk1-at、
# tools/harness/insert_disk2_selftest.shの--insert-disk2と同じ枠組み。
# 対象読取は開かない）がq88measureのソースに揃っていること。D/E系7腕の
# run_one()は、この口で差し替えイベントが打鍵(--type-at 700)より前の
# フレーム(650)でsuccess=1になったことをstderrの固定形式イベント行
# （event\tswap_disk1\tframe=...\tsuccess=...、main.c参照）で確認する
# （run_one内、打鍵前に確認できなければその腕を止める）。ここではソースに
# 両オプションが揃っているかだけを確認する。
if grep -q -- '"--swap-disk1"' "$REPO/tools/harness/frontend/main.c" \
  && grep -q -- '"--swap-disk1-at"' "$REPO/tools/harness/frontend/main.c"; then
  G7=1
else
  G7=0
fi

# G8: 30走が一意で、作業先に既存物が無いこと。生成済みmanifestで検査する。
if [ -e "$WORK_TARGET" ]; then G8=0; fi
if [ "$G2" -eq 1 ]; then
  python3 "$SUPPORT" plan-check --manifest "$STAGE/media/manifest.json" \
    >"$STAGE/g8.out" 2>"$STAGE/g8.err" || G8=0
else
  G8=0
fi

# 自己検査専用の故障注入。実関門を評価した後で1項目だけ偽にする。
if [ "${M6FE_TEST_MODE:-0}" = 1 ] && [ -n "${M6FE_TEST_FAIL_GATE:-}" ]; then
  case "$M6FE_TEST_FAIL_GATE" in
    G0) G0=0;; G1) G1=0;; G2) G2=0;; G3) G3=0;; G4) G4=0;;
    G5) G5=0;; G6) G6=0;; G7) G7=0;; G8) G8=0;;
  esac
fi

FAILED=""
for index in 0 1 2 3 4 5 6 7 8; do
  eval "value=\$G$index"
  [ "$value" -eq 1 ] || FAILED="$FAILED G$index"
done
[ -z "$FAILED" ] || emit_gate_failure "${FAILED# }"

# ここから先だけが公式環境へ到達しうる。自己検査のダミーは専用変数を使い、
# PC88_REF_* を設定しない。本番の公式パスはPC88_REF_*以外から受け取らない。
if [ "${M6FE_TEST_MODE:-0}" = 1 ]; then
  ROM_DIR="${M6FE_TEST_ROM_DIR:-}"
  DISK_DIR="${M6FE_TEST_DISK_DIR:-}"
else
  ROM_DIR="${PC88_REF_ROM_DIR:-}"
  DISK_DIR="${PC88_REF_DISK_DIR:-}"
fi
[ -n "$ROM_DIR" ] && [ -d "$ROM_DIR" ] || emit_gate_failure reference_rom
[ -n "$DISK_DIR" ] && [ -d "$DISK_DIR" ] || emit_gate_failure reference_disk_dir
REF_DISK="$DISK_DIR/N88_FE.D88"
[ -f "$REF_DISK" ] || emit_gate_failure reference_disk
source "$REPO/tools/lib_m6f_measure.sh"
REF_SHA="$(m6f_sha256 "$REF_DISK")" || emit_gate_failure reference_sha
source "$REPO/tools/lib_l3_measure.sh"
CORE="${M6FE_TEST_CORE:-$(find_l3_core)}"
[ -n "$CORE" ] || emit_gate_failure core
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || emit_gate_failure frontend
else
  [ -x "$FRONTEND" ] || emit_gate_failure frontend
fi

mkdir "$WORK_TARGET" || emit_gate_failure work_create
mkdir "$STAGE/safe" "$STAGE/runs" || emit_gate_failure stage_create
LAUNCH_COUNT=0

command_for_arm() {
  case "$1" in
    L0|L1|L4|L5|L6|L11|L96) printf '%s' 'CLS:FILES 2\n' ;;
    D-omit) printf '%s' 'CLS:FILES\n' ;;
    D-1) printf '%s' 'CLS:FILES 1\n' ;;
    D-2) printf '%s' 'CLS:FILES 2\n' ;;
    D-expr) printf '%s' 'CLS:FILES 1+1\n' ;;
    E-0) printf '%s' '10 ON ERROR GOTO 100\n20 FILES 0\n30 END\n100 CLS:PRINT ERR\n110 RESUME 30\nRUN\n' ;;
    E-3) printf '%s' '10 ON ERROR GOTO 100\n20 FILES 3\n30 END\n100 CLS:PRINT ERR\n110 RESUME 30\nRUN\n' ;;
    E-str) printf '%s' '10 ON ERROR GOTO 100\n20 FILES "B:"\n30 END\n100 CLS:PRINT ERR\n110 RESUME 30\nRUN\n' ;;
    N-wait) printf '%s' 'CLS:FILES 2\n' ;;
    *) return 1 ;;
  esac
}

media_for_arm() {
  case "$1" in
    L0|L1|L4|L5|L6|L11|L96) printf '%s' "$1" ;;
    D-*|E-*) printf '%s' D2 ;;
    N-wait) printf '%s' L1 ;;
    *) return 1 ;;
  esac
}

run_one() {
  local arm="$1" rep="$2" final_frame="$3"
  local run_dir="$STAGE/runs/$arm-r$rep"
  local disk1="$run_dir/drive1.d88" disk2="$run_dir/drive2.d88"
  local swap_disk="$run_dir/drive1-swap.d88"
  local report="$run_dir/signatures.tsv" iolog="$run_dir/iolog.txt"
  local stdout="$run_dir/stdout.txt" stderr="$run_dir/stderr.txt"
  local media command initial final ref_after
  mkdir "$run_dir" || return 1
  cp "$REF_DISK" "$disk1" || return 1
  initial="$(m6f_sha256 "$disk1")" || return 1
  [ "$initial" = "$REF_SHA" ] || return 1
  media="$(media_for_arm "$arm")" || return 1
  cp "$STAGE/media/$media.d88" "$disk2" || return 1
  command="$(command_for_arm "$arm")" || return 1
  local qargs=(--core "$CORE" --rom-dir "$ROM_DIR" --disk "$disk1"
    --frames "$final_frame" --io-log "$iolog" --io-log-from-frame 650
    --screen-signature-only --screen-signature-at baseline:600
    --screen-signature-at "final:$((final_frame - 300))"
    --screen-signature-at "late:$final_frame" --out "$report"
    --type-at 300 --type '\n' --type-at 500 --type 'CLS\n'
    --type-at 700 --type "$command")
  case "$arm" in
    D-*|E-*)
      cp "$STAGE/media/D1.d88" "$swap_disk" || return 1
      qargs+=(--disk2 "$disk2" --swap-disk1 "$swap_disk" --swap-disk1-at 650) ;;
    N-wait)
      qargs+=(--expect-disk2-empty --insert-disk2 "$disk2" --insert-disk2-at 1200
        --screen-signature-at preinsert:1100) ;;
    *) qargs+=(--disk2 "$disk2") ;;
  esac

  local attempt=0 run_rc=0
  while :; do
    attempt=$((attempt + 1)); LAUNCH_COUNT=$((LAUNCH_COUNT + 1)); run_rc=0
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" "${qargs[@]}" \
      >"$stdout" 2>"$stderr" || run_rc=$?
    # D/E系は差し替え失敗（--swap-disk1-at=650でsuccess=0、打鍵は700なので
    # 未達のまま)ならフロントエンドがrc!=0で止まる設計。打鍵前に止まった
    # runは以下の[ -s "$report" ]判定で確実に落ちる（--screen-signature-only
    # 時、reportはフレームループを最後まで走らないと書かれない）ので、
    # ここでは通常の再試行判定だけで良い。
    [ "$run_rc" -eq 0 ] && break
    [ "$run_rc" -eq 134 ] && [ "$attempt" -lt 3 ] || return 1
    rm -f "$report" "$iolog"
  done
  [ -s "$report" ] && [ -e "$iolog" ] || return 1
  case "$arm" in
    D-*|E-*)
      # G7: 差し替えイベントが打鍵(--type-at 700)より前のフレーム(650)で
      # success=1だったことを、q88measure自身がstderrへ出す固定形式の
      # イベント行（main.c write_swap_disk1_event / event行と同じ形式。
      # 画面本文ではなくこの器具が定義した通知）で確認する。無ければ
      # このrunをrun_failedとして扱い、以後の判定に進めない。
      grep -qF $'event\tswap_disk1\tframe=650\tsuccess=1' "$stderr" || return 1 ;;
  esac
  final="$(m6f_sha256 "$disk1")" || return 1
  ref_after="$(m6f_sha256 "$REF_DISK")" || return 1
  local unchanged=false
  if [ "$final" = "$REF_SHA" ] && [ "$ref_after" = "$REF_SHA" ]; then unchanged=true; fi
  python3 "$SUPPORT" normalize-run --report "$report" --iolog "$iolog" \
    --arm "$arm" --repetition "$rep" --reference-unchanged "$unchanged" \
    --output "$STAGE/safe/$arm-r$rep.safe.json" || return 1
  rm -f "$disk1" "$disk2" "$swap_disk" "$report" "$iolog" "$stdout" "$stderr"
  rmdir "$run_dir" || return 1
  return 0
}

for arm in L0 L1 L4 L5 L6 L11 L96 D-omit D-1 D-2 D-expr E-0 E-3 E-str N-wait; do
  final_frame=8000
  [ "$arm" = L96 ] && final_frame=12000
  [ "$arm" = N-wait ] && final_frame=4000
  for rep in 1 2; do
    run_one "$arm" "$rep" "$final_frame" || {
      printf '{"frontend_launch_count":%d,"judgment":"gate_failed","reason":"run_failed"}\n' "$LAUNCH_COUNT"
      exit 1
    }
    baseline_ok="$(python3 - "$STAGE/safe/$arm-r$rep.safe.json" <<'PY'
import json,sys
print("1" if json.load(open(sys.argv[1], encoding="ascii"))["baseline_ok"] else "0")
PY
)"
    if [ "$baseline_ok" != 1 ]; then
      printf '%s\n' '{"overall":"inconclusive_cls_baseline","judgments":["inconclusive_cls_baseline"]}' \
        >"$WORK_TARGET/judgment.json"
      printf '{"format":"m6fe-summary-v1","frontend_launch_count":%d,"judgments":["inconclusive_cls_baseline"],"run_count":%d}\n' \
        "$LAUNCH_COUNT" "$LAUNCH_COUNT" >"$WORK_TARGET/summary.json"
      printf 'm6f-e measurement complete: judgment=inconclusive_cls_baseline launches=%d\n' "$LAUNCH_COUNT"
      exit 0
    fi
  done
  arm_gate="$STAGE/$arm-gates.json"
  if ! python3 "$SUPPORT" arm-check --arm "$arm" \
      --run "$STAGE/safe/$arm-r1.safe.json" --run "$STAGE/safe/$arm-r2.safe.json" \
      >"$arm_gate" 2>"$STAGE/$arm-gates.err"; then
    printf '{"frontend_launch_count":%d,"judgment":"gate_failed","reason":"run_gate"}\n' "$LAUNCH_COUNT"
    exit 1
  fi
done

python3 "$SUPPORT" assemble --manifest "$STAGE/media/manifest.json" \
  --run-dir "$STAGE/safe" --output "$WORK_TARGET/observations.json" || exit 1
python3 "$REPO/tools/derive_m6fe.py" --observations "$WORK_TARGET/observations.json" \
  --output "$WORK_TARGET/derived.json" || exit 1
python3 "$REPO/tools/judge_m6fe.py" --derived "$WORK_TARGET/derived.json" \
  >"$WORK_TARGET/judgment.json" || exit 1
python3 "$SUPPORT" summary --judgment "$WORK_TARGET/judgment.json" \
  --run-dir "$STAGE/safe" --frontend-launch-count "$LAUNCH_COUNT" \
  --output "$WORK_TARGET/summary.json" || exit 1

# G12最終監査: 永続作業先は許可した4 JSONだけ。署名TSV・I/Oログ・画面本文は残さない。
AUDIT_NAMES="$(find "$WORK_TARGET" -type f -maxdepth 1 -print | sed "s#^$WORK_TARGET/##" | LC_ALL=C sort | tr '\n' ' ')"
[ "$AUDIT_NAMES" = "derived.json judgment.json observations.json summary.json " ] || {
  printf '{"frontend_launch_count":%d,"judgment":"gate_failed","reason":"G12"}\n' "$LAUNCH_COUNT"
  exit 1
}

overall="$(python3 - "$WORK_TARGET/judgment.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], encoding="ascii"))["overall"])
PY
)"
printf 'm6f-e measurement complete: judgment=%s launches=%d\n' "$overall" "$LAUNCH_COUNT"

#!/usr/bin/env bash
# m6i-a A0〜A5の単腕ドライバ。q88measureを手で起動せず、この入口を使う。
# 腕はG8追補で凍結した設定が無ければ起動前に止まる。--baselineだけは
# G8へ書く画面署名を先に採る対照なので、G8設定なしで走らせられる。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$REPO/tools/build_m6ia_measure_rom.py"
ANALYZE="$REPO/tools/analyze_m6ia_main_sub.py"
SCREEN_CHECK="$REPO/tools/check_l3_screen_output.py"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
source "$REPO/tools/lib_l3_measure.sh"

usage() {
  cat >&2 <<'EOF'
使い方: tools/measure_m6ia_main_sub.sh --arm A0|A1|A2|A3|A4|A5 \
           --g8-config PATH --result PATH
        tools/measure_m6ia_main_sub.sh --baseline --frames N --result PATH

G8設定は「key<TAB>value」。必須キー:
  frozen=yes, timeout_limit=65535, a0_frames〜a5_frames,
  a5_registers=AF,BC,DE,HL,IX,IY, key_scenario=base_Q,
  screen_line_count, screen_char_count, screen_sha256
EOF
}

arm=""
g8=""
result=""
baseline=0
requested_frames=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arm) arm="${2:-}"; shift 2 ;;
    --baseline) baseline=1; shift ;;
    --frames) requested_frames="${2:-}"; shift 2 ;;
    --g8-config) g8="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

# G8画面署名を凍結するための対照。腕ではないのでG8設定も事前登録の
# 判定名も使わない。生の--outは一時領域からSCREEN_CHECKだけが読む。
if [ "$baseline" -eq 1 ]; then
  if [ -n "$arm" ] || [ -n "$g8" ] || [ -z "$result" ] \
     || ! printf '%s' "$requested_frames" | grep -Eq '^[1-9][0-9]*$' \
     || [ "$requested_frames" -le 60 ] \
     || [ ! -d "$(dirname "$result")" ]; then
    usage
    exit 2
  fi

  run1_srm_before=-1
  run1_srm_after=-1
  run2_srm_before=-1
  run2_srm_after=-1
  baseline_fail() {
    local reason="$1"
    printf '%s\n' "{\"mode\":\"baseline\",\"deterministic\":false,\"reason\":\"$reason\",\"run1_srm_before_count\":$run1_srm_before,\"run1_srm_after_count\":$run1_srm_after,\"run2_srm_before_count\":$run2_srm_before,\"run2_srm_after_count\":$run2_srm_after}" \
      | tee "$result"
    exit 1
  }

  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
  CORE="$(find_l3_core)"
  if [ -z "$CORE" ] || ! ensure_l3_frontend; then
    baseline_fail harness_unavailable
  fi

  DISK="$WORK/generated.d88"
  python3 "$REPO/tools/make_l3_testdisk.py" "$DISK" --cylinders 40 \
    --double-sided --sectors-per-track 16 >/dev/null 2>"$WORK/disk.err" \
    || baseline_fail generated_media_failed
  disk_sha="$(shasum -a 256 "$DISK" | awk '{print $1}')"
  [ "$disk_sha" = d3becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c ] \
    || baseline_fail generated_media_mismatch

  srm_before=0
  srm_after=0
  key_frame=$((requested_frames - 50))
  for run in 1 2; do
    rom="$(mktemp -d "$WORK/rom.baseline${run}.XXXXXX")"
    python3 "$REPO/src/build_main_rom.py" "$rom" \
      >"$WORK/baseline${run}.build.out" 2>"$WORK/baseline${run}.build.err" \
      || baseline_fail control_rom_build_failed
    before="$(find "$rom" -maxdepth 1 -type f -name '*.srm' | wc -l | tr -d ' ')"
    if [ "$run" -eq 1 ]; then run1_srm_before="$before"; else run2_srm_before="$before"; fi
    srm_before=$((srm_before + before))
    [ "$before" -eq 0 ] \
      || baseline_fail srm_present_before_run

    /usr/bin/perl -e 'alarm shift; exec @ARGV' 180 "$FRONTEND" \
      --core "$CORE" --rom-dir "$rom" --disk "$DISK" \
      --frames "$requested_frames" --out "$WORK/baseline${run}.report.txt" \
      --key-matrix "0x04:1:${key_frame}:10" \
      >"$WORK/baseline${run}.stdout.txt" 2>"$WORK/baseline${run}.stderr.txt"
    qrc=$?
    after="$(find "$rom" -maxdepth 1 -type f -name '*.srm' | wc -l | tr -d ' ')"
    if [ "$run" -eq 1 ]; then run1_srm_after="$after"; else run2_srm_after="$after"; fi
    srm_after=$((srm_after + after))
    [ "$qrc" -eq 0 ] \
      || baseline_fail measurement_process_failed

    python3 "$SCREEN_CHECK" --report "$WORK/baseline${run}.report.txt" \
      >"$WORK/baseline${run}.signature.txt" 2>"$WORK/baseline${run}.signature.err" \
      || baseline_fail screen_analysis_failed
  done

  python3 "$SCREEN_CHECK" --report "$WORK/baseline1.report.txt" \
    --compare-report "$WORK/baseline2.report.txt" \
    >"$WORK/baseline.compare.txt" 2>"$WORK/baseline.compare.err"
  compare_rc=$?
  [ "$compare_rc" -eq 0 ] \
    || baseline_fail screen_not_deterministic

  screen_lines="$(awk -F= '$1=="line_count" {print $2}' "$WORK/baseline1.signature.txt")"
  screen_chars="$(awk -F= '$1=="char_count" {print $2}' "$WORK/baseline1.signature.txt")"
  screen_sha="$(awk -F= '$1=="sha256" {print $2}' "$WORK/baseline1.signature.txt")"
  if ! printf '%s' "$screen_lines" | grep -Eq '^[0-9]+$' \
     || ! printf '%s' "$screen_chars" | grep -Eq '^[0-9]+$' \
     || ! printf '%s' "$screen_sha" | grep -Eq '^[0-9a-f]{64}$'; then
    baseline_fail screen_analysis_failed
  fi
  printf '%s\n' "{\"mode\":\"baseline\",\"deterministic\":true,\"frames\":$requested_frames,\"key_scenario\":\"base_Q\",\"run1_srm_before_count\":$run1_srm_before,\"run1_srm_after_count\":$run1_srm_after,\"run2_srm_before_count\":$run2_srm_before,\"run2_srm_after_count\":$run2_srm_after,\"screen_line_count\":$screen_lines,\"screen_char_count\":$screen_chars,\"screen_sha256\":\"$screen_sha\"}" \
    | tee "$result"
  exit 0
fi

[ -z "$requested_frames" ] || { usage; exit 2; }
case "$arm" in A0|A1|A2|A3|A4|A5) ;; *) usage; exit 2 ;; esac
[ -n "$g8" ] && [ -f "$g8" ] && [ -n "$result" ] || {
  printf '%s\n' "{\"arm\":\"${arm:-unknown}\",\"judgment\":\"gate_failed\",\"passed\":false,\"reason\":\"g8_not_frozen\"}"
  exit 1
}
[ -d "$(dirname "$result")" ] || {
  echo "結果ファイルの親ディレクトリが無い" >&2; exit 2;
}

cfg() {
  awk -F '\t' -v key="$1" '$1==key { if (++n==1) value=$2 } END { if (n==1) print value; else exit 1 }' "$g8"
}

frozen="$(cfg frozen 2>/dev/null || true)"
timeout_limit="$(cfg timeout_limit 2>/dev/null || true)"
registers="$(cfg a5_registers 2>/dev/null || true)"
key_scenario="$(cfg key_scenario 2>/dev/null || true)"
frames="$(cfg "$(printf '%s' "$arm" | tr '[:upper:]' '[:lower:]')_frames" 2>/dev/null || true)"
screen_lines="$(cfg screen_line_count 2>/dev/null || true)"
screen_chars="$(cfg screen_char_count 2>/dev/null || true)"
screen_sha="$(cfg screen_sha256 2>/dev/null || true)"

if [ "$frozen" != yes ] || [ "$timeout_limit" != 65535 ] \
   || [ "$registers" != "AF,BC,DE,HL,IX,IY" ] \
   || [ "$key_scenario" != base_Q ] \
   || ! printf '%s' "$frames" | grep -Eq '^[1-9][0-9]*$' \
   || ! printf '%s' "$screen_lines" | grep -Eq '^[0-9]+$' \
   || ! printf '%s' "$screen_chars" | grep -Eq '^[0-9]+$' \
   || ! printf '%s' "$screen_sha" | grep -Eq '^[0-9a-f]{64}$'; then
  printf '%s\n' "{\"arm\":\"$arm\",\"judgment\":\"gate_failed\",\"passed\":false,\"reason\":\"g8_config_invalid\"}"
  exit 1
fi

# 実装値とG8の凍結値を実走前に照合する。
grep -Eq '^MAIN_SUB_TIMEOUT_LIMIT[[:space:]]+EQU[[:space:]]+0FFFFh' \
  "$REPO/src/l3_main/main_sub_read.asm" || {
    printf '%s\n' "{\"arm\":\"$arm\",\"judgment\":\"gate_failed\",\"passed\":false,\"reason\":\"timeout_limit_mismatch\"}"
    exit 1
  }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CORE="$(find_l3_core)"
if [ -z "$CORE" ] || ! ensure_l3_frontend; then
  printf '%s\n' "{\"arm\":\"$arm\",\"judgment\":\"gate_failed\",\"passed\":false,\"reason\":\"harness_unavailable\"}"
  exit 1
fi

DISK="$WORK/generated.d88"
python3 "$REPO/tools/make_l3_testdisk.py" "$DISK" --cylinders 40 \
  --double-sided --sectors-per-track 16 >/dev/null 2>"$WORK/disk.err" || exit 1
disk_sha="$(shasum -a 256 "$DISK" | awk '{print $1}')"
if [ "$disk_sha" != d3becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c ]; then
  printf '%s\n' "{\"arm\":\"$arm\",\"judgment\":\"gate_failed\",\"passed\":false,\"reason\":\"generated_media_mismatch\"}"
  exit 1
fi

declare -a tags
if [ "$arm" = A4 ]; then tags=(A4-cont A4-pair); else tags=("$arm"); fi
srm_before=0
srm_after=0
run_failed=0

for tag in "${tags[@]}"; do
  rom="$(mktemp -d "$WORK/rom.${tag}.XXXXXX")"
  asmwork="$(mktemp -d "$WORK/asm.${tag}.XXXXXX")"
  python3 "$BUILD" "$rom" --arm "$tag" --work-dir "$asmwork" \
    >"$WORK/${tag}.build.out" 2>"$WORK/${tag}.build.err" || { run_failed=1; break; }

  before="$(find "$rom" -maxdepth 1 -type f -name '*.srm' | wc -l | tr -d ' ')"
  srm_before=$((srm_before + before))
  if [ "$before" -ne 0 ]; then run_failed=2; break; fi

  key_frame=$((frames - 50))
  qargs=(--core "$CORE" --rom-dir "$rom" --frames "$frames"
         --io-log "$WORK/${tag}.io.txt" --int-log "$WORK/${tag}.int.txt"
         --mem-write-log "$WORK/${tag}.mem.txt" --mem-write-range DF00-E038
         --out "$WORK/${tag}.report.txt"
         --key-matrix "0x04:1:${key_frame}:10")
  if [ "$tag" != A2 ]; then qargs+=(--disk "$DISK"); fi

  /usr/bin/perl -e 'alarm shift; exec @ARGV' 180 "$FRONTEND" "${qargs[@]}" \
    >"$WORK/${tag}.stdout.txt" 2>"$WORK/${tag}.stderr.txt"
  qrc=$?
  after="$(find "$rom" -maxdepth 1 -type f -name '*.srm' | wc -l | tr -d ' ')"
  srm_after=$((srm_after + after))
  if [ "$qrc" -ne 0 ]; then run_failed=1; break; fi
done

if [ "$run_failed" -ne 0 ]; then
  if [ "$run_failed" -eq 2 ]; then judgment=gate_failed; reason=srm_present_before_run
  else judgment=unreached; reason=measurement_process_failed; fi
  printf '%s\n' "{\"arm\":\"$arm\",\"judgment\":\"$judgment\",\"passed\":false,\"reason\":\"$reason\",\"srm_before_count\":$srm_before,\"srm_after_count\":$srm_after}" | tee "$result"
  exit 1
fi

if [ "$arm" = A4 ]; then
  python3 "$ANALYZE" --arm A4 \
    --cont-memlog "$WORK/A4-cont.mem.txt" --cont-iolog "$WORK/A4-cont.io.txt" \
    --cont-report "$WORK/A4-cont.report.txt" \
    --pair-memlog "$WORK/A4-pair.mem.txt" --pair-iolog "$WORK/A4-pair.io.txt" \
    --pair-report "$WORK/A4-pair.report.txt" \
    --srm-before "$srm_before" --srm-after "$srm_after" | tee "$result"
  exit "${PIPESTATUS[0]}"
fi

extra=()
if [ "$arm" = A5 ]; then
  extra+=(--intlog "$WORK/A5.int.txt"
          --screen-expected "${screen_lines}:${screen_chars}:${screen_sha}")
fi
python3 "$ANALYZE" --arm "$arm" --memlog "$WORK/${arm}.mem.txt" \
  --iolog "$WORK/${arm}.io.txt" --report "$WORK/${arm}.report.txt" \
  --srm-before "$srm_before" --srm-after "$srm_after" "${extra[@]}" | tee "$result"
exit "${PIPESTATUS[0]}"

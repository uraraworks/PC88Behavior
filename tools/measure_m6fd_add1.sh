#!/usr/bin/env bash
# m6f-d 追補1 測定ドライバ。E-2・E-4・E-8・E-12・E-20・E-33 → IV-fill-free →
# IV-fill-res(--r-starが与えられたときだけ) の順に各腕2走で実行する。
#
# docs/notes/m6f-d-addendum1-terminal-and-reserve.md §3。構成・打鍵の形・
# 関門は tools/measure_m6fd.sh (m6f-d本編)と同じ(ドライブ1=参照diskAの
# 複製、ドライブ2=B0、`2:`付き、各腕2走、取りこぼしの扱い、rc=134の
# 回し直し)。腕の集合とフレーム数だけが違うので、その部分は独立した
# 実装だが、同じ通し検査(tools/measure_m6fd_add1_driver_selftest.sh)で
# tools/measure_m6fd.sh と同じ振る舞い(取りこぼしでの停止・継続の別、
# rc=134の吸収、G8)を確認する。
#
# **このセッションは公式ROMを使う本番の腕を回さない**(作業指示により)。
# ここに置くのは器具そのもの。
#
# 依存: tools/m6fd_entry.py の entry_fields(image, name)。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FD_ADD1_FROZEN_CONFIG:-$REPO/tools/m6fd_add1_frozen.tsv}"
BASE_CONFIG="${M6FD_FROZEN_CONFIG:-$REPO/tools/m6fd_frozen.tsv}"
FRONTEND="${M6FD_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }

# G7: 凍結照合は引数解釈・環境参照・frontend起動より先に行う(追補1・本編の両方)。
python3 "$REPO/tools/check_m6fd_add1_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
  || gate_failed preregistration_mismatch_add1
python3 "$REPO/tools/check_m6fd_preregistration.py" --config "$BASE_CONFIG" >/dev/null 2>&1 \
  || gate_failed preregistration_mismatch_base
source "$REPO/tools/lib_m6f_measure.sh"

raw_dir=""; result=""; r_star_arg=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --raw-dir) raw_dir="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    --r-star) r_star_arg="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
[ -n "$raw_dir" ] && [ -n "$result" ] && [ -n "$r_star_arg" ] || exit 2

R_STAR=""
if [ "$r_star_arg" != "none" ]; then
  case "$r_star_arg" in
    0x*|0X*) R_STAR="$((r_star_arg))" ;;
    *) gate_failed r_star_format ;;
  esac
  [ "$R_STAR" -ge 0 ] && [ "$R_STAR" -le 255 ] || gate_failed r_star_range
fi

[ -n "${PC88_REF_ROM_DIR:-}" ] || gate_failed PC88_REF_ROM_DIR_missing
[ -d "$PC88_REF_ROM_DIR" ] || gate_failed reference_rom_dir_missing
[ -n "${PC88_REF_DISK_DIR:-}" ] || gate_failed PC88_REF_DISK_DIR_missing
[ -d "$PC88_REF_DISK_DIR" ] || gate_failed reference_disk_dir_missing
REF_DISK_NAME="$(m6f_cfg "$CONFIG" reference_disk)" || gate_failed reference_disk_config
REF_DISK="$PC88_REF_DISK_DIR/$REF_DISK_NAME"
[ -f "$REF_DISK" ] || gate_failed reference_disk_missing
REF_SHA="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha

# G6: 生の像・入出力ログはリポジトリ外だけに置く。
m6f_check_output_paths "$REPO" "$raw_dir" "$result" || gate_failed G6
mkdir -p "$raw_dir" || gate_failed raw_dir
[ -d "$(dirname "$result")" ] || gate_failed result_parent
[ ! -e "$result" ] || gate_failed result_exists

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# G2
"$REPO/tools/check_cleanroom.sh" >"$WORK/g2.out" 2>"$WORK/g2.err" || gate_failed G2
# G3: 生成器・エントリ読み取りの自己検査(付け替え器具は追補1では使わない)。
"$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$WORK/g3a.out" 2>&1 || gate_failed G3_generator
"$REPO/tools/check_m6fc_markers_selftest.sh" >"$WORK/g3b.out" 2>&1 || gate_failed G3_markers
"$REPO/tools/m6fd_entry_selftest.sh" >"$WORK/g3c.out" 2>&1 || gate_failed G3_entry

source "$REPO/tools/lib_l3_measure.sh"
CORE="${M6FD_TEST_CORE:-$(find_l3_core)}"; [ -n "$CORE" ] || gate_failed core_missing
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend_missing
else
  [ -x "$FRONTEND" ] || gate_failed frontend_missing
fi

BOOT_FRAME="$(m6f_cfg "$CONFIG" boot_return_frame)"
TIMEOUT="$(m6f_cfg "$CONFIG" run_timeout_seconds)"

madd1_frames() {
  python3 - "$REPO" "$1" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import check_m6fd_add1_preregistration as c
print(c.resolve_frames_single(sys.argv[2]))
PY
}
madd1_segment() {
  # $1=arm -> "frame\ttext" (改行はまだエスケープされたまま)
  python3 - "$REPO" "$1" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import check_m6fd_add1_preregistration as c
frame, text = c.resolve_segment(sys.argv[2])
if "\t" in text or "\r" in text:
    raise SystemExit(3)
print(f"{frame}\t" + text.replace("\n", "\\n"))
PY
}

RUNS_JSON="$WORK/runs.ndjson"; : > "$RUNS_JSON"

madd1_make_b0() {
  local out="$1"; shift
  python3 "$REPO/tools/make_m6fc_blank_disk.py" "$out" --fat-value 0xFF --filler 0xFF \
    --sector-fill 18,1,13=0x00 "$@"
}

# 1走を実行する。$1=arm $2=rep $3=disk2 $4=フレーム数 $5=座標を取るか("1"=取る、
# E-*用。空ならIV-fill、取りこぼしは記録のみで続行)
madd1_exec_and_record() {
  local arm="$1" rep="$2" disk2="$3" frames_override="$4" use_writes="$5"

  local seg; seg="$(madd1_segment "$arm")" || gate_failed segment_resolve
  local seg_frame="${seg%%$'\t'*}"
  local seg_text="${seg#*$'\t'}"
  local frames; frames="$(madd1_frames "$arm")" || gate_failed frames_resolve
  [ -n "$frames_override" ] && frames="$frames_override"

  local iolog="$WORK/$arm-r$rep.iolog.txt"
  local report="$WORK/$arm-r$rep.report.txt"
  local disk1="$WORK/$arm-r$rep.drive1.d88"

  [ -e "$disk1" ] && gate_failed disk1_exists
  cp "$REF_DISK" "$disk1" || gate_failed disk1_copy
  chmod u+w "$disk1" || gate_failed disk1_mode
  local disk1_initial_sha; disk1_initial_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_sha
  [ "$disk1_initial_sha" = "$REF_SHA" ] || gate_failed disk1_copy_mismatch

  local qargs=(--core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk1" --disk2 "$disk2"
    --save-to-disk-image --frames "$frames" --io-log "$iolog" --out "$report"
    --type-at "$BOOT_FRAME" --type '\n' --type-at "$seg_frame" --type "$seg_text")

  local attempt=0 rc=0 aborts=0
  while :; do
    rc=0
    /usr/bin/perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" "$FRONTEND" "${qargs[@]}" \
      >"$WORK/$arm-r$rep.stdout.txt" 2>"$WORK/$arm-r$rep.stderr.txt" || rc=$?
    [ "$rc" = 0 ] && break
    [ "$rc" = 134 ] || gate_failed "emulator_run_${arm}_rc${rc}"
    aborts=$((aborts + 1))
    if [ "$aborts" -ge 3 ]; then
      python3 - "$arm" "$rep" "$aborts" <<'PY' >> "$RUNS_JSON" || gate_failed "run_summary_${arm}_r${rep}"
import json, sys
arm, rep, aborts = sys.argv[1:]
body = {"arm": arm, "repetition": int(rep), "abort": True, "abort_retries": int(aborts),
        "markers": [], "malformed_marker_rows": None, "writes": None, "iolog_dropped": None,
        "drive1_sha_ok": None, "image": None, "entry_fields": None}
print(json.dumps(body, sort_keys=True, separators=(",", ":")))
PY
      return 0
    fi
    rm -f "$iolog" "$report"
  done

  [ -e "$report" ] && [ -s "$iolog" ] || gate_failed measurement_artifact

  # G8: 参照ディスク本体、および使い捨て複製(ドライブ1)が測定後も直後と同じ。
  local disk1_final_sha; disk1_final_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_final_sha
  local ref_sha_after; ref_sha_after="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha_after
  [ "$ref_sha_after" = "$REF_SHA" ] || gate_failed G8
  [ "$disk1_final_sha" = "$REF_SHA" ] || gate_failed G8

  local markers_json; markers_json="$(python3 "$REPO/tools/check_m6fc_markers.py" \
    --report "$report")" || gate_failed markers

  python3 - "$REPO" "$arm" "$rep" "$iolog" "$use_writes" <<'PYEOF' >> "$RUNS_JSON" || gate_failed "run_summary_${arm}_r${rep}"
import json, re, sys
from pathlib import Path
repo, arm, rep, iolog, use_writes = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
from analyze_main_to_sub import parse_iolog
from analyze_write_path import parse_commands
from m6fc_fdc_by_drive import split_by_drive

rows, masked = parse_iolog(Path(iolog))
if sum(masked.values()):
    print("エラー: 伏せ字ログでは座標を安全に取り出せない", file=sys.stderr)
    sys.exit(1)

text = Path(iolog).read_text(encoding="utf-8", errors="replace")
dropped_total = 0
for m in re.finditer(r"取りこぼし:\s*(\d+)件", text):
    dropped_total += int(m.group(1))

# 追補1 §3: E-*は取りこぼしで止める。IV-fillは記録して続ける。
STOP_ON_DROP = use_writes == "1"
if dropped_total and STOP_ON_DROP:
    print(f"エラー: I/Oログに取りこぼしが{dropped_total}件ある({arm} r{rep})", file=sys.stderr)
    sys.exit(1)

writes = None
if use_writes == "1" and not dropped_total:
    commands = parse_commands(rows)
    split = split_by_drive(commands, 700)
    writes = split["writes"]

body = {"arm": arm, "repetition": int(rep), "writes": writes,
        "iolog_dropped": dropped_total, "abort_retries": 0,
        "drive1_sha_ok": True, "image": None, "entry_fields": None}
print(json.dumps(body, sort_keys=True, separators=(",", ":")))
PYEOF

  local image_name=""
  if [ "$use_writes" = "1" ]; then
    image_name="$arm-r$rep.d88"
    cp "$disk2" "$raw_dir/$image_name" || gate_failed save_disk
  fi

  local entry_fields_json="null"
  if [ "$use_writes" = "1" ]; then
    entry_fields_json="$(python3 - "$REPO" "$disk2" <<'PY'
import json, sys
from pathlib import Path
repo, disk2 = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
import m6fd_entry
fields = m6fd_entry.entry_fields(Path(disk2).read_bytes(), b"QZ7B")
print(json.dumps({"QZ7B": fields}, sort_keys=True, separators=(",", ":")))
PY
)" || gate_failed entry_fields
  fi

  python3 - "$RUNS_JSON" "$markers_json" "$image_name" "$entry_fields_json" <<'PY' || gate_failed "run_summary_merge_${arm}_r${rep}"
import json, sys
path, markers_raw, image_name, entry_fields_raw = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
last = json.loads(lines[-1])
markers = json.loads(markers_raw)
last["markers"] = markers["markers"]
last["malformed_marker_rows"] = markers["malformed_marker_rows"]
last["image"] = image_name or None
last["entry_fields"] = json.loads(entry_fields_raw)
lines[-1] = json.dumps(last, sort_keys=True, separators=(",", ":"))
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

# --- E: 終端の規則の前向きの確認(6腕) ---------------------------------------
for arm in E-2 E-4 E-8 E-12 E-20 E-33; do
  for rep in 1 2; do
    disk2="$WORK/$arm-r$rep.d88"
    madd1_make_b0 "$disk2" >/dev/null 2>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk
    madd1_exec_and_record "$arm" "$rep" "$disk2" "" 1
  done
  if [ -n "${M6FD_ADD1_TEST_STOP_AFTER_ARM:-}" ] && [ "$arm" = "$M6FD_ADD1_TEST_STOP_AFTER_ARM" ]; then
    printf 'm6f-d add1 measurement selftest: stopped after arm=%s\n' "$arm"
    [ -n "${M6FD_ADD1_TEST_RUNS_COPY:-}" ] && cp "$RUNS_JSON" "$M6FD_ADD1_TEST_RUNS_COPY"
    exit 0
  fi
done

# --- IV-fill-free(2走) -------------------------------------------------------
for rep in 1 2; do
  disk2="$WORK/IV-fill-free-r$rep.d88"
  madd1_make_b0 "$disk2" >/dev/null 2>"$WORK/IV-fill-free-r$rep.gen.err" || gate_failed generate_disk
  madd1_exec_and_record IV-fill-free "$rep" "$disk2" "" ""
done

if [ -n "${M6FD_ADD1_TEST_STOP_AFTER_ARM:-}" ] && [ "$M6FD_ADD1_TEST_STOP_AFTER_ARM" = "IV-fill-free" ]; then
  printf 'm6f-d add1 measurement selftest: stopped after arm=IV-fill-free\n'
  [ -n "${M6FD_ADD1_TEST_RUNS_COPY:-}" ] && cp "$RUNS_JSON" "$M6FD_ADD1_TEST_RUNS_COPY"
  exit 0
fi

# --- IV-fill-res(R*があるときだけ、2走) --------------------------------------
if [ -n "$R_STAR" ]; then
  for rep in 1 2; do
    disk2="$WORK/IV-fill-res-r$rep.d88"
    madd1_make_b0 "$disk2" --fat-position "74=$R_STAR" --fat-position "75=$R_STAR" \
      >/dev/null 2>"$WORK/IV-fill-res-r$rep.gen.err" || gate_failed generate_disk
    madd1_exec_and_record IV-fill-res "$rep" "$disk2" "" ""
  done
else
  printf 'm6f-d add1: R* が無いため IV-fill-res は回さない\n'
fi

# --- 結果の書き出し ----------------------------------------------------------
python3 - "$WORK" "$result" "${R_STAR:-}" <<'PY' || gate_failed result_write
import json, sys
from pathlib import Path
work, out, r_star_raw = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
runs = [json.loads(line) for line in (work / "runs.ndjson").read_text(encoding="utf-8").splitlines() if line]
r_star = int(r_star_raw) if r_star_raw != "" else None
body = {"schema": 1, "drive_layout": "drive1=reference_copy_protected;drive2=generated",
        "r_star_input": r_star, "runs": runs}
with out.open("x", encoding="utf-8") as f:
    json.dump(body, f, sort_keys=True, separators=(",", ":")); f.write("\n")
PY

printf 'm6f-d add1 measurement complete: raw=%s result=%s\n' "$raw_dir" "$result"

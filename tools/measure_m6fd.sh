#!/usr/bin/env bash
# m6f-d測定ドライバ。I→II→III→IV-R→(R*導出)→IV-fill→Vの順に各腕2走で実行する。
#
# **このスクリプトは公式ROMを使う本番の腕を回すためのものだが、
# このセッション自身はそれを実行しない**（作業指示により測定は回さない）。
# ここに置くのは器具そのものであり、関門と手順が事前登録
# docs/notes/m6f-d-disk-rules-preregistration.md と一致することを
# 自己検査 tools/measure_m6fd_driver_selftest.sh で確認するにとどめる。
#
# 依存: tools/derive_m6fd.py の r_star(result) と tools/m6fd_entry.py の
# entry_fields(image_bytes, name) は別担当が用意する（本稿の時点では
# 未着手）。無い場合は既定でgate_failedにする。試験用の口
# M6FD_TEST_R_STAR / M6FD_TEST_SKIP_ENTRY_FIELDS で自己検査だけ迂回できる。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FD_FROZEN_CONFIG:-$REPO/tools/m6fd_frozen.tsv}"
FRONTEND="${M6FD_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }

# G7: 凍結照合は引数解釈・環境参照・frontend起動より先に行う。
python3 "$REPO/tools/check_m6fd_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
  || gate_failed preregistration_mismatch
source "$REPO/tools/lib_m6f_measure.sh"

raw_dir=""; result=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --raw-dir) raw_dir="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
[ -n "$raw_dir" ] && [ -n "$result" ] || exit 2

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
# G3: 差分器・生成器・目印判定器・付け替え器具の自己検査。
"$REPO/tools/d88_diff_selftest.sh" >"$WORK/g3a.out" 2>&1 || gate_failed G3_d88diff
"$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$WORK/g3b.out" 2>&1 || gate_failed G3_generator
"$REPO/tools/check_m6fc_markers_selftest.sh" >"$WORK/g3c.out" 2>&1 || gate_failed G3_markers
"$REPO/tools/m6fd_relocate_selftest.sh" >"$WORK/g3d.out" 2>&1 || gate_failed G3_relocate

source "$REPO/tools/lib_l3_measure.sh"
# 試験用の口(既定は無効): M6FD_TEST_CORE で find_l3_core の結果を上書きできる。
# tools/measure_m6fd_driver_selftest.sh がコア不在環境で偽フロントエンドを
# 差し込むために使う。
CORE="${M6FD_TEST_CORE:-$(find_l3_core)}"; [ -n "$CORE" ] || gate_failed core_missing
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend_missing
else
  [ -x "$FRONTEND" ] || gate_failed frontend_missing
fi

BOOT_FRAME="$(m6f_cfg "$CONFIG" boot_return_frame)"
STIMULUS_FRAME="$(m6f_cfg "$CONFIG" stimulus_frame)"
TIMEOUT="$(m6f_cfg "$CONFIG" run_timeout_seconds)"

mfd_frames_single() {
  python3 - "$REPO" "$1" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import check_m6fd_preregistration as c
print(c.resolve_frames_single(sys.argv[2]))
PY
}
mfd_frames_phase() {
  python3 - "$REPO" "$1" "$2" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import check_m6fd_preregistration as c
print(c.resolve_frames_phase(sys.argv[2], sys.argv[3]))
PY
}
mfd_segments() {
  # $1=arm $2=phase("" for None)
  python3 - "$REPO" "$1" "$2" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import check_m6fd_preregistration as c
phase = sys.argv[3] if sys.argv[3] else None
for frame, text in c.resolve_segments(sys.argv[2], phase):
    if "\t" in text or "\r" in text or "\\n" in text:
        raise SystemExit(3)
    print(f"{frame}\t" + text.replace("\n", "\\n"))
PY
}

RUNS_JSON="$WORK/runs.ndjson"; : > "$RUNS_JSON"

# B0媒体を作る（(18,1,13)だけ書き込み禁止解除の0x00、他はfat-value/fillerに
# 従う。既定は事前登録どおり全FF）。
mfd_make_b0() {
  local out="$1"; shift
  python3 "$REPO/tools/make_m6fc_blank_disk.py" "$out" --fat-value 0xFF --filler 0xFF \
    --sector-fill 18,1,13=0x00 "$@"
}

# 1走を実行する。
# $1=arm $2=phase("" 単発) $3=rep $4=disk2パス($5=1で新規生成しない=既存像を使う)
# $5=既に生成済みならディスク2を新規生成しない("1") 生成する場合は空
# $6=entry名("" なら取らない) $7=save_image("1" なら raw-dir へ保存)
mfd_exec_and_record() {
  local arm="$1" phase="$2" rep="$3" disk2="$4" skip_gen="$5" entry_name="$6" save_image="$7"
  local is_v=0
  case " V-missing V-crc V-deleted V-single V-ff V-c9 " in *" $arm "*) is_v=1 ;; esac

  local frames
  if [ -n "$phase" ]; then frames="$(mfd_frames_phase "$arm" "$phase")" || gate_failed frames_resolve
  else frames="$(mfd_frames_single "$arm")" || gate_failed frames_resolve; fi

  local iolog="$WORK/$arm-p$phase-r$rep.iolog.txt"
  local report="$WORK/$arm-p$phase-r$rep.report.txt"
  local disk1="$WORK/$arm-p$phase-r$rep.drive1.d88"

  local qargs=()
  local drive1_sha_ok="null"
  local fdc_unit=1

  if [ "$is_v" -eq 1 ]; then
    fdc_unit=0
    # V群: ドライブ1が媒体そのもの(disk2として渡されたパスを使う)、ドライブ2なし。
    qargs=(--core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk2"
      --save-to-disk-image --frames "$frames" --io-log "$iolog" --out "$report"
      --type-at "$BOOT_FRAME" --type '\n')
  else
    [ -e "$disk1" ] && gate_failed disk1_exists
    cp "$REF_DISK" "$disk1" || gate_failed disk1_copy
    chmod u+w "$disk1" || gate_failed disk1_mode
    local disk1_initial_sha; disk1_initial_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_sha
    [ "$disk1_initial_sha" = "$REF_SHA" ] || gate_failed disk1_copy_mismatch
    qargs=(--core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk1" --disk2 "$disk2"
      --save-to-disk-image --frames "$frames" --io-log "$iolog" --out "$report"
      --type-at "$BOOT_FRAME" --type '\n')
  fi

  local nadded=0
  while IFS=$'\t' read -r seg_frame seg_text; do
    [ -n "$seg_frame" ] || continue
    case "$seg_frame" in *[!0-9]*) gate_failed segment_frame ;; esac
    qargs+=(--type-at "$seg_frame" --type "$seg_text")
    nadded=$((nadded + 1))
  done < <(mfd_segments "$arm" "$phase")
  local nseg; nseg="$(mfd_segments "$arm" "$phase" | wc -l | tr -d ' ')" || gate_failed segments_resolve
  [ "$nadded" -eq "$nseg" ] || gate_failed segments_count

  # rc=134(abort)は最大2回まで回し直す(事前登録の前例docs/notes/
  # m6f-c-addendum3-write-protect-sectors.md §3.1と同じ扱い)。回し直す
  # たびに媒体を作り直す責務は呼び出し元(生成コールバック)に無いため、
  # ここでは"disk2は既に固定内容として渡されている"前提で同じファイルの
  # まま再実行する(disk2の生成はmfd_exec_and_recordの外で1回だけ行う設計)。
  local attempt=0 rc=0 aborts=0
  while :; do
    rc=0
    /usr/bin/perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" "$FRONTEND" "${qargs[@]}" \
      >"$WORK/$arm-p$phase-r$rep.stdout.txt" 2>"$WORK/$arm-p$phase-r$rep.stderr.txt" || rc=$?
    [ "$rc" = 0 ] && break
    [ "$rc" = 134 ] || gate_failed "emulator_run_${arm}_rc${rc}"
    aborts=$((aborts + 1))
    if [ "$aborts" -ge 3 ]; then
      python3 - "$arm" "$phase" "$rep" "$aborts" <<'PY' >> "$RUNS_JSON" || gate_failed "run_summary_${arm}_r${rep}"
import json, sys
arm, phase, rep, aborts = sys.argv[1:]
body = {"arm": arm, "phase": (int(phase) if phase else None), "repetition": int(rep), "abort": True,
        "abort_retries": int(aborts), "markers": [], "malformed_marker_rows": None,
        "reads": None, "writes": None, "write_data_count": None, "fdc_unit": None,
        "iolog_dropped": None, "drive1_sha_ok": None, "image": None, "entry_fields": None}
print(json.dumps(body, sort_keys=True, separators=(",", ":")))
PY
      return 0
    fi
    rm -f "$iolog" "$report"
  done

  [ -e "$report" ] && [ -s "$iolog" ] || gate_failed measurement_artifact

  if [ "$is_v" -eq 0 ]; then
    # G8: 参照ディスク本体、および使い捨て複製(ドライブ1)の両方が測定後も
    # 直後と同じであること(m6fc精度と同じ二重確認)。不一致は即座に止める
    # (drive1_sha_okは生存した走にだけ記録されるので、常にtrueのはずの値
    # が残る——「G8を通ったことの記録」として意味がある)。
    local disk1_final_sha; disk1_final_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_final_sha
    local ref_sha_after; ref_sha_after="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha_after
    [ "$ref_sha_after" = "$REF_SHA" ] || gate_failed G8
    [ "$disk1_final_sha" = "$REF_SHA" ] || gate_failed G8
    drive1_sha_ok=true
  fi

  local markers_args=(--report "$report")
  [ -n "$entry_name" ] && markers_args+=(--name "$entry_name")
  local markers_json; markers_json="$(python3 "$REPO/tools/check_m6fc_markers.py" \
    "${markers_args[@]}")" || gate_failed markers

  # 取りこぼし検出とFDC座標の抽出。
  python3 - "$REPO" "$arm" "$phase" "$rep" "$iolog" "$STIMULUS_FRAME" "$fdc_unit" \
    "$drive1_sha_ok" <<'PYEOF' >> "$RUNS_JSON" || gate_failed "run_summary_${arm}_p${phase:-0}_r${rep}"
import json, re, sys
from pathlib import Path
repo, arm, phase, rep, iolog, stim, fdc_unit, drive1_sha_ok = sys.argv[1:]
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
# IV-fill-free/IV-fill-resは事前登録どおり入出力ログを導出に使わないため、
# 取りこぼしの有無にかかわらず座標は記録しない(null)。他の腕は取りこぼしで
# 止める(事前登録に取りこぼし許容の明記が無いため)。
# 事前登録 §5.1（測定前の補足）: 入出力ログの座標を導出に使うのは I-* の腕だけ
# （D3 の u）。取りこぼしで止めるのは I-* だけにし、他の腕は取りこぼし数を記録して
# 座標を null にする。
FDC_USED = arm.startswith("I-")
if dropped_total and FDC_USED:
    print(f"エラー: I/Oログに取りこぼしが{dropped_total}件ある({arm} phase={phase} r{rep})", file=sys.stderr)
    sys.exit(1)

if arm in ("IV-fill-free", "IV-fill-res") or (dropped_total and not FDC_USED):
    reads_list = writes_list = None
    write_data_count = None
else:
    commands = parse_commands(rows)
    split = split_by_drive(commands, int(stim))
    if fdc_unit == "0":
        reads_list, writes_list = split["drive1_read_count"], split["drive1_write_count"]
        write_data_count = None
    else:
        reads_list, writes_list = split["reads"], split["writes"]
        write_data_count = split["write_data_count"]

body = {
    "arm": arm, "phase": (int(phase) if phase else None), "repetition": int(rep),
    "reads": reads_list,
    "writes": writes_list,
    "write_data_count": write_data_count,
    "fdc_unit": int(fdc_unit), "iolog_dropped": dropped_total,
    "abort_retries": 0,
    "drive1_sha_ok": (None if drive1_sha_ok == "null" else drive1_sha_ok == "true"),
    "image": None, "entry_fields": None,
}
print(json.dumps(body, sort_keys=True, separators=(",", ":")))
PYEOF

  # markers・image・entry_fieldsを最後の行へ合流する。
  local image_name=""
  if [ "$save_image" = "1" ]; then
    image_name="$arm-r$rep.d88"
    cp "$disk2" "$raw_dir/$image_name" || gate_failed save_disk
  fi

  local entry_fields_json="null"
  if [ -n "$entry_name" ]; then
    if [ -n "${M6FD_TEST_SKIP_ENTRY_FIELDS:-}" ]; then
      entry_fields_json="$(python3 - "$REPO" "$disk2" "$entry_name" <<'PY'
import json, sys
from pathlib import Path
repo, disk2, name = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
try:
    import m6fd_entry
    fields = m6fd_entry.entry_fields(Path(disk2).read_bytes(), name.encode("ascii"))
except ImportError:
    fields = None
print(json.dumps(fields, sort_keys=True, separators=(",", ":")))
PY
)" || gate_failed entry_fields
    else
      entry_fields_json="$(python3 - "$REPO" "$disk2" "$entry_name" <<'PY'
import json, sys
from pathlib import Path
repo, disk2, name = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
import m6fd_entry
fields = m6fd_entry.entry_fields(Path(disk2).read_bytes(), name.encode("ascii"))
print(json.dumps(fields, sort_keys=True, separators=(",", ":")))
PY
)" || gate_failed entry_fields_missing_module
    fi
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

  LAST_DISK2="$disk2"
}

# --- I: 割り当ての規則の測り直し(6腕) ---------------------------------------
for spec in "I-250:250" "I-1:1" "I-3:3" "I-6:6" "I-10:10" "I-17:17"; do
  arm="${spec%%:*}"
  for rep in 1 2; do
    disk2="$WORK/$arm-r$rep.d88"
    mfd_make_b0 "$disk2" >/dev/null 2>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk
    mfd_exec_and_record "$arm" "" "$rep" "$disk2" "" QZ7B 1
  done
  if [ -n "${M6FD_TEST_STOP_AFTER_ARM:-}" ] && [ "$arm" = "$M6FD_TEST_STOP_AFTER_ARM" ]; then
    printf 'm6f-d measurement selftest: stopped after arm=%s\n' "$arm"
    [ -n "${M6FD_TEST_RUNS_COPY:-}" ] && cp "$RUNS_JSON" "$M6FD_TEST_RUNS_COPY"
    exit 0
  fi
done

# --- II: 付け替えたファイルの読み込み(2段の腕、4腕) --------------------------
# bash 3.2対応: 名前参照(local -n)は使えないので、付け替え引数は末尾の
# "$@" として直接渡す。
mfd_run_ii() {
  local arm="$1"; shift
  for rep in 1 2; do
    local disk2_p1="$WORK/$arm-p1-r$rep.d88"
    mfd_make_b0 "$disk2_p1" >/dev/null 2>"$WORK/$arm-p1-r$rep.gen.err" || gate_failed generate_disk
    mfd_exec_and_record "$arm" 1 "$rep" "$disk2_p1" "" "" 0
    local disk2_p2="$WORK/$arm-p2-r$rep.d88"
    python3 "$REPO/tools/m6fd_relocate.py" "$disk2_p1" "$disk2_p2" "$@" \
      >/dev/null 2>"$WORK/$arm-p2-r$rep.relo.err" || gate_failed relocate
    mfd_exec_and_record "$arm" 2 "$rep" "$disk2_p2" "" "" 0
  done
}
mfd_run_ii II-d --src-name QZ7B --dst-name QZ7R --dst-units 20,5
mfd_run_ii II-neg1 --src-name QZ7B --dst-name QZ7R --dst-units 20,5 --break-link-at 20
mfd_run_ii II-neg2 --src-name QZ7B --dst-name QZ7R --dst-units 20,5 --override-start 21

for rep in 1 2; do
  disk2_p1="$WORK/II-p-p1-r$rep.d88"
  mfd_make_b0 "$disk2_p1" >/dev/null 2>"$WORK/II-p-p1-r$rep.gen.err" || gate_failed generate_disk
  mfd_exec_and_record II-p 1 "$rep" "$disk2_p1" "" "" 0
  disk2_p2="$WORK/II-p-p2-r$rep.d88"
  python3 "$REPO/tools/m6fd_relocate.py" "$disk2_p1" "$disk2_p2" \
    --src-name q7l --dst-name q7r --dst-units 30 \
    >/dev/null 2>"$WORK/II-p-p2-r$rep.relo.err" || gate_failed relocate
  mfd_exec_and_record II-p 2 "$rep" "$disk2_p2" "" "" 0
done

if [ -n "${M6FD_TEST_STOP_AFTER_ARM:-}" ] && [ "$M6FD_TEST_STOP_AFTER_ARM" = "II" ]; then
  printf 'm6f-d measurement selftest: stopped after group=II\n'
  [ -n "${M6FD_TEST_RUNS_COPY:-}" ] && cp "$RUNS_JSON" "$M6FD_TEST_RUNS_COPY"
  exit 0
fi

# --- III: ディレクトリの広がり(25腕) ----------------------------------------
III_MAX="${M6FD_TEST_III_MAX:-12}"
for variant in FF 00; do
  for r in $(seq 1 "$III_MAX"); do
    rr="$(printf '%02d' "$r")"
    arm="III-$variant-$rr"
    for rep in 1 2; do
      disk2_p1="$WORK/$arm-p1-r$rep.d88"
      mfd_make_b0 "$disk2_p1" >/dev/null 2>"$WORK/$arm-p1-r$rep.gen.err" || gate_failed generate_disk
      mfd_exec_and_record "$arm" 1 "$rep" "$disk2_p1" "" "" 0
      disk2_p2="$WORK/$arm-p2-r$rep.d88"
      dir_fill_opt=()
      [ "$variant" = "00" ] && dir_fill_opt=(--dir-fill 00)
      python3 "$REPO/tools/m6fd_relocate.py" "$disk2_p1" "$disk2_p2" \
        --src-name QZ7B --dst-name "QD$rr" --dst-units 20 \
        --dst-slot "18,1,$r,0" ${dir_fill_opt[@]+"${dir_fill_opt[@]}"} \
        >/dev/null 2>"$WORK/$arm-p2-r$rep.relo.err" || gate_failed relocate
      mfd_exec_and_record "$arm" 2 "$rep" "$disk2_p2" "" "" 0
    done
  done
done
for rep in 1 2; do
  disk2="$WORK/III-none-r$rep.d88"
  mfd_make_b0 "$disk2" >/dev/null 2>"$WORK/III-none-r$rep.gen.err" || gate_failed generate_disk
  mfd_exec_and_record III-none "" "$rep" "$disk2" "" "" 0
done

if [ -n "${M6FD_TEST_STOP_AFTER_ARM:-}" ] && [ "$M6FD_TEST_STOP_AFTER_ARM" = "III" ]; then
  printf 'm6f-d measurement selftest: stopped after group=III\n'
  [ -n "${M6FD_TEST_RUNS_COPY:-}" ] && cp "$RUNS_JSON" "$M6FD_TEST_RUNS_COPY"
  exit 0
fi

# --- IV-R: 予約の印の掃引(256腕、試験用にM6FD_TEST_IV_R_MAXで絞れる) --------
IV_R_MAX="${M6FD_TEST_IV_R_MAX:-255}"
for v in $(seq 0 "$IV_R_MAX"); do
  hex="$(printf '%02X' "$v")"
  arm="IV-R-$hex"
  for rep in 1 2; do
    disk2="$WORK/$arm-r$rep.d88"
    python3 "$REPO/tools/make_m6fc_blank_disk.py" "$disk2" --fat-value "$v" --filler 0xFF \
      --sector-fill 18,1,13=0x00 --fat-position 20=0xFF \
      >/dev/null 2>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk
    mfd_exec_and_record "$arm" "" "$rep" "$disk2" "" QZ7A 0
  done
done

if [ -n "${M6FD_TEST_STOP_AFTER_ARM:-}" ] && [ "$M6FD_TEST_STOP_AFTER_ARM" = "IV-R" ]; then
  printf 'm6f-d measurement selftest: stopped after group=IV-R\n'
  [ -n "${M6FD_TEST_RUNS_COPY:-}" ] && cp "$RUNS_JSON" "$M6FD_TEST_RUNS_COPY"
  exit 0
fi

# --- D7: R* の導出(別担当のtools/derive_m6fd.pyに委ねる) --------------------
if [ -n "${M6FD_TEST_R_STAR:-}" ]; then
  if [ "$M6FD_TEST_R_STAR" = "none" ]; then R_STAR=""; else R_STAR="$M6FD_TEST_R_STAR"; fi
else
  r_star_out="$(python3 - "$REPO" "$WORK" "$raw_dir" <<'PY'
import json, sys
from pathlib import Path
repo, work, raw_dir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, str(Path(repo) / "tools"))
try:
    import derive_m6fd
except ImportError:
    print("IMPORT_ERROR")
    raise SystemExit(0)
runs = [json.loads(l) for l in (Path(work) / "runs.ndjson").read_text(encoding="utf-8").splitlines() if l.strip()]
result = {"schema": 1, "runs": runs}
r = derive_m6fd.r_star(result, raw_dir)
print("NONE" if r is None else r)
PY
)" || gate_failed r_star_derive
  case "$r_star_out" in
    IMPORT_ERROR) gate_failed derive_m6fd_missing ;;
    NONE) R_STAR="" ;;
    *) R_STAR="$r_star_out" ;;
  esac
fi

# --- IV-fill: 予約の印の要否(2腕、R*が無ければres側は回さず記録) ------------
disk2="$WORK/IV-fill-free-r1.d88"
mfd_make_b0 "$disk2" >/dev/null 2>"$WORK/IV-fill-free-r1.gen.err" || gate_failed generate_disk
mfd_exec_and_record IV-fill-free "" 1 "$disk2" "" "" 0
disk2="$WORK/IV-fill-free-r2.d88"
mfd_make_b0 "$disk2" >/dev/null 2>"$WORK/IV-fill-free-r2.gen.err" || gate_failed generate_disk
mfd_exec_and_record IV-fill-free "" 2 "$disk2" "" "" 0

if [ -n "$R_STAR" ]; then
  for rep in 1 2; do
    disk2="$WORK/IV-fill-res-r$rep.d88"
    mfd_make_b0 "$disk2" --fat-position "74=$R_STAR" --fat-position "75=$R_STAR" \
      >/dev/null 2>"$WORK/IV-fill-res-r$rep.gen.err" || gate_failed generate_disk
    mfd_exec_and_record IV-fill-res "" "$rep" "$disk2" "" "" 0
  done
else
  printf 'm6f-d: R* が無いため IV-fill-res は回さない\n'
fi

if [ -n "${M6FD_TEST_STOP_AFTER_ARM:-}" ] && [ "$M6FD_TEST_STOP_AFTER_ARM" = "IV-fill" ]; then
  printf 'm6f-d measurement selftest: stopped after group=IV-fill\n'
  [ -n "${M6FD_TEST_RUNS_COPY:-}" ] && cp "$RUNS_JSON" "$M6FD_TEST_RUNS_COPY"
  exit 0
fi

# --- V: 起動(6腕、ドライブ1に媒体・ドライブ2なし) ---------------------------
# bash 3.2対応: 連想配列(declare -A)は使えないのでcaseで分岐する。
mfd_v_boot_args() {
  case "$1" in
    V-missing) echo "--boot-sector-mode missing" ;;
    V-crc) echo "--boot-sector-mode crc" ;;
    V-deleted) echo "--boot-sector-mode deleted" ;;
    V-single) echo "--boot-sector-mode single" ;;
    V-ff) echo "" ;;
    V-c9) echo "--boot-fill 0xC9" ;;
    *) gate_failed v_boot_args ;;
  esac
}
for arm in V-missing V-crc V-deleted V-single V-ff V-c9; do
  for rep in 1 2; do
    disk1="$WORK/$arm-r$rep.d88"
    v_args="$(mfd_v_boot_args "$arm")"
    mfd_make_b0 "$disk1" $v_args \
      >/dev/null 2>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk
    mfd_exec_and_record "$arm" "" "$rep" "$disk1" "" "" 0
  done
done

# --- 結果の書き出し ----------------------------------------------------------
python3 - "$WORK" "$result" "$R_STAR" <<'PY' || gate_failed result_write
import json, sys
from pathlib import Path
work, out, r_star_raw = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
runs = [json.loads(line) for line in (work / "runs.ndjson").read_text(encoding="utf-8").splitlines() if line]
r_star = int(r_star_raw) if r_star_raw != "" else None
body = {"schema": 1, "drive_layout": "drive1=reference_copy_protected;drive2=generated;V=drive1_only",
        "r_star": r_star, "runs": runs}
with out.open("x", encoding="utf-8") as f:
    json.dump(body, f, sort_keys=True, separators=(",", ":")); f.write("\n")
PY

printf 'm6f-d measurement complete: raw=%s result=%s\n' "$raw_dir" "$result"

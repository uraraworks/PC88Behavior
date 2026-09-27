#!/usr/bin/env bash
# m6f-f測定ドライバ。事前登録 docs/notes/m6f-f-type-byte-by-save-mode-preregistration.md
# と追補1 docs/notes/m6f-f-addendum1-bsave-address.md のとおり、6腕(F-S/F-A/F-P/
# F-B/F-D/F-0)を各2走、ドライブ1=参照diskAの使い捨て複製、ドライブ2=m6fcのB0と
# 同じ規則の空媒体で実行する。フレーム8000、起動打鍵はフレーム300、刺激打鍵は
# フレーム700。手本は tools/measure_m6fd.sh（読んで流用した）。
#
# **このスクリプトは公式ROMを使う本番の腕を回すためのものだが、このセッション
# 自身はそれを実行しない**（作業指示により測定は回さない）。自己検査は
# tools/measure_m6ff_driver_selftest.sh（偽フロントエンドのみ）で行う。
#
# G3(凍結照合)は、公式ROM起動前・PC88_REF_ROM_DIR等の参照より前に行う。
# --bsave-addr 未指定、または凍結表のbsave_addrと不一致なら、公式ROM起動回数
# 0のまま gate_failed で止める(番地はマニュアルの言語仕様から親が決める値を
# ここへ渡す。このスクリプト自身はマニュアルを読まない)。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FF_FROZEN_CONFIG:-$REPO/tools/m6ff_frozen.tsv}"
FRONTEND="${M6FF_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }

raw_dir=""; result=""; bsave_addr=""; keep_images=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --raw-dir) raw_dir="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    --bsave-addr) bsave_addr="${2:-}"; shift 2 ;;
    --keep-images) keep_images=1; shift 1 ;;
    *) exit 2 ;;
  esac
done
[ -n "$raw_dir" ] && [ -n "$result" ] || exit 2

# --bsave-addr 未指定は、凍結照合より前に止める(公式ROM起動回数0)。
[ -n "$bsave_addr" ] || gate_failed bsave_addr_missing

# G3: 凍結照合は引数の番地整合も含め、公式ROM・環境変数参照より先に行う。
ADDR_DEC="$(python3 - "$REPO" "$bsave_addr" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import m6ff_keystrokes as k
try:
    print(k.parse_addr(sys.argv[2]))
except k.KeystrokeError:
    print("PARSE_ERROR")
PY
)"
[ "$ADDR_DEC" != "PARSE_ERROR" ] || gate_failed bsave_addr_parse
python3 "$REPO/tools/check_m6ff_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
  || gate_failed preregistration_mismatch
CFG_ADDR="$(awk -F '\t' '$1=="bsave_addr"{print $2}' "$CONFIG")"
[ "$CFG_ADDR" = "$ADDR_DEC" ] || gate_failed bsave_addr_mismatch

source "$REPO/tools/lib_m6f_measure.sh"

[ -n "${PC88_REF_ROM_DIR:-}" ] || gate_failed PC88_REF_ROM_DIR_missing
[ -d "$PC88_REF_ROM_DIR" ] || gate_failed reference_rom_dir_missing
[ -n "${PC88_REF_DISK_DIR:-}" ] || gate_failed PC88_REF_DISK_DIR_missing
[ -d "$PC88_REF_DISK_DIR" ] || gate_failed reference_disk_dir_missing
REF_DISK_NAME="$(m6f_cfg "$CONFIG" reference_disk)" || gate_failed reference_disk_config
REF_DISK="$PC88_REF_DISK_DIR/$REF_DISK_NAME"
[ -f "$REF_DISK" ] || gate_failed reference_disk_missing
REF_SHA="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha

# 生の像・入出力ログはリポジトリ外だけに置く。
m6f_check_output_paths "$REPO" "$raw_dir" "$result" || gate_failed output_paths
mkdir -p "$raw_dir" || gate_failed raw_dir
[ -d "$(dirname "$result")" ] || gate_failed result_parent
[ ! -e "$result" ] || gate_failed result_exists

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# G1: 器具自身の自己検査(run_all登録分のうち、本器具が直接依存するもの)。
"$REPO/tools/check_cleanroom.sh" >"$WORK/g1a.out" 2>"$WORK/g1a.err" || gate_failed G1_cleanroom
"$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$WORK/g1b.out" 2>&1 || gate_failed G1_generator
"$REPO/tools/m6fd_entry_selftest.sh" >"$WORK/g1c.out" 2>&1 || gate_failed G1_entry_reader

source "$REPO/tools/lib_l3_measure.sh"
CORE="${M6FF_TEST_CORE:-$(find_l3_core)}"; [ -n "$CORE" ] || gate_failed core_missing
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend_missing
else
  [ -x "$FRONTEND" ] || gate_failed frontend_missing
fi

BOOT_FRAME="$(m6f_cfg "$CONFIG" boot_return_frame)"
STIMULUS_FRAME="$(m6f_cfg "$CONFIG" stimulus_frame)"
RUN_FRAMES="$(m6f_cfg "$CONFIG" run_frames)"
TIMEOUT="$(m6f_cfg "$CONFIG" run_timeout_seconds)"

# G2: ドライブ2に使う空媒体を作る(m6fcのB0と同じ規則)。
mff_make_b0() {
  local out="$1"
  python3 "$REPO/tools/make_m6fc_blank_disk.py" "$out" --fat-value 0xFF --filler 0xFF \
    --sector-fill 18,1,13=0x00
}

mff_keystrokes() {
  # $1=arm
  python3 - "$REPO" "$1" "$ADDR_DEC" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import m6ff_keystrokes as k
arm, addr_dec = sys.argv[2], int(sys.argv[3])
text = k.keystrokes(arm, addr_dec if arm == "F-B" else None)
sys.stdout.write(k.escaped(text))
PY
}

mff_keystroke_sha_ok() {
  # $1=arm $2=打鍵テキスト(エスケープ後) — 凍結表のkeystroke_sha256と再照合する。
  python3 - "$REPO" "$CONFIG" "$1" "$2" <<'PY'
import hashlib, sys
sys.path.insert(0, sys.argv[1] + "/tools")
import check_m6ff_preregistration as c
cfg = c.load_tsv(__import__("pathlib").Path(sys.argv[2]))
keyed = c.parse_keyed(cfg["keystroke_sha256"])
arm, escaped_text = sys.argv[3], sys.argv[4]
text = escaped_text.replace("\\n", "\n")
digest = hashlib.sha256(text.encode("ascii")).hexdigest()
sys.exit(0 if keyed.get(arm) == digest else 1)
PY
}

ARMS="F-S F-A F-P F-B F-D F-0"
RUNS_JSON="$WORK/runs.ndjson"; : > "$RUNS_JSON"

mff_entry_name() {
  case "$1" in
    F-S) echo qzs ;; F-A) echo qza ;; F-P) echo qzp ;; F-B) echo qzb ;; F-D) echo qzd ;;
    F-0) echo "" ;;
    *) gate_failed entry_name ;;
  esac
}

for arm in $ARMS; do
  stim_escaped="$(mff_keystrokes "$arm")" || gate_failed keystrokes_resolve
  mff_keystroke_sha_ok "$arm" "$stim_escaped" || gate_failed keystroke_sha_mismatch

  for rep in 1 2; do
    disk1="$WORK/$arm-r$rep.drive1.d88"
    disk2="$WORK/$arm-r$rep.drive2.d88"
    [ -e "$disk1" ] && gate_failed disk1_exists
    cp "$REF_DISK" "$disk1" || gate_failed disk1_copy
    chmod u+w "$disk1" || gate_failed disk1_mode
    disk1_initial_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_sha
    [ "$disk1_initial_sha" = "$REF_SHA" ] || gate_failed disk1_copy_mismatch
    mff_make_b0 "$disk2" >/dev/null 2>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk

    iolog="$WORK/$arm-r$rep.iolog.txt"
    report="$WORK/$arm-r$rep.report.txt"
    qargs=(--core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk1" --disk2 "$disk2"
      --save-to-disk-image --frames "$RUN_FRAMES" --io-log "$iolog" --out "$report"
      --type-at "$BOOT_FRAME" --type '\n')
    if [ -n "$stim_escaped" ]; then
      qargs+=(--type-at "$STIMULUS_FRAME" --type "$stim_escaped")
    fi

    attempt=0; rc=0; aborts=0
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
arm, rep, aborts = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
print(json.dumps({"arm": arm, "repetition": rep, "abort": True, "abort_retries": aborts,
                   "drive1_sha_ok": None, "entry_fields": None}, sort_keys=True, separators=(",", ":")))
PY
        continue 2
      fi
      rm -f "$iolog" "$report"
    done

    [ -e "$report" ] && [ -s "$iolog" ] || gate_failed measurement_artifact

    # G7: 参照ディスク本体・使い捨て複製の両方が測定後も直前と同じであること。
    disk1_final_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_final_sha
    ref_sha_after="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha_after
    [ "$ref_sha_after" = "$REF_SHA" ] || gate_failed G7
    [ "$disk1_final_sha" = "$REF_SHA" ] || gate_failed G7

    name="$(mff_entry_name "$arm")"
    entry_fields_json="null"
    if [ -n "$name" ]; then
      entry_fields_json="$(python3 - "$REPO" "$disk2" "$name" <<'PY'
import json, sys
from pathlib import Path
repo, disk2, name = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
import m6fd_entry
fields = m6fd_entry.entry_fields(Path(disk2).read_bytes(), name.encode("ascii"))
print(json.dumps({name: fields}, sort_keys=True, separators=(",", ":")))
PY
)" || gate_failed entry_fields
    else
      # F-0(陰性対照): 他腕が使った名前のいずれかがディレクトリに見つかるかを確認する。
      entry_fields_json="$(python3 - "$REPO" "$disk2" <<'PY'
import json, sys
from pathlib import Path
repo, disk2 = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
import m6fd_entry
img = Path(disk2).read_bytes()
out = {}
for nm in ("qzs", "qza", "qzp", "qzb", "qzd"):
    out[nm] = m6fd_entry.entry_fields(img, nm.encode("ascii"))
print(json.dumps(out, sort_keys=True, separators=(",", ":")))
PY
)" || gate_failed entry_fields
    fi

    image_name=""
    if [ "$keep_images" = "1" ]; then
      image_name="$arm-r$rep.drive2.d88"
      cp "$disk2" "$raw_dir/$image_name" || gate_failed save_disk
    fi

    python3 - "$arm" "$rep" "$entry_fields_json" "$image_name" <<'PY' >> "$RUNS_JSON" || gate_failed "run_summary_${arm}_r${rep}"
import json, sys
arm, rep, entry_fields_raw, image_name = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
print(json.dumps({"arm": arm, "repetition": rep, "abort": False, "abort_retries": 0,
                   "drive1_sha_ok": True, "entry_fields": json.loads(entry_fields_raw),
                   "image": (image_name or None)},
                  sort_keys=True, separators=(",", ":")))
PY
  done
done

python3 - "$WORK" "$result" "$ADDR_DEC" <<'PY' || gate_failed result_write
import json, sys
from pathlib import Path
work, out, addr = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
runs = [json.loads(line) for line in (work / "runs.ndjson").read_text(encoding="utf-8").splitlines() if line]
body = {"schema": 1, "bsave_addr": addr,
        "drive_layout": "drive1=reference_copy_protected;drive2=generated", "runs": runs}
with out.open("x", encoding="utf-8") as f:
    json.dump(body, f, sort_keys=True, separators=(",", ":")); f.write("\n")
PY

printf 'm6f-f measurement complete: raw=%s result=%s\n' "$raw_dir" "$result"

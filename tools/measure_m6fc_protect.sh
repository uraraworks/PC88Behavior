#!/usr/bin/env bash
# m6f-c 追補3 測定ドライバ。「書き込み禁止」を決めているセクタ(18,1,13)・
# (18,1,1)の一様値Wを0x00〜0xFFで掃引し、腕P13-00〜P13-FF・P1-00〜P1-FFを
# 各2走実行する。
#
# 事前登録: docs/notes/m6f-c-addendum3-write-protect-sectors.md。
#
# 構成は追補2(docs/notes/m6f-c-addendum2-blank-disk-in-drive2.md)と同じ:
# ドライブ1に参照diskAの使い捨て複製(書き込み保護は解除しない)を入れて起動し、
# ドライブ2に生成器の媒体を入れる。打鍵は m6f-c本編の凍結表(tools/m6fc_frozen.tsv)
# のSW区間と完全に同じ文字列を使う(check_m6fc_protect_preregistration.pyが
# 起動前にこの一致を照合する)。
#
# **このスクリプトは公式ROMを使う本番の腕を回すためのものだが、
# このセッション自身はそれを実行しない**（作業指示により測定は回さない）。
# ここに置くのは器具そのものであり、関門と手順が事前登録・m6f-c本編と
# 一致することを自己検査で確認するにとどめる。
#
# 打鍵の渡し方・G8(ドライブ1不変)・装置番号の絞り込み(m6fc_fdc_by_drive.py)は
# tools/measure_m6fc.sh と同じ実装をここに複製している(共通部品への切り出しは
# 見送った。理由はコメント末尾)。両ドライバの通し検査
# (tools/measure_m6fc_driver_selftest.sh・tools/measure_m6fc_protect_driver_selftest.sh)
# で、それぞれ独立に偽フロントエンドへ渡るargvを検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FC_PROTECT_FROZEN_CONFIG:-$REPO/tools/m6fc_protect_frozen.tsv}"
FRONTEND="${M6FC_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }

# G7相当: 凍結照合は引数解釈・環境参照・frontend起動より先に行う。
python3 "$REPO/tools/check_m6fc_protect_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
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
# G3: 生成器・目印判定器・導出器の自己検査。
"$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$WORK/g3a.out" 2>&1 || gate_failed G3_generator
"$REPO/tools/check_m6fc_markers_selftest.sh" >"$WORK/g3b.out" 2>&1 || gate_failed G3_markers
"$REPO/tools/derive_m6fc_protect_selftest.sh" >"$WORK/g3c.out" 2>&1 || gate_failed G3_derive

source "$REPO/tools/lib_l3_measure.sh"
# 試験用の口(既定は無効): tools/measure_m6fc.sh と同じ設計。
CORE="${M6FC_PROTECT_TEST_CORE:-$(find_l3_core)}"; [ -n "$CORE" ] || gate_failed core_missing
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend_missing
else
  [ -x "$FRONTEND" ] || gate_failed frontend_missing
fi

BOOT_FRAME="$(m6f_cfg "$CONFIG" boot_return_frame)"
STIMULUS_FRAME="$(m6f_cfg "$CONFIG" stimulus_frame)"
FRAMES="$(m6f_cfg "$CONFIG" frames)"
KEYSTROKES="$(m6f_cfg "$CONFIG" keystrokes)"
case "$KEYSTROKES" in
  *$'\t'*|*$'\r'*) gate_failed keystrokes_format ;;
esac

# 凍結表のtarget行から掃引名->座標の対応を取り出す(照合器と同じ形式)。
mfp_target_coord() {
  python3 - "$CONFIG" "$1" <<'PY'
import sys
path, sweep = sys.argv[1], sys.argv[2]
for line in open(path, encoding="utf-8"):
    line = line.rstrip("\n")
    if not line.startswith("target\t"):
        continue
    _, value = line.split("\t", 1)
    key, _, coord = value.partition(":")
    if key == sweep:
        print(coord)
        raise SystemExit(0)
raise SystemExit(1)
PY
}
P13_COORD="$(mfp_target_coord P13)" || gate_failed target_config
P1_COORD="$(mfp_target_coord P1)" || gate_failed target_config

RUNS_JSON="$WORK/runs.ndjson"; : > "$RUNS_JSON"

# 1走ぶんを実行し、runs.ndjson へ1行追記する。$1=sweep(P13/P1) $2=coord(C,H,R) $3=w(10進) $4=rep
mfp_run_one() {
  local sweep="$1" coord="$2" w="$3" rep="$4"
  local hex; hex="$(printf '%02X' "$w")"
  local arm="$sweep-$hex"
  local disk2="$WORK/$arm-r$rep.d88"
  local disk1="$WORK/$arm-r$rep.drive1.d88"
  local iolog="$WORK/$arm-r$rep.iolog.txt"
  local report="$WORK/$arm-r$rep.report.txt"

  [ -e "$disk2" ] && gate_failed disk_exists
  python3 "$REPO/tools/make_m6fc_blank_disk.py" "$disk2" --fat-value 0xFF --filler 0xFF \
    --sector-fill "$coord=$w" >/dev/null 2>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk

  [ -e "$disk1" ] && gate_failed disk1_exists
  cp "$REF_DISK" "$disk1" || gate_failed disk1_copy
  chmod u+w "$disk1" || gate_failed disk1_mode
  local disk1_initial_sha; disk1_initial_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_sha
  [ "$disk1_initial_sha" = "$REF_SHA" ] || gate_failed disk1_copy_mismatch

  # 追補3 §3.1: 引数は本測定ドライバとそろえる（--save-to-disk-image）。
  local qargs=(--core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk1" --disk2 "$disk2"
    --save-to-disk-image --frames "$FRAMES" --io-log "$iolog" --out "$report"
    --type-at "$BOOT_FRAME" --type '\n'
    --type-at "$STIMULUS_FRAME" --type "$KEYSTROKES")

  # 追補3 §3.1: コアの abort（rc=134）は非決定的に起きた。最大2回まで回し直し、
  # 回し直すたびに媒体を作り直す。3回とも abort なら abort の走として記録する。
  local attempt=0 rc=0 aborts=0
  while :; do
    rc=0
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" "${qargs[@]}" \
      >"$WORK/$arm-r$rep.stdout.txt" 2>"$WORK/$arm-r$rep.stderr.txt" || rc=$?
    [ "$rc" = 0 ] && break
    [ "$rc" = 134 ] || gate_failed "emulator_run_${arm}_r${rep}_rc${rc}"
    aborts=$((aborts + 1))
    if [ "$aborts" -ge 3 ]; then
      printf '{"sector":"%s","w":%s,"repetition":%s,"abort":true,"abort_retries":%s,"markers":[],"reads":[],"writes":[],"write_data_count":0}\n' \
        "$sweep" "$w" "$rep" "$aborts" >> "$RUNS_JSON"
      return 0
    fi
    rm -f "$disk1" "$disk2" "$iolog" "$report"
    python3 "$REPO/tools/make_m6fc_blank_disk.py" "$disk2" --fat-value 0xFF --filler 0xFF \
      --sector-fill "$coord=$w" >/dev/null 2>>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk
    cp "$REF_DISK" "$disk1" || gate_failed disk1_copy
    chmod u+w "$disk1" || gate_failed disk1_mode
  done
  ABORT_RETRIES="$aborts"
  [ -e "$report" ] && [ -s "$iolog" ] || gate_failed measurement_artifact

  # G8: 参照ディスクの使い捨て複製(ドライブ1)は測定後も複製直後と同じ。
  local disk1_final_sha; disk1_final_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_final_sha
  [ "$disk1_final_sha" = "$REF_SHA" ] || gate_failed G8
  local ref_sha_after; ref_sha_after="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha_after
  [ "$ref_sha_after" = "$REF_SHA" ] || gate_failed G8

  local markers_json; markers_json="$(python3 "$REPO/tools/check_m6fc_markers.py" \
    --report "$report")" || gate_failed markers

  ABORT_RETRIES="$ABORT_RETRIES" python3 - "$REPO" "$sweep" "$w" "$rep" "$iolog" <<'PYEOF' >> "$RUNS_JSON" || gate_failed run_summary
import json, sys
from pathlib import Path
repo, sweep, w, rep, iolog = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
from analyze_main_to_sub import parse_iolog
from analyze_write_path import parse_commands
from m6fc_fdc_by_drive import split_by_drive

rows, masked = parse_iolog(Path(iolog))
if sum(masked.values()):
    print("エラー: 伏せ字ログでは座標を安全に取り出せない", file=sys.stderr)
    sys.exit(1)

text = Path(iolog).read_text(encoding="utf-8", errors="replace")
import re
dropped_total = 0
for m in re.finditer(r"取りこぼし:\s*(\d+)件", text):
    dropped_total += int(m.group(1))
if dropped_total:
    print(f"エラー: I/Oログに取りこぼしが{dropped_total}件ある", file=sys.stderr)
    sys.exit(1)

commands = parse_commands(rows)
split = split_by_drive(commands, 0)
reads, writes = split["reads"], split["writes"]

body = {
    "sector": sweep, "w": int(w), "repetition": int(rep),
    "abort_retries": int(__import__("os").environ.get("ABORT_RETRIES", "0")),
    "reads": reads, "writes": writes,
    "write_data_count": split["write_data_count"],
    "drive1_read_count": split["drive1_read_count"],
    "drive1_write_count": split["drive1_write_count"],
}
print(json.dumps(body, sort_keys=True, separators=(",", ":")))
PYEOF

  python3 - "$RUNS_JSON" "$markers_json" <<'PY' || gate_failed run_summary_merge
import json, sys
path, markers_raw = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().splitlines()
last = json.loads(lines[-1])
markers = json.loads(markers_raw)
last["markers"] = markers["markers"]
last["malformed_marker_rows"] = markers["malformed_marker_rows"]
lines[-1] = json.dumps(last, sort_keys=True, separators=(",", ":"))
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

for sweep_coord in "P13:$P13_COORD" "P1:$P1_COORD"; do
  sweep="${sweep_coord%%:*}"
  coord="${sweep_coord#*:}"
  W_MAX="${M6FC_PROTECT_TEST_W_MAX:-255}"
  for w in $(seq 0 "$W_MAX"); do
    mfp_run_one "$sweep" "$coord" "$w" 1
    mfp_run_one "$sweep" "$coord" "$w" 2
  done
  if [ -n "${M6FC_PROTECT_TEST_STOP_AFTER_SWEEP:-}" ] && [ "$sweep" = "$M6FC_PROTECT_TEST_STOP_AFTER_SWEEP" ]; then
    printf 'm6f-c addendum3 measurement selftest: stopped after sweep=%s\n' "$sweep"
    python3 - "$WORK" "$result" <<'PY' || gate_failed result_write
import json, sys
from pathlib import Path
work, out = Path(sys.argv[1]), Path(sys.argv[2])
runs = [json.loads(l) for l in (work / "runs.ndjson").read_text(encoding="utf-8").splitlines() if l]
body = {"schema": 1, "runs": runs,
        "drive_layout": "drive1=reference_copy_protected;drive2=generated"}
with out.open("x", encoding="utf-8") as f:
    json.dump(body, f, sort_keys=True, separators=(",", ":")); f.write("\n")
PY
    exit 0
  fi
done

python3 - "$WORK" "$result" <<'PY' || gate_failed result_write
import json, sys
from pathlib import Path
work, out = Path(sys.argv[1]), Path(sys.argv[2])
runs = [json.loads(line) for line in (work / "runs.ndjson").read_text(encoding="utf-8").splitlines() if line]
body = {"schema": 1, "runs": runs,
        "drive_layout": "drive1=reference_copy_protected;drive2=generated"}
with out.open("x", encoding="utf-8") as f:
    json.dump(body, f, sort_keys=True, separators=(",", ":")); f.write("\n")
PY

overall="$(python3 - "$REPO" "$result" <<'PY'
import json, sys
from pathlib import Path
repo, result_path = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, str(Path(repo) / "tools"))
from derive_m6fc_protect import build, load_result
result = load_result(result_path)
derived = build(result)
print(derived["overall"])
PY
)"
printf 'm6f-c addendum3 measurement complete: raw=%s result=%s overall=%s\n' "$raw_dir" "$result" "$overall"

# 共通部品への切り出しを見送った理由: measure_m6fc.sh は段階0(GB)〜段階2(A腕)
# まで含む長いドライバで、打鍵区間の解決(mfc_frames/mfc_segments)がその中の
# check_m6fc_preregistration.py の腕別テーブルに強く依存している。一方こちらは
# 単一区間・単一打鍵文字列の掃引のみで、対象セクタも凍結表のtarget行から
# 決まる。両者が共有するのは「ドライブ1複製の準備とG8」「装置番号1への絞り込み
# (m6fc_fdc_by_drive.split_by_drive)」「本物の改行を渡さない」という3点で、
# 後2つは既にモジュール(m6fc_fdc_by_drive.py)とKEYSTROKESのTSV表現(改行を含め
# ない一行文字列)で共有できている。残る「ドライブ1複製+G8」は10行程度の
# 重複であり、無理に関数化すると measure_m6fc.sh 側の動作実績のあるコードパスに
# 触れるリスクの方が大きいと判断し、複製のまま両方の通し検査で検査する。

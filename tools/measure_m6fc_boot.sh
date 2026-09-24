#!/usr/bin/env bash
# m6f-c 追補1 測定ドライバ。起動用セクタ(0,0,1)の一様値Xを0x00〜0xFFで
# 掃引し、腕BX-00〜BX-FFを各2走実行する。
#
# 事前登録: docs/notes/m6f-c-addendum1-boot-sector-sweep.md。
#
# **このスクリプトは公式ROMを使う本番の腕を回すためのものだが、
# このセッション自身はそれを実行しない**（作業指示により測定は回さない）。
# ここに置くのは器具そのものであり、関門と手順が事前登録と一致することを
# 自己検査で確認するにとどめる。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FC_BOOT_FROZEN_CONFIG:-$REPO/tools/m6fc_boot_frozen.tsv}"
FRONTEND="${M6FC_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
RUN_TIMEOUT_SECONDS=300
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }

# G7相当: 凍結照合は引数解釈・環境参照・frontend起動より先に行う。
python3 "$REPO/tools/check_m6fc_boot_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
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

# 公式ディスクは使わない(媒体は自作生成器で作る)。PC88_REF_DISK_DIRは見ない。
[ -n "${PC88_REF_ROM_DIR:-}" ] || gate_failed PC88_REF_ROM_DIR_missing
[ -d "$PC88_REF_ROM_DIR" ] || gate_failed reference_rom_dir_missing

# 出力先がリポジトリ外であること。
m6f_check_output_paths "$REPO" "$raw_dir" "$result" || gate_failed output_outside_repo
mkdir -p "$raw_dir" || gate_failed raw_dir
[ -d "$(dirname "$result")" ] || gate_failed result_parent
[ ! -e "$result" ] || gate_failed result_exists

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# G2
"$REPO/tools/check_cleanroom.sh" >"$WORK/g2.out" 2>"$WORK/g2.err" || gate_failed G2
# G3: 生成器・目印判定器・導出器の自己検査。
"$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$WORK/g3a.out" 2>&1 || gate_failed G3_generator
"$REPO/tools/check_m6fc_markers_selftest.sh" >"$WORK/g3b.out" 2>&1 || gate_failed G3_markers
"$REPO/tools/derive_m6fc_boot_selftest.sh" >"$WORK/g3c.out" 2>&1 || gate_failed G3_derive

source "$REPO/tools/lib_l3_measure.sh"
CORE="$(find_l3_core)"; [ -n "$CORE" ] || gate_failed core_missing
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend_missing
else
  [ -x "$FRONTEND" ] || gate_failed frontend_missing
fi

BOOT_FRAME="$(m6f_cfg "$CONFIG" boot_return_frame)"
STIMULUS_FRAME="$(m6f_cfg "$CONFIG" stimulus_frame)"
FRAMES="$(m6f_cfg "$CONFIG" frames)"
KEYSTROKES="$(m6f_cfg "$CONFIG" keystrokes)"

RUNS_JSON="$WORK/runs.ndjson"; : > "$RUNS_JSON"

# 1走ぶんを実行し、runs.ndjson へ1行追記する。$1=x(10進 0-255) $2=rep
mfb_run_one() {
  local x="$1" rep="$2"
  local hex; hex="$(printf '%02X' "$x")"
  local arm="BX-$hex"
  local disk="$WORK/$arm-r$rep.d88"
  local iolog="$WORK/$arm-r$rep.iolog.txt"
  local report="$WORK/$arm-r$rep.report.txt"
  [ -e "$disk" ] && gate_failed disk_exists
  python3 "$REPO/tools/make_m6fc_blank_disk.py" "$disk" --fat-value 0xFF --filler 0xFF \
    --boot-fill "$x" >/dev/null 2>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk

  local qargs=(--core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk"
    --frames "$FRAMES" --io-log "$iolog" --out "$report"
    --type-at "$BOOT_FRAME" --type '\n'
    --type-at "$STIMULUS_FRAME" --type "$KEYSTROKES")

  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$RUN_TIMEOUT_SECONDS" "$FRONTEND" "${qargs[@]}" \
    >"$WORK/$arm-r$rep.stdout.txt" 2>"$WORK/$arm-r$rep.stderr.txt" || gate_failed emulator_run
  [ -e "$report" ] && [ -s "$iolog" ] || gate_failed measurement_artifact

  local markers_json; markers_json="$(python3 "$REPO/tools/check_m6fc_markers.py" \
    --report "$report")" || gate_failed markers

  python3 - "$REPO" "$arm" "$x" "$rep" "$iolog" <<'PYEOF' >> "$RUNS_JSON" || gate_failed run_summary
import json, sys
from pathlib import Path
repo, arm, x, rep, iolog = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
from analyze_main_to_sub import parse_iolog
from analyze_write_path import parse_commands

rows, masked = parse_iolog(Path(iolog))
if sum(masked.values()):
    print("エラー: 伏せ字ログでは座標を安全に取り出せない", file=sys.stderr)
    sys.exit(1)

# 取りこぼし(容量超過)を検出する。黙って少なく数えない。
text = Path(iolog).read_text(encoding="utf-8", errors="replace")
import re
dropped_total = 0
for m in re.finditer(r"取りこぼし:\s*(\d+)件", text):
    dropped_total += int(m.group(1))
if dropped_total:
    print(f"エラー: I/Oログに取りこぼしが{dropped_total}件ある", file=sys.stderr)
    sys.exit(1)

commands = parse_commands(rows)
# フレーム0以降(全走査)のREAD DATA/WRITE DATAを座標だけ取り出す。
reads, writes = [], []
for c in commands:
    if c.param_values is None or len(c.param_values) < 4:
        continue
    base_c, base_h, base_r = c.param_values[1], c.param_values[2], c.param_values[3]
    if c.opcode == 0x06:  # READ DATA
        nsec = max(1, (c.result_bytes - 7) // 256) if c.result_bytes > 7 else 1
        target = reads
    elif c.opcode == 0x05:  # WRITE DATA
        nsec = max(1, (c.data_bytes // 256)) if c.data_bytes else 1
        target = writes
    else:
        continue
    for i in range(nsec):
        target.append({"c": base_c, "h": base_h, "r": base_r + i})

write_data_count = sum(1 for c in commands if c.opcode == 0x05)
read_001_count = sum(1 for r in reads if (r["c"], r["h"], r["r"]) == (0, 0, 1))

body = {
    "arm": arm, "x": int(x), "repetition": int(rep),
    "reads": reads, "read_001_count": read_001_count,
    "write_data_count": write_data_count,
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

for x in $(seq 0 255); do
  mfb_run_one "$x" 1
  mfb_run_one "$x" 2
done

python3 - "$WORK" "$result" <<'PY' || gate_failed result_write
import json, sys
from pathlib import Path
work, out = Path(sys.argv[1]), Path(sys.argv[2])
runs = [json.loads(line) for line in (work / "runs.ndjson").read_text(encoding="utf-8").splitlines() if line]
body = {"schema": 1, "runs": runs}
with out.open("x", encoding="utf-8") as f:
    json.dump(body, f, sort_keys=True, separators=(",", ":")); f.write("\n")
PY

overall="$(python3 - "$REPO" "$result" <<'PY'
import json, sys
from pathlib import Path
repo, result_path = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, str(Path(repo) / "tools"))
from derive_m6fc_boot import build, load_result
result = load_result(result_path)
derived = build(result)
print(derived["overall"])
PY
)"
printf 'm6f-c addendum1 measurement complete: raw=%s result=%s overall=%s\n' "$raw_dir" "$result" "$overall"

#!/usr/bin/env bash
# 公式環境なしで、後段run失敗時の部分成果物と集計を確認する。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FAKE_REPO="$WORK/repo"
OUT="$WORK/out"
OUT_ZERO="$WORK/out-zero"
OUT_DROP="$WORK/out-drop"
mkdir -p "$FAKE_REPO/tools" "$FAKE_REPO/tests/conformance" "$WORK/rom" "$WORK/disk"
cp "$SCRIPT_DIR/measure_no_disk_signals.sh" "$FAKE_REPO/tools/"
: > "$WORK/rom/MAIN.ROM"
: > "$WORK/disk/N88_FE.D88"
: > "$FAKE_REPO/tests/conformance/expected_screen.tsv"

cat > "$FAKE_REPO/tools/lib_l3_measure.sh" <<'EOF'
build_mixed_rom() { mkdir -p "$2"; : > "$2/DISK.ROM"; }
find_l3_core() { echo dummy-core; }
ensure_l3_frontend() { return 0; }
run_q88measure_retry() {
  local out_iolog="$1" out_stdout="$2" out_stderr="$3"
  shift 3
  local report="" arg
  while [ "$#" -gt 0 ]; do
    arg="$1"
    shift
    if [ "$arg" = "--out" ]; then report="$1"; shift; fi
  done
  if [ "${OFFICIAL_DROP_FAULT:-}" = 1 ] && [[ "$out_iolog" = *no_disk.official* ]]; then
    printf '%s\n' '# 取りこぼし: 1' > "$out_iolog"
  else
    printf '%s\n' '# 取りこぼし: 0' > "$out_iolog"
  fi
  printf '%s\n' 'synthetic report' > "$report"
  : > "$out_stdout"
  : > "$out_stderr"
  case "$out_iolog" in *no_disk.mixed-intervention*) return 1 ;; esac
  return 0
}
EOF

cat > "$FAKE_REPO/tools/analyze_no_disk_signals.py" <<'PY'
import os, pathlib, sys
args = sys.argv[1:]
out = pathlib.Path(args[args.index("--out") + 1])
if os.environ.get("ANALYZER_ZERO_FAULT") == "1":
    print("解析不能: 比較可能な公開ビットが0項目（結果ではなく測定失敗）", file=sys.stderr)
    raise SystemExit(2)
out.write_text("synthetic analysis\n", encoding="utf-8")
PY

PC88_NO_DISK_SIGNAL_OPT_IN=1 \
PC88_REF_ROM_DIR="$WORK/rom" \
PC88_REF_DISK_DIR="$WORK/disk" \
  bash "$FAKE_REPO/tools/measure_no_disk_signals.sh" --out-dir "$OUT" \
  >"$WORK/stdout" 2>"$WORK/stderr"
rc=$?

fail=0
ng() { echo "NG: $1" >&2; fail=$((fail + 1)); }
[ "$rc" -eq 1 ] || ng "3本目を失敗させた測定のrcが1でない（rc=${rc}）"
for tag in no_disk.official no_disk.mixed-default drive2.mixed-default no_disk.mixed-intervention; do
  [ -s "$OUT/$tag.iolog.txt" ] || ng "$tag.iolog.txt が保存されていない"
  [ -s "$OUT/$tag.report.txt" ] || ng "$tag.report.txt が保存されていない"
  [ -s "$OUT/$tag.meta.json" ] || ng "$tag.meta.json が保存されていない"
done
grep -q '^状態: 採用$' "$OUT/no_disk.official.status.txt" || ng "公式armが採用されていない"
grep -q '^ROM構成: 公式ROM一式$' "$OUT/no_disk.official.status.txt" || ng "公式armの構成表示がない"
grep -q '^状態: 採用$' "$OUT/no_disk.mixed-default.status.txt" || ng "混成no_diskが採用されていない"
grep -q '^状態: 採用$' "$OUT/drive2.mixed-default.status.txt" || ng "混成正常B:が採用されていない"
grep -q '^状態: 測定失敗' "$OUT/no_disk.mixed-intervention.status.txt" || ng "介入armが失敗になっていない"
grep -q '^状態: 部分的$' "$OUT/no_disk-suite-summary.txt" || ng "部分結果表示がない"
grep -q '^run試行数: 4本$' "$OUT/no_disk-suite-summary.txt" || ng "試行数が4でない"
grep -q '^採用成功数: 3本$' "$OUT/no_disk-suite-summary.txt" || ng "採用成功数が3でない"
grep -q '^測定失敗数: 1本$' "$OUT/no_disk-suite-summary.txt" || ng "失敗数が1でない"
grep -q '^解析失敗数: 0件$' "$OUT/no_disk-suite-summary.txt" || ng "解析失敗数が0でない"
grep -q '^採用run成果物数: 9個' "$OUT/no_disk-suite-summary.txt" || ng "採用成果物数が9でない"
grep -q '^保存済みrun成果物数: 12個' "$OUT/no_disk-suite-summary.txt" || ng "保存成果物数が12でない"

python3 - "$OUT" <<'PY' || ng "runメタデータの構成・役割が期待と違う"
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
expected = {
    "no_disk.official": ("official_no_disk", "official_full", "no_disk"),
    "no_disk.mixed-default": ("mixed_no_disk", "mixed_default", "no_disk"),
    "drive2.mixed-default": ("mixed_normal", "mixed_default", "normal_drive2"),
    "no_disk.mixed-intervention": ("mixed_intervention", "mixed_intervention", "no_disk"),
}
for tag, wanted in expected.items():
    meta = json.loads((out / f"{tag}.meta.json").read_text(encoding="utf-8"))
    got = (meta["report_role"], meta["rom_configuration"], meta["condition"])
    if got != wanted:
        raise SystemExit(f"{tag}: {got} != {wanted}")
PY

if [ "$fail" -ne 0 ]; then
  echo "--- 合成測定 stdout ---" >&2
  cat "$WORK/stdout" >&2
  echo "--- 合成測定 stderr ---" >&2
  cat "$WORK/stderr" >&2
  echo "--- 合成測定 summary ---" >&2
  cat "$OUT/no_disk-suite-summary.txt" >&2
  exit 1
fi
echo "OK: 4 runのROM構成メタデータを保存し、介入失敗時も試行4/採用3/成果物9（保存12）を集計"

# 公式1 arm・混成既定2 armの関門へ比較可能0項目を注入し、介入へ進まないことを検査する。
ANALYZER_ZERO_FAULT=1 \
PC88_NO_DISK_SIGNAL_OPT_IN=1 \
PC88_REF_ROM_DIR="$WORK/rom" \
PC88_REF_DISK_DIR="$WORK/disk" \
  bash "$FAKE_REPO/tools/measure_no_disk_signals.sh" --out-dir "$OUT_ZERO" \
  >"$WORK/zero.stdout" 2>"$WORK/zero.stderr"
zero_rc=$?
[ "$zero_rc" -eq 1 ] || ng "比較可能0項目を注入した測定のrcが1でない（rc=${zero_rc}）"
grep -q '^状態: 部分的$' "$OUT_ZERO/no_disk-suite-summary.txt" || ng "0項目時に部分的でない"
grep -q '^run試行数: 3本$' "$OUT_ZERO/no_disk-suite-summary.txt" || ng "介入を走らせず試行3本になっていない"
grep -q '^解析失敗数: 1件$' "$OUT_ZERO/no_disk-suite-summary.txt" || ng "解析失敗1件を集計していない"
grep -q '^状態: 未実施$' "$OUT_ZERO/no_disk.mixed-intervention.status.txt" || ng "介入runが未実施でない"
if [ -e "$OUT_ZERO/no_disk.mixed-intervention.iolog.txt" ]; then
  ng "公式arm事前検査失敗後に介入runを実行している"
fi
if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "OK: 比較可能0項目を解析失敗として集計し、公式＋混成既定関門不合格後の介入を阻止"

# 高密度の公式armだけを溢れさせる。最初の1 runで止め、特例採用せず
# 容量増加が必要という判断を成果物へ残すことを確かめる。
OFFICIAL_DROP_FAULT=1 \
PC88_NO_DISK_SIGNAL_OPT_IN=1 \
PC88_REF_ROM_DIR="$WORK/rom" \
PC88_REF_DISK_DIR="$WORK/disk" \
  bash "$FAKE_REPO/tools/measure_no_disk_signals.sh" --out-dir "$OUT_DROP" \
  >"$WORK/drop.stdout" 2>"$WORK/drop.stderr"
drop_rc=$?
[ "$drop_rc" -eq 1 ] || ng "公式取りこぼし注入時のrcが1でない（rc=${drop_rc}）"
grep -q '^run試行数: 1本$' "$OUT_DROP/no_disk-suite-summary.txt" || ng "公式取りこぼし後に後続runを実行した"
grep -q '^状態: 不採用$' "$OUT_DROP/no_disk.official.status.txt" || ng "公式取りこぼしrunを不採用にしていない"
grep -q 'I/O容量をさらに増やして再測定' "$OUT_DROP/no_disk-signals.txt" || ng "容量不足時の判断を記録していない"
if [ -e "$OUT_DROP/no_disk.mixed-default.iolog.txt" ]; then
  ng "公式取りこぼし確認前に混成runを実行している"
fi
if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "OK: 公式armの取りこぼし故障を先に検出し、後続runを止めて容量増加判断を記録"

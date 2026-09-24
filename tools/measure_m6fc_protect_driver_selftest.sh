#!/usr/bin/env bash
# tools/measure_m6fc_protect_driver_selftest.sh — tools/measure_m6fc_protect.sh
# (m6f-c追補3測定ドライバ)自体の自己検査。公式ROM・本物のq88measureは
# 一切使わない。tools/measure_m6fc_driver_selftest.sh と同じ設計
# (偽フロントエンドへ渡るargvを記録して検査する)。
#
# やること:
#   1. M6FC_FRONTEND に偽フロントエンドを差し込み、PC88_REF_ROM_DIR は空の
#      一時ディレクトリ、find_l3_core が見つからない環境に備えた試験用の口
#      M6FC_PROTECT_TEST_CORE でコアの実在チェックだけ迂回する。
#   2. 全512走(2掃引×256×2)を回すと重いので、試験用の口
#      M6FC_PROTECT_TEST_W_MAX(既定255=無効)と
#      M6FC_PROTECT_TEST_STOP_AFTER_SWEEP(既定は無効)でP13-00までに絞る。
#   3. 偽フロントエンドに渡ったargvを記録し、--disk2 の --sector-fill が
#      対象座標(18,1,13)と一致し、打鍵(--type-at 700直後)が
#      m6fc_protect_frozen.tsv の keystrokes と完全一致することを検査する。
#   4. G8陰性対照: 偽フロントエンドがドライブ1を書き換えたら
#      gate_failed G8で止まることを確認する。
#   5. 陰性対照: PC88_REF_DISK_DIR に参照ディスクが無いとgate_failedで止まる。
#
# 画面本文・公式ROM・vendor/・禁止された生成器/自己検査は一切触れない。
#
# 使い方: tools/measure_m6fc_protect_driver_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

# --- 偽フロントエンドを用意する(measure_m6fc.sh の自己検査と同じ設計) ------
FAKE="$WORK/fake_frontend.py"
cat > "$FAKE" <<'PYEOF'
#!/usr/bin/env python3
import json
import os
import sys


def _find(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
    return None


def main() -> int:
    argv = sys.argv[1:]
    # 追補3 §3.1 の回し直しの経路を通すため、指定回数だけ rc を返して落ちる。
    fail_n = int(os.environ.get("M6FC_PROTECT_SELFTEST_FAIL_FIRST_N", "0") or 0)
    fail_rc = int(os.environ.get("M6FC_PROTECT_SELFTEST_FAIL_RC", "134") or 134)
    counter = os.environ.get("M6FC_PROTECT_SELFTEST_FAIL_COUNTER")
    if fail_n and counter:
        n = int(open(counter).read() or 0) if os.path.exists(counter) else 0
        if n < fail_n:
            open(counter, "w").write(str(n + 1))
            return fail_rc
    out_path = _find(argv, "--out")
    iolog_path = _find(argv, "--io-log")
    disk1_path = _find(argv, "--disk")
    disk2_path = _find(argv, "--disk2")

    # --sector-fillは生成器(make_m6fc_blank_disk.py)への引数であり、
    # フロントエンドのargvには出てこない。代わりに、生成済みの--disk2を
    # 独立読み手(d88_read_sector)で読み、対象セクタ(18,1,13)の中身を
    # argvログへ一緒に記録する(生成が規則どおりだったかをここで検査する)。
    sector_1813 = None
    repo = os.environ.get("M6FC_PROTECT_SELFTEST_REPO")
    if disk2_path and repo:
        sys.path.insert(0, os.path.join(repo, "tools"))
        from d88_read_sector import D88Reader  # noqa: PLC0415
        with open(disk2_path, "rb") as f:
            reader = D88Reader(f.read())
        payload = reader.read_sector(18, 1, 13)
        sector_1813 = payload[0] if len(set(payload)) == 1 else "not_uniform"

    log_path = os.environ.get("M6FC_PROTECT_SELFTEST_ARGV_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv, "sector_18_1_13": sector_1813},
                                ensure_ascii=False) + "\n")

    if os.environ.get("M6FC_PROTECT_SELFTEST_CORRUPT_DISK1") and disk1_path:
        with open(disk1_path, "r+b") as f:
            f.seek(0)
            f.write(b"\xff")

    if iolog_path:
        with open(iolog_path, "w", encoding="utf-8") as f:
            f.write("# fake iolog (measure_m6fc_protect_driver_selftest)\n")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("[測定終了時のテキスト画面]\n")
            f.write('0| ZQok\n')
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
chmod +x "$FAKE"

mkdir -p "$WORK/rom" "$WORK/raw" "$WORK/refdisk"
ARGVLOG="$WORK/argv.jsonl"
: > "$ARGVLOG"
printf 'FAKE-REFERENCE-DISK-FOR-SELFTEST' > "$WORK/refdisk/N88_FE.D88"

# --- 1. 陽性側: P13-00までrc=0で完走する -------------------------------------
env \
  M6FC_FRONTEND="$FAKE" \
  PC88_REF_ROM_DIR="$WORK/rom" \
  PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FC_PROTECT_TEST_CORE="selftest-core" \
  M6FC_PROTECT_TEST_W_MAX=0 \
  M6FC_PROTECT_TEST_STOP_AFTER_SWEEP=P13 \
  M6FC_PROTECT_SELFTEST_ARGV_LOG="$ARGVLOG" \
  M6FC_PROTECT_SELFTEST_REPO="$REPO" \
  "$REPO/tools/measure_m6fc_protect.sh" --raw-dir "$WORK/raw" --result "$WORK/result.json" \
  >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt"
run_rc=$?

if [ "$run_rc" -eq 0 ] && grep -q 'stopped after sweep=P13' "$WORK/run.stdout.txt"; then
  ok "陽性側: ドライバがP13-00までrc=0で完走した"
else
  ng "陽性側: ドライバがrc=0で完走しなかった(rc=$run_rc)。末尾: $(tail -c 300 "$WORK/run.stderr.txt")"
fi

# --- 2. argvの検査(--sector-fillと打鍵が凍結表と一致) ------------------------
VERIFY="$WORK/verify_positive.py"
cat > "$VERIFY" <<'PYEOF'
import json
import sys
from pathlib import Path

argv_log = Path(sys.argv[1])
frozen_path = Path(sys.argv[2])


def load_keystrokes(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("keystrokes\t"):
            return line.split("\t", 1)[1]
    return None


expected_keystrokes = load_keystrokes(frozen_path)

entries = []
if argv_log.exists():
    for line in argv_log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
calls = [e["argv"] for e in entries]

fails = []
if len(calls) != 2:
    fails.append(f"呼び出しが2件でない(P13-00の2走): {len(calls)}")

for entry in entries:
    argv = entry["argv"]
    sector_val = entry.get("sector_18_1_13")
    if sector_val != 0:
        fails.append(f"生成物の(18,1,13)がW=0で塗られていない: {sector_val!r}")

    if "--type-at" not in argv:
        fails.append("--type-atが渡されていない")
        continue
    # 700直後の--typeを探す
    got_type = None
    for j in range(len(argv) - 3):
        if argv[j] == "--type-at" and argv[j + 1] == "700" and argv[j + 2] == "--type":
            got_type = argv[j + 3]
    if got_type != expected_keystrokes:
        fails.append("打鍵(700直後の--type)が凍結表のkeystrokesと不一致")
    if got_type is not None and "\n" in got_type:
        fails.append("打鍵に本物の改行文字が含まれている")

if not calls:
    fails.append("argvログが空(偽フロントエンドが一度も呼ばれていない)")

if fails:
    for m in fails:
        print("NG: " + m)
    sys.exit(1)
print(f"OK: argvが凍結表と一致(呼び出し{len(calls)}件)")
sys.exit(0)
PYEOF

verify_out="$(python3 "$VERIFY" "$ARGVLOG" "$REPO/tools/m6fc_protect_frozen.tsv" 2>&1)"
verify_rc=$?
printf '%s\n' "$verify_out"
if [ "$verify_rc" -eq 0 ]; then
  ok "argv検査: --sector-fill・打鍵が凍結表と一致"
else
  ng "argv検査が失敗した"
fi

# --- 3. 陰性対照: 参照ディスクが無いとgate_failedで止まる -------------------
rm -f "$WORK/refdisk/N88_FE.D88"
env \
  M6FC_FRONTEND="$FAKE" \
  PC88_REF_ROM_DIR="$WORK/rom" \
  PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FC_PROTECT_TEST_CORE="selftest-core" \
  M6FC_PROTECT_TEST_W_MAX=0 \
  M6FC_PROTECT_TEST_STOP_AFTER_SWEEP=P13 \
  "$REPO/tools/measure_m6fc_protect.sh" --raw-dir "$WORK/raw_missing" --result "$WORK/result_missing.json" \
  >"$WORK/missing.stdout.txt" 2>"$WORK/missing.stderr.txt"
missing_rc=$?
if [ "$missing_rc" -ne 0 ] && grep -q 'reference_disk_missing' "$WORK/missing.stdout.txt"; then
  ok "陰性対照: 参照ディスク欠落をgate_failed reference_disk_missingで検出した"
else
  ng "陰性対照: 参照ディスク欠落を検出できなかった(rc=$missing_rc)"
fi
printf 'FAKE-REFERENCE-DISK-FOR-SELFTEST' > "$WORK/refdisk/N88_FE.D88"

# --- 4. G8陰性対照: ドライブ1書き換えでgate_failed G8 ------------------------
env \
  M6FC_FRONTEND="$FAKE" \
  PC88_REF_ROM_DIR="$WORK/rom" \
  PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FC_PROTECT_TEST_CORE="selftest-core" \
  M6FC_PROTECT_TEST_W_MAX=0 \
  M6FC_PROTECT_TEST_STOP_AFTER_SWEEP=P13 \
  M6FC_PROTECT_SELFTEST_CORRUPT_DISK1=1 \
  "$REPO/tools/measure_m6fc_protect.sh" --raw-dir "$WORK/raw_g8" --result "$WORK/result_g8.json" \
  >"$WORK/g8.stdout.txt" 2>"$WORK/g8.stderr.txt"
g8_rc=$?
if [ "$g8_rc" -ne 0 ] && grep -q '"reason":"G8"' "$WORK/g8.stdout.txt"; then
  ok "G8陰性対照: ドライブ1の書き換えをgate_failed G8として検出した"
else
  ng "G8陰性対照: ドライブ1の書き換えを検出できなかった(rc=$g8_rc, stdout=$(cat "$WORK/g8.stdout.txt"))"
fi
if [ "$(cat "$WORK/refdisk/N88_FE.D88")" = "FAKE-REFERENCE-DISK-FOR-SELFTEST" ]; then
  ok "G8陰性対照: 参照ディスク本体は書き換わっていない(複製だけが壊れた)"
else
  ng "G8陰性対照: 参照ディスク本体まで書き換わってしまった"
fi

# --- 5. 追補3 §3.1: abort の回し直し ----------------------------------------
run_fail() { # $1=tag $2=fail_n $3=fail_rc
  : > "$WORK/cnt_$1"
  env M6FC_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
    M6FC_PROTECT_TEST_CORE="selftest-core" M6FC_PROTECT_TEST_W_MAX=0 \
    M6FC_PROTECT_TEST_STOP_AFTER_SWEEP=P13 M6FC_PROTECT_SELFTEST_REPO="$REPO" \
    M6FC_PROTECT_SELFTEST_FAIL_FIRST_N="$2" M6FC_PROTECT_SELFTEST_FAIL_RC="$3" \
    M6FC_PROTECT_SELFTEST_FAIL_COUNTER="$WORK/cnt_$1" \
    "$REPO/tools/measure_m6fc_protect.sh" --raw-dir "$WORK/raw_$1" --result "$WORK/result_$1.json" \
    >"$WORK/$1.stdout.txt" 2>"$WORK/$1.stderr.txt"
}
run_fail once 1 134; once_rc=$?
if [ "$once_rc" -eq 0 ] && grep -q '"abort_retries": *1' "$WORK"/*once* "$WORK/raw_once"/* 2>/dev/null; then
  ok "回し直し: 1回の abort の後に完走し、abort_retries=1 を記録した"
elif [ "$once_rc" -eq 0 ] && python3 - "$WORK" <<'PY2'
import json,sys,glob
hits=[l for f in glob.glob(sys.argv[1]+"/**/*",recursive=True) if f.endswith((".json",".ndjson")) for l in open(f,errors="replace") if '"abort_retries": 1' in l or '"abort_retries":1' in l]
raise SystemExit(0 if hits else 1)
PY2
then
  ok "回し直し: 1回の abort の後に完走し、abort_retries=1 を記録した"
else
  ng "回し直し: 1回の abort で完走しなかった、または回数が記録されていない(rc=$once_rc)"
fi
run_fail always 99 134; always_rc=$?
if [ "$always_rc" -eq 0 ] && python3 - "$WORK" <<'PY2'
import sys,glob
hits=[l for f in glob.glob(sys.argv[1]+"/**/*",recursive=True) if f.endswith((".json",".ndjson")) for l in open(f,errors="replace") if '"abort": true' in l or '"abort":true' in l]
raise SystemExit(0 if hits else 1)
PY2
then
  ok "回し直し: 3回とも abort の走を abort として記録した"
else
  ng "回し直し: 毎回 abort の走を abort として記録できなかった(rc=$always_rc)"
fi
run_fail other 1 7; other_rc=$?
if [ "$other_rc" -ne 0 ] && grep -q 'emulator_run_' "$WORK/other.stdout.txt"; then
  ok "陰性対照: 134 以外の異常終了は gate_failed になった"
else
  ng "陰性対照: 134 以外の異常終了を gate_failed にできなかった(rc=$other_rc)"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"

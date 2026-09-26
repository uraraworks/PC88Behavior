#!/usr/bin/env bash
# m6f-e器具Dの通し自己検査。公式ROM・公式diskAは使わず、署名だけを書く
# 偽フロントエンドで30走、G0〜G8の起動前停止、G14陰性対照を検査する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-driver-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

FAKE="$WORK/fake_frontend.py"
cat >"$FAKE" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import sys

repo = pathlib.Path(os.environ["M6FE_SELFTEST_REPO"])
sys.path.insert(0, str(repo / "tools"))
import predict_m6fe as predict


def one(argv, name):
    try:
        index = argv.index(name)
    except ValueError:
        return None
    return argv[index + 1]


def all_values(argv, name):
    return [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == name]


def hash_line(row, body):
    raw = f"{row}\t{body}\n".encode("utf-8")
    return (row, len(body), hashlib.sha256(raw).hexdigest())


def write_report(path, snapshots):
    with open(path, "w", encoding="ascii") as target:
        for snapshot_id, rows in snapshots:
            rows = sorted(rows)
            target.write(f"snapshot_id\t{snapshot_id}\n")
            target.write("physical_row\tchar_count\tsha256\n")
            for row, count, digest in rows:
                target.write(f"{row}\t{count}\t{digest}\n")
            whole = hashlib.sha256("".join(
                f"{row}\t{count}\t{digest}\n" for row, count, digest in rows
            ).encode("ascii")).hexdigest()
            target.write(f"line_count\t{len(rows)}\n")
            target.write(f"char_count\t{sum(item[1] for item in rows)}\n")
            target.write(f"sha256\t{whole}\n")


def ev(lines, seq, frame, kind, value):
    seq += 1
    lines.append(f"{seq:>6} {seq:>6} {frame:>6}  sub   {kind:<4}  00FB   {value:02X}   0100")
    return seq


def main():
    argv = sys.argv[1:]
    out = pathlib.Path(one(argv, "--out"))
    iolog = pathlib.Path(one(argv, "--io-log"))
    arm = out.parent.name.rsplit("-r", 1)[0]
    manifest = predict._manifest(pathlib.Path(os.environ["M6FE_SELFTEST_MANIFEST"]))
    candidate = "files_layout_rule_G5_SPLIT63_80DOT_00BLANK_SECTORS"
    counter = pathlib.Path(os.environ["M6FE_SELFTEST_COUNTER"])
    with counter.open("a", encoding="ascii") as target:
        target.write("1\n")
    argv_log = pathlib.Path(os.environ["M6FE_SELFTEST_ARGV_LOG"])
    with argv_log.open("a", encoding="ascii") as target:
        target.write(json.dumps({"arm": arm, "argv": argv}, separators=(",", ":")) + "\n")

    if arm.startswith(("D-", "E-")):
        if (one(argv, "--swap-disk1-at") != "650"
                or one(argv, "--swap-disk1") is None):
            return 2
        # 実物main.cのswap-disk1と同じ形式のイベント行をstderrへ出す
        # （--screen-signature-only時はreport本体へは出ないので、
        # 呼び出し側の確認先はstderr——実物に合わせる）。
        success = 0 if os.environ.get("M6FE_SELFTEST_SWAP_DISK1_FAIL") else 1
        sys.stderr.write(f"[q88measure] event\tswap_disk1\tframe=650\tsuccess={success}\n")
        if not success:
            return 1
    if arm == "N-wait":
        if one(argv, "--insert-disk2-at") != "1200" or "--expect-disk2-empty" not in argv:
            return 2

    baseline = [hash_line(0, "PROMPT"), hash_line(19, "FKEY")]
    if os.environ.get("M6FE_SELFTEST_BAD_BASELINE"):
        baseline.append(hash_line(5, "X"))
    if arm in predict.LAYOUT_ARMS:
        entries = [(item.physical_row, item.char_count, item.sha256)
                   for item in predict.predict_candidate(manifest, arm, candidate)]
    elif arm in ("D-omit", "D-1", "D-2", "D-expr", "N-wait"):
        entries = [(item.physical_row, item.char_count, item.sha256)
                   for item in predict.predict_candidate(manifest, arm, candidate)]
    elif arm == "E-0":
        entries = [(item.physical_row, item.char_count, item.sha256)
                   for item in predict.predict_error(5)]
    elif arm == "E-3":
        entries = [(item.physical_row, item.char_count, item.sha256)
                   for item in predict.predict_error(70)]
    else:
        entries = [(item.physical_row, item.char_count, item.sha256)
                   for item in predict.predict_error(2)]
    prompt_row = max((item[0] for item in entries), default=-1) + 1
    final = entries + [hash_line(prompt_row, "PROMPT"), hash_line(19, "FKEY")]
    snapshots = [("baseline", baseline), ("final", final), ("late", list(final))]
    if arm == "N-wait":
        snapshots.append(("preinsert", [hash_line(0, "WAIT"), hash_line(19, "FKEY")]))
    requested = {spec.split(":", 1)[0] for spec in all_values(argv, "--screen-signature-at")}
    write_report(out, [item for item in snapshots if item[0] in requested])

    lines = []
    seq = 0
    if arm in ("D-omit", "D-1"):
        seq = ev(lines, seq, 800, "OUT", 0x46)
        for value in (0, 18, 1, 1, 0, 0, 0, 0):
            seq = ev(lines, seq, 800, "OUT", value)
        seq = ev(lines, seq, 800, "IN", 0)
    if arm == "N-wait":
        for frame in (800, 900, 1000, 1100):
            seq = ev(lines, seq, frame, "OUT", 0x04)
            seq = ev(lines, seq, frame, "OUT", 1)
            seq = ev(lines, seq, frame, "IN", 0)
    iolog.write_text("# synthetic iolog\n" + "\n".join(lines) + ("\n" if lines else ""),
                     encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
chmod +x "$FAKE"

mkdir -p "$WORK/rom" "$WORK/refdisk"
printf '%s' 'SYNTHETIC-REFERENCE-DISK' >"$WORK/refdisk/N88_FE.D88"
python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/fixture" >/dev/null 2>&1 || exit 1
COUNTER="$WORK/count.txt"
ARGV_LOG="$WORK/argv.jsonl"

run_driver() {
  local target="$1"; shift
  env M6FE_FRONTEND="$FAKE" M6FE_TEST_CORE=selftest-core \
    M6FE_SELFTEST_REPO="$REPO" M6FE_SELFTEST_MANIFEST="$WORK/fixture/manifest.json" \
    M6FE_SELFTEST_COUNTER="$COUNTER" M6FE_SELFTEST_ARGV_LOG="$ARGV_LOG" \
    M6FE_TEST_ROM_DIR="$WORK/rom" M6FE_TEST_DISK_DIR="$WORK/refdisk" \
    PC88_M6FE_WORK="$target" "$@" "$REPO/tools/measure_m6fe.sh"
}

# 正常系は実際のG1/G5/G6自己検査も含めて一度だけ通す。
: >"$COUNTER"; : >"$ARGV_LOG"
run_driver "$WORK/result-positive" M6FE_TEST_MODE=1 \
  >"$WORK/positive.out" 2>"$WORK/positive.err"
positive_rc=$?
if [ "$positive_rc" -eq 0 ] \
  && grep -q 'judgment=files_layout_rule_G5_SPLIT63_80DOT_00BLANK_SECTORS' "$WORK/positive.out" \
  && [ "$(wc -l <"$COUNTER" | tr -d ' ')" = 30 ]; then
  ok "正常系は30走を完走し、一意な判定名を出した"
else
  ng "正常系が完走しない(rc=$positive_rc, launches=$(wc -l <"$COUNTER" | tr -d ' '))"
fi

if python3 - "$WORK/result-positive" "$ARGV_LOG" <<'PY'
import json, pathlib, sys
result, argv_log = map(pathlib.Path, sys.argv[1:])
judgment = json.loads((result / "judgment.json").read_text(encoding="ascii"))
summary = json.loads((result / "summary.json").read_text(encoding="ascii"))
observations = json.loads((result / "observations.json").read_text(encoding="ascii"))
def argv_value(argv, name):
    return argv[argv.index(name) + 1]

assert judgment["overall"] == "files_layout_rule_G5_SPLIT63_80DOT_00BLANK_SECTORS"
assert summary["run_count"] == summary["frontend_launch_count"] == 30
assert summary["drive1_read_count"] == {"D-omit": [1, 1], "D-1": [1, 1]}
assert set(observations["arms"]) == {"L0","L1","L4","L5","L6","L11","L96",
    "D-omit","D-1","D-2","D-expr","E-0","E-3","E-str","N-wait"}
calls = [json.loads(line) for line in argv_log.read_text(encoding="ascii").splitlines()]
assert len(calls) == 30
for call in calls:
    argv = call["argv"]
    specs = [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == "--screen-signature-at"]
    assert "baseline:600" in specs
    assert any(item.startswith("final:") for item in specs)
    assert any(item.startswith("late:") for item in specs)
    assert "--screen-signature-only" in argv
for call in calls:
    if call["arm"].startswith(("D-", "E-")):
        assert argv_value(call["argv"], "--swap-disk1-at") == "650"
PY
then
  ok "30走のJSON契約、D-1/D-omit READ件数、署名時点を確認した"
else
  # 上の短い検査で関数定義順に依存しないよう、失敗内容は画面本文なしで扱う。
  ng "正常系の出力契約が不正"
fi

# G0〜G8を1項目ずつ偽にし、NG集合がその1件だけ、起動回数0であることを照合。
for gate in G0 G1 G2 G3 G4 G5 G6 G7 G8; do
  : >"$COUNTER"; : >"$ARGV_LOG"
  target="$WORK/result-$gate"
  # G7は実物main.cのソースに--swap-disk1/--swap-disk1-atが揃ったので、
  # 他のゲートと同じ標準経路（M6FE_TEST_FAIL_GATEでの強制偽装）で試験する。
  run_driver "$target" M6FE_TEST_MODE=1 M6FE_TEST_FAST_GATES=1 M6FE_TEST_FAIL_GATE="$gate" \
    >"$WORK/$gate.out" 2>"$WORK/$gate.err"
  gate_rc=$?
  if [ "$gate_rc" -ne 0 ] && [ ! -s "$COUNTER" ] \
    && python3 - "$WORK/$gate.out" "$gate" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="ascii"))
raise SystemExit(0 if value.get("failed_gates") == [sys.argv[2]]
                 and value.get("frontend_launch_count") == 0 else 1)
PY
  then
    ok "$gate 陰性対照はNG集合={$gate}、起動回数0で停止した"
  else
    ng "$gate 陰性対照の停止条件またはNG集合が不正"
  fi
done

# G7実働: 差し替え失敗(success=0)の偽フロントエンドでは、D/E系のrunが
# run_failedとして止まり、打鍵(--type-at 700)より後に到達した形跡
# （--type-atのargv自体は積むが、フロントエンドが打鍵フレームへ到達する前に
# rc!=0で終わる設計）が無いことを確認する。偽フロントエンドはreport/iologを
# 書く前に return 1 するので、run_one側の[ -s "$report" ]判定で必ず落ちる。
: >"$COUNTER"; : >"$ARGV_LOG"
run_driver "$WORK/result-swapfail" M6FE_TEST_MODE=1 M6FE_TEST_FAST_GATES=1 \
  M6FE_SELFTEST_SWAP_DISK1_FAIL=1 >"$WORK/swapfail.out" 2>"$WORK/swapfail.err"
swapfail_rc=$?
if [ "$swapfail_rc" -ne 0 ] \
  && grep -q '"reason":"run_failed"' "$WORK/swapfail.out" \
  && [ "$(wc -l <"$COUNTER" | tr -d ' ')" -ge 15 ]; then
  ok "差し替え失敗の偽フロントエンドはD-omitでrun_failedとして止まった(打鍵前)"
else
  ng "差し替え失敗時の停止条件が不正(rc=$swapfail_rc)"
fi

# G14: baselineのrow5へ1文字相当の署名を足す。最初の1走で専用判定名になる。
: >"$COUNTER"; : >"$ARGV_LOG"
run_driver "$WORK/result-g14" M6FE_TEST_MODE=1 M6FE_TEST_FAST_GATES=1 \
  M6FE_SELFTEST_BAD_BASELINE=1 >"$WORK/g14.out" 2>"$WORK/g14.err"
g14_rc=$?
if [ "$g14_rc" -eq 0 ] && [ "$(wc -l <"$COUNTER" | tr -d ' ')" = 1 ] \
  && grep -q 'judgment=inconclusive_cls_baseline' "$WORK/g14.out"; then
  ok "G14陰性対照は最初の走でinconclusive_cls_baselineになった"
else
  ng "G14陰性対照が専用判定名で停止しない"
fi

echo
if [ "$rc" -eq 0 ]; then printf '%s\n' '全項目 OK'; else printf '%s\n' 'NG あり'; fi
exit "$rc"

#!/usr/bin/env bash
# 公開ビット差を1ビットずつ故障注入し、常時「差なし」の検査でないことを確認する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 - "$REPO" "$WORK" <<'PY'
import sys
import subprocess
import json
from pathlib import Path

repo, work = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / "tools"))
import analyze_no_disk_signals as analyzer


def write_log(path, fault=None, timing_fault=False, count_fault=False,
              completion_fault=False, timeout_fault=False):
    rows = []
    seq = 0
    clock = 100

    def add(kind, port, value, step=1):
        nonlocal seq, clock
        seq += 1
        clock += step
        rows.append((seq, clock, 750, "sub", kind, port, value, "0100"))

    def changed(field, value):
        if fault and fault[0] == field:
            return value ^ (1 << fault[1])
        return value

    # MSRはFDCデータ相と独立したsub可視入力として置く。
    add("IN", "00FA", changed("MSR", 0x80))
    add("IN", "00FE", changed("PIO_FE", 0x08))
    # SENSE DRIVE STATUS
    add("OUT", "00FB", 0x04); add("OUT", "00FB", 0x01)
    if not completion_fault:
        add("IN", "00FB", changed("ST3", 0x21), 2 if timing_fault else 1)
    if count_fault:
        add("OUT", "00FB", 0x04); add("OUT", "00FB", 0x01)
        add("IN", "00FB", changed("ST3", 0x21))
    # SEEK -> SENSE INTERRUPT STATUS
    add("OUT", "00FB", 0x0F); add("OUT", "00FB", 0x01); add("OUT", "00FB", 0x02)
    add("OUT", "00FB", 0x08)
    seek_st0 = changed("SIS", changed("SEEK_SIS", 0x21))
    add("IN", "00FB", seek_st0); add("IN", "00FB", 0x02)
    # RECALIBRATE -> SENSE INTERRUPT STATUS
    add("OUT", "00FB", 0x07); add("OUT", "00FB", 0x01)
    add("OUT", "00FB", 0x08)
    recal_st0 = changed("SIS", changed("RECAL_SIS", 0x21))
    add("IN", "00FB", recal_st0); add("IN", "00FB", 0x00)
    # READ DATA。合成試験ではデータ相を省き、公開結果7バイトだけを置く。
    add("OUT", "00FB", 0x06)
    for value in (1, 0, 0, 1, 1, 1, 0x2A, 0xFF):
        add("OUT", "00FB", value)
    for field, value in (("READ_ST0", 0x01), ("READ_ST1", 0), ("READ_ST2", 0)):
        add("IN", "00FB", changed(field, value))
    for value in (0, 0, 1, 1):
        add("IN", "00FB", value)
    if timeout_fault:
        add("OUT", "00F9", 1)

    with path.open("w", encoding="utf-8") as fp:
        fp.write("# 公開μPD765形式だけから作った合成ログ\n")
        for row in rows:
            seq_, clock_, frame, cpu, kind, port, value, pc = row
            fp.write(f"{seq_:6d} {clock_:7d} {frame:6d} {cpu} {kind:<4} "
                     f"{port} {value:02X} {pc}\n")


def write_meta(path, run_id, role, config, condition):
    path.write_text(json.dumps({
        "schema": "pc88-no-disk-run-v1", "run_id": run_id,
        "report_role": role, "rom_configuration": config,
        "condition": condition,
    }, ensure_ascii=False), encoding="utf-8")


mixed_no_meta = work / "mixed-no.meta.json"
mixed_normal_meta = work / "mixed-normal.meta.json"
official_meta = work / "official.meta.json"
intervention_meta = work / "intervention.meta.json"
write_meta(mixed_no_meta, "mixed-no", "mixed_no_disk", "mixed_default", "no_disk")
write_meta(mixed_normal_meta, "mixed-normal", "mixed_normal", "mixed_default",
           "normal_drive2")
write_meta(official_meta, "official-no", "official_no_disk", "official_full", "no_disk")
write_meta(intervention_meta, "mixed-wait", "mixed_intervention",
           "mixed_intervention", "no_disk")


def run_report(no_path, normal_path, after_frame, **kwargs):
    return analyzer.report(no_path, normal_path, after_frame,
                           mixed_no_meta, mixed_normal_meta, **kwargs)


base = work / "base.txt"
same = work / "same.txt"
write_log(base)
write_log(same)
baseline = run_report(base, same, 700)
if "差を検出した公開ビット: 0項目" not in baseline:
    print("NG: 同一合成入力を公開ビット差なしと判定できない")
    raise SystemExit(1)
print("OK: 同一合成入力は全公開ビット差なし")

# 比較可能0項目は「差なし」という結果ではなく測定失敗である。公開結果相も
# MSRも無い合成ログをCLIへ渡し、非0終了することを故障注入として確認する。
zero_a = work / "zero-a.txt"
zero_b = work / "zero-b.txt"
for path in (zero_a, zero_b):
    path.write_text(
        "     1       1    750 sub OUT  00F9 01 0100\n"
        "# 取りこぼし: 0件 / 総イベント数: 1件\n",
        encoding="utf-8",
    )
zero_run = subprocess.run(
    [sys.executable, str(repo / "tools" / "analyze_no_disk_signals.py"),
     "--no-disk", str(zero_a), "--normal", str(zero_b), "--after-frame", "700",
     "--no-disk-meta", str(mixed_no_meta),
     "--normal-meta", str(mixed_normal_meta)],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
)
if zero_run.returncode == 0 or "比較可能な公開ビットが0項目" not in zero_run.stderr:
    print("NG: 比較可能0項目の故障注入を解析失敗として検出できない")
    raise SystemExit(1)
print("OK: 比較可能0項目の故障注入を解析失敗(rc!=0)として検出")

# 公式arm事前検査の採取窓メタデータを陽性/陰性の両方で確かめる。
window_ok = work / "window-ok.txt"
window_late = work / "window-late.txt"
body = base.read_text(encoding="utf-8")
window_ok.write_text("frames    : 800\nio-log-from-frame: 700\n" + body,
                     encoding="utf-8")
window_late.write_text("frames    : 800\nio-log-from-frame: 780\n" + body,
                       encoding="utf-8")
run_report(window_ok, window_ok, 700, official_path=window_ok,
           official_meta_path=official_meta, through_frame=800,
           require_full_window=True)
try:
    run_report(window_late, window_ok, 700, official_path=window_ok,
               official_meta_path=official_meta, through_frame=800,
               require_full_window=True)
except analyzer.AnalysisError as exc:
    if "採取窓に全て入っていない" not in str(exc):
        raise
else:
    print("NG: 20F短縮窓を100F必要区間の事前検査が拒否しない")
    raise SystemExit(1)
print("OK: 公式arm事前検査は100F全区間を受理し、20F短縮窓を拒否")

cases = [
    ("ST3", analyzer.ST3_BITS, "SENSE DRIVE STATUS / ST3"),
    ("READ_ST0", analyzer.ST0_BITS, "READ DATA / ST0"),
    ("READ_ST1", analyzer.ST1_BITS, "READ DATA / ST1"),
    ("READ_ST2", analyzer.ST2_BITS, "READ DATA / ST2"),
    ("SIS", analyzer.ST0_BITS, "SENSE INTERRUPT STATUS / ST0"),
    ("SEEK_SIS", analyzer.ST0_BITS, "SEEK 後 SENSE INTERRUPT STATUS / ST0"),
    ("RECAL_SIS", analyzer.ST0_BITS, "RECALIBRATE 後 SENSE INTERRUPT STATUS / ST0"),
    ("MSR", analyzer.MSR_BITS, "FDC MSR"),
    ("PIO_FE", tuple((bit, f"bit{bit}") for bit in range(7, -1, -1)), "IN $FE"),
]
injected = 0
for field, definitions, title in cases:
    for bit, name in definitions:
        broken = work / f"broken-{field}-{bit}.txt"
        write_log(broken, fault=(field, bit))
        result = run_report(base, broken, 700)
        section = result.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0]
        expected = f"bit{bit} {name}: 差あり"
        if expected not in section:
            print(f"NG: {title} {expected} の故障注入を検出できない")
            raise SystemExit(1)
        injected += 1
print(f"OK: 公開ビット故障注入{injected}件を1ビットずつ全て検出")

temporal_faults = (
    ("timing", dict(timing_fault=True), "所要clock集合=差あり"),
    ("count", dict(count_fault=True), "発行件数=差あり"),
    ("completion", dict(completion_fault=True), "完了状態=差あり"),
    ("timeout", dict(timeout_fault=True), "自作subタイムアウト印: 差あり"),
)
for tag, kwargs, expected in temporal_faults:
    broken = work / f"broken-{tag}.txt"
    write_log(broken, **kwargs)
    result = run_report(base, broken, 700)
    if expected not in result:
        print(f"NG: 時間・完了故障注入 {tag} を検出できない")
        raise SystemExit(1)
print("OK: 所要時間・発行件数・未完了・タイムアウトの故障注入を検出")


def write_density_log(path, counts, dropped=0):
    seq = clock = 0
    with path.open("w", encoding="utf-8") as fp:
        fp.write("# 公開FDCコマンドの件数だけを作った密度合成ログ\n")
        for offset, count in enumerate(counts):
            for _ in range(count):
                for kind, value in (("OUT", 0x04), ("OUT", 0x01), ("IN", 0x21)):
                    seq += 1
                    clock += 1
                    fp.write(f"{seq:6d} {clock:7d} {750 + offset:6d} sub {kind:<4} "
                             f"00FB {value:02X} 0100\n")
        fp.write(f"# 取りこぼし: {dropped}件 / 総イベント数: {seq}件\n")


official_density = work / "density-official.txt"
normal_density = work / "density-normal.txt"
intervention_density = work / "density-intervention.txt"
write_density_log(official_density, [1, 2])
write_density_log(normal_density, [1, 2])
write_density_log(intervention_density, [2, 4])
density_result = run_report(
    official_density, normal_density, 750,
    official_path=official_density, official_meta_path=official_meta,
    intervention_path=intervention_density,
    intervention_meta_path=intervention_meta, through_frame=752,
    suite_state="完全（selftest）",
)
for expected in (
    "公式ROM一式・no_disk: 3件、1.500件/F、単位F範囲 1..2件",
    "混成介入・no_disk: 6件、3.000件/F、単位F範囲 2..4件",
    "密度比（混成介入/公式ROM一式）: 2.000倍（件数比 2:1）",
    "混成介入・no_disk窓内のsub→main応答: 0件（応答欠落を確認）",
    "m7ci入口判定区間51800件との照合: 件数不一致（今回の公式採取窓は3件）",
):
    if expected not in density_result:
        print(f"NG: 反復密度指標を期待通り算出できない: {expected}")
        raise SystemExit(1)
print("OK: 公式ROM一式/混成介入の構成・単位F件数・範囲・密度比・m7ci照合を出力")

# 密度列を先頭フレームの件数へ定数化する故障を注入する。独立した期待値
# (公式1..2、介入2..4)との不一致を陽性として捕まえる。
constantized = run_report(
    official_density, normal_density, 750,
    official_path=official_density, official_meta_path=official_meta,
    intervention_path=intervention_density,
    intervention_meta_path=intervention_meta, through_frame=752,
    suite_state="完全（selftest）", density_fault_constant=True,
)
if ("公式ROM一式・no_disk: 3件、1.500件/F、単位F範囲 1..2件" in constantized or
        "混成介入・no_disk: 6件、3.000件/F、単位F範囲 2..4件" in constantized):
    print("NG: 密度定数化故障を独立期待値で検出できない")
    raise SystemExit(1)
print("OK: 密度を定数化する故障注入を検出")

dropped_density = work / "density-dropped.txt"
write_density_log(dropped_density, [2, 4], dropped=1)
try:
    run_report(official_density, normal_density, 750,
               official_path=official_density, official_meta_path=official_meta,
               intervention_path=dropped_density,
               intervention_meta_path=intervention_meta, through_frame=752)
except analyzer.AnalysisError as exc:
    if "不採用" not in str(exc):
        raise
else:
    print("NG: 取りこぼしrunを解析器が不採用にしない")
    raise SystemExit(1)
print("OK: 取りこぼしrunを解析器が不採用として拒否")

# 「公式密度」役へ混成既定メタデータを渡す、今回の事故そのものを合成する。
mislabeled_official = work / "mislabeled-official.meta.json"
write_meta(mislabeled_official, "not-official", "official_no_disk",
           "mixed_default", "no_disk")
try:
    run_report(official_density, normal_density, 750,
               official_path=official_density,
               official_meta_path=mislabeled_official,
               intervention_path=intervention_density,
               intervention_meta_path=intervention_meta, through_frame=752)
except analyzer.AnalysisError as exc:
    if "ラベルとROM構成/条件の不一致" not in str(exc):
        raise
else:
    print("NG: 公式ラベルへ混成既定ROM構成を付ける故障注入を見逃した")
    raise SystemExit(1)
print("OK: 公式ラベルと混成既定ROM構成を食い違わせた故障注入を検出")

for expected in (
    "参照run: mixed-no［ROM構成: 混成既定",
    "対 mixed-normal［ROM構成: 混成既定",
    "参照run: official-no［ROM構成: 公式ROM一式］ 対 mixed-wait［ROM構成: 混成介入",
):
    if expected not in density_result:
        print(f"NG: 比較項目のrun構成表示が無い: {expected}")
        raise SystemExit(1)
print("OK: 報告の混成既定比較と公式対混成介入比較に参照runのROM構成を明記")

for forbidden in ("0x21", "=21", "0x80", "=80"):
    if forbidden in baseline:
        print("NG: 解析出力へ合成結果値が漏れた")
        raise SystemExit(1)
print("OK: 解析出力にFDC/MSRの生値列を含めない")

# 使い捨て介入は、既定ROMを変えず、指定版だけ一般READ入口の先頭へ
# CALL SENSE DRIVE STATUS + JR自己ループの5バイトを置く。
sys.path.insert(0, str(repo / "src" / "l3_service"))
import make_subrom as subrom
default_rom, default_used = subrom.build()
explicit_default_rom, explicit_default_used = subrom.build(intervene_no_disk_wait=False)
wait_rom, wait_used = subrom.build(intervene_no_disk_wait=True)
wait_asm = subrom.build_subrom(intervene_no_disk_wait=True)
wait_asm.resolve()
entry = wait_asm.labels["_general_read_request"]
sense = wait_asm.labels["FDC_SENSE_DRIVE_STATUS"]
expected_loop = bytes((0xCD, sense & 0xFF, sense >> 8, 0x18, 0xFB))
if not (default_rom == explicit_default_rom and default_used == explicit_default_used
        and wait_used == default_used + 5
        and bytes(wait_asm.code[entry:entry + 5]) == expected_loop
        and wait_used < subrom.SUB_ROM_FETCH_WINDOW):
    print("NG: no_disk待ち介入の既定不変・5バイトループ・フェッチ窓検査に失敗")
    raise SystemExit(1)
print("OK: 待ち介入は指定時だけSENSE反復5バイトを追加し、既定ROMは不変")
PY

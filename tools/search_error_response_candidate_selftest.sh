#!/usr/bin/env bash
# 合成抽象列だけで候補指標・定数化故障・該当なし判定を検証する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
import importlib.util
import re
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1])

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

search = load("search_error_response_candidate",
              repo / "tools/search_error_response_candidate.py")
subrom = load("make_subrom_candidate_selftest",
              repo / "src/l3_service/make_subrom.py")

fail = False
def ok(message):
    print(f"OK: {message}")
def ng(message):
    global fail
    fail = True
    print(f"NG: {message}")

reference = search.AbstractResult(
    exchange=(("main→sub", 6), ("sub→main", 1), ("main→sub", 6)),
    fdc=("SEEK", "READ DATA", "READ DATA"),
    screen_line_count=3, screen_char_count=12, screen_sha256="a" * 64)
candidate0 = search.AbstractResult(
    exchange=(("main→sub", 6), ("sub→main", 1), ("main→sub", 2)),
    fdc=("SEEK", "READ DATA", "SEEK"),
    screen_line_count=2, screen_char_count=9, screen_sha256="b" * 64)
candidate1 = search.AbstractResult(
    exchange=reference.exchange, fdc=reference.fdc,
    screen_line_count=reference.screen_line_count,
    screen_char_count=reference.screen_char_count,
    screen_sha256=reference.screen_sha256)

m0 = search.compare_result(reference, candidate0, 0)
m1 = search.compare_result(reference, candidate1, 1)
if (m0.exchange_prefix, m0.fdc_prefix) == (2, 2) and search.exact_match(m1) \
        and search.metric_vector(m0) != search.metric_vector(m1):
    ok("候補差が交換prefix・FDC prefix・画面3指標へ反映される")
else:
    ng("候補差が指標へ反映されない")

status, selected = search.classify_results([m0, m1])
if status == "found" and selected == [1]:
    ok("完全一致候補だけを発見として報告する")
else:
    ng("完全一致候補の発見判定が不正")

# 故障注入: 候補1の入力にも候補0の固定結果を返す計算器を模す。
constant0 = search.compare_result(reference, candidate0, 0)
constant1 = search.compare_result(reference, candidate0, 1)
status, selected = search.classify_results([constant0, constant1])
if status == "insensitive" and not selected:
    ok("常に同じ値を返す指標計算故障を検査不能として検出")
else:
    ng("定数化した指標計算故障を検出できない")

# 完全一致は無いが指標は異なる入力。insensitiveやfoundにしてはいけない。
candidate2 = search.AbstractResult(
    exchange=(("main→sub", 6),), fdc=("SEEK",),
    screen_line_count=1, screen_char_count=1, screen_sha256="c" * 64)
m2 = search.compare_result(reference, candidate2, 2)
status, selected = search.classify_results([m0, m2])
if status == "not_found" and selected:
    ok("完全一致0件を『見つからなかった』と判定し、最良候補は別表示する")
else:
    ng("完全一致0件を正しくnot_foundにできない")

default_rom, default_used = subrom.build()
candidate_rom0, candidate_used0 = subrom.build(error_response_candidate=0)
candidate_rom1, candidate_used1 = subrom.build(error_response_candidate=1)
diffs = [pos for pos, (left, right) in enumerate(zip(candidate_rom0, candidate_rom1))
         if left != right]
# 2026-09-10: 絶対値2042の直書きをやめた。見たいのは「既定版と候補版が
# 同サイズ」＝候補の切り替えが即値1セルしか動かさないことと、窓内であること。
if default_used == candidate_used0 == candidate_used1 \
        and candidate_used0 <= subrom.SUB_ROM_FETCH_WINDOW:
    ok(f"既定版・候補版とも同サイズ（{default_used}バイト）でフェッチ窓内")
else:
    ng("生成コードサイズまたはフェッチ窓制約が不正")
if default_rom == candidate_rom0:
    ok("既定値0x00は候補0で再現できる")
else:
    ng("既定値を候補0で再現できない")
if len(diffs) == 1 and candidate_rom0[diffs[0]] == 0 \
        and candidate_rom1[diffs[0]] == 1:
    ok("候補0/1の生成ROM差分は候補即値セル1バイトだけ")
else:
    ng("候補差が即値セル1バイト以外へ波及した")

# m7ls: 打鍵フレームを引数化しても、既定値700のargvは変更前と完全一致する。
OLD_FIXED_SUFFIX = ["--type-at", "300", "--type", r"\n",
                    "--type-at", "700", "--type", r"FILES 2\n"]
if search.keystroke_command_suffix() == OLD_FIXED_SUFFIX:
    ok("keystroke_command_suffixの既定値argvは変更前の固定argvと完全一致")
else:
    ng("keystroke_command_suffixの既定値argvが変更前と食い違う")
if search.keystroke_command_suffix(780) == \
        ["--type-at", "300", "--type", r"\n",
         "--type-at", "780", "--type", r"FILES 2\n"]:
    ok("keystroke_command_suffixは打鍵フレームを差し替えられる")
else:
    ng("keystroke_command_suffixが打鍵フレームを反映しない")

# m7ls: classify_keystroke_shiftの4判定。
def shift_arm(valid, request_length):
    return {"valid": valid, "request_length": request_length}

nondet_sides = {
    "official": {"deterministic": False, "expected_control": 5,
                "shift_arms": [shift_arm(True, 5)] * 3},
    "mixed": {"deterministic": True, "expected_control": 6,
             "shift_arms": [shift_arm(True, 6)] * 3},
}
if search.classify_keystroke_shift(nondet_sides) == "nondeterministic":
    ok("対照の繰り返し不一致をnondeterministicと判定")
else:
    ng("対照の繰り返し不一致をnondeterministicと判定できない")

flipped_sides = {
    "official": {"deterministic": True, "expected_control": 5,
                "shift_arms": [shift_arm(True, 5), shift_arm(True, 6), shift_arm(True, 5)]},
    "mixed": {"deterministic": True, "expected_control": 6,
             "shift_arms": [shift_arm(True, 6)] * 3},
}
if search.classify_keystroke_shift(flipped_sides) == "keystroke_timing_affects_branch":
    ok("有効な腕で要求長が動くとkeystroke_timing_affects_branchと判定")
else:
    ng("要求長が動いたのにkeystroke_timing_affects_branchにならない")

excluded_sides = {
    "official": {"deterministic": True, "expected_control": 5,
                "shift_arms": [shift_arm(True, 5)] * 3},
    "mixed": {"deterministic": True, "expected_control": 6,
             "shift_arms": [shift_arm(True, 6)] * 3},
}
if search.classify_keystroke_shift(excluded_sides) == "wait_length_excluded":
    ok("6腕すべて有効で要求長不変ならwait_length_excludedと判定")
else:
    ng("6腕すべて有効・不変なのにwait_length_excludedにならない")

unreached_sides = {
    "official": {"deterministic": True, "expected_control": 5,
                "shift_arms": [shift_arm(False, None), shift_arm(True, 5), shift_arm(True, 5)]},
    "mixed": {"deterministic": True, "expected_control": 6,
             "shift_arms": [shift_arm(True, 6)] * 3},
}
if search.classify_keystroke_shift(unreached_sides) == "inconclusive_ineffective_arms":
    ok("unreachedな腕が1つでもあるとwait_length_excludedにならない")
else:
    ng("unreachedな腕があるのにwait_length_excludedへ落ちる、または誤判定")

# m7ls 陽性対照①: 打鍵フレームをargvへ渡し忘れる故障（腕が常に700で走る）を、
# 有効性条件(c)（+0開始フレームのずれが打鍵フレーム移動量と対応するか）が
# 捕まえることを確かめる。files_at=780（期待ずれ+80）なのに実際のずれが
# 0（=700のまま走った）合成データを与える。
forgot_shift = search.keystroke_shift_arm_valid(
    reached=True, exchange_prefix_matches_control=True,
    start_frame_delta=0, expected_delta=780 - 700,
    window_count_differs_from_control=True)
if forgot_shift is False:
    ok("陽性対照1: 打鍵フレーム渡し忘れ（ずれ0）を条件(c)が無効と判定")
else:
    ng("陽性対照1: 打鍵フレーム渡し忘れが無効と判定されない（直す前に赤くならない）")

# m7ls 陽性対照②: 条件(c)の許容幅を無限にする故障で、陽性対照①のケースが
# 検出されなくなる（=有効と誤判定される）ことを確認し、(c)が検出を担って
# いることを裏付ける。
forgot_shift_unbounded_tolerance = search.keystroke_shift_arm_valid(
    reached=True, exchange_prefix_matches_control=True,
    start_frame_delta=0, expected_delta=780 - 700,
    window_count_differs_from_control=True,
    tolerance=10 ** 9)
if forgot_shift_unbounded_tolerance is True:
    ok("陽性対照2: 許容幅を無限にすると陽性対照1の故障が検出されなくなる"
       "（条件(c)が検出を担っている確認）")
else:
    ng("陽性対照2: 許容幅を無限にしても検出されてしまい、(c)の寄与を確認できない")

# m7lt: --sub-cpu-mode未指定時のargvは変更前と完全に同じ（空断片）。
if search.sub_cpu_mode_command_suffix(None) == []:
    ok("sub_cpu_mode_command_suffix(None)は空でargvを変えない")
else:
    ng("sub_cpu_mode_command_suffix(None)が空でない")
if search.sub_cpu_mode_command_suffix("2") == ["--sub-cpu-mode", "2"]:
    ok("sub_cpu_mode_command_suffixが指定値をargvへ反映する")
else:
    ng("sub_cpu_mode_command_suffixが指定値を反映しない")

# m7lt: no_diskの+0を校正ファイルのaxisに依らず構造だけで同定する
# （locate_plus0_no_disk: start_frameが700以上の最初のmain→sub run）。
class FakeRun:
    def __init__(self, direction, length, start_frame, end_frame):
        self.direction, self.length = direction, length
        self.start_frame, self.end_frame = start_frame, end_frame

plus0_runs = [
    FakeRun("main→sub", 8, 10, 20),
    FakeRun("sub→main", 256, 650, 690),
    FakeRun("main→sub", 5, 759, 770),
]
found = search.locate_plus0_no_disk(plus0_runs)
if found == {"exists": True, "index": 2, "length": 5, "start_frame": 759,
            "runs_before": 2, "boot_end_frame": 690}:
    ok("locate_plus0_no_diskがstart_frame>=700の最初のmain→sub runを+0として同定")
else:
    ng(f"locate_plus0_no_diskの+0同定が不正: {found}")

unreached_runs = [FakeRun("main→sub", 8, 10, 20)]
found_unreached = search.locate_plus0_no_disk(unreached_runs)
if found_unreached["exists"] is False and found_unreached["boot_end_frame"] == 20:
    ok("locate_plus0_no_diskは+0未到達をexists=Falseで表す")
else:
    ng(f"locate_plus0_no_diskの未到達表現が不正: {found_unreached}")

# m7lt: classify_cpu_mode_screenの5判定。
def cpu_mode_side(g0=True, none_ok=True,
                  m0_ok=True, m0_det=True,
                  m1_ok=True, m1_det=True, m1_eff=True, m1_len=5,
                  m2_ok=True, m2_det=True, m2_eff=True, m2_len=5):
    return {
        "g0_identity_ok": g0,
        "none_reached_ok": none_ok,
        "groups": {
            "m0": {"reached_ok": m0_ok, "deterministic": m0_det},
            "m1": {"reached_ok": m1_ok, "deterministic": m1_det,
                  "effective": m1_eff, "plus0_length": m1_len},
            "m2": {"reached_ok": m2_ok, "deterministic": m2_det,
                  "effective": m2_eff, "plus0_length": m2_len},
        },
    }

gate_failed_sides = {"official": cpu_mode_side(g0=False), "mixed": cpu_mode_side()}
if search.classify_cpu_mode_screen(gate_failed_sides) == "gate_failed":
    ok("G0不成立（noneとm0の指紋不一致）をgate_failedと判定")
else:
    ng("G0不成立をgate_failedと判定できない")

nondet_cpu_sides = {"official": cpu_mode_side(m1_det=False), "mixed": cpu_mode_side()}
if search.classify_cpu_mode_screen(nondet_cpu_sides) == "nondeterministic":
    ok("G1不成立（本体とrepeatの不一致）をnondeterministicと判定")
else:
    ng("G1不成立をnondeterministicと判定できない")

ineffective_sides = {"official": cpu_mode_side(m2_eff=False), "mixed": cpu_mode_side()}
if search.classify_cpu_mode_screen(ineffective_sides) == "inconclusive_ineffective_arms":
    ok("G2不成立（m2が効いていない）をinconclusive_ineffective_armsと判定")
else:
    ng("G2不成立をinconclusive_ineffective_armsと判定できない")

unreached_cpu_sides = {"official": cpu_mode_side(none_ok=False), "mixed": cpu_mode_side()}
if search.classify_cpu_mode_screen(unreached_cpu_sides) == "inconclusive_ineffective_arms":
    ok("G3不成立（noneが起動終わり700未満に届かない）をinconclusive_ineffective_armsと判定")
else:
    ng("G3不成立をinconclusive_ineffective_armsと判定できない")

split_persists_sides = {
    "official": cpu_mode_side(m1_len=5, m2_len=5),
    "mixed": cpu_mode_side(m1_len=6, m2_len=6),
}
if search.classify_cpu_mode_screen(split_persists_sides) == "split_persists":
    ok("全関門通過・公式5/混成6の維持をsplit_persistsと判定")
else:
    ng("全関門通過・公式5/混成6の維持がsplit_persistsにならない")

split_changes_sides = {
    "official": cpu_mode_side(m1_len=5, m2_len=6),
    "mixed": cpu_mode_side(m1_len=6, m2_len=6),
}
if search.classify_cpu_mode_screen(split_changes_sides) == "split_changes":
    ok("モードで要求長が動く／5対6以外になるケースをsplit_changesと判定")
else:
    ng("要求長が動くケースがsplit_changesにならない")

# m7lt 陽性対照①: フロントエンドが値を返し忘れる故障
# （requestedは数えるがreturned=none）を、G2（cpu_mode_screen_effective）が
# ineffectiveと判定することを確認する。
forgot_return_row = {"core_option": {"requested": 3, "returned": None},
                     "io_fingerprint": "differs-from-m0"}
forgot_return_effective = search.cpu_mode_screen_effective(
    forgot_return_row, "2", "m0-fingerprint")
if forgot_return_effective is False:
    ok("陽性対照1: 値を返し忘れる故障（returned=None）をG2がineffectiveと判定")
else:
    ng("陽性対照1: 値を返し忘れる故障がineffectiveと判定されない（直す前に赤くならない）")

# m7lt 陽性対照②: G2の「m0と指紋が異なる」条件を外す故障
# （＝値は返したが実際には効いていない場合）を、故障版の判定関数で再現し、
# 「有効」に化けることを確認する。これにより、その条件が検出を担っていることを
# 裏付ける（フロントエンド側の故障ではなく判定関数自体の陽性対照）。
def cpu_mode_screen_effective_without_fingerprint_check(row, expected_mode):
    receipt = row["core_option"]
    if receipt is None or receipt["requested"] < 1 or receipt["returned"] != expected_mode:
        return False
    return True  # 指紋比較を外した故障版

ineffective_but_returned_row = {"core_option": {"requested": 1, "returned": "2"},
                                "io_fingerprint": "same-as-m0"}
real_g2 = search.cpu_mode_screen_effective(
    ineffective_but_returned_row, "2", "same-as-m0")
faulty_g2 = cpu_mode_screen_effective_without_fingerprint_check(
    ineffective_but_returned_row, "2")
if real_g2 is False and faulty_g2 is True:
    ok("陽性対照2: 指紋比較を外すと『値は返したが効かなかった』組が有効に化ける"
       "（その条件が検出を担っている確認）")
else:
    ng("陽性対照2: 指紋比較の寄与を確認できない"
       f"（real_g2={real_g2}, faulty_g2={faulty_g2}）")

# m7lt 器具修正: io_log_full_sha256はrom-dir/disk等の走ごとのパス行を
# 除いてハッシュを取るべき（m7ltでgate_failedを起こした欠陥の修正）。
# 陰性対照・陽性対照・そして「直す前に実際に赤くなる」ことを2種の故障で確認する。

def make_synthetic_iolog(path, romdir, disk, out_value):
    with open(path, "w") as f:
        f.write("# PC88Behavior 順序付き I/O 記録\n")
        f.write("#\n")
        f.write(f"core      : mycore.so\n")
        f.write(f"rom-dir   : {romdir}\n")
        f.write(f"disk      : {disk}\n")
        f.write("frames    : 900\n\n")
        f.write("io-log-from-frame: 0\n\n")
        f.write(f"OUT 0x10 {out_value} pc=0x0100 frame=1\n")
        f.write("# 取りこぼし: 0件 / 総イベント数: 1件\n\n")

tmpdir = Path(tempfile.mkdtemp(prefix="m7lt_iolog_selftest_"))
path_a = tmpdir / "run_tagA.iolog.txt"
path_b = tmpdir / "run_tagB.iolog.txt"
path_c = tmpdir / "run_tagA_diffvalue.iolog.txt"
make_synthetic_iolog(path_a, "/tmp/run_tagA/rom", "/tmp/run_tagA/disk.d88", "0x01")
make_synthetic_iolog(path_b, "/tmp/run_tagB/rom", "/tmp/run_tagB/disk.d88", "0x01")
make_synthetic_iolog(path_c, "/tmp/run_tagA/rom", "/tmp/run_tagA/disk.d88", "0x02")

fp_a, excluded_a = search.io_log_full_sha256(path_a)
fp_b, excluded_b = search.io_log_full_sha256(path_b)
fp_c, excluded_c = search.io_log_full_sha256(path_c)

# 陰性対照: パス行だけが違う2ログは同じ指紋になるべき（m7ltの欠陥はこれが崩れていた）
if fp_a == fp_b and excluded_a == 3 and excluded_b == 3:
    ok("陰性対照: 走ごとの作業パス（core/rom-dir/disk）だけが違うログは同じ指紋（除外3行）")
else:
    ng(f"陰性対照: パス行だけの違いで指紋が割れる（fp_a==fp_b: {fp_a == fp_b}, "
       f"excluded_a={excluded_a}, excluded_b={excluded_b}）")

# 陽性対照: データ行（OUT値）が1文字違うログは違う指紋になるべき
if fp_a != fp_c:
    ok("陽性対照: データ行（OUT値）が1文字違うログは違う指紋")
else:
    ng("陽性対照: データ行が違うのに指紋が一致する（検出力が無い）")

# 故障1: 除外対象を「全見出し行」（#で始まる行やframes/io-log-from-frame行も含む）に
# 広げると、陽性対照（データ行の違いの検出）が壊れないことは確認しつつ、
# 除外し過ぎで陰性対照側の「除外行数」検査が3から動くことを見る
# （このリポジトリでは除外対象をcore/rom-dir/disk/disk2の4キーに限定しており、
#  frames等の値が変わらない行まで巻き込まないことが仕様）。
def io_log_full_sha256_over_excluding(path):
    import hashlib
    digest = hashlib.sha256()
    excluded = 0
    header_re = re.compile(rb'^(?:core|rom-dir|disk2?|frames|io-log-from-frame)\s*:')
    with open(path, "rb") as fp:
        for line in fp:
            if header_re.match(line) or line.startswith(b"#"):
                excluded += 1
                continue
            digest.update(line)
    return digest.hexdigest(), excluded

_, over_excluded_a = io_log_full_sha256_over_excluding(path_a)
if over_excluded_a != excluded_a:
    ok("故障1（除外を全見出し行へ広げる）: 除外行数が本来の3から動くことを直す前に確認")
else:
    ng("故障1: 除外を広げても除外行数が変わらない（この故障注入自体が効いていない）")

# 故障2: 除外を一切やめる（元の欠陥そのもの）と、パス行だけが違う陰性対照が
# 割れることを直す前に確認する。
def io_log_full_sha256_no_exclusion(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

faulty_fp_a = io_log_full_sha256_no_exclusion(path_a)
faulty_fp_b = io_log_full_sha256_no_exclusion(path_b)
if faulty_fp_a != faulty_fp_b:
    ok("故障2（除外をやめる＝元の欠陥）: 陰性対照が割れることを直す前に確認"
       "（m7ltのgate_failedを再現）")
else:
    ng("故障2: 除外をやめても陰性対照が割れない（この故障注入自体が効いていない）")

import shutil as _shutil
_shutil.rmtree(tmpdir, ignore_errors=True)

raise SystemExit(1 if fail else 0)
PY

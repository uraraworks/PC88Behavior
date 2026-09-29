#!/bin/sh
""":"
exec python3 "$0" "$@"
":"""
from __future__ import annotations

"""公式媒体に触れない m6i-j の G3 全陰性対照。"""

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import analyze_m6ij as a
import m6ij_measure as driver
import m6ij_script as script

HERE = Path(__file__).resolve().parent
EXPECTED_NG = {"send_missing", "first_value", "control_position", "data_position",
               "response_missing", "clock", "write_order", "candidate_table",
               "read_position_160", "final_remainder", "screen_leak",
               "fake_frontend_zero_launch", "swap_failed", "partial_log_transfer_mapping",
               "driver_transfer_mapping_reason", "double_receive", "latest_value_mismatch",
               "unread_arm_position", "unread_output_field"}


def synthetic(arm: str = "J-D1-S-N", unread_at: tuple[int, ...] = (),
              double_at: int = -1) -> list[dict]:
    events = []
    seq = {"main": 0, "sub": 0}
    clock = 0

    def add(cpu, kind, port, value, pc="0000"):
        nonlocal clock
        clock += 1
        seq[cpu] += 1
        events.append(dict(seq=seq[cpu], clock=clock, frame=2000, cpu=cpu,
                           kind=kind, port=port, value=value, pc=pc))

    sent = 0

    def send(value):
        nonlocal sent
        sent += 1
        if sent in unread_at:
            add("main", "OUT", "00FD", 0xa5, "37F4")
        add("main", "OUT", "00FD", value, "37F4")
        add("sub", "IN", "00FC", value)
        if sent == double_at:
            add("sub", "IN", "00FC", value)

    body = script.body(arm)
    for coord, data in (((18, 0, 1), body.ljust(256, b"\x00")),
                        ((18, 1, 14), bytes([0xff])*256)):
        control = [7, 8, 9, 10, coord[0]*2+coord[1], coord[2]]
        for v in control: send(v)
        for v in [0x05, int(arm[3])-1, *coord, 1, 16, 0x1b, 0xff]:
            add("sub", "OUT", "00FB", v)
        for v in data:
            send(v)
            add("sub", "OUT", "00FB", v)
        for v in range(7):
            add("sub", "IN", "00FB", v)
        add("sub", "OUT", "00FD", 0)
        add("main", "IN", "00FC", 0)
    return events


def write_log(path: Path, events: list[dict]) -> None:
    # 実ログは CPU 別節であり、clock ソートは読み込み側が行う。
    with path.open("w", encoding="ascii") as out:
        for cpu in ("main", "sub"):
            for e in events:
                if e["cpu"] == cpu:
                    out.write(f'{e["seq"]} {e["clock"]} {e["frame"]} {cpu} '
                              f'{e["kind"]} {e["port"]} {e["value"]:02X} {e["pc"]}\n')


def expect_ng(label: str, work: Path, events: list[dict]) -> None:
    path = work / (label + ".iolog.txt")
    write_log(path, events)
    try:
        a.analyze(a.load(path), "J-D1-S-N")
    except (OSError, ValueError):
        return
    raise AssertionError(label)


def test() -> list[str]:
    observed = []
    with tempfile.TemporaryDirectory(prefix="m6ij-test-") as temp:
        work = Path(temp)
        good = synthetic()
        log = work / "good.iolog.txt"
        write_log(log, good)
        result = a.analyze(a.load(log), "J-D1-S-N")
        assert len(result["writes"]) == 2 and len(result["send_runs"]) >= 1
        assert result["writes"][0]["data_match_count"] == 256
        unread_good = synthetic(unread_at=(2, 10))
        unread_log = work / "unread.iolog.txt"
        write_log(unread_log, unread_good)
        unread_result = a.analyze(a.load(unread_log), "J-D1-S-N")
        assert unread_result["unread_send_count"] == 2
        assert [x["position"] for x in unread_result["unread_send"]] == [2, 11]
        assert unread_result["unread_send"][0]["classification"] == "between_control"
        assert unread_result["unread_send"][1]["classification"] == "inside_data"
        assert "control_value" not in unread_result["unread_send"][1]
        double = synthetic(double_at=2)
        expect_ng("double_receive", work, double)
        observed.append("double_receive")
        mismatch = synthetic(unread_at=(2,))
        receives = [e for e in mismatch if e["cpu"] == "sub" and e["kind"] == "IN" and e["port"] == "00FC"]
        receives[1]["value"] ^= 1
        expect_ng("latest_value_mismatch", work, mismatch)
        observed.append("latest_value_mismatch")
        other = copy.deepcopy(unread_result)
        other["unread_send"][0]["position"] += 1
        assert a.unread_judgment({arm: unread_result if arm != "J-D2-S-N" else other
                                  for arm in script.ARMS}) == "inconclusive_unread_send"
        assert a.unread_judgment({arm: unread_result for arm in script.ARMS}) == "unread_send_rule_unique"
        observed.append("unread_arm_position")
        # 最初の送信直後から記録したログでは、受信だけが1件多くなる。
        partial = [e for e in good if e["clock"] > good[0]["clock"]]
        partial_log = work / "partial.iolog.txt"
        write_log(partial_log, partial)
        try:
            a.analyze(a.load(partial_log), "J-D1-S-N")
        except a.GateError as exc:
            assert str(exc) == "transfer_mapping"
            observed.append("partial_log_transfer_mapping")
        else:
            raise AssertionError("partial_log_transfer_mapping")
        for label, predicate, change in (
            ("send_missing", lambda x: x["cpu"] == "main" and x["kind"] == "OUT" and x["port"] == "00FD", None),
            ("first_value", lambda x: x["cpu"] == "main" and x["kind"] == "OUT" and x["port"] == "00FD", "value"),
            ("control_position", lambda x: x["cpu"] == "sub" and x["kind"] == "IN" and x["port"] == "00FC" and x["value"] == 36, "value"),
            ("data_position", lambda x: x["cpu"] == "sub" and x["kind"] == "IN" and x["port"] == "00FC" and x["value"] == ord("P"), "value"),
            ("response_missing", lambda x: x["cpu"] == "main" and x["kind"] == "IN" and x["port"] == "00FC", None),
            ("clock", lambda x: x["cpu"] == "sub" and x["kind"] == "IN" and x["port"] == "00FC", "clock"),
        ):
            bad = copy.deepcopy(good)
            ix = next(i for i, x in enumerate(bad) if predicate(x))
            if change is None: bad.pop(ix)
            elif change == "clock": bad[ix]["clock"] = bad[ix-1]["clock"]
            else: bad[ix][change] ^= 1
            expect_ng(label, work, bad)
            observed.append(label)
        # 全順序は各走を比較する。FDC コマンド順の交換なら不一致。
        reversed_result = copy.deepcopy(result)
        reversed_result["order"].reverse()
        assert result != reversed_result
        observed.append("write_order")
        # 凍結候補表を1バイト壊した場合は起動前に拒否。
        original = (HERE / "m6ij_frozen.tsv").read_text(encoding="ascii")
        bad_config = work / "bad.tsv"
        bad_config.write_text(original.replace("manifest_sha256\t", "manifest_sha256\t0", 1), encoding="ascii")
        try:
            driver.preflight(bad_config, work / "unused")
        except driver.GateError:
            observed.append("candidate_table")
        else:
            raise AssertionError("candidate_table")
        # 出力許可リスト: READ の160位置、最終余り、画面本文を通さない。
        a.axis_values({"J-D1-S-N": result["writes"]})
        base = {"schema": 1, "judgment": "inconclusive_axis_confounded",
                "unread_send_judgment": "inconclusive_unread_send",
                "frontend_launch_count": 2, "candidates": {str(i): [] for i in range(4)},
                "observations": {"J-D1-S-N": result}}
        driver.audit_result(base)
        altered = copy.deepcopy(base)
        altered["observations"]["J-D1-S-N"] = unread_result
        driver.audit_result(altered)
        altered["observations"]["J-D1-S-N"]["unread_send"][1]["control_value"] = 0x55
        try: driver.audit_result(altered)
        except driver.GateError: observed.append("unread_output_field")
        else: raise AssertionError("unread_output_field")
        for label, key in (("read_position_160", "fat_160"),
                           ("final_remainder", "tail_bytes"),
                           ("screen_leak", "screen_text")):
            bad = copy.deepcopy(base)
            bad["observations"]["J-D1-S-N"][key] = "ZQSCREENLEAK7F3D1A9E"
            try: driver.audit_result(bad)
            except driver.GateError: observed.append(label)
            else: raise AssertionError(label)
        # 偽フロントエンドでG1が起動前に止まることを計数する。
        fake = work / "fake_frontend.py"
        count = work / "launches"
        fake.write_text("#!/usr/bin/env python3\nfrom pathlib import Path\n"
                        f"Path({str(count)!r}).write_text('1')\n")
        fake.chmod(0o755)
        env = dict(os.environ, M6IJ_TEST_MODE="1", M6IJ_TEST_FROZEN=str(bad_config),
                   M6IJ_FRONTEND=str(fake))
        proc = subprocess.run([sys.executable, str(HERE / "m6ij_measure.py"),
                               "--work", str(work / "run"), "--arms", "J-D1-S-N"],
                              env=env, capture_output=True)
        assert proc.returncode and not count.exists()
        observed.append("fake_frontend_zero_launch")
        # 同じ偽フロントエンドで正常な2走と、交換イベント欠落のNGを確認。
        signature = work / "signature.tsv"
        signature.write_text("".join(
            f"snapshot_id\t{ident}\nphysical_row\tchar_count\tsha256\n"
            + "line_count\t0\nchar_count\t0\nsha256\t" + "0"*64 + "\n"
            for ident in ("baseline", "final", "late")), encoding="ascii")
        fake.write_text("#!/usr/bin/env python3\n"
                        "import os,sys,shutil\nfrom pathlib import Path\n"
                        "args=sys.argv[1:]\n"
                        "get=lambda flag: args[args.index(flag)+1]\n"
                        f"assert int(get('--io-log-from-frame')) == {script.TYPE_FRAME}\n"
                        "assert int(get('--swap-disk1-at')) < int(args[len(args)-1-args[::-1].index('--type-at')+1])\n"
                        "Path(os.environ['M6IJ_TEST_COUNT']).open('a').write('1')\n"
                        "shutil.copyfile(os.environ['M6IJ_TEST_IOLOG'],get('--io-log'))\n"
                        "shutil.copyfile(os.environ['M6IJ_TEST_SIGNATURE'],get('--out'))\n"
                        "shutil.copyfile(os.environ['M6IJ_TEST_AFTER'],get('--swap-disk1'))\n"
                        "sys.stderr.write('event\\tswap_disk1\\tframe=1200\\tsuccess='"
                        "+os.environ.get('M6IJ_TEST_SWAP_OK','1')+'\\n')\n"
                        "sys.stderr.write(get('--swap-disk1')+'\\n')\n", encoding="ascii")
        env = dict(os.environ, M6IJ_TEST_MODE="1", M6IJ_TEST_FROZEN=str(HERE / "m6ij_frozen.tsv"),
                   M6IJ_FRONTEND=str(fake), M6IJ_TEST_COUNT=str(count),
                   M6IJ_TEST_IOLOG=str(log), M6IJ_TEST_SIGNATURE=str(signature),
                   M6IJ_TEST_ROM_DIR=str(work / "rom"), M6IJ_TEST_CORE="synthetic-core",
                   M6IJ_TEST_REFERENCE=str(work / "reference.d88"))
        (work / "rom").mkdir()
        from make_m6ij_disk import build
        from make_m6fj_disk import offsets
        (work / "reference.d88").write_bytes(build("B0", "J-D1-S-N"))
        saved = bytearray(build("B0", "J-D1-S-N"))
        off = offsets(saved)
        saved[off[(18, 1, 1)]:off[(18, 1, 1)]+16] = (
            b"qjs".ljust(9, b" ") + b"\x00\x48" + b"\xff"*5)
        for r in (14, 15, 16):
            saved[off[(18, 1, r)]+72] = 0xc1
        body = script.body("J-D1-S-N")
        saved[off[(18, 0, 1)]:off[(18, 0, 1)]+len(body)] = body
        (work / "saved.d88").write_bytes(saved)
        env["M6IJ_TEST_AFTER"] = str(work / "saved.d88")
        cmd = [sys.executable, str(HERE / "m6ij_measure.py"), "--work", str(work / "positive"),
               "--arms", "J-D1-S-N"]
        proc = subprocess.run(cmd, env=env, capture_output=True)
        assert proc.returncode == 0 and count.read_text() == "11", (proc.returncode, proc.stdout.decode("ascii", "replace"), proc.stderr.decode("ascii", "replace"), count.read_text())
        assert sorted(p.name for p in (work / "positive").iterdir()) == ["result.json"]
        observed.append("fake_frontend_positive")
        env["M6IJ_TEST_IOLOG"] = str(partial_log)
        cmd[cmd.index(str(work / "positive"))] = str(work / "partial_bad")
        proc = subprocess.run(cmd, env=env, capture_output=True)
        assert proc.returncode and json.loads(proc.stdout)["reason"] == "transfer_mapping"
        observed.append("driver_transfer_mapping_reason")
        env["M6IJ_TEST_IOLOG"] = str(log)
        env["M6IJ_TEST_SWAP_OK"] = "0"
        cmd[cmd.index(str(work / "partial_bad"))] = str(work / "swap_bad")
        proc = subprocess.run(cmd, env=env, capture_output=True)
        assert proc.returncode and json.loads(proc.stdout)["judgment"] == "gate_failed"
        observed.append("swap_failed")
        assert set(observed) == EXPECTED_NG | {"fake_frontend_positive"}
        assert len(observed) == len(EXPECTED_NG)+1
    return observed


def main() -> int:
    try:
        names = test()
        print(json.dumps({"status": "OK", "negative_controls": sorted(EXPECTED_NG),
                          "positive_controls": ["synthetic_log", "fake_frontend_positive"],
                          "ng_count": len(EXPECTED_NG)}, separators=(",", ":")))
        return 0
    except (AssertionError, OSError, ValueError) as exc:
        print(json.dumps({"status": "NG", "reason": type(exc).__name__}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""追補5の合成ログ・偽フロントエンド。公式媒体は使わない。

G4: 合成ログに「手前が 0x14 でない」「D が違う」「応答件数が違う」を注入し、
それぞれ狙いの欄・判定名が変わることを確かめる。
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import m6ij_add3 as a3
import m6ij_add3_selftest as t
import m6ij_add5 as m
from m6fh_body import Image

HERE = Path(__file__).resolve().parent
NEGATIVE = {"G4_prefix_not_14", "G4_d_differs", "G4_reply_count", "leak_field", "leak_extra_field",
            "frozen_zero_launch", "fake_frontend_bad_prefix", "inconclusive_on_h1", "inconclusive_on_g2"}


def events5(arm: str, after: bytes, fault: str = "") -> list[dict]:
    """t.events に、最初の WRITE の手前の P（＝0x14）を加えた合成ログ。"""
    coords = a3.saved_coords(after, arm)
    order = a3.expected_order(coords, a3.directory_sector(after, arm))
    image = Image(after)
    result = []
    seq = {"main": 0, "sub": 0}
    clock = 0

    def add(cpu, kind, port, value):
        nonlocal clock
        clock += 1
        seq[cpu] += 1
        result.append(dict(seq=seq[cpu], clock=clock, frame=2000, cpu=cpu,
                           kind=kind, port=port, value=value, pc="37F4"))

    def send(value):
        add("main", "OUT", "00FD", value)
        add("sub", "IN", "00FC", value)

    write_number = 0
    drive = int(arm[3]) - 1
    for direction, coord in order:
        control = [drive if write_number == 0 else 6, 0x11, 0x01, drive, coord[0]*2+coord[1], coord[2]]
        is_write = direction == "WRITE"
        if is_write and write_number == 0:
            if fault == "prefix_not_14":
                send(0x15)
            elif fault == "d_differs":
                control[0] ^= 1
                send(0x14)
            else:
                send(0x14)
        for i, value in enumerate(control):
            send(value)
            if i == 0 and is_write and fault == "reply_count" and write_number in (0, 1):
                add("sub", "OUT", "00FD", 0)
        if is_write:
            write_number += 1
        data = bytes(image.sector(*coord)) if is_write else b""
        for value in data:
            send(value)
        command = [5 if is_write else 6, drive, *coord, 1, 16, 0x1b, 0xff]
        for value in command:
            add("sub", "OUT", "00FB", value)
        for value in data:
            add("sub", "OUT", "00FB", value)
        for value in range(7):
            add("sub", "IN", "00FB", value)
        if is_write:
            add("sub", "OUT", "00FD", 0)
            add("main", "IN", "00FC", 0)
    return result


def observe(work: Path, arm: str, after: bytes, fault: str = "") -> dict:
    coords = a3.saved_coords(after, arm)
    log = work / "obs.iolog.txt"
    t.write_log(log, events5(arm, after, fault))
    return m.analyze5(a3.old.load(log), arm, coords, a3.directory_sector(after, arm))


def result_for(obs: dict, launches: int = 2) -> dict:
    return m.assess({obs["arm"]: [obs, copy.deepcopy(obs)]}, launches)


def test(preflight_only: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="m6ij-add5-test-") as temp:
        work = Path(temp)
        a3.preflight(HERE / "m6ij_add3_frozen.tsv", work / "new")
        if preflight_only:
            return
        observed = set()
        arm = "T-D2-S"
        after = t.saved(arm)
        good = observe(work, arm, after)
        first = good["first_write"]
        # 正の対照: 0x14, D が付いた合成ログは想定どおりの判定・件数になる。
        assert good["failed"] == [] and first["p_is_14"] and first["s_is_d"]
        assert (first["d_p_to_11"], first["d_s_to_11"], first["d_read_end_to_p"]) == (0, 0, 0)
        assert (first["run_head"], first["p_pos_in_run"], first["run_len"]) == (0x14, 0, 263)
        assert good["later"] and all(x["s_is_06"] and x["d_s_to_11"] == 0 for x in good["later"])
        # 直前が WRITE なら、その応答は S の前にある（合成ログでは WRITE の完了直後）。直前が READ なら0件。
        assert all(x["d_prev_end_to_s"] == (1 if x["prev_is_write"] else 0) for x in good["later"])
        assert any(x["prev_is_write"] for x in good["later"]) and any(not x["prev_is_write"] for x in good["later"])
        base = result_for(good)
        assert base["judgment"] == "first_write_prefixed_by_14_D"
        assert base["gates"] == {"G1": True, "G2": True, "G3": True, "first_write_found": True}
        m.audit_result(base)
        # G4(i): 手前が 0x14 でない → 判定名が変わり、P の欄だけが偽になる。
        bad = observe(work, arm, after, "prefix_not_14")
        assert bad["failed"] == [] and not bad["first_write"]["p_is_14"] and bad["first_write"]["s_is_d"]
        assert bad["first_write"]["run_head"] == 0x15
        assert result_for(bad)["judgment"] == "first_write_other_prefix"
        observed.add("G4_prefix_not_14")
        # G4(ii): D が違う → S の欄だけが偽、H1 も落ちるので判定名は inconclusive に変わる。
        bad = observe(work, arm, after, "d_differs")
        assert bad["first_write"]["p_is_14"] and not bad["first_write"]["s_is_d"] and "H1" in bad["failed"]
        assert result_for(bad)["judgment"] == "inconclusive"
        observed.add("G4_d_differs")
        # G4(iii): 応答件数が違う → 主判定は同じで、件数の欄だけが変わる。
        bad = observe(work, arm, after, "reply_count")
        assert bad["first_write"]["d_p_to_11"] == 1 and bad["first_write"]["d_s_to_11"] == 1
        assert bad["first_write"]["p_is_14"] and bad["later"][0]["d_s_to_11"] == 1
        changed = result_for(bad)
        assert changed["summary"]["first_d_p_to_11"] != base["summary"]["first_d_p_to_11"]
        assert changed["summary"]["later_d_s_to_11"] != base["summary"]["later_d_s_to_11"]
        assert changed["summary"]["first_p_is_14"] == base["summary"]["first_p_is_14"]
        observed.add("G4_reply_count")
        # 対照の失敗は inconclusive（不一致とは扱わない）。
        h1 = copy.deepcopy(good)
        h1["failed"] = ["H1"]
        assert result_for(h1)["judgment"] == "inconclusive"
        observed.add("inconclusive_on_h1")
        other = copy.deepcopy(good)
        other["first_write"]["d_p_to_11"] = 5
        assert m.assess({arm: [good, other]}, 2)["judgment"] == "inconclusive"
        observed.add("inconclusive_on_g2")
        # 出力監査: 想定外の欄・値を拒否する。
        leaked = copy.deepcopy(base)
        leaked["observations"][arm]["screen_text"] = m.LEAK
        for name, mutate in (("leak_field", lambda r: r["observations"][arm].update(screen_text=m.LEAK)),
                             ("leak_extra_field", lambda r: r["observations"][arm]["first_write"].update(data=[1, 2, 3]))):
            r = copy.deepcopy(base)
            mutate(r)
            try:
                m.audit_result(r)
            except m.GateError:
                observed.add(name)
            else:
                raise AssertionError(name)
        # 凍結破壊で起動0回。
        bad_tsv = work / "bad.tsv"
        bad_tsv.write_text((HERE / "m6ij_add5_frozen.tsv").read_text().replace("m6ij_add5.py_sha256\t", "m6ij_add5.py_sha256\t0", 1))
        counter = work / "launches"
        fake = work / "fake.py"
        fake.write_text("#!/usr/bin/env python3\nimport os,sys,shutil\nfrom pathlib import Path\n"
                        "args=sys.argv[1:]\nget=lambda k:args[args.index(k)+1]\n"
                        "Path(os.environ['ADD5_COUNT']).open('a').write('1')\n"
                        "shutil.copyfile(os.environ['ADD5_LOG'],get('--io-log'))\n"
                        "shutil.copyfile(os.environ['ADD5_SIGNATURE'],get('--out'))\n"
                        "shutil.copyfile(os.environ['ADD5_AFTER'],get('--disk2'))\n"
                        "sys.stderr.write('ZQSCREENLEAK7F3D1A9E')\n", encoding="ascii")
        fake.chmod(0o755)
        env = dict(os.environ, M6IJ_ADD5_TEST_MODE="1", M6IJ_ADD5_TEST_FROZEN=str(bad_tsv),
                   M6IJ_ADD5_FRONTEND=str(fake), ADD5_COUNT=str(counter))
        cmd = [sys.executable, str(HERE / "m6ij_add5.py"), "--work", str(work / "invalid"), "--arms", arm]
        proc = subprocess.run(cmd, env=env, capture_output=True)
        assert proc.returncode and json.loads(proc.stdout)["frontend_launch_count"] == 0 and not counter.exists()
        observed.add("frozen_zero_launch")
        # 偽フロントエンド（正のログ → 判定、手前が違うログ → other_prefix）。漏えいの目印は出力に出ない。
        signature = work / "signature.tsv"
        signature.write_text("".join(f"snapshot_id\t{x}\nphysical_row\tchar_count\tsha256\nline_count\t0\nchar_count\t0\nsha256\t{'0'*64}\n"
                                     for x in ("baseline", "final", "late")))
        (work / "rom").mkdir()
        reference = work / "reference.d88"
        reference.write_bytes(a3.build(arm))
        after_path = work / "saved.d88"
        after_path.write_bytes(after)
        log = work / "fake.iolog.txt"
        env.update(M6IJ_ADD5_TEST_FROZEN=str(HERE / "m6ij_add5_frozen.tsv"),
                   M6IJ_ADD5_TEST_ROM_DIR=str(work / "rom"), M6IJ_ADD5_TEST_REFERENCE=str(reference),
                   M6IJ_ADD5_TEST_CORE="synthetic-core", ADD5_LOG=str(log),
                   ADD5_SIGNATURE=str(signature), ADD5_AFTER=str(after_path))
        for fault, want, name in (("", "first_write_prefixed_by_14_D", ""),
                                  ("prefix_not_14", "first_write_other_prefix", "fake_frontend_bad_prefix")):
            t.write_log(log, events5(arm, after, fault))
            out = work / ("run_" + (fault or "good"))
            cmd[3] = str(out)
            proc = subprocess.run(cmd, env=env, capture_output=True)
            assert proc.returncode == 0, proc.stdout
            res = json.loads((out / "result.json").read_text())
            assert res["judgment"] == want and res["frontend_launch_count"] == 2
            assert m.LEAK not in proc.stdout.decode() + proc.stderr.decode() + (out / "result.json").read_text()
            if name:
                observed.add(name)
        assert observed == NEGATIVE, (observed ^ NEGATIVE)


if __name__ == "__main__":
    try:
        test("--preflight" in sys.argv)
        print(json.dumps({"status": "OK", "ng_count": len(NEGATIVE)}, separators=(",", ":")))
    except (AssertionError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "NG", "reason": type(exc).__name__, "detail": str(exc)[:200]}, separators=(",", ":")))
        raise SystemExit(1)

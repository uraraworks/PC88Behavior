#!/usr/bin/env python3
"""追補3の合成ログ・偽フロントエンド。公式媒体は使わない。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import m6ij_add3 as m
from make_m6fj_disk import offsets
from m6fh_body import Image

HERE = Path(__file__).resolve().parent
NEGATIVE = {"H1_separator", "H1_request", "H2_order", "H3_response",
            "chain_wrong_units", "frozen_zero_launch", "leak_field", "fake_frontend_bad_log"}


def saved(arm: str) -> bytes:
    image = bytearray(m.build(arm))
    off = offsets(image)
    units = ((64,) if arm == "T-D2-S" else (72, 71, 68) if arm == "T-D2-X" else
             (72, 71) if len(m.body(arm)) > 2048 else (72,))
    entry_offset = off[(18, 1, 1)] + (32 if arm == "T-D2-S" else 0)
    image[entry_offset:entry_offset+16] = m.name(arm).encode().ljust(9, b" ") + b"\x00" + bytes((units[0],)) + b"\xff"*5
    for r in (14, 15, 16):
        fatpos = off[(18, 1, r)]
        for i, unit in enumerate(units):
            image[fatpos+unit] = units[i+1] if i+1 < len(units) else 0xc0 + ((len(m.body(arm))+255)//256 - 8*(len(units)-1))
        if arm.endswith("-O"):
            image[fatpos+10] = 0xff
    payload = m.body(arm)
    for i in range((len(payload)+255)//256):
        linear = units[i//8]*8+i%8
        pos = off[(linear//32, (linear//16)%2, linear%16+1)]
        image[pos:pos+min(256,len(payload)-i*256)] = payload[i*256:(i+1)*256]
    return bytes(image)


def events(arm: str, after: bytes, fault: str = "") -> list[dict]:
    coords = m.saved_coords(after, arm)
    order = m.expected_order(coords, m.directory_sector(after, arm))
    if fault == "H2_order":
        order[0], order[1] = order[1], order[0]
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
    for direction, coord in order:
        drive = int(arm[3])-1
        control = [drive if write_number == 0 else 6, 0x11, 0x01, drive,
                   coord[0]*2+coord[1], coord[2]]
        if direction == "WRITE":
            if fault == "H1_separator" and write_number == 1:
                control[0] ^= 1
            if fault == "H1_request" and write_number == 1:
                control[1] ^= 1
            write_number += 1
        for value in control:
            send(value)
        data = bytes(image.sector(*coord)) if direction == "WRITE" else b""
        for value in data:
            send(value)
        command = [5 if direction == "WRITE" else 6, drive, *coord, 1, 16, 0x1b, 0xff]
        for value in command:
            add("sub", "OUT", "00FB", value)
        for value in data:
            add("sub", "OUT", "00FB", value)
        for value in range(7):
            add("sub", "IN", "00FB", value)
        if direction == "WRITE" and not (fault == "H3_response" and write_number == 2):
            add("sub", "OUT", "00FD", 0)
            add("main", "IN", "00FC", 0)
    return result


def write_log(path: Path, rows: list[dict]):
    with path.open("w", encoding="ascii") as out:
        for cpu in ("main", "sub"):
            for e in rows:
                if e["cpu"] == cpu:
                    out.write(f'{e["seq"]} {e["clock"]} {e["frame"]} {cpu} {e["kind"]} {e["port"]} {e["value"]:02X} {e["pc"]}\n')


def test(preflight_only: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="m6ij-add3-test-") as temp:
        work = Path(temp)
        m.preflight(HERE / "m6ij_add3_frozen.tsv", work / "new")
        if preflight_only:
            return
        observed = set()
        positive = set()
        for arm in ("T-D2-S", "T-D2-X"):
            after = saved(arm)
            coords = m.saved_coords(after, arm)
            assert len(coords) == (1 if arm.endswith("-S") else 17)
            assert m.allowed_diff(m.build(arm), after, coords, arm)
            if arm == "T-D2-S":
                unit = ((coords[0][0]*2+coords[0][1])*16+coords[0][2]-1)//8
                assert unit not in (72, 73, 71, 70)
                positive.add("chain_relocated")
            log = work / "good.iolog.txt"
            write_log(log, events(arm, after))
            good = m.analyze(m.old.load(log), arm, coords, m.directory_sector(after, arm))
            assert good["failed"] == [] and any(x["direction"] == "READ" for x in good["requests"])
            positive.add(arm)
            if arm == "T-D2-S":
                good_s = good
                wrong = m.analyze(m.old.load(log), arm, [(18, 0, 1)], m.directory_sector(after, arm))
                assert "H2" in wrong["failed"]
                observed.add("chain_wrong_units")
                for fault, hypothesis in (("H1_separator", "H1"), ("H1_request", "H1"),
                                          ("H2_order", "H2"), ("H3_response", "H3")):
                    write_log(log, events(arm, after, fault))
                    result = m.analyze(m.old.load(log), arm, coords, m.directory_sector(after, arm))
                    assert hypothesis in result["failed"], fault
                    observed.add(fault)
                write_log(log, events(arm, after))
        result = {"schema": 3, "judgment": "write_request_structure_confirmed",
                  "frontend_launch_count": 2, "observations": {"T-D2-S": good_s}}
        # 許可リストに本文目印を混ぜると拒否する。
        result["observations"]["T-D2-S"]["screen_text"] = m.LEAK
        try:
            m.audit_result(result)
        except m.GateError:
            observed.add("leak_field")
        else:
            raise AssertionError("leak_field")
        bad = work / "bad.tsv"
        bad.write_text((HERE / "m6ij_add3_frozen.tsv").read_text().replace("manifest_sha256\t", "manifest_sha256\t0", 1))
        counter = work / "launches"
        fake = work / "fake.py"
        fake.write_text("#!/usr/bin/env python3\nimport os,sys,shutil\nfrom pathlib import Path\n"
                        "args=sys.argv[1:]\nget=lambda k:args[args.index(k)+1]\n"
                        "Path(os.environ['ADD3_COUNT']).open('a').write('1')\n"
                        "shutil.copyfile(os.environ['ADD3_LOG'],get('--io-log'))\n"
                        "shutil.copyfile(os.environ['ADD3_SIGNATURE'],get('--out'))\n"
                        "shutil.copyfile(os.environ['ADD3_AFTER'],get('--disk2'))\n"
                        "sys.stderr.write('ZQSCREENLEAK7F3D1A9E')\n", encoding="ascii")
        fake.chmod(0o755)
        env = dict(os.environ, M6IJ_ADD3_TEST_MODE="1", M6IJ_ADD3_TEST_FROZEN=str(bad),
                   M6IJ_ADD3_FRONTEND=str(fake), ADD3_COUNT=str(counter))
        cmd = [sys.executable, str(HERE / "m6ij_add3.py"), "--work", str(work / "invalid"),
               "--arms", "T-D2-S"]
        proc = subprocess.run(cmd, env=env, capture_output=True)
        assert proc.returncode and json.loads(proc.stdout)["frontend_launch_count"] == 0 and not counter.exists()
        observed.add("frozen_zero_launch")
        signature = work / "signature.tsv"
        signature.write_text("".join(f"snapshot_id\t{x}\nphysical_row\tchar_count\tsha256\nline_count\t0\nchar_count\t0\nsha256\t{'0'*64}\n" for x in ("baseline", "final", "late")))
        (work / "rom").mkdir()
        reference = work / "reference.d88"
        reference.write_bytes(m.build("T-D2-S"))
        after_path = work / "saved.d88"
        after_path.write_bytes(saved("T-D2-S"))
        log = work / "good.iolog.txt"
        write_log(log, events("T-D2-S", after_path.read_bytes()))
        env.update(M6IJ_ADD3_TEST_FROZEN=str(HERE / "m6ij_add3_frozen.tsv"),
                   M6IJ_ADD3_TEST_ROM_DIR=str(work / "rom"), M6IJ_ADD3_TEST_REFERENCE=str(reference),
                   M6IJ_ADD3_TEST_CORE="synthetic-core", ADD3_LOG=str(log),
                   ADD3_SIGNATURE=str(signature), ADD3_AFTER=str(after_path))
        cmd[cmd.index(str(work / "invalid"))] = str(work / "positive")
        proc = subprocess.run(cmd, env=env, capture_output=True)
        assert proc.returncode == 0 and counter.read_text() == "11" and (work / "positive" / "result.json").is_file()
        assert m.LEAK not in proc.stdout.decode() and m.LEAK not in proc.stderr.decode()
        assert m.LEAK not in (work / "positive" / "result.json").read_text()
        positive.add("fake_frontend")
        write_log(log, events("T-D2-S", after_path.read_bytes(), "H1_separator"))
        cmd[cmd.index(str(work / "positive"))] = str(work / "bad_log")
        proc = subprocess.run(cmd, env=env, capture_output=True)
        bad_result = json.loads((work / "bad_log" / "result.json").read_text())
        assert proc.returncode == 0 and bad_result["judgment"] == "inconclusive_structure"
        assert bad_result["observations"]["T-D2-S"]["failed"] == ["H1"]
        assert m.LEAK not in proc.stdout.decode() and m.LEAK not in proc.stderr.decode()
        observed.add("fake_frontend_bad_log")
        assert observed == NEGATIVE, (observed, NEGATIVE)
        assert positive == {"chain_relocated", "T-D2-S", "T-D2-X", "fake_frontend"}


if __name__ == "__main__":
    try:
        test("--preflight" in sys.argv)
        print(json.dumps({"status": "OK", "ng_count": len(NEGATIVE)}, separators=(",", ":")))
    except (AssertionError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "NG", "reason": type(exc).__name__}, separators=(",", ":")))
        raise SystemExit(1)

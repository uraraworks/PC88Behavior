#!/usr/bin/env python3
"""m6i-j 追補3。自作媒体と受信要求だけを扱う独立モード。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import analyze_m6ij as old
import analyze_write_path as fdc
import check_m6ij_disk as diskcheck
import compare_screen_signatures as screens
import m6ij_script as base
import m6ij_measure as old_driver
from make_m6fj_disk import offsets
from make_m6ij_disk import build as old_build
from m6fh_body import BodyError, Image, chain, read_bounded

HERE = Path(__file__).resolve().parent
ARMS = base.ARMS + ("T-D2-S", "T-D2-X")
FILES = ("m6ij_add3.py", "measure_m6ij_add3.sh", "m6ij_add3_selftest.py",
         "m6ij_add3_selftest.sh")
LEAK = "ZQSCREENLEAK7F3D1A9E"


class GateError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def body(arm: str) -> bytes:
    if arm in base.ARMS:
        return base.body(arm)
    if arm == "T-D2-S":
        return b"10 PRINT 2\r\n\x1a"
    if arm == "T-D2-X":
        return ("\r\n".join(f"{i*10} REM " + "0"*20 for i in range(1, 141)) + "\r\n").encode("ascii") + b"\x1a"
    raise GateError("arm")


def name(arm: str) -> str:
    return base.name(arm) if arm in base.ARMS else "qts" if arm == "T-D2-S" else "qtx"


def keys(arm: str) -> str:
    if arm in base.ARMS:
        return base.keys(arm)
    lines = body(arm)[:-1].decode("ascii").split("\r\n")[:-1]
    return "new\n" + "\n".join(lines) + f'\ncls:save "2:{name(arm)}",a\n'


def media_kind(arm: str) -> str:
    return "B1" if arm.endswith("-O") else "B0"


def build(arm: str) -> bytes:
    if arm in base.ARMS:
        return old_build(media_kind(arm), arm)
    image = bytearray(old_build("B0", "J-D2-S-N"))
    if arm == "T-D2-S":
        off = offsets(image)
        # 追補4: トラック18ヘッド0（単位72・73）と 71・70 を自作ファイル2件の鎖で使用中にする（追補3の 72・71・68・67 では公式ROMが 73 を選び本体がトラック18に残った）。
        for index, (label, units) in enumerate(((b"holda", (72, 73)), (b"holdb", (71, 70)))):
            image[off[(18, 1, 1)]+16*index:off[(18, 1, 1)]+16*(index+1)] = (
                label.ljust(9, b" ") + b"\x00" + bytes((units[0],)) + b"\xff"*5)
            for r in (14, 15, 16):
                image[off[(18, 1, r)]+units[0]] = units[1]
                image[off[(18, 1, r)]+units[1]] = 0xc1
            linear = units[0]*8
            pos = off[(linear//32, (linear//16)%2, linear%16+1)]
            image[pos:pos+13] = b"10 PRINT 1\r\n\x1a"
    return bytes(image)


def inspect_input(data: bytes, arm: str) -> list[str]:
    if arm in base.ARMS:
        return diskcheck.inspect(data, media_kind(arm), arm)
    faults = []
    try:
        image = Image(data)
        if len(image.sectors) != 1280:
            faults.append("shape")
        directory = bytes(image.sector(18, 1, 1))
        fat = bytes(image.sector_prefix((18, 1, 14), 160))
        if any(fat != bytes(image.sector_prefix((18, 1, r), 160)) for r in (15, 16)):
            faults.append("fat_copies")
        if bytes(image.sector(18, 1, 13)) != bytes(256):
            faults.append("marker")
        if any(bytes(image.sector(18, 1, r)) != b"\xff"*256 for r in range(2, 13)):
            faults.append("directory")
        if arm == "T-D2-S":
            for i, (label, units) in enumerate(((b"holda", (72, 73)), (b"holdb", (71, 70)))):
                want = label.ljust(9, b" ") + b"\x00" + bytes((units[0],)) + b"\xff"*5
                if directory[16*i:16*i+16] != want:
                    faults.append("directory")
            if directory[32:] != b"\xff"*224:
                faults.append("directory")
            for units in ((72, 73), (71, 70)):
                linear = units[0]*8
                if bytes(image.sector_prefix((linear//32, (linear//16)%2, linear%16+1), 13)) != b"10 PRINT 1\r\n\x1a":
                    faults.append("old_body")
        elif directory != b"\xff"*256:
            faults.append("directory")
        used = {72: 73, 73: 0xc1, 71: 70, 70: 0xc1} if arm == "T-D2-S" else {}
        if any(fat[u] != (0xa0 if u in (74, 75) else used.get(u, 0xff)) for u in range(160)):
            faults.append("fat")
    except (BodyError, KeyError, ValueError):
        return ["shape"]
    return sorted(set(faults))


def saved_coords(after: bytes, arm: str) -> list[tuple[int, int, int]]:
    image = Image(after)
    coords, count = chain(image, name(arm).encode("ascii"))
    if count != (len(body(arm))+255)//256 or len(set(coords)) != count:
        raise GateError("saved_chain")
    if arm == "T-D2-S" and (not coords or coords[0][0:2] == (18, 0)):
        raise GateError("reserved_units_used")
    actual, maximum = read_bounded(image, coords, len(body(arm)))
    if actual != body(arm) or maximum != len(body(arm))-1:
        raise GateError("saved_body")
    fat = bytes(image.sector_prefix((18, 1, 14), 160))
    if any(fat != bytes(image.sector_prefix((18, 1, r), 160)) for r in (15, 16)):
        raise GateError("fat_copies")
    if fat[74:76] != b"\xa0\xa0" or (arm.endswith("-O") and fat[10] != 0xff):
        raise GateError("fat_reserved")
    return coords


def allowed_diff(before: bytes, after: bytes, coords: list[tuple[int, int, int]], arm: str) -> bool:
    a, b = Image(before), Image(after)
    if set(a.sectors) != set(b.sectors):
        return False
    body_positions = {coord: i for i, coord in enumerate(coords)}
    changed_units = {((c*2+h)*16+r-1)//8 for c, h, r in coords}
    if arm.endswith("-O"):
        changed_units.add(10)
    entry_sector = directory_sector(after, arm)
    for coord in a.sectors:
        kind = old.location(coord)
        if kind == "fat":
            aa, bb = a.sector_prefix(coord, 160), b.sector_prefix(coord, 160)
            if any(aa[u] != bb[u] for u in range(160) if u not in changed_units):
                return False
        elif kind == "directory":
            aa, bb = bytes(a.sector(*coord)), bytes(b.sector(*coord))
            if coord == (18, 1, entry_sector):
                matches = [off for off in range(0, 256, 16)
                           if bb[off:off+9].rstrip(b" ") == name(arm).encode("ascii")]
                if len(matches) != 1:
                    return False
                off = matches[0]
                if aa[:off] != bb[:off] or aa[off+16:] != bb[off+16:]:
                    return False
            elif aa != bb:
                return False
        elif coord not in body_positions:
            if bytes(a.sector(*coord)) != bytes(b.sector(*coord)):
                return False
        else:
            limit = min(256, len(body(arm))-body_positions[coord]*256)
            if bytes(b.sector_prefix(coord, limit)) != body(arm)[body_positions[coord]*256:body_positions[coord]*256+limit]:
                return False
    return True


def expected_order(coords: list[tuple[int, int, int]], directory_r: int) -> list[tuple[str, tuple[int, int, int]]]:
    fat = [(18, 1, r) for r in (14, 15, 16)]
    out = [("READ", c) for c in fat + [(18, 1, 13)] + [(18, 1, r) for r in range(1, directory_r+1)]]
    out += [("WRITE", (18, 1, directory_r))] + [("WRITE", c) for c in fat]
    for i, coord in enumerate(coords):
        out.append(("WRITE", coord))
        for f in fat:
            out.append(("WRITE", f))
            if i == len(coords)-1:
                out.append(("READ", f))
    return out


def directory_sector(data: bytes, arm: str) -> int:
    image = Image(data)
    target = name(arm).encode("ascii")
    for r in range(1, 13):
        sector = image.sector(18, 1, r)
        for offset in range(0, 256, 16):
            if bytes(sector[offset:offset+9]).rstrip(b" ") == target:
                return r
            if sector[offset] == 0xff:
                raise GateError("entry_missing")
    raise GateError("entry_missing")


def analyze(rows, arm: str, coords: list[tuple[int, int, int]], directory_r: int) -> dict:
    _, _, _, unread = old.exchanges(rows)  # 送信と受信の全単射
    commands = [c for c in fdc.parse_commands(rows) if c.opcode in (5, 6)]
    incoming = [e for e in rows if e.cpu == "sub" and e.kind == "IN" and e.port == "00FC"]
    expected = expected_order(coords, directory_r)
    actual = [("WRITE" if c.opcode == 5 else "READ", old.coordinate(c.param_values or [])) for c in commands]
    failed = set()
    if actual != expected:
        failed.add("H2")
    requests = []
    write_index = 0
    previous_end = -1
    for index, c in enumerate(commands):
        direction, coord = actual[index]
        received = [e.value for e in incoming if previous_end < e.clock < c.clock]
        previous_end = c.end_clock
        if not c.param_values or (c.param_values[0] & 1) != int(arm[3])-1:
            failed.add("H1")
        if direction == "READ":
            # FDCデータ相は記録せず、subがこの要求に先立って受信した制御値だけを記録。
            requests.append({"direction": "READ", "coord": list(coord),
                             "receive_length": len(received), "receive_values": received})
            continue
        write_index += 1
        if c.data_bytes != 256 or c.result_bytes != 7 or c.data_values is None:
            failed.add("H1")
        before = [e for e in incoming if e.clock < c.clock]
        control = [e.value for e in before[-262:-256]] if len(before) >= 262 else []
        payload = [e.value for e in before[-256:]]
        want_control = [int(arm[3])-1 if write_index == 1 else 6,
                        0x11, 0x01, int(arm[3])-1, coord[0]*2+coord[1], coord[2]]
        if control != want_control or payload != c.data_values or len(received) < 262:
            failed.add("H1")
        if coord in coords and c.data_values is not None:
            body_index = coords.index(coord)
            limit = min(256, len(body(arm))-body_index*256)
            if bytes(c.data_values[:limit]) != body(arm)[body_index*256:body_index*256+limit]:
                failed.add("H1")
        next_clock = commands[index+1].clock if index+1 < len(commands) else 2**63
        replies = [e for e in rows if e.cpu == "sub" and e.kind == "OUT" and e.port == "00FD"
                   and c.end_clock < e.clock < next_clock]
        main_replies = [e for e in rows if e.cpu == "main" and e.kind == "IN" and e.port == "00FC"
                        and c.end_clock < e.clock < next_clock]
        if len(replies) != 1 or len(main_replies) != 1 or replies[0].clock >= main_replies[0].clock or replies[0].value != main_replies[0].value:
            failed.add("H3")
        requests.append({"direction": "WRITE", "coord": list(coord), "separator": control[0] if control else 0,
                         "request": control[1:] if control else [0]*5, "data_length": c.data_bytes})
    return {"arm": arm, "failed": sorted(failed), "requests": requests,
            "unread_send_count": len(unread), "unread_send_positions": [p for p, _ in unread]}


def audit_result(result: dict) -> None:
    if set(result) != {"schema", "judgment", "frontend_launch_count", "observations"} or result["schema"] != 3:
        raise GateError("output_audit")
    if result["judgment"] not in ("write_request_structure_confirmed", "inconclusive_structure"):
        raise GateError("output_audit")
    for arm, obs in result["observations"].items():
        if arm not in ARMS or set(obs) != {"arm", "failed", "requests", "unread_send_count", "unread_send_positions"} or obs["arm"] != arm:
            raise GateError("output_audit")
        if any(x not in ("H1", "H2", "H3") for x in obs["failed"]):
            raise GateError("output_audit")
        if obs["unread_send_count"] != len(obs["unread_send_positions"]) or any(
                type(p) is not int or p < 1 for p in obs["unread_send_positions"]):
            raise GateError("output_audit")
        for row in obs["requests"]:
            if row.get("direction") == "WRITE":
                if set(row) != {"direction", "coord", "separator", "request", "data_length"}:
                    raise GateError("output_audit")
                values = [row["separator"], *row["request"]]
                if len(row["request"]) not in (0, 5):
                    raise GateError("output_audit")
            elif row.get("direction") == "READ":
                if set(row) != {"direction", "coord", "receive_length", "receive_values"} or row["receive_length"] != len(row["receive_values"]):
                    raise GateError("output_audit")
                values = row["receive_values"]
            else:
                raise GateError("output_audit")
            if len(row["coord"]) != 3 or len(values) > 16 or any(type(v) is not int or not 0 <= v <= 255 for v in [*row["coord"], *values]):
                raise GateError("output_audit")


def frozen(path: Path, test: bool = False) -> dict[str, str]:
    rows = [line.split("\t") for line in path.read_text(encoding="ascii").splitlines()]
    if any(len(row) != 2 for row in rows) or len({r[0] for r in rows}) != len(rows):
        raise GateError("G1")
    cfg = dict(rows)
    if set(cfg) != {"manifest_sha256", *(f"{f}_sha256" for f in FILES),
                    *(f"body_{a}_sha256" for a in ARMS), *(f"media_{a}_sha256" for a in ARMS)}:
        raise GateError("G1")
    if any(len(v) != 64 or any(c not in "0123456789abcdef" for c in v) for v in cfg.values()):
        raise GateError("G1")
    return cfg


def manifest() -> dict:
    return {"schema": 3, "arms": [{"arm": arm, "body_length": len(body(arm)),
                                    "body_sha256": sha(body(arm)), "media_sha256": sha(build(arm)),
                                    "keys": keys(arm), "runs": 2,
                                    "frames": 60000 if arm == "T-D2-X" else base.FRAMES} for arm in ARMS],
            "frames": base.FRAMES, "swap_frame": base.SWAP_FRAME, "type_frame": base.TYPE_FRAME}


def preflight(config: Path, work: Path) -> dict:
    if work.exists():
        raise GateError("work_exists")
    cfg = frozen(config)
    if sha(canonical(manifest())) != cfg["manifest_sha256"]:
        raise GateError("G1")
    for filename in FILES:
        if sha((HERE / filename).read_bytes()) != cfg[f"{filename}_sha256"]:
            raise GateError("G1")
    # 本体の G0〜G4 も凍結済みの器具で再実行する（本体の値・出力は変更しない）。
    old_driver.preflight(HERE / "m6ij_frozen.tsv", work)
    for arm in ARMS:
        if sha(body(arm)) != cfg[f"body_{arm}_sha256"] or sha(build(arm)) != cfg[f"media_{arm}_sha256"]:
            raise GateError("G1")
        if (arm == "T-D2-X" and ((len(body(arm))+255)//256 != 17 or not body(arm).endswith(b"\r\n\x1a"))) or (
                arm != "T-D2-X" and diskcheck.check_body("J-D2-S-N" if arm == "T-D2-S" else arm, body(arm))):
            raise GateError("G2_body")
        if inspect_input(build(arm), arm):
            raise GateError("G2_disk")
    if len({(arm, rep) for arm in ARMS for rep in (1, 2)}) != 20:
        raise GateError("G4")
    return manifest()


def default_core() -> str:
    proc = subprocess.run(["bash", "-c", 'REPO="$1"; source "$REPO/tools/lib_l3_measure.sh"; find_l3_core',
                           "m6ij-add3", str(HERE.parent)], capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def run_one(arm: str, rep: int, stage: Path, frontend: Path, core: str,
            rom: Path, reference: bytes, fake: bool = False) -> dict:
    run = stage / f"{arm}-r{rep}"
    run.mkdir()
    refpath, target = run / "reference.d88", run / "target.d88"
    refpath.write_bytes(reference)
    refpath.chmod(0o444)
    before = build(arm)
    target.write_bytes(before)
    report, log = run / "signatures.tsv", run / "events.iolog.txt"
    frames = 60000 if arm == "T-D2-X" else base.FRAMES
    end_frame = base.TYPE_FRAME + 8*len(keys(arm))
    if base.SWAP_FRAME >= base.TYPE_FRAME or end_frame >= frames-500:
        raise GateError("G4")
    args = [str(frontend), "--core", core, "--rom-dir", str(rom),
            "--disk", str(refpath), "--save-to-disk-image", "--frames", str(frames),
            "--io-log", str(log), "--io-log-from-frame", str(base.TYPE_FRAME),
            "--screen-signature-only", "--screen-signature-at", "baseline:1100",
            "--screen-signature-at", f"final:{frames-500}",
            "--screen-signature-at", f"late:{frames-1}", "--out", str(report),
            "--type-at", "300", "--type", "\\n", "--type-at", str(base.TYPE_FRAME),
            "--type", keys(arm).replace("\n", "\\n")]
    if arm.startswith("J-D1"):
        args += ["--swap-disk1", str(target), "--swap-disk1-at", str(base.SWAP_FRAME)]
    else:
        args += ["--disk2", str(target)]
    try:
        proc = subprocess.run(args, capture_output=True, timeout=900, env=dict(os.environ, M6FH_LONG_TYPING="1"))
    except subprocess.TimeoutExpired:
        raise GateError("run_timeout") from None
    if proc.returncode or not report.is_file() or not log.is_file():
        raise GateError("frontend")
    if arm.startswith("J-D1"):
        event = f"event\tswap_disk1\tframe={base.SWAP_FRAME}\tsuccess=1".encode()
        if event not in proc.stderr or str(target).encode() not in proc.stderr:
            raise GateError("G4_swap")
    if sha(refpath.read_bytes()) != sha(reference):
        raise GateError("reference_changed")
    after = target.read_bytes()
    coords = saved_coords(after, arm)
    if not allowed_diff(before, after, coords, arm):
        raise GateError("media_diff")
    baseline, final, late = (screens.read_report(report, label) for label in ("baseline", "final", "late"))
    if final != late or baseline.lines.get(19) != final.lines.get(19):
        raise GateError("screen_completion")
    return analyze(old.load(log), arm, coords, directory_sector(after, arm))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path(os.environ.get("PC88_M6IJ_ADD3_WORK", "")))
    ap.add_argument("--arms", help="自己検査専用")
    args = ap.parse_args()
    launches = 0
    test = os.environ.get("M6IJ_ADD3_TEST_MODE") == "1"
    try:
        if str(args.work) in ("", "."):
            raise GateError("work_missing")
        if args.arms and not test:
            raise GateError("arms_test_only")
        arms = ARMS if args.arms is None else tuple(args.arms.split(","))
        if not arms or len(set(arms)) != len(arms) or any(a not in ARMS for a in arms):
            raise GateError("arms_invalid")
        config = Path(os.environ["M6IJ_ADD3_TEST_FROZEN"]) if test and "M6IJ_ADD3_TEST_FROZEN" in os.environ else HERE / "m6ij_add3_frozen.tsv"
        preflight(config, args.work)
        if not test:
            subprocess.run([sys.executable, str(HERE / "m6ij_add3_selftest.py")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        rom = Path(os.environ.get("M6IJ_ADD3_TEST_ROM_DIR" if test else "PC88_REF_ROM_DIR", ""))
        reference_path = Path(os.environ.get("M6IJ_ADD3_TEST_REFERENCE", "")) if test else Path(os.environ.get("PC88_REF_DISK_DIR", "")) / "N88_FE.D88"
        if not rom.is_dir() or not reference_path.is_file():
            raise GateError("reference_missing")
        reference = reference_path.read_bytes()
        frontend = Path(os.environ.get("M6IJ_ADD3_FRONTEND", HERE / "harness/frontend/q88measure"))
        if not frontend.is_file():
            raise GateError("frontend_missing")
        core = os.environ.get("M6IJ_ADD3_TEST_CORE", "") if test else default_core()
        if not core:
            raise GateError("core_missing")
        observations = {}
        args.work.mkdir(parents=True)
        with tempfile.TemporaryDirectory(prefix="runs-", dir=args.work) as temp:
            for arm in arms:
                runs = []
                for rep in (1, 2):
                    launches += 1
                    runs.append(run_one(arm, rep, Path(temp), frontend, core, rom, reference, test))
                if runs[0] != runs[1]:
                    raise GateError("repeat_mismatch")
                observations[arm] = runs[0]
        judgment = ("write_request_structure_confirmed" if len(arms) == len(ARMS) and
                    all(not obs["failed"] for obs in observations.values()) else "inconclusive_structure")
        result = {"schema": 3, "judgment": judgment, "frontend_launch_count": launches,
                  "observations": observations}
        audit_result(result)
        (args.work / "result.json").write_bytes(canonical(result))
        print(json.dumps({"judgment": judgment, "frontend_launch_count": launches}, separators=(",", ":")))
        return 0
    except (OSError, ValueError, BodyError, fdc.SafeError, screens.SignatureInputError,
            subprocess.CalledProcessError) as exc:
        reason = str(exc) if isinstance(exc, GateError) else type(exc).__name__
        print(json.dumps({"judgment": "gate_failed", "reason": reason,
                          "frontend_launch_count": launches}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

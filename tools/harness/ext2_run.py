#!/usr/bin/env python3
"""
ext2_run.py — ext2（バンク側から常駐部ルーチンをCALLする設計の可否）の
本走ランナー兼一次集計。

docs/notes/ext2-relay-to-resident-preregistration.md の腕を、
tools/harness/make_ext2_rom_test.py が生成する自作ROMだけで2走ずつ実行し、
判定名ごとの結果を JSON で出す。公式ROM・private/ は一切使わない。
tools/harness/ext1_run.py と同じ流儀。
"""

import argparse
import pathlib
import subprocess
import sys
import json

REPO = pathlib.Path(__file__).resolve().parents[2]
GEN = REPO / "tools" / "harness" / "make_ext2_rom_test.py"


def find_core():
    vendor = REPO.parent / "vendor" / "quasi88-libretro"
    cands = sorted(vendor.glob("quasi88_libretro.*"))
    if not cands:
        raise SystemExit("コアが無い。tools/setup_harness.sh を先に実行すること")
    return str(cands[0])


def run_q88measure(frontend, core, romdir, frames, out, memlog=None, memrange=None,
                    intlog=None, from_frame=0):
    cmd = [str(frontend), "--core", core, "--rom-dir", str(romdir),
           "--frames", str(frames), "--out", str(out)]
    if memlog:
        cmd += ["--mem-write-log", str(memlog), "--mem-write-range", memrange,
                "--mem-write-from-frame", str(from_frame)]
    if intlog:
        cmd += ["--int-log", str(intlog)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def parse_memlog(path):
    out = []
    for line in pathlib.Path(path).read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 5:
            continue
        seq, frame, pc, addr, value = parts
        out.append((int(seq), int(frame), pc, addr, value))
    return out


def last_value(events, addr):
    v = None
    for _, _, _, a, val in events:
        if a == addr:
            v = val
    return v


def u16_last(events, lo_addr, hi_addr):
    lo = last_value(events, lo_addr)
    hi = last_value(events, hi_addr)
    if lo is None or hi is None:
        return None
    return int(hi, 16) * 256 + int(lo, 16)


def parse_intlog_main(path):
    text = pathlib.Path(path).read_text().splitlines()
    out = []
    in_main = False
    for line in text:
        if line.strip() == "# main":
            in_main = True
            continue
        if line.strip() == "# sub":
            in_main = False
            continue
        if not in_main:
            continue
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 8:
            continue
        seq, clock, frame, who, im, level, ret_pc, handler_pc = parts
        out.append((int(seq), int(clock), int(frame), im, level, ret_pc, handler_pc))
    return out


def build_all_roms(workdir):
    romdir = workdir / "roms"
    for arm in ("call", "call-badadd", "call-b5", "call-b6", "call-neg"):
        subprocess.run([sys.executable, str(GEN), str(romdir / arm), "--arm", arm],
                        check=True, capture_output=True)
    return romdir


def run_call_walk(frontend, core, romdir, workdir, tag, frames=30):
    memlog = workdir / f"{tag}.memlog.txt"
    out = workdir / f"{tag}.report.txt"
    rc, so, se = run_q88measure(frontend, core, romdir, frames, out,
                                 memlog=memlog, memrange="0xC200-0xC22F")
    if rc != 0:
        raise SystemExit(f"{tag}: q88measure失敗 rc={rc}\n{so}\n{se}")
    ev = parse_memlog(memlog)
    res = {}
    res["completed"] = u16_last(ev, "C202", "C203")
    res["match"] = u16_last(ev, "C204", "C205")
    res["win_ok"] = u16_last(ev, "C206", "C207")
    res["resid_hits"] = u16_last(ev, "C208", "C209")
    return res


def run_q2_walk(frontend, core, romdir, workdir, tag, frames=500, need_intlog=True):
    memlog = workdir / f"{tag}.memlog.txt"
    intlog = workdir / f"{tag}.intlog.txt" if need_intlog else None
    out = workdir / f"{tag}.report.txt"
    rc, so, se = run_q88measure(frontend, core, romdir, frames, out,
                                 memlog=memlog, memrange="0xC200-0xC22F",
                                 intlog=intlog, from_frame=0)
    if rc != 0:
        raise SystemExit(f"{tag}: q88measure失敗 rc={rc}\n{so}\n{se}")
    ev = parse_memlog(memlog)
    res = {}
    res["completed"] = u16_last(ev, "C202", "C203")
    res["match"] = u16_last(ev, "C204", "C205")
    res["active_hit"] = u16_last(ev, "C20B", "C20C")
    res["ret_pc_outside_window_while_bank_active"] = None
    if intlog is not None and intlog.exists():
        iv = parse_intlog_main(intlog)
        outside = 0
        for (_, _, _, im, level, ret_pc, handler_pc) in iv:
            try:
                addr = int(ret_pc, 16)
            except ValueError:
                continue
            if addr < 0x6000:
                outside += 1
        res["ret_pc_outside_window_while_bank_active"] = outside
        res["intlog_total"] = len(iv)
    return res


def run_neg_walk(frontend, core, romdir, workdir, tag, frames=30):
    memlog = workdir / f"{tag}.memlog.txt"
    out = workdir / f"{tag}.report.txt"
    rc, so, se = run_q88measure(frontend, core, romdir, frames, out,
                                 memlog=memlog, memrange="0xC200-0xC22F")
    if rc != 0:
        raise SystemExit(f"{tag}: q88measure失敗 rc={rc}\n{so}\n{se}")
    ev = parse_memlog(memlog)
    res = {}
    res["completed"] = u16_last(ev, "C202", "C203")
    res["neg_vals"] = [last_value(ev, f"{0xC220+n:04X}") for n in range(4)]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    args = ap.parse_args()
    workdir = pathlib.Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    frontend = REPO / "tools" / "harness" / "frontend" / "q88measure"
    core = find_core()
    romdir = build_all_roms(workdir)

    results = {}

    for walk in (1, 2):
        results[f"call_walk{walk}"] = run_call_walk(
            frontend, core, romdir / "call", workdir, f"call_w{walk}")
    for walk in (1, 2):
        results[f"badadd_walk{walk}"] = run_call_walk(
            frontend, core, romdir / "call-badadd", workdir, f"badadd_w{walk}")
    for v in ("b5", "b6"):
        for walk in (1, 2):
            results[f"{v}_walk{walk}"] = run_q2_walk(
                frontend, core, romdir / f"call-{v}", workdir, f"{v}_w{walk}")
    for walk in (1, 2):
        results[f"neg_walk{walk}"] = run_neg_walk(
            frontend, core, romdir / "call-neg", workdir, f"neg_w{walk}")

    out_json = workdir / "ext2_results.json"
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"書き出した: {out_json}")
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

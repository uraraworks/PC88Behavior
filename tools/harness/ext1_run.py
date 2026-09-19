#!/usr/bin/env python3
"""
ext1_run.py — ext1（拡張ROMバンク測定）の本走ランナー兼一次集計。

docs/notes/ext1-rom-bank-preregistration.md（改訂1・追補1）の8腕を、
tools/harness/make_ext_rom_test.py が生成する自作ROMだけで2走ずつ実行し、
判定名ごとの結果を JSON で出す。公式ROM・private/ は一切使わない。

写し・生のログはこのスクリプトが指定する作業ディレクトリ（既定は
呼び出し側が渡す --workdir、通常はリポジトリ外のscratchpad）に置く。
結果ノートに転記するのは集計値のみ（判定名・カウント・clock差分など）。
"""

import argparse
import pathlib
import re
import subprocess
import sys
import json

REPO = pathlib.Path(__file__).resolve().parents[2]
GEN = REPO / "tools" / "harness" / "make_ext_rom_test.py"


def find_core():
    vendor = REPO.parent / "vendor" / "quasi88-libretro"
    cands = sorted(vendor.glob("quasi88_libretro.*"))
    if not cands:
        raise SystemExit("コアが無い。tools/setup_harness.sh を先に実行すること")
    return str(cands[0])


def run_q88measure(frontend, core, romdir, frames, out, memlog=None, memrange=None,
                    iolog=None, intlog=None, from_frame=0):
    cmd = [str(frontend), "--core", core, "--rom-dir", str(romdir),
           "--frames", str(frames), "--out", str(out)]
    if memlog:
        cmd += ["--mem-write-log", str(memlog), "--mem-write-range", memrange,
                "--mem-write-from-frame", str(from_frame)]
    if iolog:
        cmd += ["--io-log", str(iolog), "--io-log-from-frame", str(from_frame)]
    if intlog:
        cmd += ["--int-log", str(intlog)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def parse_memlog(path):
    """[(seq,frame,pc,addr,value), ...] のリスト(addr/valueは文字列16進)"""
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


def parse_iolog_main(path):
    """main節のOUT/INイベントを [(seq,clock,frame,kind,port,value,pc), ...] で返す"""
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
        seq, clock, frame, who, kind, port, value, pc = parts
        out.append((int(seq), int(clock), int(frame), kind, port, value, pc))
    return out


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
    subprocess.run([sys.executable, str(GEN), str(romdir / "ra"), "--arm", "ra"],
                    check=True, capture_output=True)
    subprocess.run([sys.executable, str(GEN), str(romdir / "ra_b4"), "--arm", "ra",
                     "--omit-bank", "2"], check=True, capture_output=True)
    for v in ("b5", "b6", "b7"):
        subprocess.run([sys.executable, str(GEN), str(romdir / f"q3_{v}"), "--arm", f"q3-{v}"],
                        check=True, capture_output=True)
    return romdir


def run_ra_walk(frontend, core, romdir, workdir, tag, frames=30):
    memlog = workdir / f"{tag}.memlog.txt"
    iolog = workdir / f"{tag}.iolog.txt"
    out = workdir / f"{tag}.report.txt"
    rc, so, se = run_q88measure(frontend, core, romdir, frames, out,
                                 memlog=memlog, memrange="0xC100-0xC134",
                                 iolog=iolog, from_frame=0)
    if rc != 0:
        raise SystemExit(f"{tag}: q88measure失敗 rc={rc}\n{so}\n{se}")
    ev = parse_memlog(memlog)
    io = parse_iolog_main(iolog)
    res = {}
    res["b1_head"] = last_value(ev, "C100")
    res["b1_tail"] = last_value(ev, "C101")
    res["b1_romver"] = last_value(ev, "C102")
    res["b1_other"] = last_value(ev, "C103")
    res["b2"] = {}
    for n in range(4):
        base = 0xC110 + n * 3
        res["b2"][n] = dict(
            head=last_value(ev, f"{base:04X}"),
            tail=last_value(ev, f"{base+1:04X}"),
            romver=last_value(ev, f"{base+2:04X}"),
        )
    res["b3_head"] = last_value(ev, "C130")
    res["b3_tail"] = last_value(ev, "C131")
    res["b3_romver"] = last_value(ev, "C132")
    res["b3_other"] = last_value(ev, "C133")
    # B8: バンク0の往復1回分。io-logの0071列で "切替(FE)"→"復元(元の値)" の
    # 最初のペアを拾う(RUN_A はバンク0から順に4回往復するので先頭ペア=バンク0)。
    outs71 = [(clock, val) for (_, clock, _, kind, port, val, _) in io
              if kind == "OUT" and port == "0071"]
    b8_delta = None
    if len(outs71) >= 2:
        b8_delta = outs71[1][0] - outs71[0][0]
    res["b8_clock_delta"] = b8_delta
    res["_outs71_head"] = outs71[:4]
    return res


def run_q3_walk(frontend, core, romdir, workdir, tag, frames=500, need_intlog=True):
    memlog = workdir / f"{tag}.memlog.txt"
    intlog = workdir / f"{tag}.intlog.txt" if need_intlog else None
    out = workdir / f"{tag}.report.txt"
    rc, so, se = run_q88measure(frontend, core, romdir, frames, out,
                                 memlog=memlog, memrange="0xC1E0-0xC1FF",
                                 intlog=intlog, from_frame=0)
    if rc != 0:
        raise SystemExit(f"{tag}: q88measure失敗 rc={rc}\n{so}\n{se}")
    ev = parse_memlog(memlog)
    res = {}
    res["completed"] = u16_last(ev, "C1F0", "C1F1")
    res["match"] = u16_last(ev, "C1F2", "C1F3")
    res["active_hit"] = u16_last(ev, "C1E1", "C1E2")
    res["ret_pc_in_window"] = None
    if intlog is not None and intlog.exists():
        iv = parse_intlog_main(intlog)
        in_win = 0
        for (_, _, _, im, level, ret_pc, handler_pc) in iv:
            try:
                addr = int(ret_pc, 16)
            except ValueError:
                continue
            if 0x6000 <= addr <= 0x7FFF:
                in_win += 1
        res["ret_pc_in_window"] = in_win
        res["intlog_total"] = len(iv)
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
        results[f"ra_walk{walk}"] = run_ra_walk(
            frontend, core, romdir / "ra", workdir, f"ra_w{walk}")
    for walk in (1, 2):
        results[f"b4_walk{walk}"] = run_ra_walk(
            frontend, core, romdir / "ra_b4", workdir, f"b4_w{walk}")
    for v in ("b5", "b6", "b7"):
        for walk in (1, 2):
            results[f"{v}_walk{walk}"] = run_q3_walk(
                frontend, core, romdir / f"q3_{v}", workdir, f"{v}_w{walk}")

    out_json = workdir / "ext1_results.json"
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"書き出した: {out_json}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
b2_extract_boot_probe.py — 書き込み記録 (--mem-write-log) から起動用セクタの控えを復元する白リスト

入力: q88measure --mem-write-log の出力、b2_make_boot_probe.py の --out-layout。
根拠: docs/notes/goal-b-policy-addendum1-boot-sector-2026-10-24.md 第3・4節、
      docs/notes/b2-boot-sector-handoff-preregistration.md 第5節（記録の白リスト）。

## 白リスト（これ以外は内容を出さない）

  A. 発行元 PC が RAM 上（--ram-pc-lo 以上）で、**かつ** その PC が生成器の控え用の書き込み命令の
     どれかに当たり（レイアウトの stores と PC から逆算した先頭番地で照合）、**かつ** 書き込み先が
     その命令に決まっている控えの位置と一致する行 ……… 値を控えとして復元する
  B. 発行元 PC が ROM 側の行 ………………………… 値は一切表示しない。番地の範囲と件数だけ
  C. 発行元 PC が RAM 上だが A に当たらない行（スタックへの積み込みなど）……… 件数だけ
  D. 形式に合わない行 ………………………………… 件数だけ

控えを出すのは A だけ。ROM が RAM に書いた値は、ROM 内部のテーブルやバッファ外の内容が
混ざりうる（docs/notes/contamination-2026-09-25-fat-buffer-overrun-values.md）ので、
B の値は出力のどこにも出ない。

## 真の番地の三者照合

  base_true      : A の行の発行元 PC から逆算した番地（書き込み記録の PC は実際に実行された番地）
  base_reported  : 控えの P（CALL→POP で知った番地）から逆算した番地
  base_by_addr   : 控えの書き込み先番地から逆算した番地（A の照合に通った行はこれと一致する）
  三者が揃っていれば consistent=yes。

## 終了コード

  0 = 控えが完結し三者が一致  3 = 控えが見つからない (no_record)
  4 = 見つかったが不完全または食い違い  2 = 入力の不備（取りこぼしあり等）

## 故障注入（器具の自己検査専用。既定では無効）

  B2X_FAULT_TRUST_ROM_WRITES=1  発行元 PC の照合を外し、控えの置き場にある行を
                                 PC に関係なく最後の書き込みで採る（白リストの穴）
"""

import argparse
import json
import os
import pathlib
import re
import sys

ROW_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s*$")


def parse_log(path):
    rows = []
    unparsed = 0
    dropped = None
    total = None
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("# 取りこぼし:"):
            m = re.match(r"# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件", line)
            if m:
                dropped, total = int(m.group(1)), int(m.group(2))
            continue
        if not line.strip() or line.startswith("#") or re.match(r"^[A-Za-z\-]+\s*:", line):
            continue
        m = ROW_RE.match(line)
        if m:
            rows.append((int(m.group(1)), int(m.group(3), 16), int(m.group(4), 16), int(m.group(5), 16)))
        else:
            unparsed += 1
    return rows, unparsed, dropped, total


def merge_ranges(rows):
    """(addr) の集合から、連続する番地の範囲と、その中の書き込み件数。"""
    cnt = {}
    for _, addr in rows:
        cnt[addr] = cnt.get(addr, 0) + 1
    out = []
    for a in sorted(cnt):
        if out and a == out[-1][1] + 1:
            out[-1][1] = a
            out[-1][2] += cnt[a]
        else:
            out.append([a, a, cnt[a]])
    return out


def extract(rows, layout, ram_pc_lo, fault_trust=False):
    stores = layout["stores"]
    rec_off = layout["rec_off"]
    fields = layout["fields"]
    res = {
        "rom_rows": [], "ram_other": 0, "probe_rows": 0, "inconsistent": 0,
        "found": False, "base_true": None,
    }
    ram = [(i, pc, a, v) for i, pc, a, v in rows if pc >= ram_pc_lo]
    res["rom_rows"] = [(pc, a) for _, pc, a, v in rows if pc < ram_pc_lo]
    store_pcs = {}
    for s in stores:
        store_pcs.setdefault(s["pc"], []).append(s)

    # base_true の候補: 控えの書き込み命令の PC から逆算。最も多くの行を説明する候補を採る
    def explains(base, pc, a):
        off = pc - base
        for s in store_pcs.get(off, []):
            if s["kind"] == "fixed" and a == base + rec_off + s["field"]:
                return True
            if s["kind"] == "seq":
                d = a - (base + rec_off + s["first"])
                if d >= 0 and d % s["stride"] == 0 and d // s["stride"] < s["count"]:
                    return True
        return False

    cands = {}
    for _, pc, a, v in ram:
        for off in store_pcs:
            b = pc - off
            if 0 <= b <= 0xFFFF:
                cands.setdefault(b, 0)
    best, best_n = None, 0
    for b in cands:
        n = sum(1 for _, pc, a, v in ram if explains(b, pc, a))
        if n > best_n:
            best, best_n = b, n
    if best is None or best_n == 0:
        res["ram_other"] = len(ram)
        return res

    base = best
    res["base_true"] = base
    rec = {}
    nacc = 0
    ninc = 0
    nother = 0
    seq_pos = {}
    for _, pc, a, v in ram:
        off = pc - base
        if off in store_pcs:
            if explains(base, pc, a):
                rec[a - (base + rec_off)] = v
                nacc += 1
            else:
                ninc += 1
        else:
            nother += 1
    if fault_trust:
        # 故障注入: 発行元 PC を見ず、控えの置き場に当たる全行を最後の書き込みで採る
        for _, pc, a, v in rows:
            o = a - (base + rec_off)
            if 0 <= o < layout["rec_len"]:
                rec[o] = v
    res["probe_rows"] = nacc
    res["inconsistent"] = ninc
    res["ram_other"] = nother
    res["rec"] = rec
    res["found"] = True
    return res


def field_bytes(rec, fields, name):
    off, n = fields[name]
    out = []
    for i in range(n):
        if off + i not in rec:
            return None
        out.append(rec[off + i])
    return out


def le(bs): return None if bs is None else sum(b << (8 * i) for i, b in enumerate(bs))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True, type=pathlib.Path, help="--mem-write-log の出力")
    ap.add_argument("--layout", required=True, type=pathlib.Path, help="生成器の --out-layout")
    ap.add_argument("--ram-pc-lo", type=lambda v: int(v, 0), default=0x8000,
                    help="発行元 PC がこの値以上なら RAM 上とみなす（既定 0x8000）")
    ap.add_argument("--max-rom-ranges", type=int, default=40)
    ap.add_argument("--near", action="append", default=[], metavar="LO-HI",
                    help="この窓に重なる ROM 書き込みの範囲は件数の上限なしで先に出す（読み込み先の確認用）。複数可")
    args = ap.parse_args()

    layout = json.loads(args.layout.read_text(encoding="utf-8"))
    rows, unparsed, dropped, total = parse_log(args.log)
    if dropped is None:
        print("NG: 記録の末尾（取りこぼしの行）が無い。途中で切れた記録は使わない", file=sys.stderr)
        return 2
    if dropped != 0:
        print(f"NG: 取りこぼしが{dropped}件ある。範囲を狭めるか容量を見直すこと", file=sys.stderr)
        return 2

    fault = bool(os.environ.get("B2X_FAULT_TRUST_ROM_WRITES"))
    res = extract(rows, layout, args.ram_pc_lo, fault_trust=fault)

    out = []
    out.append("# b2_extract_boot_probe (白リスト: 控えは書いた命令が自作コードのものだけ。ROM が書いた値は出さない)")
    out.append(f"rows_total={len(rows)} unparsed_rows={unparsed}")
    rr = res["rom_rows"]
    ranges = merge_ranges(rr)
    out.append(f"rom_pc_writes: rows={len(rr)} ranges={len(ranges)}")
    wins = []
    for w in args.near:
        a, b = w.split("-")
        wins.append((int(a, 16), int(b, 16)))
    near = [r for r in ranges if any(r[1] >= lo and r[0] <= hi for lo, hi in wins)]
    rest = [r for r in ranges if r not in near]
    for lo, hi, n in near:
        out.append(f"  rom_range_near {lo:04X}-{hi:04X} rows={n}")
    for lo, hi, n in rest[:args.max_rom_ranges]:
        out.append(f"  rom_range {lo:04X}-{hi:04X} rows={n}")
    if len(rest) > args.max_rom_ranges:
        out.append(f"  (ほか {len(rest) - args.max_rom_ranges} 範囲)")
    out.append(f"ram_pc_other_writes: rows={res['ram_other']}")

    if not res["found"]:
        out.append("probe: found=no (no_record)")
        print("\n".join(out))
        return 3

    F = layout["fields"]
    rec = res["rec"]
    magic = field_bytes(rec, F, "magic")
    ok_magic = magic == [ord(c) for c in layout["magic"]]
    endv = field_bytes(rec, F, "END")
    complete = ok_magic and endv == [layout["end_value"]]
    P = le(field_bytes(rec, F, "P"))
    base_true = res["base_true"]
    base_reported = None if P is None else (P - layout["here_sector_off"]) & 0xFFFF
    consistent = (base_reported == base_true) and res["inconsistent"] == 0
    out.append(f"probe: found=yes magic={'ok' if ok_magic else 'ng'} complete={'yes' if complete else 'no'} "
               f"probe_rows={res['probe_rows']} inconsistent_rows={res['inconsistent']}")
    def hx(v, w=4): return "----" if v is None else f"{v:0{w}X}"
    out.append(f"base_true={hx(base_true)} base_reported={hx(base_reported)} "
               f"consistent={'yes' if consistent else 'no'}")
    F_ = field_bytes(rec, F, "F")
    A_ = field_bytes(rec, F, "A")
    af = None if (F_ is None or A_ is None) else (A_[0] << 8) | F_[0]
    out.append("regs: AF=%s BC=%s DE=%s HL=%s IX=%s IY=%s SP=%s" % (
        hx(af), hx(le(field_bytes(rec, F, "BC"))), hx(le(field_bytes(rec, F, "DE"))),
        hx(le(field_bytes(rec, F, "HL"))), hx(le(field_bytes(rec, F, "IX"))),
        hx(le(field_bytes(rec, F, "IY"))), hx(le(field_bytes(rec, F, "SP")))))
    f2 = field_bytes(rec, F, "F2")
    iv = field_bytes(rec, F, "I")
    out.append("intr: iff2=%s i=%s" % (
        "-" if f2 is None else str((f2[0] >> 2) & 1), "--" if iv is None else f"{iv[0]:02X}"))
    out.append("ret=%s" % hx(le(field_bytes(rec, F, "RET"))))
    mk = field_bytes(rec, F, "MK")
    out.append("markers: " + (" ".join(f"k{k + 1}={m:X}" for k, m in enumerate(mk)) if mk else "----"))
    print("\n".join(out))
    if not (complete and consistent):
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())

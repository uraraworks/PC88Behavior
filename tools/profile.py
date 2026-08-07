#!/usr/bin/env python3
"""
profile.py — 測定結果を突き合わせて「需要プロファイル」を出す

measurements/*.txt を読み、実行された番地の集合を条件どうしで比べる。
知りたいのは 2 つ。

  1. 実装すべき番地の集合はどこまで広がるのか（和集合）
  2. 条件を足したときに新しく増えるのか、それとも飽和するのか（差分）

飽和しないうちは「測り足りない」。実装に入る判断はこの曲線を見てから下す。

扱うのはアドレスの集合だけで、ROM の内容には一切触れない。

使い方:
  tools/profile.py measurements/*.txt              # 各条件の内訳と和集合
  tools/profile.py --growth measurements/frames-*  # 条件を足した順に増分を見る
"""

import argparse
import pathlib
import re
import sys

# 測定結果は CPU ごとに節が分かれている（PC-88 は Z80 が 2 個）
SECTIONS = {}
for _cpu, _tag in (("[メインCPU]", "main"), ("[サブCPU]", "sub")):
    for _jp, _en in (("実行された番地 (fetch)", "exec"),
                     ("データとして読まれた番地", "read"),
                     ("書き込まれた番地", "write"),
                     ("入力された I/O ポート", "io_in"),
                     ("出力された I/O ポート", "io_out")):
        SECTIONS[f"{_cpu} {_jp}"] = f"{_tag}_{_en}"

ROM_END = 0x8000   # メイン ROM は 0000-7FFF に見える


def parse(path):
    """測定結果を {種別: set(アドレス)} に読み込む"""
    out = {v: set() for v in SECTIONS.values()}
    meta = {}
    cur = None
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\w[\w-]*)\s*:\s*(.*)$", line)
        if m and cur is None:
            meta[m.group(1)] = m.group(2)
        m = re.match(r"^\[(.+)\]$", line.strip())
        if m:
            cur = SECTIONS.get(m.group(1))
            continue
        m = re.match(r"^\s+([0-9A-F]+)-([0-9A-F]+)\s+\((\d+)\)", line)
        if m and cur:
            out[cur].update(range(int(m.group(1), 16), int(m.group(2), 16) + 1))
    return meta, out


def rom_part(addrs):
    return {a for a in addrs if a < ROM_END}


SUB_ROM_END = 0x2000   # サブ ROM (DISK.ROM) は 2KB だが余裕をみる


def sub_rom_part(addrs):
    return {a for a in addrs if a < SUB_ROM_END}


def fmt_ranges(addrs, limit=None):
    """連続する番地をまとめて文字列にする"""
    if not addrs:
        return "(なし)"
    xs = sorted(addrs)
    runs, start, prev = [], xs[0], xs[0]
    for a in xs[1:]:
        if a != prev + 1:
            runs.append((start, prev))
            start = a
        prev = a
    runs.append((start, prev))
    shown = runs if limit is None else runs[:limit]
    s = " ".join(f"{a:04X}-{b:04X}" for a, b in shown)
    if limit is not None and len(runs) > limit:
        s += f" ... (他 {len(runs) - limit} 区間)"
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--growth", action="store_true",
                    help="引数の順に足していったときの増分を出す")
    args = ap.parse_args()

    data = [(pathlib.Path(f).stem, parse(f)) for f in args.files]

    print("=== 条件ごとの実行番地（ROM 領域 0000-7FFF のみ） ===")
    for name, (meta, m) in data:
        r = rom_part(m["main_exec"])
        sr = sub_rom_part(m["sub_exec"])
        print(f"  {name:24s} main {len(r):6d} ({len(r)/ROM_END*100:5.1f}%)"
              f"   sub {len(sr):5d}"
              f"   frames={meta.get('frames','?')}")

    union = set(); union_sub = set()
    for _, (_, m) in data:
        union |= rom_part(m["main_exec"])
        union_sub |= sub_rom_part(m["sub_exec"])
    print(f"\n  {'和集合':24s} main {len(union):6d} ({len(union)/ROM_END*100:5.1f}%)"
          f"   sub {len(union_sub):5d}")

    if args.growth:
        print("\n=== 条件を足したときの増分 ===")
        acc = set()
        for name, (_, m) in data:
            r = rom_part(m["main_exec"])
            new = r - acc
            acc |= r
            print(f"  {name:24s} 累計 {len(acc):6d}  新規 {len(new):5d}"
                  + (f"   {fmt_ranges(new, 4)}" if new else ""))
        print("\n  新規が 0 に張り付くまでは測り足りない。")

    # I/O は数が少ないので全部出す。実装の手掛かりとして密度が高い。
    print("\n=== 触れられた I/O ポート（和集合） ===")
    for cpu in ("main", "sub"):
        for k, label in (("io_in", "入力"), ("io_out", "出力")):
            ports = set()
            for _, (_, m) in data:
                ports |= m[f"{cpu}_{k}"]
            if ports:
                print(f"  {cpu:4s} {label}: " + " ".join(f"{p:02X}" for p in sorted(ports)))


if __name__ == "__main__":
    sys.exit(main())

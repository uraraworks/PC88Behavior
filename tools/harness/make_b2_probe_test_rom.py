#!/usr/bin/env python3
"""
make_b2_probe_test_rom.py — 起動用セクタのコード（b2_make_boot_probe.py）の自己検査用 ROM を作る

ここで出力するバイト列は**すべて自分で書いたもの**で、公式 ROM・公式ディスクとは何の関係もない。
この試験 ROM が、公式 ROM の起動処理の代わりに「起動用セクタを RAM のある番地 X へ置き、
既知のレジスタ・既知の SP・既知の戻り先で呼び出す」ところまでを自作で再現する。

  1. 生成器のセクタ像を RAM の X へ LDIR で写す（発行元 PC は ROM なので ROM 書き込みになる）
  2. 目印を X+256*k（k=1..8）へ自作の規則で置く（一部わざと壊す・置かない）
  3. 既知のレジスタ（AF BC DE HL IX IY・I レジスタ）と SP を設定し、EI または DI にして
     X（セクタ先頭）を CALL する。戻り先 = この ROM の CALL の直後（RETLAND）
  4. RET する腕では、戻ってきたあと各レジスタと SP を RAM の R2 へ書き、完了印を置く。
     --decoy を付けると、そのあと**控えの置き場を ROM が別の値で上書き**する
     （白リストが ROM の書き込みを控えとして採らないことの検査用）

期待値（expected.json）は、この ROM を作る側の仕様から決める。コアの出力から写さない。

  expected.json:
    regs, sp_entry, ret_addr, iff2, i_reg, markers(期待マスク), rom_events(ROM が書く番地の列),
    r2(戻り後の控え先), load_addr, probe_load_addr(置いた番地), decoy_word
"""

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "asm"))
sys.path.insert(0, str(REPO / "tools"))

from z80text import Assembler  # noqa: E402
import b2_make_boot_probe as gen  # noqa: E402

N88_SIZE = 0x8000
DISK_SIZE = 0x0800

REGS = {"AF": 0xC39D, "BC": 0x3C5A, "DE": 0x91E2, "HL": 0x4DB7, "IX": 0xD2C8, "IY": 0x5F31}
I_REG = 0x6B
S0 = 0xF000              # CALL の直前の SP。入口の SP は S0-2
S_BOOT = 0xF800          # 準備中の SP
R2 = 0xE000              # RET 後の控え先
DECOY = 0x7E7E

# 目印の置き方 "std": k=3 は3バイト目を壊す、k=5 は置かない、k=7 は4バイト目（タグ）を壊す
def marker_bytes(k, mode):
    if mode == "none":
        return None
    b = bytearray(gen.expected_marker(k))
    if mode == "std":
        if k == 3:
            b[2] = 0x58
        if k == 5:
            return None
        if k == 7:
            b[3] = 0x5A
    return bytes(b)


def expected_mask(k, mode):
    mb = marker_bytes(k, mode)
    if mb is None:
        return 0
    exp = gen.expected_marker(k)
    return sum(1 << j for j in range(4) if mb[j] == exp[j])


def build(args):
    sector = pathlib.Path(args.probe_sector).read_bytes()
    layout = json.loads(pathlib.Path(args.layout).read_text(encoding="utf-8"))
    X = args.place_addr if args.place_addr is not None else layout["load_addr"]
    arm = layout["arm"]
    K = layout["k_markers"]

    lines = []
    A = lines.append
    A("    org 0000h")
    A("    jp START")
    A("    org 0100h")
    A("START:")
    A("    di")
    A(f"    ld sp,{S_BOOT:#06x}")
    A("    ld hl,PROBE_IMG")
    A(f"    ld de,{X:#06x}")
    A("    ld bc,256")
    A("    ldir")
    events = []                    # ROM が書く番地（発行元 PC は ROM）
    events += list(range(X, X + 256))
    for k in range(1, K + 1):
        mb = marker_bytes(k, args.markers)
        if mb is None:
            continue
        for j, v in enumerate(mb):
            a = X + 256 * k + j
            A(f"    ld a,{v:#04x}")
            A(f"    ld ({a:#06x}),a")
            events.append(a)
    if args.mimic_base is not None:
        # 別の RAM 番地へ小さなコードを写して実行し、目印の値(7E7E)を書かせる。
        # 発行元 PC は「控え用の書き込み命令の位置(mimic_base+オフセット)」に合わせてあり、
        # 書き込み先も控えの SP 欄に合わせてある（直す前の抽出器はこれを控えと見なして値を出す）
        fx = [s for s in layout["stores"] if s["kind"] == "fixed" and s["field"] in
              (layout["fields"]["SP"][0], layout["fields"]["SP"][0] + 1)]
        fx.sort(key=lambda s: s["field"])
        assert fx[1]["pc"] == fx[0]["pc"] + 3
        mb = args.mimic_base
        q = mb + fx[0]["pc"] - 2
        rec = mb + layout["rec_off"]
        a1, a2 = rec + layout["fields"]["SP"][0], rec + layout["fields"]["SP"][0] + 1
        img = bytes([0x3E, DECOY & 0xFF, 0x32, a1 & 0xFF, a1 >> 8, 0x32, a2 & 0xFF, a2 >> 8, 0xC9])
        A(f"    ld hl,MIMIC_IMG")
        A(f"    ld de,{q:#06x}")
        A(f"    ld bc,{len(img)}")
        A("    ldir")
        events += list(range(q, q + len(img)))
        A(f"    call {q:#06x}")
        events += [S_BOOT - 1, S_BOOT - 2]
        mimic_img = img
    if args.trap_at is not None:
        A("    ld a,76h")
        A(f"    ld ({args.trap_at:#06x}),a")
        events.append(args.trap_at)
    A(f"    ld a,{I_REG:#04x}")
    A("    ld i,a")
    A(f"    ld ix,{REGS['IX']:#06x}")
    A(f"    ld iy,{REGS['IY']:#06x}")
    A(f"    ld hl,{REGS['AF']:#06x}")
    A("    push hl")
    events += [S_BOOT - 1, S_BOOT - 2]
    A("    pop af")
    A(f"    ld bc,{REGS['BC']:#06x}")
    A(f"    ld de,{REGS['DE']:#06x}")
    A(f"    ld sp,{S0:#06x}")
    A(f"    ld hl,{REGS['HL']:#06x}")
    A("    ei" if args.iff else "    di")
    A(f"    call {X:#06x}")
    events += [S0 - 1, S0 - 2]
    A("RETLAND:")
    if arm == "ret":
        A(f"    ld ({R2:#06x}),hl"); events += [R2, R2 + 1]
        A(f"    ld ({R2 + 2:#06x}),de"); events += [R2 + 2, R2 + 3]
        A(f"    ld ({R2 + 4:#06x}),bc"); events += [R2 + 4, R2 + 5]
        A(f"    ld ({R2 + 6:#06x}),ix"); events += [R2 + 6, R2 + 7]
        A(f"    ld ({R2 + 8:#06x}),iy"); events += [R2 + 8, R2 + 9]
        A("    push af"); events += [S0 - 1, S0 - 2]
        A("    pop hl")
        A(f"    ld ({R2 + 10:#06x}),hl"); events += [R2 + 10, R2 + 11]
        A("    ld hl,0")
        A("    add hl,sp")
        A(f"    ld ({R2 + 12:#06x}),hl"); events += [R2 + 12, R2 + 13]
        A("    ld a,0A5h")
        A(f"    ld ({R2 + 14:#06x}),a"); events += [R2 + 14]
        if args.decoy:
            rec = X + layout["rec_off"]
            A(f"    ld hl,{DECOY:#06x}")
            for slot in ("DE", "BC"):
                a = rec + layout["fields"][slot][0]
                A(f"    ld ({a:#06x}),hl")
                events += [a, a + 1]
    A("DONE:")
    A("    jr DONE")
    A("    org 4000h")
    A("PROBE_IMG:")
    for i in range(0, len(sector), 16):
        A("    db " + ",".join(f"{b:#04x}" for b in sector[i:i + 16]))
    if args.mimic_base is not None:
        A("    org 4800h")
        A("MIMIC_IMG:")
        A("    db " + ",".join(f"{b:#04x}" for b in mimic_img))
    A("    org 7fffh")
    A("    db 0")

    work = pathlib.Path(args.outdir)
    work.mkdir(parents=True, exist_ok=True)
    asm_path = work / "b2test.asm"
    asm_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    asm = Assembler()
    code = asm.assemble(asm_path)
    if len(code) != N88_SIZE:
        raise SystemExit(f"N88.ROM のサイズが {len(code)} (32768 でない)")
    retland = asm.symtab["RETLAND"]
    (work / "N88.ROM").write_bytes(code)
    disk = bytearray(DISK_SIZE)
    disk[0:2] = b"\x18\xFE"
    (work / "DISK.ROM").write_bytes(disk)

    exp = {
        "regs": REGS, "i_reg": I_REG, "iff2": 1 if args.iff else 0,
        "sp_entry": S0 - 2, "ret_addr": retland, "r2": R2,
        "arm": arm, "place_addr": X, "load_addr": layout["load_addr"],
        "entry_off": layout["entry_off"],
        "markers": [expected_mask(k, args.markers) for k in range(1, K + 1)],
        "rom_events": events, "decoy_word": DECOY if ((args.decoy and arm == "ret") or args.mimic_base is not None) else None,
        "decoy_text": f"{DECOY:04X}", "mimic": args.mimic_base is not None,
        "marker_mode": args.markers,
    }
    pathlib.Path(args.expected).write_text(json.dumps(exp, indent=1), encoding="utf-8")
    print(f"生成した: {work/'N88.ROM'} RETLAND={retland:04X} place={X:04X} arm={arm}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--probe-sector", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--expected", required=True)
    ap.add_argument("--place-addr", type=lambda v: int(v, 0), default=None,
                    help="セクタ像を置く番地（既定はレイアウトの load_addr。違う値は陰性対照）")
    ap.add_argument("--iff", type=int, choices=(0, 1), default=1, help="呼ぶ直前に EI(1) / DI(0)")
    ap.add_argument("--markers", choices=("std", "all", "none"), default="std")
    ap.add_argument("--decoy", action="store_true")
    ap.add_argument("--mimic-base", type=lambda v: int(v, 0), default=None,
                    help="別の RAM 番地 B' に控えを真似る小さなコードを写して実行する（白リストの検査用）")
    ap.add_argument("--trap-at", type=lambda v: int(v, 0), default=None,
                    help="この番地に HALT を置く（陰性対照で CALL の飛び先を止める）")
    build(ap.parse_args())


if __name__ == "__main__":
    main()

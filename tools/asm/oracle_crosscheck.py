#!/usr/bin/env python3
"""
oracle_crosscheck.py — z80text.py と外部アセンブラ2種のバイト突き合わせ

M7（L4）段階0の後半。docs/notes/l4-asm-oracle.md 参照。
自作アセンブラ tools/asm/z80text.py を、検査専用の正解役2種
（sjasmplus / z88dk-z80asm。ビルドには使わない）と1命令ずつ突き合わせる。

外部アセンブラのパスは環境変数から受け取る（リポジトリに絶対パスを
焼き込まない）:
  Z80_ORACLE_SJASMPLUS  sjasmplus バイナリ
  Z80_ORACLE_Z88DK      z88dk-z80asm バイナリ

いずれか未設定なら SKIP（正解役なし＝未検査）を目立つ形で出し、
終了コード 2 で終わる（0=合格として誤解されないようにするため）。

故障注入（陽性対照）: 環境変数 Z80TEXT_FAULT_LINE=<index> を渡すと、
z80text.py の出力（このスクリプトが読み込んだ後のバイト列。z80text.py
本体は変更しない）の該当命令の先頭バイトを 1 ビット反転させてから
比較する。NG を検出できることを確かめる目的専用。
"""

import os
import subprocess
import sys
import pathlib
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
GEN = HERE / "gen_z80_corpus.py"
Z80TEXT = HERE / "z80text.py"

MAIN_PREFIXES = {0xCB, 0xDD, 0xED, 0xFD}

# --- 網羅の期待集合（Zilog の文書化命令の数え上げ。根拠は docs/notes/
#     l4-asm-oracle.md の「追記（2026-09-15）」節に対応表を記載） -------
#
# 数え方は「外部アセンブラの出力バイト列」の側から求める（自作の表を
# 使わない＝circular にしない）。ここに書く期待集合は Zilog のニーモニック
# 表からの手計算で、コーパス生成器（gen_z80_corpus.py）とは独立に作った。

# 主命令ページ: 0x00-0xFF から4種の前置きバイトを除いた 252 種。
EXPECT_MAIN = set(range(0x100)) - MAIN_PREFIXES

# CB xx: 0x00-0xFF から SLL 相当（0x30-0x37, 未文書化）8種を除いた 248 種。
EXPECT_CB = set(range(0x100)) - set(range(0x30, 0x38))

# ED xx: 56 種。
#   IN r,(C)  7種: 40,48,50,58,60,68,78 （(HL)=70 は未文書化 IN F,(C) なので除く）
#   OUT (C),r 7種: 41,49,51,59,61,69,79
#   SBC HL,ss 4種: 42,52,62,72
#   ADC HL,ss 4種: 4A,5A,6A,7A
#   LD (nn),dd（ED形。BC/DE/SP。HLは主ページの短い形になるため無し）3種: 43,53,73
#   LD dd,(nn)（同上）                                              3種: 4B,5B,7B
#   NEG  1種: 44   RETN 1種: 45   RETI 1種: 4D
#   IM 0/1/2 3種: 46,56,5E
#   LD I,A/LD R,A/LD A,I/LD A,R 4種: 47,4F,57,5F
#   RRD/RLD 2種: 67,6F
#   ブロック転送・探索・入出力 16種: A0,A1,A2,A3,A8,A9,AA,AB,B0,B1,B2,B3,B8,B9,BA,BB
# 合計 7+7+4+4+3+3+1+1+1+3+4+2+16 = 56
EXPECT_ED = {
    0x40, 0x48, 0x50, 0x58, 0x60, 0x68, 0x78,
    0x41, 0x49, 0x51, 0x59, 0x61, 0x69, 0x79,
    0x42, 0x52, 0x62, 0x72,
    0x4A, 0x5A, 0x6A, 0x7A,
    0x43, 0x53, 0x73,
    0x4B, 0x5B, 0x7B,
    0x44, 0x45, 0x4D,
    0x46, 0x56, 0x5E,
    0x47, 0x4F, 0x57, 0x5F,
    0x67, 0x6F,
    0xA0, 0xA1, 0xA2, 0xA3, 0xA8, 0xA9, 0xAA, 0xAB,
    0xB0, 0xB1, 0xB2, 0xB3, 0xB8, 0xB9, 0xBA, 0xBB,
}
assert len(EXPECT_ED) == 56, len(EXPECT_ED)

# DD xx（非CB）・FD xx（非CB）: 各39種。IY 側も同じバイト値集合（前置きが
# DD→FD に変わるだけでオペコード本体は同じ）。
#   ADD IX,ss      4種: 09,19,29,39
#   LD IX,nn / LD (nn),IX / LD IX,(nn)  3種: 21,22,2A
#   INC IX / DEC IX                     2種: 23,2B
#   INC (IX+d) / DEC (IX+d) / LD (IX+d),n  3種: 34,35,36
#   LD r,(IX+d)  7種: 46,4E,56,5E,66,6E,7E
#   LD (IX+d),r  7種: 70,71,72,73,74,75,77
#   ALU (IX+d)   8種: 86,8E,96,9E,A6,AE,B6,BE
#   PUSH IX/POP IX/EX (SP),IX/JP (IX)/LD SP,IX  5種: E1,E3,E5,E9,F9
# 合計 4+3+2+3+7+7+8+5 = 39
EXPECT_DDFD = {
    0x09, 0x19, 0x29, 0x39,
    0x21, 0x22, 0x2A,
    0x23, 0x2B,
    0x34, 0x35, 0x36,
    0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E, 0x7E,
    0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x77,
    0x86, 0x8E, 0x96, 0x9E, 0xA6, 0xAE, 0xB6, 0xBE,
    0xE1, 0xE3, 0xE5, 0xE9, 0xF9,
}
assert len(EXPECT_DDFD) == 39, len(EXPECT_DDFD)

# DD CB d xx / FD CB d xx: 各31種（SLLに当たる0x36は除く。回転7種＋
# BIT/RES/SET各8種の「(HL)相当」オペコード。前置きに依らずCBページの
# バイト値そのもの）。
#   回転（RLC/RRC/RL/RR/SLA/SRA/SRL）7種: 06,0E,16,1E,26,2E,3E
#   （0x30-0x37 は SLL、(HL)相当は 0x36。未文書化なので除く。
#    SRL の (HL)相当は 0x38+6=0x3E）
#   BIT b,(HL)相当 8種: 46,4E,56,5E,66,6E,76,7E
#   RES b,(HL)相当 8種: 86,8E,96,9E,A6,AE,B6,BE
#   SET b,(HL)相当 8種: C6,CE,D6,DE,E6,EE,F6,FE
# 合計 7+8+8+8 = 31
EXPECT_DDFDCB = {
    0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x3E,
    0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E, 0x76, 0x7E,
    0x86, 0x8E, 0x96, 0x9E, 0xA6, 0xAE, 0xB6, 0xBE,
    0xC6, 0xCE, 0xD6, 0xDE, 0xE6, 0xEE, 0xF6, 0xFE,
}
assert len(EXPECT_DDFDCB) == 31, len(EXPECT_DDFDCB)


def die_skip(msg):
    print("=" * 70)
    print("SKIP: 正解役なし＝未検査")
    print(msg)
    print("=" * 70)
    sys.exit(2)


def read_manifest(tsv_path):
    rows = []
    with open(tsv_path, encoding="utf-8") as f:
        next(f)
        for line in f:
            idx, text, length, tag = line.rstrip("\n").split("\t")
            rows.append((int(idx), text, int(length), tag))
    return rows


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def assemble_z80text(asm_path, out_path):
    r = run([sys.executable, str(Z80TEXT), str(asm_path), "-o", str(out_path)])
    return r.returncode == 0, r.stderr


def assemble_sjasmplus(sj_bin, asm_path, out_path):
    r = run([sj_bin, "--nologo", f"--raw={out_path}", str(asm_path)])
    return r.returncode == 0, r.stdout + r.stderr


def assemble_z88dk(zd_bin, asm_path, out_path):
    r = run([zd_bin, "-m=z80_strict", "-no-synth", "-b", f"-o={out_path}", str(asm_path)])
    return r.returncode == 0, r.stdout + r.stderr


def split_chunks(data, rows):
    """(addr順に並んだ) rows の expect_len を使って data をインデックスごとに切る。
    合計が data の長さと合わなければ None を返す（=組めない扱い）。"""
    total = sum(r[2] for r in rows)
    if total != len(data):
        return None
    chunks = []
    off = 0
    for _, _, length, _ in rows:
        chunks.append(data[off:off + length])
        off += length
    return chunks


def _check_category(label, actual, expect):
    """actual/expect はバイト値の集合。一致すれば True、ずれれば欠け／余分を表示して False。"""
    if actual == expect:
        print(f"  {label}: {len(actual)} / {len(expect)} 一致 OK")
        return True
    missing = sorted(expect - actual)
    extra = sorted(actual - expect)
    print(f"  {label}: {len(actual)} / {len(expect)} 不一致 NG")
    if missing:
        print(f"    欠けているバイト値: {[hex(x) for x in missing]}")
    if extra:
        print(f"    余分なバイト値: {[hex(x) for x in extra]}")
    return False


def coverage_report(chunks, rows, label):
    main_first = set()
    cb_second = set()
    ed_second = set()
    dd_second = set()
    fd_second = set()
    ddcb_last = set()
    fdcb_last = set()
    for c in chunks:
        if not c:
            continue
        b0 = c[0]
        if b0 not in MAIN_PREFIXES:
            main_first.add(b0)
        elif b0 == 0xCB:
            if len(c) >= 2:
                cb_second.add(c[1])
        elif b0 == 0xED:
            if len(c) >= 2:
                ed_second.add(c[1])
        elif b0 == 0xDD:
            if len(c) >= 2 and c[1] == 0xCB:
                if len(c) >= 4:
                    ddcb_last.add(c[3])
            elif len(c) >= 2:
                dd_second.add(c[1])
        elif b0 == 0xFD:
            if len(c) >= 2 and c[1] == 0xCB:
                if len(c) >= 4:
                    fdcb_last.add(c[3])
            elif len(c) >= 2:
                fd_second.add(c[1])
    print(f"--- 網羅（{label}）---")
    ok = True
    ok &= _check_category("主命令ページ 先頭バイト", main_first, EXPECT_MAIN)
    ok &= _check_category("CB xx", cb_second, EXPECT_CB)
    ok &= _check_category("ED xx", ed_second, EXPECT_ED)
    ok &= _check_category("DD xx（非CB）", dd_second, EXPECT_DDFD)
    ok &= _check_category("FD xx（非CB）", fd_second, EXPECT_DDFD)
    ok &= _check_category("DD CB d xx 末尾バイト", ddcb_last, EXPECT_DDFDCB)
    ok &= _check_category("FD CB d xx 末尾バイト", fdcb_last, EXPECT_DDFDCB)
    return ok


def main():
    sj_bin = os.environ.get("Z80_ORACLE_SJASMPLUS")
    zd_bin = os.environ.get("Z80_ORACLE_Z88DK")
    if not sj_bin or not zd_bin:
        die_skip(
            "Z80_ORACLE_SJASMPLUS / Z80_ORACLE_Z88DK のいずれか（または両方）が"
            "未設定。外部正解役なしでは自作アセンブラの符号化を検査できない。"
        )
    if not pathlib.Path(sj_bin).exists() or not pathlib.Path(zd_bin).exists():
        die_skip(f"指定されたパスにバイナリが無い: sjasmplus={sj_bin} z88dk={zd_bin}")

    fault_line = os.environ.get("Z80TEXT_FAULT_LINE")
    fault_line = int(fault_line) if fault_line else None

    with tempfile.TemporaryDirectory(prefix="z80oracle_") as td:
        td = pathlib.Path(td)
        asm_path = td / "corpus.asm"
        tsv_path = td / "corpus.tsv"
        r = run([sys.executable, str(GEN), "-o", str(asm_path), "-m", str(tsv_path)])
        if r.returncode != 0:
            print(r.stdout, r.stderr, file=sys.stderr)
            print("コーパス生成に失敗", file=sys.stderr)
            sys.exit(1)
        rows = read_manifest(tsv_path)
        print(f"コーパス: {len(rows)} 行")

        z_bin = td / "z80text.bin"
        ok_z, err_z = assemble_z80text(asm_path, z_bin)
        sj_out = td / "sj.bin"
        ok_sj, err_sj = assemble_sjasmplus(sj_bin, asm_path, sj_out)
        zd_out = td / "zd.bin"
        ok_zd, err_zd = assemble_z88dk(zd_bin, asm_path, zd_out)

        if not (ok_z and ok_sj and ok_zd):
            print("組めない: z80text=%s sjasmplus=%s z88dk=%s" % (ok_z, ok_sj, ok_zd))
            if not ok_z:
                print("--- z80text stderr ---\n", err_z)
            if not ok_sj:
                print("--- sjasmplus stderr ---\n", err_sj)
            if not ok_zd:
                print("--- z88dk stderr ---\n", err_zd)
            sys.exit(1)

        data_z = bytearray(z_bin.read_bytes())
        data_sj = sj_out.read_bytes()
        data_zd = zd_out.read_bytes()

        if fault_line is not None:
            # 陽性対照: z80text 側の該当命令の先頭バイトを 1 ビット反転する。
            # z80text.py 本体は変更しない。crosscheck 側の後処理のみ。
            off = sum(r[2] for r in rows if r[0] < fault_line)
            if off < len(data_z):
                data_z[off] ^= 0x01
                print(f"[故障注入] line={fault_line} offset={off} を1ビット反転")

        chunks_z = split_chunks(bytes(data_z), rows)
        chunks_sj = split_chunks(data_sj, rows)
        chunks_zd = split_chunks(data_zd, rows)

        ng_rows = []
        if chunks_z is None or chunks_sj is None or chunks_zd is None:
            print(f"総バイト数不一致: z80text={len(data_z)} sjasmplus={len(data_sj)} "
                  f"z88dk={len(data_zd)} 期待={sum(r[2] for r in rows)}")
            # 揃う範囲だけでも見る
            n = min(len(data_z), len(data_sj), len(data_zd))
            ng_rows.append((-1, "(総バイト数不一致のため行対応不能)", "", "", ""))
        else:
            for (idx, text, length, tag), cz, csj, czd in zip(rows, chunks_z, chunks_sj, chunks_zd):
                if not (cz == csj == czd):
                    if csj != czd:
                        kind = "外部同士が違う"
                    else:
                        kind = "自作だけ違う"
                    ng_rows.append((idx, text, cz.hex(), csj.hex(), czd.hex(), kind))

        n_total = len(rows)
        n_ng = len(ng_rows)
        n_ok = n_total - n_ng if chunks_z is not None else 0
        print(f"3者一致: {n_ok} / {n_total}")
        print(f"不一致: {n_ng} 件")
        for row in ng_rows[:20]:
            print("  NG:", row)

        cov_ok = True
        if chunks_zd is not None:
            cov_ok &= coverage_report(chunks_zd, rows, "z88dk")
        if chunks_sj is not None:
            cov_ok2 = coverage_report(chunks_sj, rows, "sjasmplus")
            cov_ok &= cov_ok2

        if n_ng > 0 or not cov_ok or chunks_z is None:
            print("判定: NG")
            sys.exit(1)
        print("判定: OK")
        sys.exit(0)


if __name__ == "__main__":
    main()

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
    print(f"主命令ページ 先頭バイト種類数: {len(main_first)} / 252")
    print(f"CB xx 種類数: {len(cb_second)} / 248")
    print(f"ED xx 種類数: {len(ed_second)}")
    print(f"DD xx（非CB）種類数: {len(dd_second)}")
    print(f"FD xx（非CB）種類数: {len(fd_second)}")
    print(f"DD CB d xx 末尾バイト種類数: {len(ddcb_last)}")
    print(f"FD CB d xx 末尾バイト種類数: {len(fdcb_last)}")
    ok = len(main_first) == 252 and len(cb_second) == 248
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

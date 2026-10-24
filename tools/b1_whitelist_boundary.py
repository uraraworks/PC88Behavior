#!/usr/bin/env python3
"""b1_whitelist_boundary.py — q88measure --boundary-log の出力を白リストで濾す。

位置づけ: docs/notes/b1-g1-demand-preregistration.md「記録の白リスト」。
ゲーム実走の記録からコミットしてよい行だけを通す。通らない行は
**内容を一切表示せず、件数だけ**を数える（標準エラーに数字のみ）。

使い方:
  b1_whitelist_boundary.py <入力> --id G1 --rom official|self [--out <出力>]
  b1_whitelist_boundary.py --selftest

通す行（全行 fullmatch。アドレスは大文字16進4桁、数値は10進整数のみ）:
  A <addr> <n> <n> <n> <n> <n>       横断(total call jump int ret)
  B <addr> <n>                       ROMデータ読み
  C <addr> <n> <n> <n> <n>           共有RAM番地
  # (A 終わり) / # (B 終わり) / # (C 終わり)
  frames    : <n>                    走りの長さ
  instr     : ram=<n> rom=<n> none=<n>   命令数の集計
  ret-stack : dropped=<n>            戻り対応づけの取りこぼし数
このほか出力の先頭に、走の条件として「識別子」「ROMの種別」の2行を
このスクリプトが自分で付ける（入力からは写さない）。
落とす行: 上記以外の全部（見出しの説明コメント、core/rom-dir/disk/disk2 の
パス行、レジスタ値の混入、その他未知の行）。
"""
import re
import sys

_A = r"[0-9A-F]{4}"
_N = r"[0-9]{1,10}"
PATTERNS = [
    re.compile(rf"A {_A}(?: {_N}){{5}}"),
    re.compile(rf"B {_A} {_N}"),
    re.compile(rf"C {_A}(?: {_N}){{4}}"),
    re.compile(r"# \([ABC] 終わり\)"),
    re.compile(rf"frames    : {_N}"),
    re.compile(rf"instr     : ram={_N} rom={_N} none={_N}"),
    re.compile(rf"ret-stack : dropped={_N}"),
]
ID_RE = re.compile(r"G[1-9][0-9]*")
ROMS = ("official", "self")


def filter_lines(lines, gid, rom):
    out = [f"# 識別子: {gid}", f"# ROM: {rom}"]
    dropped_comment = dropped_other = 0
    for ln in lines:
        ln = ln.rstrip("\n")
        if ln == "":
            continue  # 空行は内容を持たない。件数にも数えない
        if any(p.fullmatch(ln) for p in PATTERNS):
            out.append(ln)
        elif ln.startswith("#"):
            dropped_comment += 1
        else:
            dropped_other += 1
    return out, dropped_comment, dropped_other


def selftest():
    bad = [
        "core      : /x/y/core.dylib", "disk      : /a/b.d88", "A 1000 1 1 0 0 1 EXTRA",
        "A 1000 1 1 0 0", "a 1000 1 1 0 0 1", "B 12G4 1", "C 1000 1 1 1",
        "# 故障注入(leak_reg)で混ぜたレジスタ値: A5C3", "# (D 終わり)", "xyz",
        "B 3000 1 ", "A 1000 1 1 0 0 1 ",
    ]
    good = ["A 1000 2 2 0 0 2", "B 3000 2", "C A800 2 2 1 1", "# (A 終わり)",
            "frames    : 20", "instr     : ram=1 rom=2 none=3", "ret-stack : dropped=0"]
    out, dc, do = filter_lines(good + bad, "G1", "self")
    assert out[2:] == good, "通すべき行が通っていない"
    assert dc == 2 and do == len(bad) - 2, (dc, do)
    for b in bad:
        assert b not in out
    print("OK: 白リスト自己検査 (通す%d行・落とす%d行)" % (len(good), len(bad)))


def main(argv):
    if argv[1:] == ["--selftest"]:
        selftest()
        return 0
    args = argv[1:]
    try:
        src = args[0]
        gid = args[args.index("--id") + 1]
        rom = args[args.index("--rom") + 1]
        dst = args[args.index("--out") + 1] if "--out" in args else None
    except (IndexError, ValueError):
        print("使い方: b1_whitelist_boundary.py <入力> --id G1 --rom official|self [--out F]",
              file=sys.stderr)
        return 2
    if not ID_RE.fullmatch(gid) or rom not in ROMS:
        print("識別子またはROM種別が不正", file=sys.stderr)
        return 2
    with open(src, encoding="utf-8", errors="replace") as f:
        out, dc, do = filter_lines(f, gid, rom)
    text = "\n".join(out) + "\n"
    if dst:
        with open(dst, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    print(f"dropped: comment={dc} other={do} kept={len(out) - 2}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

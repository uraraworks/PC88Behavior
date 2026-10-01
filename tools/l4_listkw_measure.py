#!/usr/bin/env python3
"""PC88Behavior: l4-s5h「小文字で打った語の LIST 表示」の測定・照合器具。

事前登録: docs/notes/l4-s5h-list-lowercase-words-preregistration.md

打つのは自分で作った BASIC 行だけ（予約語の一覧 keywords.tsv の各語と、
文脈を変えた行）。`new` → 行 → `cls` → `list` を打ち、`list` の出力のうち
「先頭の空白を除いた最初の文字が数字で、80セルすべてが表示可能 ASCII」の行
（= 自分で打った行の LIST 表示）だけを取り出す。それ以外の行（`Ok` 行・
`list` のエコー・属性など）の文字は一切読まず、件数だけ数える
（tools/l4_list_classify.py と同じ取り扱い。CLAUDE.md 禁止事項7）。

モード:
  measure --rom-dir DIR --out FILE   全腕を走らせ、腕ごとに
                                      id, 打った行, 観測行の署名(sha256先頭16桁),
                                      候補 M_A の署名, 一致/不一致 を TSV に書く
  check --rom-dir DIR --expected FILE  コミット済み期待値（署名）と突き合わせる
  predict                             候補 M_A の予測を腕ごとに出す（確認用）
  selftest                            器具の自己検査（陰性対照・陽性対照・
                                      検出力）。ROMは使わない

観測行の本文は、`--show-differs` を付けたときだけ「候補と不一致だった腕」
について標準出力へ出す（自分で打った行の表示なので禁止事項7の対象外。
l4-program.md 第2節と同じ扱い）。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
FRONT = REPO / "tools" / "harness" / "frontend" / "q88measure"
KEYWORDS_TSV = REPO / "src" / "l4_basic" / "keywords.tsv"
STRIDE = 120
COLS = 80
ROWS = 25
LINES_PER_RUN = 15
SYMBOL_WORDS = {"+", "-", "*", "/", "^", "¥", "'", ">", "=", "<"}


def load_words() -> list[str]:
    words = []
    for ln in KEYWORDS_TSV.read_text(encoding="utf-8").splitlines():
        if not ln or ln.startswith("#"):
            continue
        w = ln.split("\t")[0]
        if w in SYMBOL_WORDS or w == "¥":
            continue
        words.append(w)
    return words


# ----------------------------------------------------------------------
# 腕の定義。本文（行番号の後ろ）を小文字で打つ。
# ----------------------------------------------------------------------
CONTEXTS = [
    # REM・アポストロフィ・DATA・文字列の中身
    ("c01", "rem abc print end Ab"),
    ("c02", "'abc print end"),
    ("c03", 'data abc,end,"x y",print'),
    ("c04", 'print "abc end"'),
    ("c05", 'print "abc'),
    ("c06", 'print "abc":end'),
    ("c07", "a=1:'abc end"),
    ("c08", "a=1:rem abc end"),
    ("c09", "if a then rem abc end"),
    ("c10", "if a then 10 else rem abc end"),
    ("c11", "data end:end"),
    ("c12", 'data "a:b",end'),
    ("c13", 'rem "abc'),
    ("c14", "print 1 'abc end"),
    ("c15", "xrem abc end"),
    ("c16", "xdata abc,end"),
    ("c17", "rem"),
    ("c18", "rem:end"),
    ("c19", "end:rem abc"),
    ("c20", "remabc end"),
    # 空白なしの連結・変数名
    ("c21", "fora=1to3"),
    ("c22", "ifa=1thenprint2elseprint3"),
    ("c23", "goto10"),
    ("c24", "gosub10"),
    ("c25", "go to 10"),
    ("c26", "a=1:b=2:c=3"),
    ("c27", 'abc$="x"'),
    ("c28", "a%=1:b!=2:c#=3"),
    ("c29", "printa"),
    ("c30", "onxgosub1,2"),
    ("c31", "end:end"),
    ("c32", "x=abs(-1)+sgn(1)"),
    ("c33", 'print chr$(65);left$("abc",1)'),
    ("c34", "defint a-z"),
    ("c35", "a = 1 : b = 2"),
    ("c36", '?"x";a'),
    ("c37", "print a;b,c"),
    ("c38", "a=&hff:b=&b101:c=&o17"),
    ("c39", "a=1e5:b=1d5:c=1.5e-3"),
    ("c40", "a=1.5#:b=2!"),
    ("c41", 'a$="abc"+"def"'),
    ("c42", "if a=1 then 10 else 20"),
    ("c43", "x=fnab(1):deffnab(x)=x*2"),
    ("c44", 'open "a" for input as #1'),
    ("c45", 'field #1,10 as a$:line input a$'),
    ("c46", 'print using"##";1'),
    ("c47", "pset(1,1):line(0,0)-(1,1),2,bf"),
    ("c48", "mid$(a$,1)=\"x\":a$=inkey$"),
    ("c49", "print#1,a:input#1,a$"),
    ("c50", "locate1,1:color 7:width 80,25:screen 0"),
    ("c51", "a=b mod c:d=e and f or g xor h"),
    ("c52", "ab=cd:xy=1"),
    ("c53", "e=1:d=2:f=3:g=4"),
    ("c54", "x1=y2:zz9=1"),
    ("c55", "if a then print b else end"),
    ("c56", "for i=1 to 10 step 2:next i"),
    ("c57", "while a<>b:wend"),
    ("c58", "print 1;:print 2"),
    ("c59", "on error goto 100:resume next"),
    ("c60", "tron:troff"),
]


# 追補1（l4-s5h 追補1 事前登録）。初回600腕で M_A と食い違った箇所
# （GO TO・THEN/ELSE 直後の REM・`remabc`・`?` 展開の空白・数値定数）の境界を詰める。
ADDENDUM1 = [
    # REM の境界
    ("a01", "rema"), ("a02", "rem1"), ("a03", 'rem"x end'), ("a04", "rem'x end"),
    ("a05", "rem.x end"), ("a06", "rem(x end)"), ("a07", "rem-x end"),
    ("a08", "rem x:end y"), ("a09", "rem  x end"), ("a10", "a=1:rem x end"),
    ("a11", "if a thenrem x end"), ("a12", "if a elserem x end"),
    ("a13", "a=1 rem x end"), ("a14", "print rem x end"), ("a15", "for rem x end"),
    ("a16", "remx end"),
    # DATA の境界
    ("d01", "dataabc,end"), ("d02", "data1,abc"), ("d03", 'data"x",abc'),
    ("d04", "if a then data abc,end"), ("d05", "if a else data abc,end"),
    ("d06", "a=1:data abc,end:print abc"), ("d07", "data abc ,end"),
    ("d08", "datax end"),
    # ? の展開と空白
    ("q01", "?a"), ("q02", "?1"), ("q03", '?"x"'), ("q04", "?-1"), ("q05", "?(1)"),
    ("q06", "?:end"), ("q07", "?"), ("q08", "? 1"), ("q09", "?;1"), ("q10", "?a$"),
    ("q11", "?abs(1)"), ("q12", "?chr$(65)"), ("q13", "?#1,a"), ("q14", "?,a"),
    ("q15", '? "x"'), ("q16", "a=1:?1"), ("q17", "if a then ?1"), ("q18", "?1:?2"),
    ("q19", "?.5"), ("q20", "?&hff"), ("q21", "?x$;y"), ("q22", "? a"),
    ("q23", "?tab(3);1"), ("q24", '?using"#";1'),
    # GO TO・GO SUB
    ("g01", "goto 10"), ("g02", "go  to 10"), ("g03", "go to10"),
    ("g04", "on x go to 10,20"), ("g05", "if a then go to 10"), ("g06", "gosub 10"),
    ("g07", "go sub 10"), ("g08", "goto10"), ("g09", "go"), ("g10", "go to"),
    ("g11", "xgo toy"),
    # 数値定数（記録のみ。実装の対象にするかは結果を見て決める）
    ("n01", "a=.5"), ("n02", "a=0.5"), ("n03", "a=1."), ("n04", "a=1.0"),
    ("n05", "a=007"), ("n06", "a=1e5"), ("n07", "a=1e-5"), ("n08", "a=1d5"),
    ("n09", "a=1.5e3"), ("n10", "a=1e+5"), ("n11", "a=100000"),
    ("n12", "a=123456789"), ("n13", "a=1234567.5"), ("n14", "a=12345678901234567890"),
    ("n15", "a=1!"), ("n16", "a=1#"), ("n17", "a=1%"), ("n18", "a=32768"),
    ("n19", "a=&h10"), ("n20", "a=&hffff"), ("n21", "a=&o17"), ("n22", "a=&10"),
    ("n23", "a=&b101"), ("n24", "a=.5e1"), ("n25", "a=1.5e-3"), ("n26", "a=0.0001"),
    ("n27", "a=12345.678"), ("n28", "a=1234567890"),
]


def build_arms(addendum: bool = True) -> list[tuple[str, str]]:
    arms: list[tuple[str, str]] = []
    words = load_words()
    for fam, fmt in (("w1", "{w}"), ("w2", "({w})"), ("w3", "x{w}y")):
        for i, w in enumerate(words):
            wl = w.lower()
            arms.append((f"{fam}_{i:03d}", fmt.format(w=wl)))
    for cid, body in CONTEXTS:
        arms.append((cid, body))
    if addendum:
        for cid, body in ADDENDUM1:
            arms.append((cid, body))
    return arms


# ----------------------------------------------------------------------
# 候補 M_A: 「文頭の REM／DATA と ' 以降・文字列の中身を除き、英字をすべて
# 大文字にする」。空白は触らない。`?` は文頭なら "PRINT " に展開する。
# 試走（l4-s5h 事前登録「試走」節）で見た7行と矛盾しない最小の規則。
# ----------------------------------------------------------------------
def predict_body(body: str) -> str:
    out: list[str] = []
    i = 0
    n = len(body)
    stmt_start = True
    while i < n:
        c = body[i]
        rest = body[i:]
        if c == '"':
            j = body.find('"', i + 1)
            j = n if j < 0 else j + 1
            out.append(body[i:j])
            i = j
            stmt_start = False
            continue
        if c == "'":
            out.append(body[i:])
            break
        if stmt_start and rest[:3].lower() == "rem":
            out.append("REM")
            out.append(body[i + 3:])
            break
        if stmt_start and rest[:4].lower() == "data":
            out.append("DATA")
            i += 4
            while i < n and body[i] != ":":
                if body[i] == '"':
                    j = body.find('"', i + 1)
                    j = n if j < 0 else j + 1
                    out.append(body[i:j])
                    i = j
                else:
                    out.append(body[i])
                    i += 1
            stmt_start = False
            continue
        if c == "?" and stmt_start:
            out.append("PRINT ")
            i += 1
            stmt_start = False
            continue
        if c == ":":
            out.append(c)
            stmt_start = True
        elif c == " ":
            out.append(c)
        else:
            out.append(c.upper())
            stmt_start = False
        i += 1
    return "".join(out)


# ----------------------------------------------------------------------
# 候補 M_B（追補1、初回測定のあとに立てた事後の候補）: M_A に次を足す。
#   - 打鍵はすべて小文字で届く（ハーネスの性質）ので、本文は先に小文字にする。
#   - 文頭に THEN／ELSE の直後も数える（語の直前が英数字でないときだけ）。
#   - REM／DATA は、直後が英字でないときだけ語として認める（`remabc` は名前）。
#   - `?` は PRINT に展開し、直後が英数字のときだけ空白を1個入れる。
#   - `go` + 空白 + `to` は GOTO、`go` + 空白 + `sub` は GOSUB に詰める。
# 数値定数は予測しない（打鍵どおり＝大文字化のみ。食い違いは記録される）。
# ----------------------------------------------------------------------
def predict_body_b(body: str) -> str:
    body = body.lower()
    out: list[str] = []
    i = 0
    n = len(body)
    stmt_start = True

    def alpha(ch: str) -> bool:
        return "a" <= ch <= "z"

    def alnum(ch: str) -> bool:
        return alpha(ch) or ("0" <= ch <= "9")

    def copy_quoted(i: int) -> int:
        j = body.find('"', i + 1)
        j = n if j < 0 else j + 1
        out.append(body[i:j])
        return j

    while i < n:
        c = body[i]
        rest = body[i:]
        prev = body[i - 1] if i > 0 else " "
        if c == '"':
            i = copy_quoted(i)
            stmt_start = False
            continue
        if c == "'":
            out.append(body[i:])
            break
        if stmt_start and rest[:3] == "rem" and not alpha(rest[3:4] or " "):
            out.append("REM")
            out.append(body[i + 3:])
            break
        if stmt_start and rest[:4] == "data" and not alpha(rest[4:5] or " "):
            out.append("DATA")
            i += 4
            while i < n and body[i] != ":":
                if body[i] == '"':
                    i = copy_quoted(i)
                else:
                    out.append(body[i])
                    i += 1
            stmt_start = False
            continue
        if c == "?" and stmt_start:
            nxt = rest[1:2]
            out.append("PRINT" + (" " if nxt and alnum(nxt) else ""))
            i += 1
            stmt_start = False
            continue
        if not alnum(prev) and rest[:2] == "go":
            j = 2
            while j < len(rest) and rest[j] == " ":
                j += 1
            if j > 2:
                if rest[j:j + 2] == "to":
                    out.append("GOTO")
                    i += j + 2
                    stmt_start = False
                    continue
                if rest[j:j + 3] == "sub":
                    out.append("GOSUB")
                    i += j + 3
                    stmt_start = False
                    continue
        if not alnum(prev) and (rest[:4] == "then" or rest[:4] == "else"):
            out.append(rest[:4].upper())
            i += 4
            stmt_start = True
            continue
        if c == ":":
            out.append(c)
            stmt_start = True
        elif c == " ":
            out.append(c)
        else:
            out.append(c.upper())
            stmt_start = False
        i += 1
    return "".join(out)


def line_text(lineno: int, body: str) -> str:
    return f"{lineno} {body.lstrip(' ')}"


def predicted_list_text(lineno: int, body: str) -> str:
    # 打鍵は小文字で届く（ハーネスの性質。初回測定の c01 で判明、追補1に記録）。
    return f"{lineno} {predict_body(body.lstrip(' ').lower())}"


def predicted_list_text_b(lineno: int, body: str) -> str:
    return f"{lineno} {predict_body_b(body.lstrip(' '))}"


def sig(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:16]


# ----------------------------------------------------------------------
# 走らせ方
# ----------------------------------------------------------------------
def find_core() -> pathlib.Path:
    cands = sorted((REPO.parent / "vendor" / "quasi88-libretro").glob("quasi88_libretro.*"))
    if not cands:
        raise SystemExit("コアが無い。先に tools/setup_harness.sh を実行すること")
    return cands[0]


def run_chunk(rom_dir: str, official: bool, lines: list[str], work: pathlib.Path,
              tag: str) -> tuple[list[str], int, bool]:
    """lines = 行番号つきの打鍵行。戻り値: (list_lineの文字列, 数えたother行数, 打てない警告)"""
    txt = "new\n" + "".join(l + "\n" for l in lines) + "cls\nlist\n"
    frames = 1200 + 200 * len(lines)
    dump = work / f"{tag}.bin"
    args = [str(FRONT), "--core", str(find_core()), "--rom-dir", rom_dir,
            "--frames", str(frames)]
    if official:
        args += ["--type-at", "300", "--type", "\n", "--type-at", "420", "--type", txt]
    else:
        args += ["--type-at", "60", "--type", txt]
    args += ["--vram-dump", str(dump), "--vram-dump-at", str(frames - 50)]
    env = dict(os.environ, M6FH_LONG_TYPING="1")  # 打鍵数の上限(512)だけを緩める
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if p.returncode != 0:
        raise SystemExit(f"q88measure が失敗(rc={p.returncode}, {tag})")
    err = p.stderr.decode("utf-8", errors="replace").lower()
    untypable = ("untypable" in err) or ("打てない" in err)
    return extract_list_lines(dump.read_bytes()) + (untypable,)


def extract_list_lines(data: bytes) -> tuple[list[str], int]:
    """VRAM写しから、数字始まり・全セル表示可能ASCII の行だけ文字列で返す。
    それ以外の行は中身を見ず、数字始まりでない非空行の件数だけ返す。"""
    listed: list[str] = []
    other = 0
    for r in range(ROWS):
        row = data[r * STRIDE:r * STRIDE + COLS]
        if not all(0x20 <= b <= 0x7E for b in row):
            other += 1
            continue
        s = row.decode("ascii").rstrip(" ")
        first = s.lstrip(" ")[:1]
        if first.isdigit():
            listed.append(s)
        elif s != "":
            other += 1
    return listed, other


def chunk_arms(arms):
    for k in range(0, len(arms), LINES_PER_RUN):
        yield k, arms[k:k + LINES_PER_RUN]


def measure(rom_dir: str, official: bool) -> list[dict]:
    arms = build_arms()
    records: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        for k, chunk in chunk_arms(arms):
            typed = []
            for j, (aid, body) in enumerate(chunk):
                typed.append(f"{(j + 1) * 10} {body}")
            listed, other, untypable = run_chunk(rom_dir, official, typed, work, f"c{k:04d}")
            gate_ok = (not untypable) and len(listed) == len(chunk)
            for j, (aid, body) in enumerate(chunk):
                ln = (j + 1) * 10
                obs = listed[j] if gate_ok else None
                pred = predicted_list_text(ln, body)
                pred_b = predicted_list_text_b(ln, body)
                records.append({
                    "id": aid,
                    "typed": line_text(ln, body),
                    "obs": obs,
                    "obs_sig": sig(obs) if obs is not None else "gate_failed",
                    "pred_sig": sig(pred),
                    "pred_b_sig": sig(pred_b),
                    "match": (obs == pred) if obs is not None else None,
                    "match_b": (obs == pred_b) if obs is not None else None,
                    "pred_b": pred_b,
                })
    return records


def write_tsv(records, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# id\tobs_sig\tpred_MA_sig\tmatch_MA\tpred_MB_sig\tmatch_MB\n")
        for r in records:
            nm = {True: "match", False: "differs", None: "gate_failed"}
            f.write(f"{r['id']}\t{r['obs_sig']}\t{r['pred_sig']}\t{nm[r['match']]}"
                    f"\t{r['pred_b_sig']}\t{nm[r['match_b']]}\n")


def cmd_measure(a) -> int:
    official = a.official
    rec = measure(a.rom_dir, official)
    write_tsv(rec, a.out)
    nm = sum(1 for r in rec if r["match"] is True)
    nd = sum(1 for r in rec if r["match"] is False)
    ng = sum(1 for r in rec if r["match"] is None)
    nb = sum(1 for r in rec if r["match_b"] is True)
    print(f"arms={len(rec)} match_MA={nm} differs_MA={nd} match_MB={nb} gate_failed={ng}")
    if a.show_differs:
        for r in rec:
            if r["match_b"] is False:
                print(f"{r['id']}\t{r['typed']}\t=>\t{r['obs']}\t(M_B: {r['pred_b']})")
    return 0 if ng == 0 else 1


def cmd_check(a) -> int:
    """コミット済み期待値(obs_sigの列)と、この ROM の観測の署名を突き合わせる。"""
    exp = {}
    for ln in pathlib.Path(a.expected).read_text(encoding="utf-8").splitlines():
        if not ln or ln.startswith("#"):
            continue
        f = ln.split("\t")
        exp[f[0]] = f[1]
    rec = measure(a.rom_dir, False)
    bad = 0
    for r in rec:
        e = exp.get(r["id"])
        if e is None:
            print(f"NG {r['id']}: 期待値に無い")
            bad += 1
        elif r["obs_sig"] != e:
            bad += 1
            if a.show_differs:
                print(f"NG {r['id']}\t{r['typed']}\t=>\t{r['obs']}")
            else:
                print(f"NG {r['id']}: 署名不一致")
    missing = set(exp) - {r["id"] for r in rec}
    for m in sorted(missing):
        print(f"NG {m}: 期待値だけにある")
        bad += 1
    print(f"arms={len(rec)} ng={bad}")
    return 0 if bad == 0 else 1


def cmd_predict(a) -> int:
    for aid, body in build_arms():
        print(f"{aid}\t{predicted_list_text(10, body)}")
    return 0


def cmd_selftest(a) -> int:
    fails = []

    def expect(name, cond):
        if not cond:
            fails.append(name)
        print(("OK  " if cond else "NG  ") + name)

    # 陽性対照: 数字始まり・表示可能ASCII の行は取り出される
    def mk(rows):
        d = bytearray(b" " * (STRIDE * ROWS))
        for r, s in rows.items():
            b = s.encode("latin-1").ljust(COLS, b" ")
            d[r * STRIDE:r * STRIDE + COLS] = b
        return bytes(d)

    listed, other = extract_list_lines(mk({0: "list", 1: "10 PRINT 1", 2: "Ok"}))
    expect("陽性: 数字始まりの行だけが取り出される", listed == ["10 PRINT 1"])
    expect("陰性: 英字始まりの行(list/Ok)は本文を返さず件数だけ数える", other == 2)
    # 陰性対照: 範囲外コードを含む行は、数字始まりでも取り出さない
    listed, other = extract_list_lines(mk({1: "10 \xb1\xb2"}))
    expect("陰性: 表示可能ASCII外を含む行は取り出さない", listed == [] and other == 1)
    # 予測の確認（既知の観測: 試走の7行 + A1〜A12の一部）
    cases = {
        "print 1": "PRINT 1", "end": "END", "goto 10": "GOTO 10",
        "for i=1 to 3:next i": "FOR I=1 TO 3:NEXT I",
        'a=1:b$="x"': 'A=1:B$="x"', "rem print end": "REM print end",
        "?1": "PRINT 1", "print 1:print 2": "PRINT 1:PRINT 2",
        'print "abc"': 'PRINT "abc"', "print  1": "PRINT  1",
    }
    for body, want in cases.items():
        expect(f"予測 M_A: {body!r}", predict_body(body) == want)
    # M_B: 初回測定で観測した食い違い（事後に取り込んだもの）を再現する
    cases_b = {
        "go to 10": "GOTO 10", "if a then rem abc end": "IF A THEN REM abc end",
        "remabc end": "REMABC END", '?"x";a': 'PRINT"x";A', "?1": "PRINT 1",
        "xrem abc end": "XREM ABC END", "a=1:'abc end": "A=1:'abc end",
        "rem abc print end Ab": "REM abc print end ab",
    }
    for body, want in cases_b.items():
        expect(f"予測 M_B: {body!r}", predict_body_b(body) == want)
    # 検出力: 現行(PRINTだけ大文字化)の自作ROM相当の出力は M_A と食い違う
    only_print = lambda b: b.replace("print", "PRINT")
    diffs = sum(1 for _, b in CONTEXTS if only_print(b) != predict_body(b))
    expect("検出力: PRINTだけ大文字化する実装は多数の腕で M_A と食い違う", diffs > 30)
    # 腕の数・一意性
    arms = build_arms()
    ids = [a_[0] for a_ in arms]
    expect("腕のidが一意", len(ids) == len(set(ids)))
    expect("全腕の本文が表示可能ASCII・80桁未満",
           all(all(0x20 <= ord(ch) <= 0x7E for ch in b) and len(b) < 70 for _, b in arms))
    print(f"arms={len(arms)}")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--rom-dir", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--official", action="store_true",
                   help="公式ROM。起動後の Enter を1回余分に打つ")
    m.add_argument("--show-differs", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("--rom-dir", required=True)
    c.add_argument("--expected", required=True)
    c.add_argument("--show-differs", action="store_true")
    sub.add_parser("predict")
    sub.add_parser("selftest")
    a = ap.parse_args()
    return {"measure": cmd_measure, "check": cmd_check,
            "predict": cmd_predict, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

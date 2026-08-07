#!/usr/bin/env python3
"""
gen_suite.py — 命令表から測定条件を生成して走らせる

tools/basic_surface.tsv の 1 行 = 1 条件。まとめないのは帰属を残すため。
「この番地はどの命令の実装か」が分からなくなると、L3/L4 の実装単位を切れないし、
差分実行で食い違ったときにどこを見ればいいか分からなくなる。

フレーム数は打鍵の長さから決める。1 文字あたり (hold+gap)=8 フレーム。
起動プロンプトを抜けるまでの分と、実行が終わるまでの余裕を足す。

使い方:
  tools/gen_suite.py --list              条件の一覧だけ出す
  tools/gen_suite.py                     全部走らせる
  tools/gen_suite.py --only PRINT CIRCLE 指定した命令だけ
  tools/gen_suite.py --category graphics 分類で絞る
"""

import argparse
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TSV = REPO / "tools" / "basic_surface.tsv"
MEASURE = REPO / "tools" / "measure.sh"
DISK = "N88_FE.D88"

FRAMES_PER_KEY = 8
# 起動プロンプトを抜けてから打ち始めるまで
START_NODISK = 400
START_DISK = 700
# 打ち終わってから測定を終えるまでの余裕
TAIL = 900


def load():
    rows = []
    for line in TSV.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("\t")
        while len(f) < 5:
            f.append("")
        while len(f) < 6:
            f.append("")
        rows.append({"name": f[0], "category": f[1], "needs": f[2],
                     "code": f[3], "note": f[4], "expect": f[5] or "ok"})
    return rows


def plan(row):
    """1 条件ぶんの measure.sh 引数を組み立てる"""
    needs = row["needs"]
    if needs == "skip":
        return None
    code = row["code"]
    if not code:
        return None
    # 末尾の改行は必須。無いと打ち込んだだけで実行されない。
    # 出力もエラーも出ないので、数字だけ見ていると気づけない
    # （実際に 170 条件すべてがこれで空振りしていた）。
    if not code.endswith("\\n"):
        code += "\\n"

    disk = needs in ("disk", "diskw")
    start = START_DISK if disk else START_NODISK
    # \n はプログラム行の区切り。打鍵数の見積もりでは 1 文字として数える
    nkeys = len(code.replace("\\n", "\n"))
    frames = start + nkeys * FRAMES_PER_KEY + TAIL

    args = [str(MEASURE), "s-" + row["name"].lower(), "--frames", str(frames)]
    if disk:
        args += ["--disk-name", DISK]
        if needs == "diskw":
            args += ["--disk-writable"]
        args += ["--type-at", "300", "--type", "\\n", "--type-at", "700"]
    else:
        args += ["--type-at", "120", "--type", "\\n", "--type-at", "400"]
    args += ["--type", code]

    # INPUT 系は実行中に値を打つ必要がある
    if row["category"] == "input":
        answer_at = start + nkeys * FRAMES_PER_KEY + 400
        args += ["--type-at", str(answer_at), "--type", "42\\n"]
        frames = answer_at + 400 + TAIL
        args[args.index("--frames") + 1] = str(frames)
    return args


def screen_of(path):
    """測定結果からテキスト画面の行を取り出す（行番号19の機能キー表示は除く）"""
    lines, on = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("[測定終了時のテキスト画面]"):
            on = True
            continue
        if on:
            if not line.strip():
                break
            m = re.match(r"^\s+(\d+)\|\s?(.*)$", line)
            if m and int(m.group(1)) < 19:
                lines.append(m.group(2).rstrip())
    return lines


def verify(name, expect="ok"):
    """その条件が実際に実行されたかを画面で確かめる。

    BASIC はコマンドを実行し終えると Ok を返す。最後の行が打った内容のままなら、
    RETURN が届いていないか、まだ実行中か、入力待ちで止まっている。
    「エラーが出ていない」は「実行された」を意味しない。
    """
    f = REPO / "measurements" / f"s-{name.lower()}.txt"
    if not f.exists():
        return "測定結果が無い"
    scr = [l for l in screen_of(f) if l.strip()]
    if not scr:
        return "画面が空"

    # 打ち込んだ内容はそのまま画面に出る。プログラム行（行番号で始まる）は
    # 実行結果ではないので、エラー判定の対象から外す。
    # これを外さないと "20 ERROR 5" という行を「エラーが起きた」と誤認する。
    results = [l for l in scr if not re.match(r"^\s*\d+\s", l)]
    err = [l for l in results
           if re.search(r"\berror\b|not found|protected|missing|overflow|redo from",
                        l, re.I)]
    if expect == "err":
        return None if err else "エラーが出るはずの条件なのに出ていない"
    if err:
        return "エラー: " + err[-1].strip()
    if expect == "any":
        return None
    if scr[-1].strip().lower() != "ok":
        return "未完了(最後が Ok でない): " + scr[-1].strip()[:40]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--category")
    a = ap.parse_args()

    rows = load()
    if a.only:
        want = {x.upper() for x in a.only}
        rows = [r for r in rows if r["name"].upper() in want]
    if a.category:
        rows = [r for r in rows if r["category"] == a.category]

    todo, skipped = [], []
    for r in rows:
        p = plan(r)
        (todo if p else skipped).append((r, p))

    if a.list:
        for r, p in todo:
            print(f"{r['name']:16s} {r['category']:10s} {r['needs']:6s} frames={p[p.index('--frames')+1]}")
        for r, _ in skipped:
            print(f"{r['name']:16s} {r['category']:10s} skip   {r['note']}")
        print(f"\n測定 {len(todo)} 件 / 見送り {len(skipped)} 件")
        return 0

    ng, bad = [], []
    for i, (r, p) in enumerate(todo, 1):
        print(f"[{i:3d}/{len(todo)}] {r['name']:16s} ", end="", flush=True)
        res = subprocess.run(p, capture_output=True, text=True)
        # 連続実行するとコアの終了処理がまれに異常終了する (SIGABRT)。
        # レポートはその前に書き出されているのでデータは無傷であり、
        # 同じ条件を単独で回すと再現せず結果も一致する。
        # 握りつぶさずに記録した上で、中身の検証は続ける。
        aborted = res.returncode != 0
        why = verify(r["name"], r["expect"])
        if why:
            print("要確認: " + why)
            bad.append((r["name"], why))
        elif aborted:
            print(f"ok（ただし終了コード {res.returncode}）")
            ng.append(r["name"])
        else:
            print("ok")
    print(f"\n測定 {len(todo)} 件、異常終了 {len(ng)} 件、要確認 {len(bad)} 件")
    if ng:
        print("異常終了（データは取得済み）:", " ".join(ng))
    for n, w in bad:
        print(f"  {n:16s} {w}")
    if skipped:
        print(f"見送り {len(skipped)} 件（理由は basic_surface.tsv の note）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

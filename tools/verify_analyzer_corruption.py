#!/usr/bin/env python3
"""PC88Behavior: analyze_sub_proto.py の検出力を検算するための破壊テスト。

「不自然に揃った数字は観測系の故障を疑う」という規律に基づき、100.0%という
一致率が観測系(=解析器)の自己参照や集計バグで出ていないかを、意図的に壊した
入力に対して確認する。

第三者が再実行できるように、破壊操作(a)(b)は本スクリプト内で完結させる
(手作業で作った合成ログを別途コミットしない)。入力は measurements/ 配下の
実測ログのみで、公式ROM・逆アセンブル結果には一切触れない。

(a) shuffle-clock: 各行の clock 列の値集合をそのまま使い、行への割り当てだけを
    シャッフルする(seq/frame/cpu/kind/port/valueは一切変更しない)。真の発生順が
    失われるので、解析器が本当にclock順の「直前のOUT」を見ているなら、
    一致率は偶然一致率(1/256≒0.39%)近くまで落ちるはず。
(b) offset-value: すべてのIN行のvalueに+1(mod 256)する。OUT側の値はそのまま。
    解析器が本当に「OUT値とIN値を独立に比較」しているなら、100%だった一致率は
    ほぼ0%まで崩れるはず。崩れない場合、解析器がOUT値とIN値のどちらかを
    実質的に同じ変数から読んでいる(自己参照)疑いが濃い。

使い方:
    python3 tools/verify_analyzer_corruption.py \
        --iolog measurements/m6c-sub-d5-seqfile.iolog.txt \
        --intlog measurements/m6c-sub-d5-seqfile.intlog.txt \
        --workdir /tmp/m6c-corruption-check
"""
from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
from pathlib import Path

# cmp_io.py の gzip 透過オープンを共有する（.gz と非圧縮を同じ経路で読む。
# 2026-08-10 measurements/*.iolog.txt,*.intlog.txt を gzip 化したため必要。
# docs/notes/disclosure-2026-08-10.md 参照。二重実装しない）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402


def _read_text_maybe_gz(path: Path) -> str:
    with cmp_io._open_iolog(str(path)) as f:
        return f.read()


IO_ROW_RE = re.compile(
    r"^(\s*)(\d+)(\s+)(\d+)(\s+)(\d+)(\s+)(main|sub)(\s+)(IN|OUT)(\s+)([0-9A-Fa-f]{4})(\s+)([0-9A-Fa-f]{2})(\s+)([0-9A-Fa-f]{4})(\s*)$"
)


def make_shuffled_clock(src: Path, dst: Path, seed: int = 1234) -> None:
    """clock列の値集合はそのまま、行への割り当てだけをシャッフルする。"""
    lines = _read_text_maybe_gz(src).splitlines(keepends=True)
    row_idxs = []
    clocks = []
    for i, line in enumerate(lines):
        m = IO_ROW_RE.match(line)
        if not m:
            continue
        row_idxs.append(i)
        clocks.append(int(m.group(4)))
    rng = random.Random(seed)
    shuffled = clocks[:]
    rng.shuffle(shuffled)
    out_lines = lines[:]
    for i, new_clock in zip(row_idxs, shuffled):
        m = IO_ROW_RE.match(lines[i])
        g = list(m.groups())
        g[3] = str(new_clock)
        out_lines[i] = "".join(g)
    dst.write_text("".join(out_lines), encoding="utf-8")


def make_offset_in_values(src: Path, dst: Path, delta: int = 1) -> None:
    """全INイベントのvalueに+delta(mod 256)する。OUTはそのまま。"""
    lines = _read_text_maybe_gz(src).splitlines(keepends=True)
    out_lines = lines[:]
    for i, line in enumerate(lines):
        m = IO_ROW_RE.match(line)
        if not m:
            continue
        g = list(m.groups())
        kind = g[9]
        if kind == "IN":
            val = int(g[13], 16)
            val = (val + delta) % 256
            g[13] = f"{val:02X}"
        out_lines[i] = "".join(g)
    dst.write_text("".join(out_lines), encoding="utf-8")


def run_analyzer(iolog: Path, intlog: Path, out: Path) -> None:
    script = Path(__file__).parent / "analyze_sub_proto.py"
    subprocess.run(
        [sys.executable, str(script), "--iolog", str(iolog), "--intlog", str(intlog), "--out", str(out)],
        check=True,
    )


FC_FD_RE = re.compile(
    r"OUT 00FD \(発行数(\d+)件\) -> IN 00FC:\n"
    r"    畳む前\(raw\)    : 一致 (\d+) / 不一致 (\d+).*\n"
    r"    値変化時のみ\(collapsed\): 一致 (\d+) / 不一致 (\d+)"
)
FC_FROM_SUB_RE = re.compile(
    r"OUT 00FC \(発行数(\d+)件\) -> IN 00FD:\n"
    r"    畳む前\(raw\)    : 一致 (\d+) / 不一致 (\d+).*\n"
    r"    値変化時のみ\(collapsed\): 一致 (\d+) / 不一致 (\d+)"
)


def extract_fc_fd(report: Path) -> dict:
    text = report.read_text(encoding="utf-8")
    result = {}
    m = FC_FD_RE.search(text)
    if m:
        n, rm, rmm, cm, cmm = (int(x) for x in m.groups())
        result["main->sub OUT $FD -> IN $FC"] = {
            "raw_match": rm, "raw_mismatch": rmm,
            "collapsed_match": cm, "collapsed_mismatch": cmm,
        }
    m = FC_FROM_SUB_RE.search(text)
    if m:
        n, rm, rmm, cm, cmm = (int(x) for x in m.groups())
        result["sub->main OUT $FC -> IN $FD"] = {
            "raw_match": rm, "raw_mismatch": rmm,
            "collapsed_match": cm, "collapsed_mismatch": cmm,
        }
    return result


def pct(m: int, mm: int) -> str:
    total = m + mm
    if total == 0:
        return "n/a (サンプル無し)"
    return f"{m/total*100:.2f}% ({m}/{total})"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--intlog", required=True, type=Path)
    ap.add_argument("--workdir", required=True, type=Path)
    args = ap.parse_args()

    args.workdir.mkdir(parents=True, exist_ok=True)

    baseline_out = args.workdir / "baseline.txt"
    run_analyzer(args.iolog, args.intlog, baseline_out)
    baseline = extract_fc_fd(baseline_out)

    shuffled_io = args.workdir / "shuffled.iolog.txt"
    make_shuffled_clock(args.iolog, shuffled_io)
    shuffled_out = args.workdir / "shuffled.txt"
    run_analyzer(shuffled_io, args.intlog, shuffled_out)
    shuffled = extract_fc_fd(shuffled_out)

    offset_io = args.workdir / "offset.iolog.txt"
    make_offset_in_values(args.iolog, offset_io)
    offset_out = args.workdir / "offset.txt"
    run_analyzer(offset_io, args.intlog, offset_out)
    offset = extract_fc_fd(offset_out)

    print(f"# 破壊テスト結果: {args.iolog.name}")
    print()
    for pair in baseline:
        print(f"## {pair}")
        b = baseline.get(pair, {})
        s = shuffled.get(pair, {})
        o = offset.get(pair, {})
        print(f"  baseline (無加工)        : raw {pct(b.get('raw_match',0), b.get('raw_mismatch',0))}"
              f" / collapsed {pct(b.get('collapsed_match',0), b.get('collapsed_mismatch',0))}")
        print(f"  (a) shuffle-clock (順序破壊): raw {pct(s.get('raw_match',0), s.get('raw_mismatch',0))}"
              f" / collapsed {pct(s.get('collapsed_match',0), s.get('collapsed_mismatch',0))}")
        print(f"  (b) offset-value (値+1)    : raw {pct(o.get('raw_match',0), o.get('raw_mismatch',0))}"
              f" / collapsed {pct(o.get('collapsed_match',0), o.get('collapsed_mismatch',0))}")
        print()
    print(f"詳細レポート: {baseline_out}, {shuffled_out}, {offset_out}")


if __name__ == "__main__":
    main()

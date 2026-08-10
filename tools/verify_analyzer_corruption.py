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

## 2026-08-10 伏せ字化への対応

`measurements/*.iolog.txt` の `$FB`/`$FC`/`$FD` の value 列は
`tools/redact_iolog.py` で `--` に伏せ字化されている
(docs/notes/disclosure-2026-08-10.md)。この破壊テストの (a)(b) は
どちらも「value 列を操作して一致率が崩れるか」を見るテストなので、
value が既に `--` に固定されているログに対しては前提が崩れる:

  - (b) offset-value は伏せ字済みの value(`--`)には delta を加算できない
    (数値ではない)。そもそも analyze_sub_proto.py 側の2026-08-10の修正で
    $FC/$FD ペアは値比較の対象から明示的に除外されるようになったため、
    このテストが検算しようとしていた「$FD→$FCの100%一致」自体が
    レポートに現れない。**意味のある結果を出せないので SKIP する。**
  - (a) shuffle-clock はポートの意味に関係なくclock列を壊すテストなので、
    伏せていない制御ポートに対しては原理上は今でも成立する。ただし
    実測データ(measurements/m6c-sub-d5-seqfile 等)では、伏せていない
    ポートペアの中に $FD→$FC ほど強い基準一致率(偶然を大きく超える水準)を
    持つものが見つからない場合がある。基準が弱いと「シャッフルで崩れたか」
    の判定自体に意味が無いため、本スクリプトはレポートから動的に
    「伏せられていないポートペアの中で最も一致率が高いもの」を選び、
    そのペアで(a)を実行する。該当するペアが1つも無ければ(a)もSKIPする
    (判断根拠は下記 `pick_unmasked_pair` のdocstring)。

このスクリプトは入力ログが伏せ字済みかどうかを自動判定し、SKIPが必要な
場合は `tools/conform_l3.sh` の書式(SKIP: 理由 / 必要なもの / 当時の結果の
在処)を踏襲して表示する。

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


MASKED_VALUE = "--"

# value 列は2桁hexまたは伏せ字マーカー(`--`)のどちらも受理する。
# 受理しないと、伏せ字済みログに対して make_shuffled_clock が
# $FB/$FC/$FD の行を丸ごと「マッチしない行」として素通りさせてしまい
# (=シャッフル対象から漏れる)、シャッフルの効き目を弱める方向に
# 静かにズレる(これも「無言で崩れる」の一種なので直す)。
IO_ROW_RE = re.compile(
    r"^(\s*)(\d+)(\s+)(\d+)(\s+)(\d+)(\s+)(main|sub)(\s+)(IN|OUT)(\s+)"
    r"([0-9A-Fa-f]{4})(\s+)([0-9A-Fa-f]{2}|--)(\s+)([0-9A-Fa-f]{4})(\s*)$"
)

FOOTER_MARKER_SNIPPET = "tools/redact_iolog.py: 伏せた記録"


def detect_masked_ports(path: Path) -> set[str]:
    """入力ログ中で value 列が `--` になっているポートの集合を返す。

    tools/redact_iolog.py の対象ポート指定(既定 $FB/$FC/$FD)は
    再実行時に --ports で変わりうるので、footer の記載を鵜呑みにせず
    実際の行を見て判定する(値そのものは集めない。ポート名だけ)。
    """
    ports: set[str] = set()
    for line in _read_text_maybe_gz(path).splitlines():
        fields = line.strip().split()
        # 旧形式(7列): seq frame cpu kind port value pc
        # 新形式(8列): seq clock frame cpu kind port value pc
        # いずれも末尾から3番目がport、2番目がvalue。
        if len(fields) in (7, 8) and fields[-2] == MASKED_VALUE:
            ports.add(fields[-3].upper())
    return ports


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
    """全INイベントのvalueに+delta(mod 256)する。OUTはそのまま。

    伏せ字(`--`)の行はそもそも数値でないため変更しない(そのまま残す)。
    このテスト自体は伏せ字済みログに対しては呼ばない方針だが、
    直接呼ばれた場合に例外で落ちるよりは無変更のほうが安全側。
    """
    lines = _read_text_maybe_gz(src).splitlines(keepends=True)
    out_lines = lines[:]
    for i, line in enumerate(lines):
        m = IO_ROW_RE.match(line)
        if not m:
            continue
        g = list(m.groups())
        kind = g[9]
        value_s = g[13]
        if kind == "IN" and value_s != MASKED_VALUE:
            val = int(value_s, 16)
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


def _pair_re(out_port: str, in_port: str) -> re.Pattern:
    op = out_port.upper().zfill(4)
    ip = in_port.upper().zfill(4)
    return re.compile(
        # ヘッダ行の末尾には「※少数OUT罠の疑い」の注記が付くことがある
        # (analyze_sub_proto.py analyze_q1_data_path() の warn 変数)。
        # 同じ行の残りとして [^\n]* で吸収してから改行を要求する。
        rf"OUT {op} \(発行数(\d+)件\) -> IN {ip}:[^\n]*\n"
        rf"    畳む前\(raw\)    : 一致 (\d+) / 不一致 (\d+).*\n"
        rf"    値変化時のみ\(collapsed\): 一致 (\d+) / 不一致 (\d+)"
    )


# 全ペアを走査してポート名・件数・一致率を拾う汎用パターン
# (analyze_sub_proto.py analyze_q1_data_path() の出力書式に依存する。
# 二重実装ではなく「正規表現でその出力を読む」だけなので、書式が変わったら
# ここも追従が必要——それ自体は元からの制約で、今回追加した制約ではない)。
ANY_PAIR_RE = re.compile(
    r"OUT (\w{4}) \(発行数(\d+)件\) -> IN (\w{4}):[^\n]*\n"
    r"    畳む前\(raw\)    : 一致 (\d+) / 不一致 (\d+).*\n"
    r"    値変化時のみ\(collapsed\): 一致 (\d+) / 不一致 (\d+)"
)


def extract_pair(text: str, out_port: str, in_port: str, label: str) -> dict:
    m = _pair_re(out_port, in_port).search(text)
    if not m:
        return {}
    n, rm, rmm, cm, cmm = (int(x) for x in m.groups())
    return {
        label: {
            "raw_match": rm, "raw_mismatch": rmm,
            "collapsed_match": cm, "collapsed_mismatch": cmm,
        }
    }


# (a)(b)を伏せ字前と同じ形で回すときの対象(元々の書式に合わせて維持)。
DEFAULT_PAIRS = [
    ("00FD", "00FC", "main->sub OUT $FD -> IN $FC"),
    ("00FC", "00FD", "sub->main OUT $FC -> IN $FD"),
]


def extract_default_pairs(report: Path) -> dict:
    text = report.read_text(encoding="utf-8")
    result: dict = {}
    for out_port, in_port, label in DEFAULT_PAIRS:
        result.update(extract_pair(text, out_port, in_port, label))
    return result


MIN_SAMPLE_FOR_PICK = 200  # 少数サンプルの偶然一致で選んでしまわないための下限
# 偶然一致率(1/256≒0.39%)の5倍を下回る基準では「崩れて見える」余地が
# そもそも無い(既にほぼ底値)。シャッフルテストとして意味を持たせる
# ための下限(analyze_sub_proto.pyのCHANCE_RATE=1/256と揃える)。
MIN_BASELINE_RATE_FOR_PICK = 5 * (1.0 / 256.0)


def pick_unmasked_pair(report_text: str, masked_ports: set[str]) -> tuple[str, str, int, int] | None:
    """伏せられていないポートペアの中で、最も一致率(collapsed)が高いものを選ぶ。

    (a) shuffle-clock は「clock順を壊すと一致率が崩れる」ことを見るテストなので、
    比較対象は「シャッフルで崩れて見えるだけの基準一致率」を持つ必要がある。
    偶然一致率(0.39%)に近い基準では、シャッフル後もほぼ同じ値になるのが
    正常であり、崩れたかどうかを判定する意味が無い。そのため
    「サンプル数が十分(>=200)、かつ一致率が最も高い」ペアを機械的に選ぶ
    (手で決め打ちしない。ログが変われば選ばれるペアも変わってよい)。

    見つからない場合は None を返し、呼び出し側は(a)もSKIPする
    (=伏せていないポートの中に、崩して見せられるだけの基準一致率を持つ
    ペアが無かった、という事実をそのまま報告する)。
    """
    best: tuple[str, str, int, int] | None = None
    best_rate = -1.0
    for m in ANY_PAIR_RE.finditer(report_text):
        out_port, out_n, in_port, rm, rmm, cm, cmm = m.groups()
        if out_port in masked_ports or in_port in masked_ports:
            continue
        cm_i, cmm_i = int(cm), int(cmm)
        total = cm_i + cmm_i
        if total < MIN_SAMPLE_FOR_PICK:
            continue
        rate = cm_i / total if total else 0.0
        if rate < MIN_BASELINE_RATE_FOR_PICK:
            continue
        if rate > best_rate:
            best_rate = rate
            best = (out_port, in_port, cm_i, cmm_i)
    return best


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

    masked_ports = detect_masked_ports(args.iolog)

    baseline_out = args.workdir / "baseline.txt"
    run_analyzer(args.iolog, args.intlog, baseline_out)
    baseline_text = baseline_out.read_text(encoding="utf-8")

    print(f"# 破壊テスト結果: {args.iolog.name}")
    print()

    if not masked_ports:
        # --- 伏せ字なし: 従来どおり $FD/$FC ペアで (a)(b) を両方実行する ---
        baseline = extract_default_pairs(baseline_out)

        shuffled_io = args.workdir / "shuffled.iolog.txt"
        make_shuffled_clock(args.iolog, shuffled_io)
        shuffled_out = args.workdir / "shuffled.txt"
        run_analyzer(shuffled_io, args.intlog, shuffled_out)
        shuffled = extract_default_pairs(shuffled_out)

        offset_io = args.workdir / "offset.iolog.txt"
        make_offset_in_values(args.iolog, offset_io)
        offset_out = args.workdir / "offset.txt"
        run_analyzer(offset_io, args.intlog, offset_out)
        offset = extract_default_pairs(offset_out)

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
        return

    # --- 伏せ字あり: (b) は SKIP。(a) は伏せていないポートで機械的に選び直す ---
    print(
        "SKIP: (b) offset-value — 入力ログは伏せ字済み(2026-08-10。"
        "docs/notes/disclosure-2026-08-10.md)。"
    )
    print(
        f"  伏せ字対象ポート: {', '.join('$' + p[-2:] for p in sorted(masked_ports))}"
    )
    print(
        "  (b) はIN値に+1して一致率が崩れるかを見るテストだが、伏せ字済みの"
        "value(`--`)は数値ではないため+1できない。そもそも analyze_sub_proto.py"
        "側の2026-08-10の修正で、これらのポートは値比較そのものから除外される"
        "ようになったため、このテストが検算しようとしていた「$FD→$FCの100%"
        "一致」自体がレポートに現れない。意味のある結果を出せないためSKIPする。"
    )
    print(
        "  当時（伏せ字前）の破壊テスト結果は measurements/m6c-corruption-check/ に"
        "記録が残っている（docs/notes/m6-sub-proto.md も参照）。"
    )
    print(
        "  公式環境(PC88_REF_ROM_DIR/PC88_REF_DISK_DIR)があれば、"
        "tools/harness のフロントエンド(q88measure --io-log <出力先>)で"
        "伏せ字前の生ログをその場で作れる。伏せ字は redact_iolog.py という"
        "別工程でしか適用されないため、harnessが吐く直後のログには"
        "元の値が残っている。そのログをそのまま本スクリプトに渡せば"
        "(b)を含めた完全な検算ができる（そのログは伏せ字前なので"
        "コミットしないこと。使い捨てのworkdirに置くこと）。"
    )
    print()

    best = pick_unmasked_pair(baseline_text, masked_ports)
    if best is None:
        print(
            "SKIP: (a) shuffle-clock — 伏せていないポートの中に、シャッフルで"
            f"崩れて見せられるだけの基準一致率(サンプル数{MIN_SAMPLE_FOR_PICK}件以上)"
            "を持つペアが見つからなかった。制御ポート同士は元々偶然一致率に近い"
            "水準しか出ておらず、シャッフルしても『崩れたかどうか』を判定する"
            "意味のある基準が無い(pick_unmasked_pair()のdocstring参照)。"
        )
        print(f"詳細レポート: {baseline_out}")
        return

    out_port, in_port, base_cm, base_cmm = best
    label = f"(伏せ字のため再選択) OUT ${out_port[-2:]} -> IN ${in_port[-2:]}"
    print(
        f"注記: (a) shuffle-clock は $FD/$FC が伏せ字済みのため対象を"
        f"再選択した。選んだペア: OUT ${out_port[-2:]} -> IN ${in_port[-2:]}"
        f"（伏せていないポートの中で最も一致率が高いもの。"
        f"基準 collapsed 一致率 {base_cm/(base_cm+base_cmm)*100:.1f}%"
        f"、サンプル{base_cm+base_cmm}件）。"
    )
    print()

    baseline = extract_pair(baseline_text, out_port, in_port, label)

    shuffled_io = args.workdir / "shuffled.iolog.txt"
    make_shuffled_clock(args.iolog, shuffled_io)
    shuffled_out = args.workdir / "shuffled.txt"
    run_analyzer(shuffled_io, args.intlog, shuffled_out)
    shuffled = extract_pair(shuffled_out.read_text(encoding="utf-8"), out_port, in_port, label)

    b = baseline.get(label, {})
    s = shuffled.get(label, {})
    print(f"## {label}")
    print(f"  baseline (無加工)        : raw {pct(b.get('raw_match',0), b.get('raw_mismatch',0))}"
          f" / collapsed {pct(b.get('collapsed_match',0), b.get('collapsed_mismatch',0))}")
    print(f"  (a) shuffle-clock (順序破壊): raw {pct(s.get('raw_match',0), s.get('raw_mismatch',0))}"
          f" / collapsed {pct(s.get('collapsed_match',0), s.get('collapsed_mismatch',0))}")
    print()
    print(f"詳細レポート: {baseline_out}, {shuffled_out}")


if __name__ == "__main__":
    main()

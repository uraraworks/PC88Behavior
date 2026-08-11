#!/usr/bin/env python3
"""PC88Behavior: サブCPU視点での $FE 待ち状態の解析。

`docs/spec/l3-subrom.md` 1.13節は main の `IN $FE` を4箇所の待ちループに
分類し、遷移を確定した（`tools/analyze_main_to_sub.py` の
`WAIT_LOOP_PCS`）。しかしそれは main 視点のみで、**sub視点**の待ち状態は
未解析だった。自作サブROMを実装するには、sub が「いつ $FE を読みに行き、
どんな値の並びを経て抜けるか」「その前後で $FF に何を書くか」を知る必要が
ある。

本スクリプトは既存の解析器（`analyze_main_to_sub.py` の
`wait_loop_transitions` / `WAIT_LOOP_PCS`）と同じ手法を sub 側に適用する:

1. sub の `IN $FE` イベントを直前のリターンアドレス(pc)でグループ化する
   （同じ処理を行うたびに同じpcへ戻るという事実だけを使う。PCクラスタは
   決め打ちせず、件数閾値以上のものを機械的に「待ちループ候補」とみなす）。
2. 各pcについて、連続する読み取り値の遷移(前の値→次の値)を集計する
   （1.13節と同じ発想）。
3. 各「待ちループの一続き(スピン)」の直前・直後に sub が `OUT $FF` に
   書いた値を対応付ける。`$FF`はデータポート($FB/$FC/$FD)ではないため
   伏せ字対象外——値がそのまま読める(CLAUDE.md禁止事項5、
   docs/notes/disclosure-2026-08-10.md)。1.12節のフェーズコード語彙
   (0F/0E/09/08=SEND系, 0B/0A/0D/0C=RECV系)に照らして、各待ちループが
   SEND側かRECV側かを機械的に分類する。

このスクリプトはPCの具体値を集計・表示するが、`docs/spec/l3-subrom.md`
本体にPCの具体値は書かない(1.14節と同じ判断——sub内部のどの番地に
実装しても成立する構造上の性質であり、実装目標にはならないため)。
PCは`docs/notes/`の解析ノート側にのみ記録する。

再実行方法:
    python3 tools/analyze_sub_fe.py \
        --iolog measurements/m6g-d0-boot-run1.iolog.txt.gz \
        --out /tmp/sub-fe-run1.txt

    python3 tools/analyze_sub_fe.py cross \
        --iolog measurements/m6c-sub-d0-boot.iolog.txt.gz \
                measurements/m6c-sub-d1-files.iolog.txt.gz \
                measurements/m6c-sub-d2-save.iolog.txt.gz \
                measurements/m6c-sub-d5-seqfile.iolog.txt.gz \
        --label d0-boot d1-files d2-save d5-seqfile \
        --out /tmp/sub-fe-cross.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

# cmp_io.py の gzip 透過オープンを共有する(.gz と非圧縮を同じ経路で読む。
# 二重実装しない)。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402

MASKED_VALUE = "--"
ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+"
    r"([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2}|--)\s+([0-9A-Fa-f]{4})\s*$"
)

# 1.12節で確定したSEND/RECVのフェーズコード語彙(main/sub共通)。
SEND_CODES = {0x0F, 0x0E, 0x09, 0x08}
RECV_CODES = {0x0B, 0x0A, 0x0D, 0x0C}

# 待ちループ候補と判定する最小出現件数。0710/0724/0735のような
# 「起動時1回きりのSEND手順」相当のループは件数が20台と少ないため、
# それを拾える閾値にする(m6-main-to-sub.mdのSMALL_OUT_WARN=20とは
# 別の目的の閾値だが、値の大きさの目安として揃えた)。
MIN_LOOP_COUNT = 10


@dataclass
class Ev:
    seq: int
    clock: int
    frame: int
    cpu: str
    kind: str
    port: str
    value: int | None
    pc: str


def parse_iolog(path: Path) -> tuple[list[Ev], dict[tuple[str, str, str], int]]:
    rows: list[Ev] = []
    masked: dict[tuple[str, str, str], int] = {}
    with cmp_io._open_iolog(str(path)) as f:
        for line in f:
            m = ROW_RE.match(line)
            if not m:
                continue
            seq, clock, frame, cpu, kind, port, value_s, pc = m.groups()
            port_u = port.upper()
            if value_s == MASKED_VALUE:
                key = (cpu, port_u, kind)
                masked[key] = masked.get(key, 0) + 1
                value: int | None = None
            else:
                value = int(value_s, 16)
            rows.append(Ev(int(seq), int(clock), int(frame), cpu, kind,
                            port_u, value, pc.upper()))
    rows.sort(key=lambda e: e.clock)
    return rows, masked


@dataclass
class LoopStats:
    pc: str
    n_events: int
    n_spins: int
    transitions: Counter  # (prev,val) -> count
    entry_values: Counter  # スピン最初の値
    exit_values: Counter  # スピン最後の値
    prev_ff: Counter  # スピン開始直前の直近 sub OUT $FF 値
    next_ff: Counter  # スピン終了直後の直近 sub OUT $FF 値
    post_kind_port: Counter  # スピン終了直後、直近OUT $FF「の次」に来たイベントの (cpu違反なし) kind+port


def analyze_sub_fe(rows: list[Ev]) -> dict[str, LoopStats]:
    """sub の IN $FE をpc別に分類し、遷移と前後の$FFコンテキストを集計する。

    「スピン」= clock順で連続する、同一pcの sub IN $FE 読み取りの並び。
    実データ(06DD/06FC等)で、スピン中に他ポートのイベントが割り込む
    事例は無いことを確認済み(手動検査)。スピンの前後にある直近の
    sub OUT $FF イベントを、全イベント列上の前方/後方走査で1回だけ
    求める(O(n))。
    """
    sub_rows = [e for e in rows if e.cpu == "sub"]
    n = len(sub_rows)

    # 各indexについて「直前の直近 sub OUT $FF 値」「直後の直近 sub OUT $FF 値」
    # をO(n)の前後2パスで求める。
    prev_ff_at = [None] * n
    cur = None
    for i, e in enumerate(sub_rows):
        prev_ff_at[i] = cur
        if e.kind == "OUT" and e.port == "00FF" and e.value is not None:
            cur = e.value

    next_ff_at = [None] * n
    next_ff_event_idx = [None] * n  # そのOUT $FFイベント自体のindex(post_kind_port用)
    cur = None
    cur_idx = None
    for i in range(n - 1, -1, -1):
        next_ff_at[i] = cur
        next_ff_event_idx[i] = cur_idx
        e = sub_rows[i]
        if e.kind == "OUT" and e.port == "00FF" and e.value is not None:
            cur = e.value
            cur_idx = i

    fe_counts: Counter[str] = Counter(
        e.pc for e in sub_rows if e.kind == "IN" and e.port == "00FE"
    )
    candidate_pcs = {pc for pc, c in fe_counts.items() if c >= MIN_LOOP_COUNT}

    stats: dict[str, LoopStats] = {
        pc: LoopStats(pc, 0, 0, Counter(), Counter(), Counter(), Counter(), Counter(), Counter())
        for pc in candidate_pcs
    }

    idx = 0
    while idx < n:
        e = sub_rows[idx]
        if e.kind == "IN" and e.port == "00FE" and e.pc in candidate_pcs:
            pc = e.pc
            j = idx
            vals: list[int | None] = []
            while (
                j < n
                and sub_rows[j].kind == "IN"
                and sub_rows[j].port == "00FE"
                and sub_rows[j].pc == pc
            ):
                vals.append(sub_rows[j].value)
                j += 1
            st = stats[pc]
            st.n_events += len(vals)
            st.n_spins += 1
            prev_v = None
            for v in vals:
                if prev_v is not None and v is not None and prev_v is not None:
                    st.transitions[(prev_v, v)] += 1
                prev_v = v
            if vals and vals[0] is not None:
                st.entry_values[vals[0]] += 1
            if vals and vals[-1] is not None:
                st.exit_values[vals[-1]] += 1
            st.prev_ff[prev_ff_at[idx]] += 1
            st.next_ff[next_ff_at[j - 1]] += 1
            # 直後のOUT $FF「の次」に来た実イベント(データがIN $FCかOUT $FDか等)
            ff_idx = next_ff_event_idx[j - 1]
            if ff_idx is not None and ff_idx + 1 < n:
                nxt = sub_rows[ff_idx + 1]
                st.post_kind_port[f"{nxt.kind} ${nxt.port[-2:]}"] += 1
            else:
                st.post_kind_port["(無し)"] += 1
            idx = j
        else:
            idx += 1
    return stats


def classify_role(st: LoopStats) -> str:
    """直前・直後のOUT $FF値がSEND語彙かRECV語彙かで役割を推定する。"""
    prev_top = st.prev_ff.most_common(1)
    next_top = st.next_ff.most_common(1)
    votes = []
    for top in (prev_top, next_top):
        if not top:
            continue
        val, _ = top[0]
        if val is None:
            continue
        if val in SEND_CODES:
            votes.append("SEND")
        elif val in RECV_CODES:
            votes.append("RECV")
    if not votes:
        return "不明(前後にOUT $FFの語彙なし)"
    if len(set(votes)) == 1:
        return votes[0]
    return f"不定(前後で食い違い: {votes})"


def fmt_transitions(c: Counter, top: int = 6) -> str:
    items = sorted(c.items(), key=lambda kv: -kv[1])[:top]
    return ", ".join(f"{a:02X}->{b:02X}({n})" for (a, b), n in items)


def fmt_value_counter(c: Counter, top: int = 6) -> str:
    items = sorted(c.items(), key=lambda kv: -kv[1])[:top]
    parts = []
    for v, n in items:
        vs = f"{v:02X}" if v is not None else "(無し)"
        parts.append(f"{vs}({n})")
    return ", ".join(parts)


def write_single_report(rows: list[Ev], label: str, out, masked: dict | None = None) -> dict[str, LoopStats]:
    stats = analyze_sub_fe(rows)
    print(f"# sub視点 $FE 待ち状態解析: {label}", file=out)
    print(file=out)
    if masked:
        total = sum(masked.values())
        print(
            f"## 注記: 伏せ字(値秘匿)イベント{total}件を含む"
            f"(このスクリプトが対象とする $FE/$FF は伏せ字対象外のため影響しない。"
            f"件数のみ記録)",
            file=out,
        )
        for (cpu, port, kind), cnt in sorted(masked.items()):
            print(f"    {cpu} {kind} ${port[-2:]}: {cnt}件", file=out)
        print(file=out)

    print(f"## 候補待ちループ(sub IN $FE, pc別, 件数>={MIN_LOOP_COUNT}): {len(stats)}種", file=out)
    print(file=out)
    # 件数(n_events)が同点のpcが複数あると、Pythonのset反復順が
    # PYTHONHASHSEEDに依存して実行ごとに変わりうる(文字列ハッシュの
    # ランダム化)。決定論性を壊さないよう、同点はpc文字列で必ず
    # 二次キーを取る(実測でrun1/run2の出力順が入れ替わる事例を確認済み。
    # 値そのものは変わらないが「決定論性」の確認手順を壊すため固定する)。
    for pc, st in sorted(stats.items(), key=lambda kv: (-kv[1].n_events, kv[0])):
        role = classify_role(st)
        print(f"### pc={pc} (n={st.n_events}件, スピン数={st.n_spins})", file=out)
        print(f"  推定ロール: {role}", file=out)
        print(f"  遷移: {fmt_transitions(st.transitions)}", file=out)
        print(f"  スピン開始値: {fmt_value_counter(st.entry_values)}", file=out)
        print(f"  スピン終了値: {fmt_value_counter(st.exit_values)}", file=out)
        print(f"  直前の sub OUT $FF 値: {fmt_value_counter(st.prev_ff)}", file=out)
        print(f"  直後の sub OUT $FF 値: {fmt_value_counter(st.next_ff)}", file=out)
        print(
            f"  直後のOUT $FFの次に来た実イベント: "
            f"{', '.join(f'{k}({n})' for k, n in st.post_kind_port.most_common(4))}",
            file=out,
        )
        print(file=out)
    return stats


def write_cross_report(all_rows: dict[str, list[Ev]], out) -> None:
    print("# 条件横断比較: sub視点 $FE 待ち状態", file=out)
    print(file=out)
    per_label_stats: dict[str, dict[str, LoopStats]] = {}
    for label, rows in all_rows.items():
        per_label_stats[label] = analyze_sub_fe(rows)

    all_pcs = set()
    for stats in per_label_stats.values():
        all_pcs |= set(stats.keys())

    print(f"## pc別、条件横断での一致確認(同一sub ROMなら全条件で同じpc集合・同じ遷移語彙が出るはず)", file=out)
    print(file=out)
    for pc in sorted(all_pcs):
        print(f"### pc={pc}", file=out)
        roles = set()
        trans_sets = []
        for label, stats in per_label_stats.items():
            st = stats.get(pc)
            if st is None:
                print(f"  {label}: 出現なし", file=out)
                continue
            role = classify_role(st)
            roles.add(role)
            trs = set(st.transitions.keys())
            trans_sets.append(trs)
            print(
                f"  {label}: n={st.n_events} ロール={role} "
                f"遷移語彙={sorted(f'{a:02X}->{b:02X}' for a,b in trs)}",
                file=out,
            )
        if trans_sets:
            common = set.intersection(*trans_sets) if len(trans_sets) == len(all_rows) else set()
            union = set.union(*trans_sets)
            print(
                f"  条件横断: 全条件共通の遷移={sorted(f'{a:02X}->{b:02X}' for a,b in common)}"
                f" / 全条件の和集合={sorted(f'{a:02X}->{b:02X}' for a,b in union)}"
                f" / ロール一致={'YES' if len(roles) == 1 else 'NO(' + str(roles) + ')'}",
                file=out,
            )
        print(file=out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode_pos", nargs="?", default="single", choices=["single", "cross"])
    ap.add_argument("--iolog", nargs="+", required=True, type=Path)
    ap.add_argument("--label", nargs="*", default=None)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.mode_pos == "single":
        if len(args.iolog) != 1:
            print("error: single モードは --iolog 1個のみ", file=sys.stderr)
            sys.exit(2)
        label = args.label[0] if args.label else args.iolog[0].name
        rows, masked = parse_iolog(args.iolog[0])
        with args.out.open("w", encoding="utf-8") as out:
            write_single_report(rows, label, out, masked)
    else:
        labels = args.label or [p.name for p in args.iolog]
        if len(labels) != len(args.iolog):
            print("error: --iolog と --label の個数が一致しない", file=sys.stderr)
            sys.exit(2)
        all_rows: dict[str, list[Ev]] = {}
        for label, p in zip(labels, args.iolog):
            rows, _masked = parse_iolog(p)
            all_rows[label] = rows
        with args.out.open("w", encoding="utf-8") as out:
            write_cross_report(all_rows, out)

    print(f"written: {args.out}")


if __name__ == "__main__":
    main()

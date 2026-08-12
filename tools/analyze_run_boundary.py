#!/usr/bin/env python3
"""PC88Behavior: 「連続送信(run)の途中か、runが終わったか」をsubがどう
判別しているかを、既存の伏せ字済みログの再解析だけで調べる（M6n想定）。

背景: コミット c73fb00 までの自作サブROMは、mainの複数バイト連続SEND
（`docs/notes/m6-main-to-sub.md` 2.2節、SEND連続長1,2,5,6,8,12等）の
途中で、1バイト完遂するたびにアイドルディスパッチャへ戻ってしまい、
runの続きを待っているmainとかみ合わずデッドロックしていた
(`docs/notes/m6m-fe-bit-analysis.md`)。本稿は「runの続きか、runの終わりで
応答に転じるべきか」をsubが**何を見て**判別しているかを、値を使わず
$FE/$FF（フェーズコード・待ちループのビット）だけから確定させる。

追加測定は行っていない。既存の `measurements/m6c-sub-{d0-boot,d1-files,
d2-save,d5-seqfile}.iolog.txt.gz`（4条件、共通クロックなし、決定論性は
`docs/notes/m6-conformance.md`で確認済み）を再解析する。main側SEND
分類は`tools/analyze_main_to_sub.py`の`parse_iolog`/`classify_transactions`
/`tx_kind`をそのままimportして使う（二重実装しない）。

やっていることは以下の3つで、いずれも「PCとclockと$FF値(伏せ字対象外)
だけを見て集計する」という既存解析器と同種の操作である。ROMの内容・
逆アセンブルには一切触れていない。

1. `main_send_run_ff_positions`: main側の連続SEND run内で、各データ
   バイト（`OUT $FD`, pc=37F4/3811）の直前に`OUT $FF 0F`が現れるかを、
   run内の位置（先頭/継続）別に集計する。
2. `main_send_run_last_pc_parity`: run内最終バイトのpc（37F4/3811）と、
   run長の偶奇の対応を確認する（`pc=3811`がrun終端専用のマーカーか、
   単なる2エントリ・ループアンローリングの片割れかを判定する）。
3. `sub_recv_finish_successors`: sub側で`OUT $FF 0C`（RECVプリミティブの
   最終手順、1.15節手順7）の直後に来るイベントを分類する。分類は
   「直後のイベントの kind/port/pc」のみを機械的な鍵として使い、
   件数が一定閾値以上の鍵ごとに、その鍵から**必ず**どこへ進むか
   （次もRECVか、SENDへ転じるか）を、その後に続く`OUT $FF`語彙
   （1.12節: 0B/0A/0D/0C=RECV系, 0F/0E/09/08=SEND系）で確認する。

再実行方法:
    python3 tools/analyze_run_boundary.py \
        --iolog measurements/m6c-sub-d0-boot.iolog.txt.gz \
                measurements/m6c-sub-d1-files.iolog.txt.gz \
                measurements/m6c-sub-d2-save.iolog.txt.gz \
                measurements/m6c-sub-d5-seqfile.iolog.txt.gz \
        --label d0-boot d1-files d2-save d5-seqfile \
        --out measurements/m6n-run-boundary.txt

決定論性は `measurements/m6g-d0-boot-run{1,2}.iolog.txt.gz` に対する
実行結果を diff して確認する（`docs/notes/m6n-run-boundary.md`参照）。
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402

Ev = m2s.Ev

SEND_PCS = m2s.SEND_PCS  # {"37F4", "3811"}
SEND_CODES = {0x0F, 0x0E, 0x09, 0x08}
RECV_CODES = {0x0B, 0x0A, 0x0D, 0x0C}


# --- 1・2. main側 SEND run 内部構造 ---------------------------------------


def main_send_runs(rows: list[Ev]) -> list[list[int]]:
    """main の全行(main_rows のインデックス列)のうち、`OUT $FD` かつ
    pc in SEND_PCS のイベントを、間に他ポートイベント(IN/OUT $FE/$FF は
    許す。それ以外=次のFD/FCが挟まる)が無い限り同一runとして束ねる。

    `main_rows`（この関数が返すインデックスの元になる配列）は
    呼び出し側で `[e for e in rows if e.cpu == "main"]` を渡す前提。
    """
    main_rows = [e for e in rows if e.cpu == "main"]
    fd_idx = [
        i for i, e in enumerate(main_rows)
        if e.kind == "OUT" and e.port == "00FD" and e.pc in SEND_PCS
    ]
    runs: list[list[int]] = []
    cur: list[int] = []
    for i in fd_idx:
        if cur:
            between = main_rows[cur[-1] + 1:i]
            other = [e for e in between if e.port not in ("00FE", "00FF")]
            if other:
                runs.append(cur)
                cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    return runs, main_rows


def send_run_ff_positions(rows: list[Ev]) -> dict[str, Counter]:
    """run内の位置(先頭/継続)別に、直前の窓に`OUT $FF 0F`が現れるかを数える。"""
    runs, main_rows = main_send_runs(rows)
    result = {"first": Counter(), "continuation": Counter()}
    all_fd_idx = [i for r in runs for i in r]
    for r in runs:
        for pos, idx in enumerate(r):
            j = all_fd_idx.index(idx)
            start = (all_fd_idx[j - 1] + 1) if j > 0 else 0
            window = main_rows[start:idx]
            has0f = any(
                e.kind == "OUT" and e.port == "00FF" and e.value == 0x0F
                for e in window
            )
            key = "first" if pos == 0 else "continuation"
            result[key]["0F あり" if has0f else "0F なし"] += 1
    return result


def send_run_last_pc_parity(rows: list[Ev]) -> Counter:
    """run長(バイト数)の偶奇と、run最終バイトのpc(37F4/3811)の対応。"""
    runs, main_rows = main_send_runs(rows)
    c = Counter()
    for r in runs:
        if len(r) < 2:
            continue
        parity = "偶数" if len(r) % 2 == 0 else "奇数"
        last_pc = main_rows[r[-1]].pc
        c[(parity, last_pc)] += 1
    return c


def send_run_length_hist(rows: list[Ev]) -> Counter:
    runs, _ = main_send_runs(rows)
    return Counter(len(r) for r in runs)


# --- pc=3811 の $FF 直後値 ---------------------------------------------


def data_pc_next_ff(rows: list[Ev]) -> dict[str, Counter]:
    """main OUT $FD (pc=37F4/3811) の直後に来る main OUT $FF の値を、
    pcごとに集計する(1.12節フェーズコード語彙との対応確認)。"""
    main_rows = [e for e in rows if e.cpu == "main"]
    result = {"37F4": Counter(), "3811": Counter()}
    n = len(main_rows)
    for i, e in enumerate(main_rows):
        if e.kind == "OUT" and e.port == "00FD" and e.pc in SEND_PCS:
            for j in range(i + 1, n):
                nxt = main_rows[j]
                if nxt.kind == "OUT" and nxt.port == "00FF":
                    result[e.pc][nxt.value] += 1
                    break
                if nxt.port == "00FD":
                    break
    return result


# --- 3. sub側 RECVプリミティブ完了直後の分岐 -------------------------------

RECV_FINISH_VALUE = 0x0C  # 1.15節手順7


def sub_recv_finish_successors(rows: list[Ev]) -> Counter:
    """sub OUT $FF=0x0C (RECV手順7、プリミティブ完了)の直後に来るイベント
    (kind, port, pc)の分布。"""
    sub_rows = [e for e in rows if e.cpu == "sub"]
    n = len(sub_rows)
    c = Counter()
    for i, e in enumerate(sub_rows):
        if e.kind == "OUT" and e.port == "00FF" and e.value == RECV_FINISH_VALUE:
            if i + 1 < n:
                nxt = sub_rows[i + 1]
                key = (nxt.kind, nxt.port, nxt.pc)
            else:
                key = ("(end)", "", "")
            c[key] += 1
    return c


def successor_eventual_ff(rows: list[Ev], succ_key: tuple[str, str, str], window: int = 40) -> Counter:
    """ある後継サイト(succ_key)に入った後、直後window件以内に現れる最初の
    sub OUT $FF 値を集計する(RECV系語彙かSEND系語彙かで、そのサイトが
    「次はRECV」「次はSEND」のどちらへ必ず進むかを確認する)。"""
    sub_rows = [e for e in rows if e.cpu == "sub"]
    n = len(sub_rows)
    c = Counter()
    for i, e in enumerate(sub_rows):
        if e.kind == "OUT" and e.port == "00FF" and e.value == RECV_FINISH_VALUE:
            if i + 1 >= n:
                continue
            nxt = sub_rows[i + 1]
            if (nxt.kind, nxt.port, nxt.pc) != succ_key:
                continue
            for j in range(i + 1, min(n, i + 1 + window)):
                cand = sub_rows[j]
                if cand.kind == "OUT" and cand.port == "00FF" and cand.value is not None:
                    if cand.value == RECV_FINISH_VALUE:
                        continue  # 自分自身(直前finishの残響)は無視
                    c[cand.value] += 1
                    break
    return c


# --- レポート ---------------------------------------------------------


def classify_ff_value(v: int | None) -> str:
    if v is None:
        return "(不明)"
    if v in SEND_CODES:
        return "SEND系"
    if v in RECV_CODES:
        return "RECV系"
    return f"未分類(0x{v:02X})"


def write_single_report(rows: list[Ev], label: str, out) -> None:
    print(f"# run境界判別解析: {label}", file=out)
    print(file=out)

    print("## 1. main側SEND run内の`OUT $FF 0F`有無(先頭/継続)", file=out)
    pos = send_run_ff_positions(rows)
    for key in ("first", "continuation"):
        total = sum(pos[key].values())
        print(f"  {key}: {dict(pos[key])} (計{total}件)", file=out)
    print(file=out)

    print("## 2. run長ヒストグラム / run長の偶奇と最終バイトpcの対応", file=out)
    print(f"  run長ヒストグラム: {dict(sorted(send_run_length_hist(rows).items()))}", file=out)
    parity = send_run_last_pc_parity(rows)
    for (par, pc), n in sorted(parity.items()):
        print(f"  run長{par} -> 最終バイトpc={pc}: {n}件", file=out)
    print(file=out)

    print("## pc=37F4/3811 直後のmain OUT $FF値", file=out)
    nff = data_pc_next_ff(rows)
    for pc, c in nff.items():
        print(f"  pc={pc}: {dict(c)}", file=out)
    print(file=out)

    print("## 3. sub OUT $FF=0C(RECV完了)直後のイベント分布", file=out)
    succ = sub_recv_finish_successors(rows)
    total_finish = sum(succ.values())
    print(f"  RECV完了(OUT $FF=0C)総数: {total_finish}", file=out)
    for key, n in sorted(succ.items(), key=lambda kv: -kv[1]):
        kind, port, pc = key
        port_s = f"${port[-2:]}" if port else ""
        print(f"  次: {kind} {port_s} pc={pc}: {n}件", file=out)
        # そのサイトが最終的にRECV系/SEND系のどちらの$FFへ至るか
        eventual = successor_eventual_ff(rows, key)
        if eventual:
            classified = Counter()
            for v, c2 in eventual.items():
                classified[classify_ff_value(v)] += c2
            print(f"    -> その後最初に現れるOUT $FF語彙: {dict(classified)}", file=out)
    print(file=out)


def write_cross_report(all_rows: dict[str, list[Ev]], out) -> None:
    print("# 条件横断: run境界判別解析", file=out)
    print(file=out)

    print("## 1. SEND run先頭/継続での`OUT $FF 0F`有無(条件別)", file=out)
    for label, rows in all_rows.items():
        pos = send_run_ff_positions(rows)
        f = pos["first"]
        c = pos["continuation"]
        f_total = sum(f.values()) or 1
        c_total = sum(c.values()) or 1
        print(
            f"  {label}: 先頭 0Fあり={f.get('0F あり', 0)}/{f_total} "
            f"({100*f.get('0F あり', 0)/f_total:.0f}%)  "
            f"継続 0Fなし={c.get('0F なし', 0)}/{c_total} "
            f"({100*c.get('0F なし', 0)/c_total:.0f}%)",
            file=out,
        )
    print(file=out)

    print("## 2. run長偶奇と最終バイトpcの対応(条件別、例外があれば明示)", file=out)
    for label, rows in all_rows.items():
        parity = send_run_last_pc_parity(rows)
        exceptions = []
        for (par, pc), n in parity.items():
            expect = "3811" if par == "偶数" else "37F4"
            if pc != expect:
                exceptions.append(f"{par}run終端pc={pc}(期待{expect})x{n}件")
        status = "例外なし" if not exceptions else f"例外: {exceptions}"
        print(f"  {label}: {dict(parity)} -> {status}", file=out)
    print(file=out)

    print("## 3. sub RECV完了(OUT $FF=0C)直後の後継サイトが行き着く先(条件別)", file=out)
    for label, rows in all_rows.items():
        succ = sub_recv_finish_successors(rows)
        print(f"  {label}:", file=out)
        for key, n in sorted(succ.items(), key=lambda kv: -kv[1]):
            kind, port, pc = key
            if n < 3:
                continue
            port_s = f"${port[-2:]}" if port else ""
            eventual = successor_eventual_ff(rows, key)
            classified = Counter()
            for v, c2 in eventual.items():
                classified[classify_ff_value(v)] += c2
            single = len(classified) == 1
            verdict = (
                f"単一語彙({list(classified.keys())[0]})"
                if single and classified
                else f"複数語彙混在{dict(classified)}"
            )
            print(f"    次={kind} {port_s} pc={pc}: {n}件 -> {verdict}", file=out)
    print(file=out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode_pos", nargs="?", default="single", choices=["single", "cross"])
    ap.add_argument("--iolog", nargs="+", required=True, type=Path)
    ap.add_argument("--label", nargs="+", required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    if len(args.iolog) != len(args.label):
        print("error: --iolog と --label の個数が一致しない", file=sys.stderr)
        sys.exit(2)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        if args.mode_pos == "single":
            if len(args.iolog) != 1:
                print("error: single モードは --iolog 1個のみ", file=sys.stderr)
                sys.exit(2)
            rows, _masked = m2s.parse_iolog(args.iolog[0])
            write_single_report(rows, args.label[0], out)
        else:
            all_rows: dict[str, list[Ev]] = {}
            for label, p in zip(args.label, args.iolog):
                rows, _masked = m2s.parse_iolog(p)
                all_rows[label] = rows
            write_cross_report(all_rows, out)
    print(f"written: {args.out}")


if __name__ == "__main__":
    main()

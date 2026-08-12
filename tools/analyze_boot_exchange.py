#!/usr/bin/env python3
"""PC88Behavior: 起動時（バルク転送に入るまで）のmain⇔sub要求/応答構造を
解析する（M6l想定）。

`docs/notes/m6-main-to-sub.md`（1.10〜1.13節）で確定した SEND/RECV
プリミティブ、`docs/notes/m6j-bulk-trigger.md`（1.14節）で確定した
バルク転送の起点、`docs/notes/m6-fdc-ports.md`（1.7〜1.9節）で確定した
`$FA`/`$FB` の意味論——これら3本の解析はいずれも「main側だけ」「sub側
だけ」のどちらか一方の視点にとどまっていた。本スクリプトは共通クロック
付きログ（`measurements/m6g-d0-boot-run{1,2}`）だけが持つ強み、すなわち
**main と sub を同じ時間軸に置ける**性質を使い、起動シーケンスの
main→sub SEND/RECV往復と、sub側のFDCポーリング（`$FA`/`$FB`）を
時間窓で突き合わせる。

やっていることは以下の3つで、いずれも「measurements/*.iolog.txt を
読んで、既知のPC分類でイベントを束ね、時間窓で件数を数える」という
既存の解析器と同じ種類の操作である。ROMの内容・逆アセンブルには
一切触れていない。パーサ・SEND/RECV分類は`tools/analyze_main_to_sub.py`
を import して再利用し、二重実装しない。

1. `group_runs`: `tools/analyze_main_to_sub.py` の `classify_transactions`
   が返す main 側イベント列を、種別（SEND/RECV/BULK_RECV）が変わる
   境界で連続run に束ねる。バルク転送本体（最初に1000件を超える
   BULK_RECV run）の直前までを「起動シーケンス」の対象区間とする。
2. `sub_side_counterparts`: 各runの時間窓で、sub側の対応イベント
   （main SENDに対する sub `IN $FC`、main RECVに対する sub `OUT $FD`）
   の件数をpc別に集計する。
3. `fdc_window_counts`: 各run（SEND run + 直後のRECV/BULK_RECV run）の
   時間窓で、sub の `$FA`/`$FB` アクセス件数を数える。「応答の直前に
   sub が実際にFDCを叩いているか」「叩いている量が応答バイト数と
   相関するか」を、値を一切見ずに件数だけで確認する。

再実行方法:
    python3 tools/analyze_boot_exchange.py \
        --iolog measurements/m6g-d0-boot-run1.iolog.txt.gz \
        --label m6g-run1 \
        --out measurements/m6l-boot-exchange-run1.txt

    python3 tools/analyze_boot_exchange.py \
        --iolog measurements/m6g-d0-boot-run2.iolog.txt.gz \
        --label m6g-run2 \
        --out measurements/m6l-boot-exchange-run2.txt

決定論性は `diff measurements/m6l-boot-exchange-run{1,2}.txt` で確認する
（ファイル名を出す行以外が一致するはず）。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# analyze_main_to_sub.py のパーサ・SEND/RECV分類を共有する（二重実装しない）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402

Ev = m2s.Ev

# バルク転送本体とみなす最小件数（1.14節: 定常ループは5632件、境界用runは
# 最大でも数件）。この閾値未満のBULK_RECV run（起動シーケンス中に混在する
# 短いバースト境界run）は起動シーケンスの対象に含める。
BULK_RUN_MIN = 1000


@dataclass
class Run:
    kind: str  # "SEND" / "RECV" / "BULK_RECV"
    events: list[Ev]

    @property
    def lo(self) -> int:
        return self.events[0].clock

    @property
    def hi(self) -> int:
        return self.events[-1].clock

    @property
    def pcs(self) -> list[str]:
        seen: list[str] = []
        for e in self.events:
            if e.pc not in seen:
                seen.append(e.pc)
        return seen


def group_runs(tx: list[Ev]) -> list[Run]:
    """main側 SEND/RECV/BULK_RECV イベント列を、種別が変わる境界で
    連続runに束ねる。"""
    runs: list[Run] = []
    cur_kind: str | None = None
    cur: list[Ev] = []
    for e in tx:
        k = m2s.tx_kind(e)
        if k != cur_kind:
            if cur:
                runs.append(Run(cur_kind, cur))  # type: ignore[arg-type]
            cur_kind = k
            cur = [e]
        else:
            cur.append(e)
    if cur:
        runs.append(Run(cur_kind, cur))  # type: ignore[arg-type]
    return runs


def split_boot_and_bulk(runs: list[Run]) -> tuple[list[Run], Run | None]:
    """起動シーケンス区間（バルク転送本体の直前まで）と、バルク転送本体
    run を分離する。バルク転送本体が見つからない場合は (runs全部, None)。"""
    for i, r in enumerate(runs):
        if r.kind == "BULK_RECV" and len(r.events) >= BULK_RUN_MIN:
            return runs[:i], r
    return runs, None


def pair_rounds(boot_runs: list[Run]) -> list[tuple[Run, Run]]:
    """SEND run の直後に続く RECV/BULK_RECV run を1組の「ラウンド」として
    対にする（起動シーケンス中は SEND run の直後が必ず RECV run である
    ことを前提にする。前提が崩れたら例外を投げず、対応しないSEND runは
    捨てて警告用に呼び出し側へ知らせる——本関数はraiseしない）。"""
    rounds: list[tuple[Run, Run]] = []
    i = 0
    while i < len(boot_runs) - 1:
        a, b = boot_runs[i], boot_runs[i + 1]
        if a.kind == "SEND" and b.kind in ("RECV", "BULK_RECV"):
            rounds.append((a, b))
            i += 2
        else:
            i += 1
    return rounds


# --- sub側対応イベントの集計 ---------------------------------------------
#
# ポートの向き（`docs/notes/m6l-boot-exchange.md` で確定・裏取り）:
#   main OUT $FD (TX) は sub IN $FC (RX) で受け取られる
#   main IN  $FC (RX) は sub OUT $FD (TX) から送られる
# つまり main視点の $FD=送信/$FC=受信 に対し、sub視点は $FC=受信/$FD=送信
# であり、両者は「自分の送信は$FD、自分の受信は$FCという、CPUごとに
# 自分の視点で対称なポート番号を使う」設計である（同じ$FD/$FCという
# 番号を両CPUが自分視点でTX/RXに使っているだけで、共有ラッチが2本
# あると考えれば矛盾しない）。

def sub_rx_counts(rows: list[Ev], lo: int, hi: int) -> dict:
    events = [e for e in rows if e.cpu == "sub" and e.kind == "IN" and e.port == "00FC" and lo <= e.clock <= hi]
    return {"n": len(events), "pcs": _pc_hist(events)}


def sub_tx_counts(rows: list[Ev], lo: int, hi: int) -> dict:
    events = [e for e in rows if e.cpu == "sub" and e.kind == "OUT" and e.port == "00FD" and lo <= e.clock <= hi]
    return {"n": len(events), "pcs": _pc_hist(events)}


def _pc_hist(events: list[Ev]) -> dict[str, int]:
    hist: dict[str, int] = {}
    for e in events:
        hist[e.pc] = hist.get(e.pc, 0) + 1
    return hist


# --- FDC ($FA/$FB) 相関 ---------------------------------------------------

def fdc_window_counts(rows: list[Ev], lo: int, hi: int) -> tuple[int, int]:
    """[lo,hi]区間の sub $FA / $FB アクセス件数（IN/OUT問わず）。"""
    fa = sum(1 for e in rows if e.cpu == "sub" and e.port == "00FA" and lo <= e.clock <= hi)
    fb = sum(1 for e in rows if e.cpu == "sub" and e.port == "00FB" and lo <= e.clock <= hi)
    return fa, fb


def fdc_total(rows: list[Ev], lo: int, hi: int) -> tuple[int, int]:
    return fdc_window_counts(rows, lo, hi)


# --- レポート -------------------------------------------------------------

def response_kind(run: Run) -> str:
    n = len(run.events)
    if run.kind == "BULK_RECV":
        return f"BULK({n})"
    if n == 1:
        return "1byte"
    return f"{n}byte"


def write_report(rows: list[Ev], label: str, out) -> None:
    tx = m2s.classify_transactions(rows)
    runs = group_runs(tx)
    boot_runs, bulk_run = split_boot_and_bulk(runs)
    # バルク転送本体そのものも「ラウンド」として数える(SENDでバルクの
    # トリガーを送り、応答としてバルクを受け取る、という意味では他の
    # ラウンドと同型)。pair_roundsにはbulk_runを含めた列を渡す。
    pairing_input = boot_runs + ([bulk_run] if bulk_run is not None else [])
    rounds = pair_rounds(pairing_input)

    print(f"# 起動時main<->sub往復構造解析: {label}", file=out)
    print(file=out)
    print(f"バルク転送本体の直前までのrun数: {len(boot_runs)} / ラウンド数(バルク含む): {len(rounds)}", file=out)
    if bulk_run is not None:
        print(f"バルク転送本体: {len(bulk_run.events)}件 clock={bulk_run.lo}-{bulk_run.hi}", file=out)
    else:
        print("バルク転送本体: 見つからなかった(BULK_RUN_MIN未満)", file=out)
    print(file=out)

    print("## ラウンド別: SEND件数 -> RECV/BULK件数 と sub側FDC($FA/$FB)アクセス件数", file=out)
    print(f"{'#':>3} {'SENDlen':>7} {'send_clock':>18} {'応答':>10} {'応答clock':>18} {'subFA':>6} {'subFB':>6}", file=out)
    fdc_by_response_kind: dict[str, list[tuple[int, int]]] = {}
    for i, (send_run, resp_run) in enumerate(rounds):
        fa, fb = fdc_window_counts(rows, send_run.lo, resp_run.hi)
        rk = response_kind(resp_run)
        fdc_by_response_kind.setdefault(rk, []).append((fa, fb))
        print(
            f"{i:>3} {len(send_run.events):>7} "
            f"{send_run.lo:>8}-{send_run.hi:<8} {rk:>10} "
            f"{resp_run.lo:>8}-{resp_run.hi:<8} {fa:>6} {fb:>6}",
            file=out,
        )
    print(file=out)

    print("## 応答種別ごとのFDCアクセス件数(値ではなく件数のみ)", file=out)
    for rk, pairs in fdc_by_response_kind.items():
        fas = [p[0] for p in pairs]
        fbs = [p[1] for p in pairs]
        print(f"  応答={rk}: n={len(pairs)} FA={fas} FB={fbs}", file=out)
    print(file=out)

    # 起動シーケンス全体でのFDCアクセスの分布確認(ラウンド外に漏れが無いか)
    if rounds:
        seq_lo, seq_hi = rounds[0][0].lo, rounds[-1][1].hi
        total_fa, total_fb = fdc_window_counts(rows, seq_lo, seq_hi)
        sum_fa = sum(fa for fa, _ in (p for pairs in fdc_by_response_kind.values() for p in pairs))
        sum_fb = sum(fb for _, fb in (p for pairs in fdc_by_response_kind.values() for p in pairs))
        print("## FDCアクセスの集中度確認(ラウンドの外で発生していないか)", file=out)
        print(f"  起動シーケンス全体(clock {seq_lo}-{seq_hi}): FA={total_fa} FB={total_fb}", file=out)
        print(f"  各ラウンドの時間窓の合計:                 FA={sum_fa} FB={sum_fb}", file=out)
        print(
            "  (一致すればラウンドの時間窓の外でFDCアクセスが起きていない"
            "ことを意味する。一致しなければ、ラウンド境界の外にも"
            "FDCアクセスがあることになる)",
            file=out,
        )
        print(file=out)

    print("## sub側対応イベント件数(main SEND/RECVの相手側)", file=out)
    if rounds:
        seq_lo, seq_hi = rounds[0][0].lo, rounds[-1][1].hi
        rx = sub_rx_counts(rows, seq_lo, seq_hi)
        tx_ = sub_tx_counts(rows, seq_lo, seq_hi)
        main_send_n = sum(len(a.events) for a, _ in rounds)
        main_recv_n = sum(len(b.events) for _, b in rounds)
        print(f"  main OUT $FD (SEND) 件数: {main_send_n}", file=out)
        print(f"  sub  IN  $FC (RX)   件数: {rx['n']}  pc別={rx['pcs']}", file=out)
        print(f"  main IN  $FC (RECV) 件数: {main_recv_n}", file=out)
        print(f"  sub  OUT $FD (TX)   件数: {tx_['n']}  pc別={tx_['pcs']}", file=out)
        if main_send_n != rx["n"]:
            print(
                f"  注記: main SEND件数({main_send_n})とsub RX件数({rx['n']})が"
                f"一致しない(差={main_send_n - rx['n']})。全SENDバイトに"
                f"sub側の明示的な IN $FC が対応するわけではない可能性がある"
                f"（3節参照）。",
                file=out,
            )
        if main_recv_n != tx_["n"]:
            print(
                f"  注記: main RECV件数({main_recv_n})とsub TX件数({tx_['n']})が"
                f"一致しない(差={main_recv_n - tx_['n']})。",
                file=out,
            )
    print(file=out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    rows, masked = m2s.parse_iolog(args.iolog)
    masked_total = sum(masked.values())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        if masked_total:
            print(
                f"# 注記: 入力ログに伏せ字(値秘匿)イベントが{masked_total}件含まれる。"
                f"本解析は値を一切使わない(件数・PC・clockのみ)ため影響しない。",
                file=out,
            )
            print(file=out)
        write_report(rows, args.label, out)


if __name__ == "__main__":
    main()

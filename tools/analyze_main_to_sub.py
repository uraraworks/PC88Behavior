#!/usr/bin/env python3
"""PC88Behavior: メイン→サブ方向の要求(コマンド)プロトコル解析。

`docs/notes/m6-sub-proto.md`(第1〜4版)・`docs/notes/m6-fdc-ports.md` で
$FC/$FD がデータ経路であること、$FA/$FB がサブ内部のFDCポーリングである
ことまでは確定した。本スクリプトはその先、**mainが実際にどういう手順で
サブに「読んでくれ」と頼んでいるか**を、iolog に記録された PC(直前の
リターンアドレス)を手がかりに、mainのコード上のサブルーチン境界を
再構成することで調べる。

やっていることは以下の3つのみで、いずれも「measurements/*.iolog.txt を
読んで統計を取る」という既存の解析器と同じ種類の操作である。ROMの内容や
命令列そのものは一切読んでいない——読んでいるのは「同じPCに何度も
戻ってくる」という事実(=そこにサブルーチンの呼び出し境界がある)だけ。

1. `classify_transactions`: main の OUT $FD ("send 1byte") / IN $FC
   ("recv 1byte") イベントを、そのイベントを記録した直後PCでグループ化する。
   同じ処理を行うたびに同じPCに戻ってくるという事実だけから、
   「1バイト送信」「1バイト受信」「高速バルク転送」という3種の
   トランザクション型が浮かび上がる(PCクラスタそのものは各条件の
   実測から機械的に決まる。決め打ちしていない)。
2. `reconstruct_requests`: 連続する SEND イベント列を「1つの要求」として
   束ね、要求直後に続く RECV/BULK イベント列を「応答」として対応付ける。
3. `wait_loop_transitions`: main の IN $FE ポーリングループ(PCごとに
   グループ化)で、ループを抜ける直前直後の値の組を集計する。
   どのビット/値遷移が「相手の準備完了」を意味するかを、
   複数条件・多数サンプルでの再現性から判定する。

再実行方法:
    python3 tools/analyze_main_to_sub.py \
        --iolog measurements/m6c-sub-d0-boot.iolog.txt \
        --label d0-boot \
        --out measurements/m6i-main-to-sub-d0-boot.txt

    python3 tools/analyze_main_to_sub.py cross \
        --iolog measurements/m6c-sub-d0-boot.iolog.txt measurements/m6c-sub-d1-files.iolog.txt \
                measurements/m6c-sub-d2-save.iolog.txt measurements/m6c-sub-d5-seqfile.iolog.txt \
        --label d0-boot d1-files d2-save d5-seqfile \
        --out measurements/m6i-main-to-sub-cross.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+"
    r"([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*$"
)


@dataclass
class Ev:
    seq: int
    clock: int
    frame: int
    cpu: str
    kind: str
    port: str
    value: int
    pc: str


def parse_iolog(path: Path) -> list[Ev]:
    rows: list[Ev] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            m = ROW_RE.match(line)
            if not m:
                continue
            seq, clock, frame, cpu, kind, port, value, pc = m.groups()
            rows.append(Ev(int(seq), int(clock), int(frame), cpu, kind,
                            port.upper(), int(value, 16), pc.upper()))
    rows.sort(key=lambda e: e.clock)
    return rows


# --- 1. トランザクション分類 -------------------------------------------
#
# PCクラスタは各条件の実測(measurements/m6c-sub-*)から機械的に決まった。
# main OUT $FD の直後PCは {37F4, 3811} の2種類、main IN $FC の直後PCは
# {3863, 3880}(ハンドシェイク経由の1バイト受信/連続受信) と
# {C269}(ハンドシェイクを介さない高速バルク転送) の2群に分かれる。
# 分割自体は「同じ処理は同じPCに戻る」という事実の集計であり、
# 意味の割り当て(SEND/RECV/BULKという名前)はこちらの解釈である。
SEND_PCS = {"37F4", "3811"}
RECV_HANDSHAKE_PCS = {"3863", "3880"}
RECV_BULK_PCS = {"C269"}


def classify_transactions(rows: list[Ev]) -> list[Ev]:
    out = []
    for e in rows:
        if e.cpu != "main":
            continue
        if e.kind == "OUT" and e.port == "00FD" and e.pc in SEND_PCS:
            out.append(e)
        elif e.kind == "IN" and e.port == "00FC" and (
            e.pc in RECV_HANDSHAKE_PCS or e.pc in RECV_BULK_PCS
        ):
            out.append(e)
    return out


def tx_kind(e: Ev) -> str:
    if e.kind == "OUT":
        return "SEND"
    if e.pc in RECV_BULK_PCS:
        return "BULK_RECV"
    return "RECV"


# --- 2. 要求(リクエスト)の再構成 ----------------------------------------
#
# 観測: main OUT $FD の直後PCは、同じ送信ループ内の「まだ続きがある」
# バイトでは 37F4、そのループを終えて次の処理へ抜ける最後のバイトでは
# 3811 になる(全条件で例外なく、3811は単独でしか出現しない=長さ1の
# 「run」しか無いことを本解析で確認する)。つまり **3811 は
# 「このバイトでSEND列が終わる」ことを示す境界マーカーとして
# 機械的に使える**。これを要求の区切りに使う。


@dataclass
class Request:
    trigger: Ev  # 応答を引き起こしたSENDイベント本体
    preceding: list[Ev]  # 直前に連続していたSEND列(triggerを含む。参考表示用の近似)
    response: list[Ev]  # trigger直後、次のSENDまでに続くRECV/BULK_RECV列


def reconstruct_requests(tx: list[Ev], gap_threshold: int = 200) -> list[Request]:
    """SENDイベントを、直後に続く応答(RECV/BULK_RECV列, 次のSENDまで)と
    1:1で対応付ける。

    「複数バイトの1コマンド」への合成(header)は行わない —— 観測上、
    1バイトのSENDだけでも直後に応答(RECVやBULK_RECV)が続く場合があり
    (例: 単発のステータス確認)、逆に複数バイトのSENDが応答を伴わずに
    続くこともある(パラメータの積み上げ)。この2つを機械的に区別する
    確実な境界情報がログには無いため、**応答が実際に観測された
    SENDイベントだけ**を「要求」として確定させる(response空の
    SENDは要求として数えない)。

    `preceding` は表示用の近似情報として、triggerイベントの直前で
    (a)応答(RECV/BULK_RECV)を挟まず、かつ(b) clock差が gap_threshold
    以内で連続しているSEND列を遡って集めたもの。これは「複数バイトの
    コマンドらしき塊」を目視できるようにするための**近似**であり、
    厳密な境界の確定ではない(該当節に明記する)。
    """
    requests: list[Request] = []
    pending_send_run: list[Ev] = []
    i = 0
    n = len(tx)
    while i < n:
        e = tx[i]
        if tx_kind(e) == "SEND":
            if pending_send_run and e.clock - pending_send_run[-1].clock <= gap_threshold:
                pending_send_run.append(e)
            else:
                pending_send_run = [e]
            # 直後(次のSENDまで)に応答が続くか見る
            resp = []
            j = i + 1
            while j < n and tx_kind(tx[j]) != "SEND":
                resp.append(tx[j])
                j += 1
            if resp:
                requests.append(Request(e, list(pending_send_run), resp))
                pending_send_run = []  # 応答が確定したら塊をリセット
            i = j if j > i + 1 else i + 1
        else:
            i += 1
    return requests


def check_3811_is_singleton(tx: list[Ev]) -> tuple[int, int]:
    """pc=3811 のSENDが常に単独(直前直後がpc=3811でない)かを確認する。

    戻り値: (単独だった件数, 連続していた件数)
    """
    solo = 0
    consecutive = 0
    prev_was_3811 = False
    for e in tx:
        if tx_kind(e) != "SEND":
            prev_was_3811 = False
            continue
        if e.pc == "3811":
            if prev_was_3811:
                consecutive += 1
            else:
                solo += 1
            prev_was_3811 = True
        else:
            prev_was_3811 = False
    return solo, consecutive


# --- 3. $FE 待ちループの遷移 --------------------------------------------

WAIT_LOOP_PCS = {
    "37DC": "SEND前(相手の受信準備待ち)",
    "37FF": "SEND後(相手の受理確認待ち)",
    "3853": "RECV前(相手のデータ準備待ち)",
    "386F": "RECV後(相手の受理解除待ち)",
}


def wait_loop_transitions(rows: list[Ev]) -> dict[str, dict]:
    by_pc: dict[str, list[int]] = {}
    for e in rows:
        if e.cpu == "main" and e.kind == "IN" and e.port == "00FE" and e.pc in WAIT_LOOP_PCS:
            by_pc.setdefault(e.pc, []).append(e.value)
    result = {}
    for pc, vals in by_pc.items():
        transitions: dict[tuple[int, int], int] = {}
        prev = None
        for v in vals:
            if prev is not None and v != prev:
                transitions[(prev, v)] = transitions.get((prev, v), 0) + 1
            prev = v
        result[pc] = {"n": len(vals), "transitions": transitions}
    return result


# --- 4. モード比率(ハンドシェイク型 vs バルク型) -------------------------

def mode_counts(tx: list[Ev]) -> dict[str, int]:
    counts = {"SEND": 0, "RECV": 0, "BULK_RECV": 0}
    for e in tx:
        counts[tx_kind(e)] += 1
    return counts


def response_burst_lengths(requests: list[Request]) -> list[int]:
    return [len(r.response) for r in requests if r.response]


def run_lengths(tx: list[Ev], target_kinds: set[str]) -> list[int]:
    """target_kinds(例 {"SEND"} や {"RECV","BULK_RECV"})に属するイベントが
    連続する長さ(他種イベントに一度も中断されない区間の長さ)のリストを返す。

    発見の経緯: 当初「main OUT $FD の直後PCは 37F4(継続) / 3811(最後の1バイト)の
    2種類で、3811は単独でしか出現しない」という仮説を立てたが(check_3811_is_singleton)、
    これは短い(応答が単発の)要求にしか当てはまらなかった。d5-seqfile条件で
    実際に多バイトの書き込みバースト(SEND列が267件連続する区間、8箇所)を
    確認したところ、そこでは 37F4 と 3811 が**交互に**現れていた
    (`docs/notes/m6-main-to-sub.md` 参照)。つまり 3811 は「列の最後」を
    示す境界マーカーではなく、RECV側の 3863/3880 交互パターンと対になる
    「送信ループのもう一方の折返しエントリ」だったと解釈し直す方が
    観測と整合する。この関数はその再解釈を条件横断で再現するために追加した。
    """
    runs = []
    cur = 0
    for e in tx:
        if tx_kind(e) in target_kinds:
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    return runs


# --- レポート出力 ---------------------------------------------------------

def fmt_header(h: list[Ev]) -> str:
    return " ".join(f"{e.value:02X}" for e in h)


def write_single_report(rows: list[Ev], label: str, out) -> None:
    tx = classify_transactions(rows)
    solo, consecutive = check_3811_is_singleton(tx)
    requests = reconstruct_requests(tx)
    counts = mode_counts(tx)
    burst_lens = response_burst_lengths(requests)

    print(f"# main→サブ 要求プロトコル解析: {label}", file=out)
    print(file=out)
    print("## トランザクション件数(PCクラスタ別)", file=out)
    print(f"  SEND(main OUT $FD, ハンドシェイク型): {counts['SEND']}", file=out)
    print(f"  RECV(main IN $FC, ハンドシェイク型): {counts['RECV']}", file=out)
    print(f"  BULK_RECV(main IN $FC, 高速バルク型): {counts['BULK_RECV']}", file=out)
    print(file=out)

    print("## pc=3811 (SEND終端マーカー仮説の検証) の単独性(同一pcの連続のみ)", file=out)
    print(f"  単独出現: {solo}件 / 同一pc(3811)が連続: {consecutive}件", file=out)
    print(
        "  (これは「3811の直後にまた3811が来るか」だけを見た指標であり、"
        "下のSEND連続長ヒストグラムで分かるとおり、実際には37F4と3811が"
        "交互に現れる長い書き込みバーストが存在する。単独性だけでは"
        "「3811=列の最後」という仮説は反証も証明もできない。詳細は"
        "docs/notes/m6-main-to-sub.md 参照)",
        file=out,
    )
    print(file=out)

    from collections import Counter
    send_runs = Counter(run_lengths(tx, {"SEND"}))
    recv_runs = Counter(run_lengths(tx, {"RECV", "BULK_RECV"}))
    print("## SEND連続長ヒストグラム(他イベントに中断されない区間の長さ)", file=out)
    for length, n in sorted(send_runs.items(), key=lambda kv: -kv[0])[:10]:
        print(f"  長さ{length}: {n}区間", file=out)
    print("## RECV/BULK_RECV連続長ヒストグラム", file=out)
    for length, n in sorted(recv_runs.items(), key=lambda kv: -kv[0])[:10]:
        print(f"  長さ{length}: {n}区間", file=out)
    print(file=out)

    print(f"## 再構成した要求(request)件数: {len(requests)}", file=out)
    if requests:
        print("### 先頭5件のヘッダ(SEND列, 16進バイト列)と応答長", file=out)
        for r in requests[:5]:
            print(
                f"  clock={r.trigger.clock:>8} frame={r.trigger.frame:>5} "
                f"preceding=[{fmt_header(r.preceding)}] response_len={len(r.response)}",
                file=out,
            )
        print("### 末尾5件", file=out)
        for r in requests[-5:]:
            print(
                f"  clock={r.trigger.clock:>8} frame={r.trigger.frame:>5} "
                f"preceding=[{fmt_header(r.preceding)}] response_len={len(r.response)}",
                file=out,
            )
    print(file=out)

    if burst_lens:
        from collections import Counter
        c = Counter(burst_lens)
        print("## 応答バイト数の分布(0件の応答は除く)", file=out)
        for length, n in sorted(c.items(), key=lambda kv: -kv[1])[:10]:
            print(f"  {length}バイト: {n}件", file=out)
        print(file=out)

    print("## $FE 待ちループの値遷移(main IN $FE, PC別)", file=out)
    for pc, meaning in WAIT_LOOP_PCS.items():
        info = wait_loop_transitions(rows).get(pc)
        if not info:
            print(f"  pc={pc} ({meaning}): 出現なし", file=out)
            continue
        trs = sorted(info["transitions"].items(), key=lambda kv: -kv[1])
        trs_str = ", ".join(f"{a:02X}->{b:02X}({n})" for (a, b), n in trs[:6])
        print(f"  pc={pc} ({meaning}): n={info['n']} 遷移={trs_str}", file=out)
    print(file=out)


def write_cross_report(all_rows: dict[str, list[Ev]], out) -> None:
    print("# 条件横断比較: main→サブ 要求プロトコル", file=out)
    print(file=out)

    print("## SEND連続長267(256バイト書き込みバースト相当)の出現回数", file=out)
    for label, rows in all_rows.items():
        tx = classify_transactions(rows)
        from collections import Counter
        c = Counter(run_lengths(tx, {"SEND"}))
        print(f"  {label}: 267長={c.get(267, 0)}回 (SEND総数={sum(c.values()) and sum(l*n for l,n in c.items())})", file=out)
    print(file=out)

    print("## 応答バイト数の最頻値(条件別)", file=out)
    for label, rows in all_rows.items():
        tx = classify_transactions(rows)
        requests = reconstruct_requests(tx)
        lens = response_burst_lengths(requests)
        if not lens:
            print(f"  {label}: 応答付き要求なし", file=out)
            continue
        from collections import Counter
        c = Counter(lens)
        top = c.most_common(3)
        print(f"  {label}: 要求数={len(requests)} 応答長トップ3={top}", file=out)
    print(file=out)

    print("## $FE 待ちループ遷移の条件横断一致(同じ遷移が全条件で出るか)", file=out)
    for pc, meaning in WAIT_LOOP_PCS.items():
        per_cond = {}
        for label, rows in all_rows.items():
            info = wait_loop_transitions(rows).get(pc)
            if info:
                per_cond[label] = set(info["transitions"].keys())
        if not per_cond:
            continue
        common = set.intersection(*per_cond.values()) if per_cond else set()
        print(f"  pc={pc} ({meaning}):", file=out)
        for label, trs in per_cond.items():
            print(f"    {label}: {sorted(trs)}", file=out)
        print(f"    全条件共通の遷移: {sorted(common)}", file=out)
    print(file=out)

    print("## 先頭の要求ヘッダ(diskA起動シーケンス, 条件間で一致するか)", file=out)
    for label, rows in all_rows.items():
        tx = classify_transactions(rows)
        requests = reconstruct_requests(tx)
        headers = [fmt_header(r.preceding) for r in requests[:3]]
        print(f"  {label}: {headers}", file=out)
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
            rows = parse_iolog(args.iolog[0])
            write_single_report(rows, args.label[0], out)
        else:
            all_rows = {label: parse_iolog(p) for label, p in zip(args.label, args.iolog)}
            write_cross_report(all_rows, out)


if __name__ == "__main__":
    main()

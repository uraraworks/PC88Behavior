#!/usr/bin/env python3
"""PC88Behavior: 公式subの起動時FDC初期化シーケンス（1.16節手順8の中身）を、
値を一切見ずに構造（$FBの書き/読みバイト数の並び）だけで解析する (M6q)。

背景: 混成ROM実走診断(last.txt, 2026-08-12 16:56版)で、sub側の構造的一致
プレフィックスが分岐点28で切れることが分かった。基準(公式)側は「結果
フェーズ直後にTC三つ組み(1.21節)」という構造が来るが、自作subは
FDC_SPECIFY(結果フェーズを持たないコマンド)しか呼んでおらず、この構造
自体が起きない。1.16節手順8「FDC初期化」は中身が未確定のまま残っていた。

本稿はこれを、既存ログの再解析だけで具体化する。

値は一切見ない。$FA/$FB/$FC/$FD の値はもちろん、$F7/$F8/$FE/$FF の値も
本解析では使わない(区間の境界検出にport/kind/pcの構造だけを使う)。

方法:
  1. sub イベント列から、1.16節手順6〜7 (OUT $F8 の2連続書き込み。値は
     見ないが「BOOT_HANDSHAKE後、最初のFDC/FE系アクセスより前に来る
     $F8への2連続OUT」という構造で機械的に特定できる) の直後から、
     次に $FE または $FF へのアクセスが現れるまでの区間を
     「起動時FDC初期化区間」として切り出す。
  2. その区間内の $FB アクセスを、kind(IN/OUT)が変わるまでを1つの
     run として連続長を数える(間に挟まる $FA ポーリングは無視する。
     m6pで確立済みの手法と同じ)。
  3. runの並び (OUT run長, IN run長, OUT run長, ...) を
     「1コマンドぶんの (書きバイト数, 読みバイト数)」の列とみなし、
     公開されているμPD765/8272データシートのコマンド書式
     (コマンドフェーズのバイト数・結果フェーズのバイト数)と突き合わせて
     候補を絞る。一意に決まらないものは候補を併記する(推測で1つに
     決めない)。
  4. 区間内でのTC三つ組み(1.21節、$F7/$F8のみで検出可能)の位置も
     runの並びに対して記録する。

再実行方法:
    python3 tools/analyze_boot_fdc_sequence.py cross \
        --iolog d0-boot    measurements/m6c-sub-d0-boot.iolog.txt.gz \
        --iolog d1-files   measurements/m6c-sub-d1-files.iolog.txt.gz \
        --iolog d2-save    measurements/m6c-sub-d2-save.iolog.txt.gz \
        --iolog d5-seqfile measurements/m6c-sub-d5-seqfile.iolog.txt.gz \
        --out measurements/m6q-boot-fdc-sequence-cross.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_fdc_ports import IoEvent, parse_iolog  # noqa: E402


# μPD765/8272 系データシートの公開仕様(ハードウェアの事実。CLAUDE.mdの
# 「(a) ハードウェアの事実」に該当し参照可)。コマンドフェーズの総バイト数
# (コマンドバイト自身を含む)と、結果フェーズのバイト数(実行フェーズで
# データポートを使うコマンドは実行フェーズのバイト数を別記)。
# 実行フェーズがデータ転送を伴うコマンド(READ系/WRITE系/FORMAT)は、
# 本解析ではIN runまたはOUT runの中に実行フェーズが結果フェーズと連続して
# 現れる(データポートと結果ポートが同じ$FBのため、run分割では区別できない)。
UPD765_COMMANDS = {
    # name: (cmd_phase_bytes, result_phase_bytes, exec_phase_dir_or_None)
    #   exec_phase_dir: "read" (実行フェーズがIN, 例: READ系),
    #                    "write" (実行フェーズがOUT, 例: WRITE系/FORMAT),
    #                    None (実行フェーズなし)
    "SPECIFY":                 (3, 0, None),
    "RECALIBRATE":              (2, 0, None),
    "SEEK":                     (3, 0, None),
    "SENSE INTERRUPT STATUS":   (1, 2, None),   # 保留割り込みが無い場合は結果1バイト(仕様書1.21節注記と同型の可変)
    "SENSE INTERRUPT STATUS(inv)": (1, 1, None),
    "SENSE DRIVE STATUS":       (2, 1, None),
    "READ ID":                  (2, 7, None),
    "READ DATA(1sec)":          (9, 7, "read"),   # exec 256 + result 7 = IN run 263
    "READ DELETED DATA(1sec)":  (9, 7, "read"),
    "READ A TRACK(1sec)":       (9, 7, "read"),
    "WRITE DATA(1sec)":         (9, 7, "write"),  # exec(write)は別run、result(read)=7
    "WRITE DELETED DATA(1sec)": (9, 7, "write"),
    "FORMAT A TRACK":           (6, 7, "write"),
}


def find_boot_init_window(sub_events: list[IoEvent]) -> tuple[int, int] | None:
    """1.16節手順6〜7 (OUT $F8 の2連続) の直後から、次の $FE/$FF アクセス
    (境界: FDC初期化区間の終わり=定常ハンドシェイクへの復帰)までの
    半開区間 [start, end) をイベントindexで返す。値は見ない。
    """
    f8_out_idx = [i for i, e in enumerate(sub_events)
                  if e.port == "00F8" and e.kind == "OUT"]
    # 手順6・7は連続する2件で、直前に$FA/$FBアクセスが無い(FDC初期化はまだ
    # 始まっていない)という構造で特定する。
    for i in range(len(f8_out_idx) - 1):
        a, b = f8_out_idx[i], f8_out_idx[i + 1]
        if b != a + 1:
            continue
        # a より前に $FA/$FB アクセスが1件も無いこと(起動直後である証拠)
        if any(e.port in ("00FA", "00FB") for e in sub_events[:a]):
            continue
        start = b + 1
        end = len(sub_events)
        for j in range(start, len(sub_events)):
            if sub_events[j].port in ("00FE", "00FF"):
                end = j
                break
        return start, end
    return None


def segment_runs(window: list[IoEvent]) -> list[dict]:
    """$FBアクセスをkind別のrunに分割する(間の$FA/$F7/$F8は無視して
    連続とみなす。m6pの手法と同じ)。戻り値は
    [{"kind":..,"len":..,"start_seq":..,"end_seq":..}, ...] で、
    加えて区間中の$F7/$F8イベント(TC三つ組み検出用)の位置も別リストで返す。
    """
    runs: list[dict] = []
    cur_kind: str | None = None
    cur_len = 0
    cur_start = None
    cur_end = None

    def flush():
        nonlocal cur_kind, cur_len, cur_start, cur_end
        if cur_kind is not None and cur_len > 0:
            runs.append({
                "kind": cur_kind, "len": cur_len,
                "start_seq": cur_start, "end_seq": cur_end,
            })
        cur_kind = None
        cur_len = 0
        cur_start = None
        cur_end = None

    for e in window:
        if e.port == "00FB":
            if e.kind == cur_kind:
                cur_len += 1
                cur_end = e.seq
            else:
                flush()
                cur_kind = e.kind
                cur_len = 1
                cur_start = e.seq
                cur_end = e.seq
        # $FA/$F7/$F8は run を区切らない(無視して連続とみなす)
    flush()
    return runs


def find_tc_triads(window: list[IoEvent]) -> list[int]:
    """区間内で $F7/$F8 の並びから TC三つ組み(1.21節: OUT $F8 -> OUT $F7
    -> IN $F8。値は見ずpc/port/kindの並びだけで検出)の出現seqを返す。
    """
    only = [e for e in window if e.port in ("00F7", "00F8")]
    out = []
    i = 0
    while i + 2 < len(only) + 1 and i + 2 <= len(only) - 1 + 1:
        if i + 2 >= len(only):
            break
        a, b, c = only[i], only[i + 1], only[i + 2]
        if (a.kind == "OUT" and a.port == "00F8"
                and b.kind == "OUT" and b.port == "00F7"
                and c.kind == "IN" and c.port == "00F8"):
            out.append(a.seq)
            i += 3
        else:
            i += 1
    return out


def candidates_for(write_len: int, read_len: int) -> list[str]:
    """(書きバイト数, 読みバイト数) から一意/複数のコマンド候補を返す。
    実行フェーズがreadのコマンドは result_phase_bytes を read_len に
    合算した値(N+7)で照合する。読みだけ・書きだけの単純一致も見る。
    """
    hits = []
    for name, (cmd_b, res_b, exec_dir) in UPD765_COMMANDS.items():
        if exec_dir == "read":
            # execバイト数Nは可変(セクタ数依存)。res_b(7)を差し引いた分が
            # データ部と解釈できるかだけを緩く許容する(N>=1のとき合致)。
            if write_len == cmd_b and read_len >= res_b and (read_len - res_b) >= 1:
                hits.append(f"{name}(N={read_len - res_b})")
            continue
        if exec_dir == "write":
            # 実行フェーズはOUT側runに現れる(このrunはread専用集計のため
            # 対象外。read_lenはresult_phaseのみと比較)
            if write_len >= cmd_b and read_len == res_b:
                hits.append(name)
            continue
        if write_len == cmd_b and read_len == res_b:
            hits.append(name)
    return hits


def report(label: str, sub_events: list[IoEvent]) -> str:
    lines = [f"### {label}", ""]
    win = find_boot_init_window(sub_events)
    if win is None:
        lines.append("起動時FDC初期化区間を特定できなかった(手順6-7の2連続OUT $F8が見つからない)")
        lines.append("")
        return "\n".join(lines)
    start, end = win
    window = sub_events[start:end]
    lines.append(f"区間: index[{start}:{end}) (event数={len(window)}), "
                 f"seq範囲=[{window[0].seq if window else '-'}, "
                 f"{window[-1].seq if window else '-'}]")
    lines.append("")

    runs = segment_runs(window)
    tc_seqs = set(find_tc_triads(window))

    lines.append("run列 (OUT=書き/コマンドフェーズ相当, IN=読み/結果or実行フェーズ相当):")
    for i, r in enumerate(runs):
        cand = ""
        if r["kind"] == "IN":
            # 直前がOUT runならペアとして候補照合
            if i > 0 and runs[i - 1]["kind"] == "OUT":
                w = runs[i - 1]["len"]
                rd = r["len"]
                hits = candidates_for(w, rd)
                cand = f"  <- (write={w},read={rd}) 候補: {hits if hits else '該当なし(未確定)'}"
        lines.append(f"  [{i}] {r['kind']} run 長={r['len']} "
                     f"seq=[{r['start_seq']},{r['end_seq']}]{cand}")
        # このrunの直後にTC三つ組みがあるかどうか(seq近傍で判定)
        following_tc = [s for s in tc_seqs if r["end_seq"] < s <= r["end_seq"] + 20]
        if following_tc:
            lines.append(f"      -> 直後にTC三つ組み(1.21節) seq={sorted(following_tc)}")
    lines.append("")
    lines.append(f"区間内TC三つ組み検出数: {len(tc_seqs)}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("cross")
    c.add_argument("--iolog", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    c.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.mode == "cross":
        out_lines = ["# M6q: 起動時FDC初期化シーケンスの構造解析 (cross)", ""]
        for label, path in args.iolog:
            events, masked = parse_iolog(Path(path))
            out_lines.append(report(label, events["sub"]))
        Path(args.out).write_text("\n".join(out_lines), encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

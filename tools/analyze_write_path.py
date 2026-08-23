#!/usr/bin/env python3
"""tools/analyze_write_path.py — 書き込み経路（SAVE）のFDCコマンド列を、
**値を出さずに構造だけ**取り出す（M6の書き込み経路、docs/PLAN.md）。

既存の `analyze_exchange14_read_rules.py` の `commands()` は、コマンドの
パラメータ列の後に来るのが**結果フェーズ（IN）**であることを前提にして
いるため、READ系は解析できるが **WRITE系（データフェーズがOUT）は
解析できない**（データ部の1バイト目を次のコマンド語と読み違える）。
ここでは方向の切り替わりでフェーズを判定する:

    コマンド語(OUT) → パラメータ n バイト(OUT)
      → [データフェーズ] 方向が変わるまでの連続バイト
      → [結果フェーズ] 反対方向の連続バイト

READ系はデータも結果もINなので両者を分離しない（この解析では不要）。
WRITE系はデータがOUT・結果がINなので自然に分離される。

**出力に値（バイトの中身）は一切含めない。** 出すのはコマンド語の
オペコード（μPD765/8272のデータシートに載る公開仕様の値）、各フェーズの
バイト数、発生順・件数だけである。公式ディスクの内容は扱わない。
"""
import argparse
import collections
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402

# μPD765/8272 の公開コマンド表（パラメータバイト数）
PARAM_COUNTS = {
    0x02: 8, 0x03: 2, 0x04: 1, 0x05: 8, 0x06: 8, 0x07: 1,
    0x08: 0, 0x09: 8, 0x0A: 1, 0x0C: 8, 0x0D: 5, 0x0F: 2,
    0x11: 8, 0x19: 8, 0x1D: 8,
}
NO_RESULT = {0x03, 0x07, 0x0F}
NAMES = {
    0x02: "READ TRACK", 0x03: "SPECIFY", 0x04: "SENSE DRIVE STATUS",
    0x05: "WRITE DATA", 0x06: "READ DATA", 0x07: "RECALIBRATE",
    0x08: "SENSE INTERRUPT STATUS", 0x09: "WRITE DELETED DATA",
    0x0A: "READ ID", 0x0C: "READ DELETED DATA", 0x0D: "FORMAT TRACK",
    0x0F: "SEEK", 0x11: "SCAN EQUAL", 0x19: "SCAN LOW OR EQUAL",
    0x1D: "SCAN HIGH OR EQUAL",
}
WRITE_OPCODES = {0x05, 0x09, 0x0D}   # データフェーズがOUTになるコマンド


class SafeError(Exception):
    pass


@dataclass
class Command:
    opcode: int
    nparam: int
    data_bytes: int      # データフェーズのバイト数（方向は下のdata_kind）
    data_kind: str | None
    result_bytes: int
    clock: int
    frame: int
    # データ部の値。**位置対応の突き合わせに内部でのみ使う**。
    # __repr__ にも標準出力にも出さない（クリーンルーム規律）。
    data_values: list[int] | None = None
    # パラメータ部の値。**位置対応の突き合わせに内部でのみ使う**。
    # __repr__ にも標準出力にも出さない（クリーンルーム規律）。
    param_values: list[int] | None = None
    # データ入力を含む連続IN列。READ系では末尾7バイトが結果相になる。
    # エラー経路の公開ステータス分類に内部でだけ使い、値は出力しない。
    input_values: list[int] | None = None

    def __repr__(self) -> str:      # 値を持たないが、事故防止に明示しておく
        return f"Command(op={self.opcode:#04x})"


def parse_commands(rows) -> list[Command]:
    fb = [e for e in rows if e.cpu == "sub" and e.port == "00FB"]
    out: list[Command] = []
    i = 0
    while i < len(fb):
        if fb[i].kind != "OUT":
            i += 1                      # コマンド語の前の孤立INは読み飛ばす
            continue
        first = fb[i]
        if first.value is None:
            raise SafeError("伏せ字ログではコマンド語を判定できない")
        opcode = first.value & 0x1F
        nparam = PARAM_COUNTS.get(opcode)
        if nparam is None:
            raise SafeError(f"公開FDCコマンド表に無いコマンド語 {opcode:#04x}")
        if i + nparam >= len(fb):
            break                        # ログ末尾で切れている
        params: list[int] = []
        for j in range(1, nparam + 1):
            if fb[i + j].kind != "OUT":
                raise SafeError("パラメータ列の途中で方向が変化した")
            params.append(fb[i + j].value)
        i += nparam + 1
        data_kind, data_bytes = None, 0
        data_values: list[int] = []
        if opcode not in NO_RESULT:
            if opcode in WRITE_OPCODES:
                data_kind = "OUT"
                while i < len(fb) and fb[i].kind == "OUT":
                    data_values.append(fb[i].value)
                    data_bytes += 1
                    i += 1
        result_bytes = 0
        input_values: list[int] = []
        while i < len(fb) and fb[i].kind == "IN":
            input_values.append(fb[i].value)
            result_bytes += 1
            i += 1
        out.append(Command(opcode, nparam, data_bytes, data_kind,
                           result_bytes, first.clock, first.frame,
                           data_values if data_kind == "OUT" else None,
                           params, input_values))
    return out


def data_position_map(rows, cmds) -> list[tuple[int, int, int, int]]:
    """各WRITE系コマンドについて、**直前にsubが受信した列（IN $FC）のどこに
    データ部が現れるか**を求める。戻り値は
    (frame, 受信列長, 一致開始位置, データ部の末尾から受信列の末尾までの余り)。

    値そのものは戻り値にも標準出力にも出さない（位置と件数だけ）。
    一致が見つからないものは一致開始位置 -1 で返す。
    """
    import bisect
    fc = [e for e in rows if e.cpu == "sub" and e.port == "00FC" and e.kind == "IN"]
    fcc = [e.clock for e in fc]
    out = []
    for c in cmds:
        if c.opcode not in WRITE_OPCODES or c.data_bytes == 0:
            continue
        j = bisect.bisect_left(fcc, c.clock)
        recv = [e.value for e in fc[max(0, j - (c.data_bytes + 400)): j]]
        data = c.data_values
        if data is None or any(v is None for v in recv):
            out.append((c.frame, len(recv), -1, -1))
            continue
        hit = -1
        for off in range(len(recv) - len(data) + 1):
            if recv[off: off + len(data)] == data:
                hit = off
        tail = -1 if hit < 0 else len(recv) - hit - len(data)
        out.append((c.frame, len(recv), hit, tail))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("iolog", nargs="+", type=Path)
    ap.add_argument("--label", nargs="+", required=True)
    ap.add_argument("--position-map", action="store_true",
                     help="各WRITEのデータ部が、直前の受信列(sub IN $FC)の"
                          "どの位置に現れるかを出す（位置と件数のみ。値は出さない）")
    args = ap.parse_args()
    if len(args.iolog) != len(args.label):
        print("iolog と --label の数が違う", file=sys.stderr)
        return 2

    for path, label in zip(args.iolog, args.label):
        rows, masked = m2s.parse_iolog(path)
        if sum(masked.values()):
            print(f"## {label}: 伏せ字ログのため解析不可")
            continue
        cmds = parse_commands(rows)
        counter = collections.Counter(c.opcode for c in cmds)
        print(f"## {label}: FDCコマンド {len(cmds)} 件")
        for op, n in sorted(counter.items(), key=lambda x: -x[1]):
            sub = [c for c in cmds if c.opcode == op]
            extra = ""
            if op in WRITE_OPCODES:
                sizes = collections.Counter(c.data_bytes for c in sub)
                extra = "  データ部バイト数: " + ", ".join(
                    f"{k}×{v}回" for k, v in sorted(sizes.items(), reverse=True)[:4])
            res = collections.Counter(c.result_bytes for c in sub)
            print(f"   {NAMES.get(op, hex(op)):<24} {n:>5} 件  "
                  f"結果バイト数: {', '.join(f'{k}×{v}' for k, v in sorted(res.items(), reverse=True)[:3])}{extra}")
        if args.position_map:
            pm = data_position_map(rows, cmds)
            if pm:
                print("   データ部の位置対応（受信列の末尾からの余り: 0なら"
                      "「受信列の末尾ちょうどがデータ部」）")
                tails = collections.Counter(t for _, _, _, t in pm)
                print("     余りバイト数の分布: " + ", ".join(
                    f"{k}×{v}件" for k, v in sorted(tails.items())))
                miss = sum(1 for _, _, h, _ in pm if h < 0)
                print(f"     一致が見つからなかったWRITE: {miss} / {len(pm)} 件")
        w = [c for c in cmds if c.opcode in WRITE_OPCODES]
        if w:
            print(f"   → 書き込み系コマンドの初出: frame {w[0].frame}"
                  f"（コマンド列の {cmds.index(w[0]) + 1} 番目）")
        else:
            print("   → 書き込み系コマンド（WRITE DATA / WRITE DELETED / FORMAT）は0件")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""tools/check_l3_write.py — 書き込み経路（仕様書1.35節）が端まで通ったかを
判定する。公式環境不要（tools/verify_l3.sh の `--write-test` シナリオ用）。

**subのFDCデータフェーズを基準に**、2つを別々に判定する:

  (1) 窓の正しさ: subがFDCへ流した256バイトが、**subがそのrunで最後に
      受け取った256バイト**と一致するか（1.35節が確定した「受信列の末尾
      ちょうど256バイト」）。
  (2) 往復: 同じ256バイトが、そのあとmainが読み戻した256バイトと一致するか
      （ディスクへ実際に書けて、読み出し経路から返ってくるか）。

(1)と(2)を分けるのは、失敗したときにどちらが壊れているかを区別するため。
mainの送信列を run に切り直す方式は、直後の要求ヘッダが同じ run に見えて
しまい脆かったので採らない（第54版で実際に踏んだ）。

出力は件数だけで、値は出さない。
終了コード: 両方一致なら0、不一致があれば1、判定材料が無ければ2。
"""
import argparse
import bisect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s          # noqa: E402
from analyze_write_path import parse_commands, WRITE_OPCODES  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("iolog", type=Path, help="書き込みフェーズの iolog")
    ap.add_argument("--read-log", type=Path,
                     help="読み戻しフェーズ（同じディスクを別実行で読む）の iolog。"
                          "省略すると(1)窓の正しさだけを判定する")
    ap.add_argument("--recv-port", default="00FC",
                     help="mainが受信するポート（既定 00FC。このハーネスでは"
                          "sub OUT $FD ↔ main IN $FC が対応する）")
    args = ap.parse_args()

    rows, masked = m2s.parse_iolog(args.iolog)
    if sum(masked.values()):
        print("判定不能: 伏せ字ログでは往復を突き合わせられない")
        return 2

    writes = [c for c in parse_commands(rows)
              if c.opcode in WRITE_OPCODES and c.data_bytes]
    if not writes:
        print("判定不能: sub が WRITE DATA を1回も発行していない")
        return 2
    if len(writes) != 1:
        print(f"判定不能: WRITE DATA が {len(writes)} 回ある（この検査は1回を前提）")
        return 2
    w = writes[0]
    if w.data_bytes != 256:
        print(f"不一致: データ部が {w.data_bytes} バイト（256を期待）")
        return 1
    wrote = w.data_values

    sub_recv = [e for e in rows if e.cpu == "sub" and e.port == "00FC" and e.kind == "IN"]
    before = [e.value for e in sub_recv if e.clock < w.clock]
    if len(before) < 256:
        print(f"判定不能: WRITE前のsub受信が {len(before)} バイトしか無い")
        return 2
    tail = before[-256:]
    same_window = sum(1 for a, b in zip(wrote, tail) if a == b)

    print(f"(1) 窓の正しさ: FDCへ流した256バイト vs subが最後に受け取った256バイト"
          f" → {same_window}/256 位置一致")
    if args.read_log is None:
        return 0 if same_window == 256 else 1

    rrows, rmasked = m2s.parse_iolog(args.read_log)
    if sum(rmasked.values()):
        print("判定不能: 読み戻しログが伏せ字")
        return 2
    rrecv = [e.value for e in rrows
             if e.cpu == "main" and e.port == args.recv_port and e.kind == "IN"]
    if len(rrecv) < 256:
        print(f"判定不能: 読み戻しログのmain受信が {len(rrecv)} バイトしか無い")
        return 2
    back = rrecv[-256:]
    same_trip = sum(1 for a, b in zip(wrote, back) if a == b)
    print(f"(2) 往復: FDCへ流した256バイト vs 別実行で読み戻した256バイト"
          f" → {same_trip}/256 位置一致")
    return 0 if (same_window == 256 and same_trip == 256) else 1


if __name__ == "__main__":
    raise SystemExit(main())

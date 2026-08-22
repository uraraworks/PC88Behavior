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

    # (3) 座標: WRITE DATA の C/H/R が、データ部の直前2バイト
    #     [論理トラック, R] から導いた値と一致するか（1.35節・m7ax）。
    track, sector = before[-258], before[-257]
    want = (track >> 1, track & 1, sector)
    got = (w.param_values[1], w.param_values[2], w.param_values[3])
    coord_ok = (want == got)
    print(f"(3) 座標: C=track>>1・H=track&1・R=直前1バイト → "
          f"{'一致' if coord_ok else '不一致'}")

    # (4) 応答: 第68版・m7bzで境界を訂正した。公式8/8ではWRITE結果7件の
    # 直後にmainから1バイト受信し、そのあとsubが1バイト返す。従来検査は
    # 「WRITE結果後〜最初の受信前」に応答を期待しており、自作main/subが
    # 同じ誤解を共有していた。結果末尾はWRITEの$FBアクセス272件目で切る。
    fb = [e for e in rows if e.cpu == "sub" and e.port == "00FB"
          and e.clock >= w.clock]
    if len(fb) < 272:
        print("判定不能: WRITEの結果フェーズ末尾を特定できない")
        return 2
    result_end = fb[271].clock
    next_recv = [e.clock for e in sub_recv if e.clock > result_end]
    if not next_recv:
        print("判定不能: WRITE結果後の1バイト受信が無い")
        return 2
    request_clock = next_recv[0]
    following = [e.clock for e in sub_recv if e.clock > request_clock]
    limit = following[0] if following else float("inf")
    sub_send = [e for e in rows
                if e.cpu == "sub" and e.port == "00FD" and e.kind == "OUT"
                and request_clock < e.clock < limit]
    # 件数だけでは足りない。**アイドルディスパッチャ経由でも1バイト出る**ので、
    # 応答を送らない版でも件数1になり検出力ゼロになる（第57版で踏んだ）。
    # 実測（m7ay）では57/57すべて同一の固定値だったので、値まで見る。
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "l3_service"))
    import make_subrom as sub_rom
    ack_ok = (len(sub_send) == 1
              and sub_send[0].value == sub_rom.WRITE_ACK_RESPONSE)
    print(f"(4) 応答: WRITE結果後の1バイト受信から次の受信までのsub送信 = {len(sub_send)}"
          f"、値が書き込み応答の観測値と一致 = {'はい' if ack_ok else 'いいえ'}")
    if args.read_log is None:
        return 0 if (same_window == 256 and coord_ok and ack_ok) else 1

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
    return 0 if (same_window == 256 and same_trip == 256 and coord_ok and ack_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())

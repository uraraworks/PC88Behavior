#!/usr/bin/env python3
"""
check_l3_response.py — tools/verify_l3.sh の判定部分

自作サブROM（`src/l3_service/make_subrom.py`）が、試験用 main ドライバ
（`tools/make_l3_test_main.py`）からの交換#3/#4要求に対して、
自作テストディスク（`tools/make_l3_testdisk.py`）の内容どおりに
交換#3で1バイト、交換#4で256バイトを正しく応答しているかを、
`--io-log` の main 側 `IN $FC` 列から機械的に判定する。

交換#3の1バイトは意味・値とも未確定なので値一致の対象にしない。ただし、
各要求につきその位置に厳密に1バイト存在し、その直後の256バイトが自作
ディスクの規則生成値と全件一致することを要求する。これは期待を弱める
処置ではなく、m7kで確定した交換境界（交換#3=応答1バイト、交換#4=応答
256バイト）へ旧期待を訂正する処置である。

判定は「mainが最終的に受け取るデータ列」だけを見る
（`docs/spec/l3-subrom.md` 5.1節の原則と同じ型）。
"""

import argparse
import sys


def sector_pattern(cyl: int, sec: int) -> list[int]:
    """tools/make_l3_testdisk.py の sector_pattern() と同じ式。"""
    return [((cyl * 97 + sec * 57 + i * 7 + 13) & 0xFF) for i in range(256)]


def extract_main_in_fc(path: str) -> list[int]:
    vals = []
    in_main = False
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s == "# main":
                in_main = True
                continue
            if s == "# sub":
                in_main = False
                continue
            if not in_main or not s or s.startswith("#"):
                continue
            fields = s.split()
            if len(fields) not in (7, 8):
                continue
            kind, port, value = fields[-4], fields[-3], fields[-2]
            if kind == "IN" and port.upper() == "00FC":
                vals.append(int(value, 16))
    return vals


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("iolog")
    ap.add_argument("--requests", required=True,
                     help="cyl:sec のカンマ区切り列（make_l3_test_main.py と同じ列を渡すこと）")
    ap.add_argument("--skip-prefix-bytes", type=int, default=0,
                     help="main の IN $FC 列の先頭Nバイトを比較対象から除外する。"
                          "tools/make_l3_test_main.py --dispatch-switch-test が"
                          "本来の要求列の前に割り込みシナリオの応答1バイトを"
                          "挟むため、その分だけ読み飛ばすのに使う。")
    args = ap.parse_args()

    requests = []
    for tok in args.requests.split(","):
        c, s = tok.split(":")
        requests.append((int(c), int(s)))

    got = extract_main_in_fc(args.iolog)[args.skip_prefix_bytes:]
    want: list[int] = []
    for c, s in requests:
        want += sector_pattern(c, s)

    print(f"要求: {requests}")
    expected_count = len(requests) * 257
    print(f"期待応答数: {expected_count}（交換#3: 1 + 交換#4: 256）x {len(requests)}"
          f" / 受信バイト数: {len(got)}")

    if len(got) != expected_count:
        print(f"不一致: 応答数が違う（{len(got)} != {expected_count}）")
        return 1

    for req_idx, (c, s) in enumerate(requests):
        # 各257件の先頭は交換#3の意味未特定応答。存在と位置だけを検査し、
        # 値は仕事3でブラックボックス介入により確定するまで期待しない。
        sector = got[req_idx * 257 + 1:(req_idx + 1) * 257]
        expected_sector = sector_pattern(c, s)
        for off, (expected, actual) in enumerate(zip(expected_sector, sector)):
            if expected != actual:
                print(f"不一致: 要求{req_idx}=cyl{c}:sec{s} の交換#4応答 {off} バイト目"
                      f" 期待={expected:02X} 実際={actual:02X}")
                return 1

    print(f"一致: 交換#3の構造 {len(requests)} 件 + "
          f"交換#4の値 {len(want)} バイト全件")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
check_l3_response.py — tools/verify_l3.sh の判定部分

自作サブROM（`src/l3_service/make_subrom.py`）が、試験用 main ドライバ
（`tools/make_l3_test_main.py`）からの256バイト読み出し要求に対して、
自作テストディスク（`tools/make_l3_testdisk.py`）の内容どおりに
正しく応答しているかを、`--io-log` の main 側 `IN $FC` 列から機械的に
判定する。

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
    args = ap.parse_args()

    requests = []
    for tok in args.requests.split(","):
        c, s = tok.split(":")
        requests.append((int(c), int(s)))

    got = extract_main_in_fc(args.iolog)
    want: list[int] = []
    for c, s in requests:
        want += sector_pattern(c, s)

    print(f"要求: {requests}")
    print(f"期待バイト数: {len(want)} / 受信バイト数: {len(got)}")

    if len(got) < len(want):
        print(f"不一致: 受信が足りない（{len(got)} < {len(want)}）")
        return 1

    n = min(len(want), len(got))
    for i in range(n):
        if want[i] != got[i]:
            req_idx = i // 256
            off = i % 256
            c, s = requests[req_idx] if req_idx < len(requests) else (None, None)
            print(f"不一致: {i} バイト目（要求{req_idx}=cyl{c}:sec{s} の {off} バイト目）"
                  f" 期待={want[i]:02X} 実際={got[i]:02X}")
            return 1

    print(f"一致: {len(want)} バイト全件（要求 {len(requests)} 件 x 256バイト）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

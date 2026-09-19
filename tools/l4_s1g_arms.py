#!/usr/bin/env python3
"""PC88Behavior: l4-s1g 事前登録
（docs/notes/l4-s1g-screen-editor-return-preregistration.md、改訂1
`3b3be75`）どおりに、各腕の打鍵計画（`--key-matrix PORT:BIT:FRAME:HOLD`の
列）を機械的に組み立てる器具。q88measureは呼ばない（呼び出しは実測担当が
別途行う）。文字キーのport:bitは`docs/spec/l3-main.md`第9節のQ1文字コード
対応表（無修飾・小文字）から機械的に転記したもの（既存資料、本ノートの
新規作成物ではない）。CAPS/SHIFTは使わない（事前登録「器具の使い方」節）。

各腕は「手順（ステップ列）」として表現する。ステップは
  ("type", "print 12")  英数字・空白の並びを1文字ずつ押す
  ("key", "RETURN"/"HOME"/"UP"/"DOWN"/"LEFT"/"RIGHT")  特殊キー1回
のいずれか。build_program()が、既定HOLD=4・GAP=8で連続する
`--key-matrix`列に展開し、各ステップの直後のフレーム番号も返す
（写しを撮る基準に使う）。
"""
from __future__ import annotations

import argparse
import json

HOLD = 4
GAP = 8
START_FRAME = 700

# docs/spec/l3-main.md 第9節（無修飾・小文字のQ1コード対応表）から転記。
CHAR_KEYS = {
    "0": (0x00, 0), "1": (0x00, 1), "2": (0x00, 2), "3": (0x00, 3),
    "4": (0x00, 4), "5": (0x00, 5), "6": (0x00, 6), "7": (0x00, 7),
    "8": (0x01, 0), "9": (0x01, 1),
    "a": (0x02, 1), "b": (0x02, 2), "c": (0x02, 3), "d": (0x02, 4),
    "e": (0x02, 5), "f": (0x02, 6), "g": (0x02, 7),
    "h": (0x03, 0), "i": (0x03, 1), "j": (0x03, 2), "k": (0x03, 3),
    "l": (0x03, 4), "m": (0x03, 5), "n": (0x03, 6), "o": (0x03, 7),
    "p": (0x04, 0), "q": (0x04, 1), "r": (0x04, 2), "s": (0x04, 3),
    "t": (0x04, 4), "u": (0x04, 5), "v": (0x04, 6), "w": (0x04, 7),
    "x": (0x05, 0), "y": (0x05, 1), "z": (0x05, 2),
    " ": (0x09, 6),
}

SPECIAL_KEYS = {
    "RETURN": (0x01, 7),
    "HOME": (0x08, 0),
    "UP": (0x08, 1),
    "RIGHT": (0x08, 2),
    "DEL": (0x08, 3),
    "DOWN": (0x0A, 1),
    "LEFT": (0x0A, 2),
}


def build_program(steps: list[tuple[str, str]], start_frame: int = START_FRAME):
    """steps を打鍵計画に展開する。戻り値:
    key_matrix: [{"label","port","bit","frame","hold"}, ...]
    step_end_frames: 各ステップの最後の押下が終わった直後のフレーム番号の列
    """
    frame = start_frame
    km = []
    step_end_frames = []
    for kind, arg in steps:
        if kind == "type":
            for ch in arg:
                if ch not in CHAR_KEYS:
                    raise ValueError(f"未対応の文字: {ch!r}")
                port, bit = CHAR_KEYS[ch]
                km.append({"label": f"type_{ch}", "port": f"{port:02X}",
                           "bit": bit, "frame": frame, "hold": HOLD})
                frame += GAP
        elif kind == "key":
            if arg not in SPECIAL_KEYS:
                raise ValueError(f"未対応のキー: {arg!r}")
            port, bit = SPECIAL_KEYS[arg]
            km.append({"label": arg, "port": f"{port:02X}", "bit": bit,
                       "frame": frame, "hold": HOLD})
            frame += GAP
        else:
            raise ValueError(f"未知のステップ種別: {kind!r}")
        step_end_frames.append(frame)
    return km, step_end_frames


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--steps-json", required=True,
                     help='[["type","print 12"],["key","RETURN"]]形式')
    ap.add_argument("--start-frame", type=int, default=START_FRAME)
    args = ap.parse_args()
    steps = [tuple(s) for s in json.loads(args.steps_json)]
    km, ends = build_program(steps, args.start_frame)
    print(json.dumps({"key_matrix": km, "step_end_frames": ends}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

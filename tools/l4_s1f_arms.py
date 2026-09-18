#!/usr/bin/env python3
"""PC88Behavior: l4-s1f 事前登録
（docs/notes/l4-s1f-screen-editor-preregistration.md、改訂1`39620ac`）
どおりに、24腕それぞれの打鍵計画（`--key-matrix PORT:BIT:FRAME:HOLD`の列）
を機械的に組み立てる器具。q88measureそのものは呼ばない（呼び出しは
`tools/l4_s1f_run.sh`が行う）。

**このファイルはq88measureの実行を伴わないため、公式ROMが無くても
生成・検査できる。** 実際にq88measureへ渡して走らせる部分
（`tools/l4_s1f_run.sh`）は公式ROM（`PC88_REF_ROM_DIR`）が要る。

打鍵の組み立て方（事前登録「打鍵の作り方」節どおり）:
  1. CAPS(0A:7)を開始フレームで押し、マーカー打鍵〜対象キー押下が
     終わるまで保持する（保持型、トグルではない）。
  2. マーカー`QXZJK`（04:1,05:0,05:2,03:2,03:3）を既定HOLD=4、
     間隔GAP=8フレームで順に打つ。打ち終えるとカーソルは自然に
     マーカー行の列5（行末）に来る。
  3. 位置決め: 「行末」は追加の位置決め無し（列5のまま）。「行中」は
     ←(0A:2)を3回。「行頭」は←を5回（列0に到達）。位置決め自体は
     測定対象に含めない（前後の写しは測定対象キーの前後だけで取る）。
     ただし対象キー自体が←の場合は、位置決めと測定対象を同じ物理キーで
     連続して押す形になる（行頭腕は規定より1回多く、列0に達した後さらに
     1回押す＝境界を超えて押す）。
  4. 対象キー（無修飾はそのまま、SHIFT条件は対象キー開始10フレーム前から
     SHIFT(08:6)を押し始め、対象キーの保持期間を通じて下げたままにする）
     を1回押す。
  5. D=10フレーム後、目印文字`W`(04:7)を1回押つ。

各腕の打鍵計画は「写し(前)を撮るフレーム」「対象キー押下」
「写し(直後)を撮るフレーム」「目印文字」「写し(目印後)を撮るフレーム」
を合わせて返す。実際のq88measure呼び出しとvram-dumpの発行は
`tools/l4_s1f_run.sh`が行う。

G7（再実行で同じ計画になる）: 乱数・時刻・環境依存の要素を使わない。
"""
from __future__ import annotations

import argparse
import json

CAPS = (0x0A, 7)
SHIFT = (0x08, 6)
MARKER_KEYS = [("Q", 0x04, 1), ("X", 0x05, 0), ("Z", 0x05, 2), ("J", 0x03, 2), ("K", 0x03, 3)]
MARK_W = (0x04, 7)

ARROWS = {"left": (0x0A, 2), "right": (0x08, 2), "up": (0x08, 1), "down": (0x0A, 1)}
INSDEL = (0x08, 3)
HOMECLR = (0x08, 0)

START_FRAME = 700
HOLD = 4
GAP = 8
D = 10  # 反映の遅れ(docs/spec/l3-main.md 第8節、l4-s1bで確定済み)
SETTLE_AFTER_MARK = 20  # 目印文字打鍵後、次に進む前の余裕

POSITIONS = ("head", "mid", "tail")

# 条件名 -> (対象キーport,bit, SHIFT有無)
CONDITIONS = {
    "arrow_left_noshift": (ARROWS["left"], False),
    "arrow_right_noshift": (ARROWS["right"], False),
    "arrow_up_noshift": (ARROWS["up"], False),
    "arrow_down_noshift": (ARROWS["down"], False),
    "insdel_noshift": (INSDEL, False),
    "insdel_shift": (INSDEL, True),
    "homeclr_noshift": (HOMECLR, False),
    "homeclr_shift": (HOMECLR, True),
}


def build_arm(condition: str, position: str) -> dict:
    if condition not in CONDITIONS:
        raise ValueError(f"未知の条件: {condition}")
    if position not in POSITIONS:
        raise ValueError(f"未知の位置: {position}")
    (key_port, key_bit), shifted = CONDITIONS[condition]

    presses = []  # (label, port, bit, frame, hold)
    frame = START_FRAME

    # 1. CAPS押しっぱなし開始
    caps_start = frame
    presses.append(("caps_down", CAPS[0], CAPS[1], caps_start, None))  # holdは最後に確定

    # 2. マーカー QXZJK
    for label, port, bit in MARKER_KEYS:
        frame += GAP
        presses.append((f"marker_{label}", port, bit, frame, HOLD))
    frame_after_marker = frame + GAP  # マーカー打ち終わり後の余裕

    # 3. 位置決め(←のみ、測定対象には含めない)
    frame = frame_after_marker
    is_left_condition = condition == "arrow_left_noshift"
    if position == "tail":
        n_position_presses = 0
    elif position == "mid":
        n_position_presses = 3
    elif position == "head":
        n_position_presses = 5
    position_press_frames = []
    for i in range(n_position_presses):
        frame += GAP
        position_press_frames.append(frame)
        presses.append((f"position_left_{i}", ARROWS["left"][0], ARROWS["left"][1], frame, HOLD))

    # 4. 対象キー押下。←条件の行頭腕は「規定より1回多く」=
    #    位置決め5回に続けてもう1回(6回目)を測定対象として押す。
    if is_left_condition and position == "head":
        frame += GAP
        target_press_frame = frame
        # この1回が測定対象(境界を超えて押す)
    else:
        frame += GAP
        target_press_frame = frame

    dump_before_frame = target_press_frame - 2  # 押す直前の写し

    if shifted:
        shift_start = target_press_frame - 10
        shift_hold = 10 + HOLD + 5  # 対象キー開始10フレーム前〜保持期間+余裕
        presses.append(("shift_down", SHIFT[0], SHIFT[1], shift_start, shift_hold))

    presses.append(("target_key", key_port, key_bit, target_press_frame, HOLD))

    dump_after_frame = target_press_frame + HOLD + D  # 反映後の写し

    # 5. 目印文字 W
    mark_frame = dump_after_frame + GAP
    presses.append(("mark_W", MARK_W[0], MARK_W[1], mark_frame, HOLD))
    dump_after_mark_frame = mark_frame + HOLD + D

    # CAPSのholdを確定(最後の打鍵まで保持)
    caps_hold = (dump_after_mark_frame + SETTLE_AFTER_MARK) - caps_start
    presses[0] = ("caps_down", CAPS[0], CAPS[1], caps_start, caps_hold)

    total_frames = dump_after_mark_frame + SETTLE_AFTER_MARK

    return {
        "condition": condition,
        "position": position,
        "shifted": shifted,
        "key_matrix": [
            {"label": lbl, "port": f"{p:02X}", "bit": b, "frame": f, "hold": h}
            for (lbl, p, b, f, h) in presses
        ],
        "dump_before_frame": dump_before_frame,
        "dump_after_frame": dump_after_frame,
        "dump_after_mark_frame": dump_after_mark_frame,
        "total_frames": max(1200, total_frames),
        "nonblank_check_frame": dump_before_frame,
    }


def build_all_arms() -> dict:
    arms = {}
    for cond in CONDITIONS:
        for pos in POSITIONS:
            arms[f"{cond}/{pos}"] = build_arm(cond, pos)
    return arms


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--condition", help="単一腕のみ出力する場合の条件名")
    ap.add_argument("--position", choices=POSITIONS)
    ap.add_argument("--output")
    ap.add_argument("--check", action="store_true",
                     help="出力を書かず既存ファイルと一致するかだけ確認する(G7用)")
    args = ap.parse_args()

    if args.condition and args.position:
        doc = {f"{args.condition}/{args.position}": build_arm(args.condition, args.position)}
    else:
        doc = build_all_arms()

    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        assert args.output, "--checkには--outputが要る"
        with open(args.output, encoding="utf-8") as f:
            existing = f.read()
        if existing != text:
            print("[l4_s1f_arms] NG: 再生成した計画が既存ファイルと不一致")
            return 1
        print(f"[l4_s1f_arms] OK: {len(doc)}腕 (G7: 既存ファイルと一致)")
        return 0

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[l4_s1f_arms] {len(doc)}腕 -> {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

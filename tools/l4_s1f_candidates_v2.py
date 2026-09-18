#!/usr/bin/env python3
"""PC88Behavior: l4-s1f 候補表 v2。

事前登録の追補
docs/notes/l4-s1f-screen-editor-preregistration-addendum.md が定める
「マーカー開始列は絶対列0ではなく、実測した開始列(col_start)からの
相対位置で候補を作る」規則に従い、Q1候補を**列範囲(window)限定の
署名**として作り直す(元のtools/l4_s1f_candidates.py・
docs/notes/l4-s1f-candidate-table.jsonは変更せず残す。版を分ける)。

背景(追補の実測、本番の腕数には数えない): 実ROMでは起動直後の
マーカー行(row0=1)に、マーカーを打つ前から既に非空白セルが列0〜20に
ある(内容には触れない。件数と位置のみ既に追補に記録済み)。マーカーは
その直後の列22から書かれる(col_start=22、2回の独立走行で再現)。
このため「行全体(列0-79)の署名」で候補を判定すると、既存の非空白
セルが必ず候補と不一致になる。列範囲を「col_start-1」〜「col_start+6」
の8バイトに絞ることで、既存セル(列0-20)を判定対象から外す。

window内の位置: idx0=col_start-1（del_leftが列-1にはみ出す場合の受け皿）、
idx1-5=マーカー本来の列0-4相当、idx6=col_start+5相当(ins_spaceの右シフト
先・行末位置)、idx7=col_start+6（さらに余裕1）。

署名の作り方はtools/l4_s1f_candidates.pyのnormalize/sha256と同じ
(末尾の0x20を除いてSHA-256)。画面本文はここにも一切登場しない。
"""
from __future__ import annotations

import argparse
import hashlib
import json

SPACE = 0x20
WINDOW_LEN = 8  # idx0=col_start-1 .. idx7=col_start+6
MARKER = [0x51, 0x58, 0x5A, 0x4A, 0x4B]  # Q X Z J K (CAPS込み、確認済み)

POSITIONS = {"head": 0, "mid": 2, "tail": 5}  # マーカー内の相対列(0-4何文字目相当)


def baseline_window() -> list[int]:
    # idx0 = col_start-1 (window外なので既定は空白と仮定。実測でG9同様に
    # 確認する対象。ここでは既存内容が無い前提の候補を作る)
    w = [SPACE] * WINDOW_LEN
    for i, code in enumerate(MARKER):
        w[1 + i] = code  # idx1..idx5 = マーカー5文字
    return w


def normalize(w: list[int]) -> bytes:
    return bytes(w).rstrip(bytes([SPACE]))


def sig(w: list[int]) -> dict:
    norm = normalize(w)
    return {
        "row_sha256": hashlib.sha256(norm).hexdigest(),
        "normalized_length": len(norm),
        "nonblank_count": sum(1 for c in w if c != SPACE),
    }


def fault_sig(w: list[int]) -> dict:
    w2 = list(w)
    idx = None
    for i in range(WINDOW_LEN - 1, -1, -1):
        if w2[i] != SPACE:
            idx = i
            break
    if idx is None:
        w2[0] = 0x2A
    else:
        v = (w2[idx] + 1) % 0x100
        if v == SPACE:
            v = (v + 1) % 0x100
        w2[idx] = v
    return sig(w2)


# window内でのカーソル列(idxで表す。idx1=マーカー列0, ... idx5=マーカー列4,
# idx6=マーカー列5相当=行末の1つ先=自然な行末位置)
def col_in_window(pos_offset: int) -> int:
    return 1 + pos_offset  # head=idx1, mid=idx3, tail=idx6


def del_left(w: list[int], idx: int) -> list[int]:
    if idx <= 0:
        return list(w)
    out = w[:idx - 1] + w[idx:] + [SPACE]
    return out[:WINDOW_LEN]


def del_at(w: list[int], idx: int) -> list[int]:
    if idx >= WINDOW_LEN or w[idx] == SPACE:
        return list(w)
    out = w[:idx] + w[idx + 1:] + [SPACE]
    return out[:WINDOW_LEN]


def ins_space(w: list[int], idx: int) -> list[int]:
    if idx >= WINDOW_LEN or w[idx] == SPACE:
        return list(w)
    out = w[:idx] + [SPACE] + w[idx:]
    return out[:WINDOW_LEN]


def build_arms() -> dict:
    base = baseline_window()
    arms = {}

    def add(cond: str, pos: str, candidates: dict[str, list[int]]):
        key = f"{cond}/{pos}"
        entry = {}
        for name, w in candidates.items():
            entry[name] = sig(w)
        first_name = next(iter(candidates))
        entry["_fault_dummy_of_" + first_name] = fault_sig(candidates[first_name])
        arms[key] = entry

    for cond in ("arrow_left_noshift", "arrow_right_noshift"):
        for pos_name in POSITIONS:
            cands = {"no_change": base}
            if cond == "arrow_left_noshift" and pos_name == "head":
                cands["wrap_prev_line"] = base
            if cond == "arrow_right_noshift" and pos_name == "tail":
                cands["wrap_next_line"] = base
            add(cond, pos_name, cands)

    for cond in ("arrow_up_noshift", "arrow_down_noshift"):
        for pos_name in POSITIONS:
            add(cond, pos_name, {"no_change": base, "row_move": base})

    for cond in ("insdel_noshift", "insdel_shift"):
        for pos_name, off in POSITIONS.items():
            idx = col_in_window(off)
            cands = {
                "del_left": del_left(base, idx),
                "del_at": del_at(base, idx),
                "ins_mode_only": list(base),
                "ins_space": ins_space(base, idx),
            }
            add(cond, pos_name, cands)

    # HOME/CLRは行内窓ではなく画面全体の非空白件数で判定するため候補表には
    # 含めない(追補「HOME/CLRの判定」節を参照。ここではarrow/insdelのみ)。

    return arms


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", default="docs/notes/l4-s1f-candidate-table-v2.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    doc = {
        "version": 2,
        "window_len": WINDOW_LEN,
        "window_anchor": "idx0 = col_start-1 (col_startは実測、追補参照)",
        "arms_q1_windowed": build_arms(),
        "positions_offset_in_marker": POSITIONS,
        "note": "追補により列範囲(window)限定の署名に変更。HOME/CLRは画面全体の"
                "非空白件数で別途判定するためここには含まない。画面本文は含まない。",
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        with open(args.output, encoding="utf-8") as f:
            existing = f.read()
        if existing != text:
            print("[l4_s1f_candidates_v2] NG: 再生成した判定表が既存ファイルと不一致")
            return 1
        print(f"[l4_s1f_candidates_v2] OK: {len(doc['arms_q1_windowed'])}条件×位置 "
              f"(G7: 既存ファイルと一致)")
        return 0

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[l4_s1f_candidates_v2] {len(doc['arms_q1_windowed'])}条件×位置 -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

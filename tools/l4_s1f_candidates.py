#!/usr/bin/env python3
"""PC88Behavior: l4-s1f 事前登録
（docs/notes/l4-s1f-screen-editor-preregistration.md、改訂1
コミット`39620ac`）が定める8キー条件×3位置=24腕の、Q1（行署名）候補を
機械的に計算し、判定表として書き出す器具。

測定の**前に**候補の期待SHA-256を固定する（事前登録「候補（仮説）と
その作り方」節）。実測後に候補を後出しで足さない。

対象キーの port:bit・マーカー文字コード（CAPS込み）は、いずれも
`docs/spec/l3-main.md` 第9節（Q1文字コード対応表、公式ROMの内容では
なく「挙動から再構成した対応表」として既にコミット済みのもの）から
機械的に転記する:
  Q=04:1(コード71,CAPS込み51) X=05:0(78,58) Z=05:2(7A,5A)
  J=03:2(6A,4A) K=03:3(6B,4B) W=04:7(77,57、目印文字)
  CAPS=0A:7 SHIFT=08:6
  矢印: ←=0A:2 →=08:2 ↑=08:1 ↓=0A:1
  INS/DEL=08:3 HOME/CLR=08:0

行の文字域は80バイト（`tools/l4_vram_probe.py`のCOLS=80）。本スクリプトは
実際の写し(vram-dump)を一切読まない。マーカー行の無編集時の内容を
文字コード対応表から機械的に組み立て、事前登録の候補操作を適用した
結果を`row_signature()`と同じ正規化（末尾の0x20を除いてSHA-256）で
署名するだけ。画面本文（実測値）はここには登場しない。

出力: JSON。各(condition, position)につき、候補名・row_sha256・
nonblank_count・normalized_length と、故障注入用ダミー候補
（1バイトだけ違う文字コードにずらした期待署名、G8用）。
Q2（CRTC列/行）・Q3（目印座標）は、マーカー行の実際の行番号(row0)が
走行前には決め打ちできない（事前登録「マーカー行の行番号(row0)は
決め打ちしない」節）ため、row0・positionを変数にした式（symbolic）で
記録する。実測後、解析担当がその式に実際のrow0・列を代入して照合する。

G7（再実行で同じ表になる）: 乱数・時刻・環境依存の要素を使わない。
"""
from __future__ import annotations

import argparse
import hashlib
import json

COLS = 80
SPACE = 0x20

# マーカー文字列 QXZJK のCAPS込みコード（docs/spec/l3-main.md 第9節・第10節）
MARKER = [0x51, 0x58, 0x5A, 0x4A, 0x4B]  # Q X Z J K
MARK_W = 0x57  # 目印文字 W（Q3）

POSITIONS = {"head": 0, "mid": 2, "tail": 5}


def baseline_row() -> list[int]:
    row = [SPACE] * COLS
    for i, code in enumerate(MARKER):
        row[i] = code
    return row


def normalize(row: list[int]) -> bytes:
    b = bytes(row)
    return b.rstrip(bytes([SPACE]))


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def nonblank_count(row: list[int]) -> int:
    return sum(1 for c in row if c != SPACE)


def sig(row: list[int]) -> dict:
    norm = normalize(row)
    return {
        "row_sha256": sha256_hex(norm),
        "normalized_length": len(norm),
        "nonblank_count": nonblank_count(row),
    }


def fault_sig(row: list[int]) -> dict:
    """G8故障注入: 末尾以外の非空白セルを1バイトだけ違う値にずらす。

    候補どうしの判定に検出力があることを確かめるためのダミー。
    実測とは絶対に一致してはならない値なので、判定結果には使わない。
    """
    row2 = list(row)
    # 非空白セルのうち最後のものを +1 (0x20と衝突しないように mod 0x100,
    # 0x20になってしまう場合はさらに+1)
    idx = None
    for i in range(COLS - 1, -1, -1):
        if row2[i] != SPACE:
            idx = i
            break
    if idx is None:
        row2[0] = 0x2A  # 陰性の陰性対照(全空白)用: '*'相当のダミー
    else:
        v = (row2[idx] + 1) % 0x100
        if v == SPACE:
            v = (v + 1) % 0x100
        row2[idx] = v
    return sig(row2)


# --- Q1候補生成 -------------------------------------------------------

def del_left(row: list[int], col: int) -> list[int]:
    if col <= 0:
        return list(row)  # 行頭: 左に文字が無い -> no_change
    out = row[:col - 1] + row[col:] + [SPACE]
    return out[:COLS]


def del_at(row: list[int], col: int) -> list[int]:
    if col >= COLS or row[col] == SPACE:
        return list(row)  # カーソル位置に文字が無い -> no_change
    out = row[:col] + row[col + 1:] + [SPACE]
    return out[:COLS]


def ins_space(row: list[int], col: int) -> list[int]:
    if col >= COLS or row[col] == SPACE:
        return list(row)  # 右にずらす文字が無い -> no_change
    out = row[:col] + [SPACE] + row[col:]
    return out[:COLS]


def clear_row() -> list[int]:
    return [SPACE] * COLS


def build_arms() -> dict:
    base = baseline_row()
    arms = {}

    def add(cond: str, pos: str, candidates: dict[str, list[int]]):
        key = f"{cond}/{pos}"
        entry = {}
        for name, row in candidates.items():
            entry[name] = sig(row)
        # G8: 各候補のうち先頭(判定の主根拠になりやすいもの)に対して
        # ダミーを1つ作る。全候補ではなく代表1件で十分(自己検査の目的)。
        first_name = next(iter(candidates))
        entry["_fault_dummy_of_" + first_name] = fault_sig(candidates[first_name])
        arms[key] = entry

    for cond, key_pb in [("left", "0A:2"), ("right", "08:2")]:
        for pos_name, col in POSITIONS.items():
            cands = {"no_change": base}
            if cond == "left" and pos_name == "head":
                cands["wrap_prev_line"] = base  # 行内容はno_changeと同じ(Q2/Q3で区別)
            if cond == "right" and pos_name == "tail":
                cands["wrap_next_line"] = base
            add(f"arrow_{cond}_noshift", pos_name, cands)

    for cond in ("up", "down"):
        for pos_name in POSITIONS:
            cands = {"no_change": base, "row_move": base}
            add(f"arrow_{cond}_noshift", pos_name, cands)

    for cond in ("insdel_noshift", "insdel_shift"):
        for pos_name, col in POSITIONS.items():
            cands = {
                "del_left": del_left(base, col),
                "del_at": del_at(base, col),
                "ins_mode_only": list(base),
                "ins_space": ins_space(base, col),
            }
            add(cond, pos_name, cands)

    for cond in ("homeclr_noshift", "homeclr_shift"):
        for pos_name in POSITIONS:
            cands = {"clear": clear_row(), "home": list(base)}
            add(cond, pos_name, cands)

    return arms


# Q2/Q3の候補は、事前登録「Q2（CRTC）の候補の作り方」「Q3（目印位置）の
# 候補の作り方」節の表をそのまま機械可読な形にしただけ(symbolic)。
# row0(マーカー行の実際の行番号)・col(位置0/2/5)は実測後に代入する。
Q2Q3_RULES = {
    "no_change_arrow": {"col": "col±1(左右キー) または col(上下キー)",
                          "row": "row0(左右キー) または row0±1(上下キー)"},
    "wrap_prev_line": {"col": "row0-1行の非空白末尾+1(または79)", "row": "row0-1"},
    "wrap_next_line": {"col": "0", "row": "row0+1"},
    "row_move": {"col": "col(不変)", "row": "row0±1"},
    "boundary_reflow": {"col": "実測値をそのまま記録(候補としては扱わない)",
                          "row": "実測値をそのまま記録"},
    "del_left": {"col": "col-1", "row": "row0"},
    "del_at": {"col": "col(不変)", "row": "row0"},
    "ins_mode_only": {"col": "col(不変)", "row": "row0"},
    "ins_space": {"col": "col(不変)", "row": "row0"},
    "clear": {"col": "0", "row": "0"},
    "home": {"col": "0", "row": "0"},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", default="docs/notes/l4-s1f-candidate-table.json")
    ap.add_argument("--check", action="store_true",
                     help="出力を書かず既存ファイルと一致するかだけ確認する(G7用)")
    args = ap.parse_args()

    doc = {
        "arms_q1": build_arms(),
        "q2q3_rules": Q2Q3_RULES,
        "positions": POSITIONS,
        "note": "Q1は実測SHA-256、Q2/Q3はrow0・col未定のためsymbolic式のみ。"
                "画面本文は含まない(候補の期待署名と式のみ)。",
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        with open(args.output, encoding="utf-8") as f:
            existing = f.read()
        if existing != text:
            print("[l4_s1f_candidates] NG: 再生成した判定表が既存ファイルと不一致")
            return 1
        print(f"[l4_s1f_candidates] OK: {len(doc['arms_q1'])}条件×位置 "
              f"(G7: 既存ファイルと一致)")
        return 0

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[l4_s1f_candidates] {len(doc['arms_q1'])}条件×位置 -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

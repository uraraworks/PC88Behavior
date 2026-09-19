#!/usr/bin/env python3
"""PC88Behavior: l4-c6 スクリーンエディタ適合の場面固定 — 記録道具。

docs/spec/l3-main.md 第16節（`l4-s1f`本体・追補1〜3）・第17節
（`l4-s1g`本体・追補）が確定した腕（真の直接モード、settle手順＋G11
つき）を、公式ROM・自作main ROM（`src/build_main_rom.py`）の両方に
同じ打鍵計画で流し、判定に使う最小限の情報（座標・件数・SHA-256）だけを
JSONで返す。画面本文は一切出力しない（CLAUDE.md禁止事項7）。

対象の腕（第18節「未確定」に当たる腕は含めない。理由は各腕のコメント）:
  第16節: arrow_{left,right,up,down}_mid・insdel_{noshift,shift}_mid・
          homeclr_{noshift,shift}_mid（行の途中、各1腕）・
          B1・B2・B2p（B2'改）・B3・B3p（B3'改）・B4（真の境界）
  第17節: R1a・R1b・R1c・U1・E1・T1・T2・PC1（陽性対照）
  第18節項5・l4-s1h（キーリピート、
  docs/notes/l4-s1h-key-repeat-results.md）:
    s1h_q1_main（qキーの繰り返し時系列）・s1h_g4_pos/s1h_g5_neg
    （陽性・陰性対照）・s1h_q2_a〜f（→の6腕）・s1h_q3_main
    （→単発での列79越え）

除外（第18節・各節「未実施・未確定」節のとおり、この版では対象外）:
  挿入モードで列79まで実文字が詰まった行への挿入・挿入モードを抜ける
  条件・→単発での列79越え（長押しでの`wrap_to_next_line`のみ確認）・
  80文字を越える論理行・CTRL系編集キー・G7（CRTC/iolog）。

出力してよいもの（これ以外は出さない）:
  1. 変化したセルの座標(row0,col0)・「押す前が空白だったか」
  2. 押す前が空白だったセルについてだけ、自分で打った文字(`w`,数値の
     一部)のコード（画面本文ではなく自分の打鍵の結果）
  3. 出力行のnonblank_count・normalized_length・SHA-256
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "tools/harness/frontend/q88measure"
COLS, STRIDE = 80, 120

CHAR = {
    "0": ("00", 0), "1": ("00", 1), "2": ("00", 2), "3": ("00", 3), "4": ("00", 4),
    "9": ("01", 1),
    "q": ("04", 1), "x": ("05", 0), "z": ("05", 2), "j": ("03", 2), "k": ("03", 3),
    "p": ("04", 0), "r": ("04", 2), "i": ("03", 1), "n": ("03", 6), "t": ("04", 4),
    " ": ("09", 6), "l": ("03", 4), "s": ("04", 3), "e": ("02", 5), "w": ("04", 7),
    "u": ("04", 5),
}
SPECIAL = {
    "LEFT": ("0A", 2), "RIGHT": ("08", 2), "UP": ("08", 1), "DOWN": ("0A", 1),
    "DEL": ("08", 3), "HOME": ("08", 0), "RETURN": ("01", 7), "SHIFT": ("08", 6),
}
SETTLE = [("01", 7, 700, 4), ("01", 7, 1000, 4)]  # G11: 起動時入力待ちを抜ける


def find_core() -> str:
    cands = list((REPO.parent / "vendor/quasi88-libretro").glob("quasi88_libretro.*"))
    if not cands:
        raise SystemExit("エラー: コアが無い(vendor/quasi88-libretro)")
    return str(cands[0])


def build_tokens(tokens: list[str], start: int = 1300, hold: int = 4, gap: int = 8):
    frame = start
    km = []
    for t in tokens:
        port, bit = SPECIAL.get(t) or CHAR[t]
        km.append((port, bit, frame, hold))
        frame += gap
    return km, frame


def run_q88(romdir: str, kms, dumps, prefix: str, frames: int):
    args = [str(FRONTEND), "--core", find_core(), "--rom-dir", romdir, "--frames", str(frames)]
    paths = []
    for name, fr in dumps:
        p = f"{prefix}.{name}.bin"
        args += ["--vram-dump", p, "--vram-dump-at", str(fr)]
        paths.append(p)
    for port, bit, fr, hold in kms:
        args += ["--key-matrix", f"0x{port}:{bit}:{fr}:{hold}"]
    r = subprocess.run(args, capture_output=True, text=True)
    Path(f"{prefix}.stderr.txt").write_text(r.stderr)
    written = re.findall(r"VRAM写しを書き出した: (\S+) \(frame=\d+\)", r.stderr)
    if len(written) == len(paths):
        paths = written
    return r.returncode, paths, r.stderr


def char_row(path: str, row0: int) -> bytes:
    data = Path(path).read_bytes()
    off = row0 * STRIDE
    return data[off:off + COLS]


def diff_cells(before: str, after: str, rows=range(25)):
    b = Path(before).read_bytes()
    a = Path(after).read_bytes()
    out = []
    for r in rows:
        off = r * STRIDE
        for c in range(COLS):
            bv, av = b[off + c], a[off + c]
            if bv != av:
                out.append({"row0": r, "col0": c, "was_blank": bv == 0x20,
                            "char_after": f"{av:02X}" if bv == 0x20 else None})
    return out


def nonblank_rows(path: str):
    out = {}
    for r in range(25):
        n = sum(1 for b in char_row(path, r) if b != 0x20)
        if n:
            out[r] = n
    return out


def row_sig(path: str, row0: int):
    row = char_row(path, row0)
    norm = row.rstrip(b"\x20")
    return {"row_sha256": hashlib.sha256(norm).hexdigest(),
            "nonblank_count": sum(1 for b in row if b != 0x20),
            "normalized_length": len(norm)}


# ---- 腕の定義 -------------------------------------------------------

MARKER_PREP = ["HOME", "q", "x", "z", "j", "k"]

MID_ARMS = {
    "arrow_left_mid": (MARKER_PREP + ["LEFT", "LEFT", "LEFT"], "LEFT", False),
    "arrow_right_mid": (MARKER_PREP + ["LEFT", "LEFT", "LEFT"], "RIGHT", False),
    "arrow_up_mid": (MARKER_PREP + ["LEFT", "LEFT", "LEFT"], "UP", False),
    "arrow_down_mid": (MARKER_PREP + ["LEFT", "LEFT", "LEFT"], "DOWN", False),
    "insdel_noshift_mid": (MARKER_PREP + ["LEFT", "LEFT", "LEFT"], "DEL", False),
    "insdel_shift_mid": (MARKER_PREP + ["LEFT", "LEFT", "LEFT"], "DEL", True),
    "homeclr_noshift_mid": (MARKER_PREP + ["LEFT", "LEFT", "LEFT"], "HOME", False),
    "homeclr_shift_mid": (MARKER_PREP + ["LEFT", "LEFT", "LEFT"], "HOME", True),
}

BOUNDARY_ARMS = {
    # (prep_tokens, target_port, target_bit, target_hold)
    "B1": (["HOME"], "0A", 2, 4),
    "B2": (["HOME", "DOWN"], "0A", 2, 4),
    "B2p": (["HOME", "q", "DOWN", "LEFT"], "0A", 2, 4),
    "B3": (["HOME"], "08", 3, 4),
    "B3p": (["HOME", "q", "DOWN", "LEFT"], "08", 3, 4),
    "B4": (["HOME"], "08", 2, 600),
}

S1G_ARMS = {
    "R1a": ["HOME", "p", "r", "i", "n", "t", " ", "1", "2", "LEFT", "LEFT", "4", "RETURN"],
    "R1b": ["HOME", "p", "r", "i", "n", "t", " ", "1", "2", "LEFT", "LEFT", "4", "RIGHT", "RETURN"],
    "R1c": ["HOME", "p", "r", "i", "n", "t", " ", "1", "2", "LEFT", "LEFT", "4"] + ["LEFT"] * 7 + ["RETURN"],
    "U1": ["HOME", "p", "r", "i", "n", "t", " ", "1", "2", "RETURN", "UP", "UP", "RIGHT",
           "9", "9", "LEFT", "LEFT", "LEFT", "UP", "RETURN"],
    "T1": ["HOME", "p", "r", "i", "n", "t", " ", "1", "2", "3", "LEFT", "LEFT", "LEFT", "4", "RETURN"],
    "T2": ["HOME", "p", "r", "i", "n", "t", " ", "1", "2", "3", "LEFT", "LEFT", "LEFT", "4", "RIGHT", "RETURN"],
    "PC1": ["HOME", "p", "r", "i", "n", "t", " ", "1", "2", "RETURN"],
    "E1": ["HOME", "n", "e", "w", "RETURN", "1", "0", " ", "p", "r", "i", "n", "t", " ", "1", "2", "RETURN",
           "l", "i", "s", "t", "RETURN", "UP", "UP"] + ["RIGHT"] * 9 + ["4", "RETURN", "r", "u", "n", "RETURN"],
}

# ---- l4-s1h キーリピート適合の腕 ------------------------------------
# docs/notes/l4-s1h-key-repeat-results.md（事前登録c9d5935+追補）が
# 確定したQ1(qキー時系列)・Q2(→の6腕)・Q3(→単発の列79越え)・
# G4/G5(陽性・陰性対照)をそのまま流用する。フレーム設計
# (press_frame=end+16、D=10、mark_frameの間隔24)はl4-s1hの
# tools/l4_key_repeat_record.pyと同じ値を使う(器具の再利用、二重実装
# しない——数値だけこちらにも複製する形になるが、q88measureの呼び出し
# 方自体はrun_q88/build_tokens/diff_cellsをそのまま使う)。

S1H_D = 10
S1H_SWEEP_OFFSETS = [30, 35, 40, 45, 50, 55, 60, 90, 150, 210, 270, 330, 390, 420, 450]

# 腕名 -> HOLD(qキー)。Noneは無打鍵(G5陰性対照)。
S1H_SWEEP_ARMS = {
    "s1h_q1_main": 400,
    "s1h_g4_pos": 4,
    "s1h_g5_neg": None,
}

# 腕名 -> (起点トークン列, →キーのHOLD)
S1H_LANDING_ARMS = {
    "s1h_q2_a": (["HOME"], 4),
    "s1h_q2_b": (["HOME"], 26),
    "s1h_q2_c": (["HOME"], 34),
    "s1h_q2_d": (["HOME"], 40),
    "s1h_q2_e": (["HOME"], 60),
    "s1h_q2_f": (["HOME"], 600),
    "s1h_q3_main": (["HOME", "DOWN", "LEFT"], 4),
}

ALL_ARM_NAMES = (list(MID_ARMS) + list(BOUNDARY_ARMS) + list(S1G_ARMS)
                  + list(S1H_SWEEP_ARMS) + list(S1H_LANDING_ARMS))


def run_s1h_sweep_arm(romdir: str, name: str, workdir: Path):
    hold = S1H_SWEEP_ARMS[name]
    km, end = build_tokens(["HOME"])
    press_frame = end + 16
    dump_before = press_frame - 2
    dumps = [("d0", dump_before)]
    for i, off in enumerate(S1H_SWEEP_OFFSETS):
        dumps.append((f"d{i + 1}", press_frame + off))
    kms = list(SETTLE) + km
    if hold is not None:
        kms = kms + [(*CHAR["q"], press_frame, hold)]
    total = dumps[-1][1] + 40
    prefix = str(workdir / name)
    rc, paths, err = run_q88(romdir, kms, dumps, prefix, total)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    d0 = paths[0]
    series = [diff_cells(d0, p) for p in paths[1:]]
    return {"rc": rc, "series_diffs": series}


def run_s1h_landing_arm(romdir: str, name: str, workdir: Path):
    start_tokens, hold = S1H_LANDING_ARMS[name]
    km, end = build_tokens(list(start_tokens))
    target_frame = end + 16
    dump_before = target_frame - 2
    km.append((*SPECIAL["RIGHT"], target_frame, hold))
    after_target = target_frame + hold + S1H_D
    mark_frame = after_target + 24
    km.append((*CHAR["w"], mark_frame, 4))
    after_mark = mark_frame + 4 + S1H_D
    total = after_mark + 30
    prefix = str(workdir / name)
    rc, paths, err = run_q88(romdir, SETTLE + km,
                              [("before", dump_before), ("aftertarget", after_target),
                               ("aftermark", after_mark)],
                              prefix, total)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    before_p, at_p, am_p = paths
    return {"rc": rc, "mark_diff": diff_cells(at_p, am_p)}


def run_mid_arm(romdir: str, name: str, workdir: Path):
    prep, target, shift = MID_ARMS[name]
    km, end = build_tokens(prep)
    target_frame = end + 24 - 8
    port, bit = SPECIAL.get(target) or CHAR[target]
    if shift:
        km.append(("08", 6, target_frame - 10, 19))
    km.append((port, bit, target_frame, 4))
    mark_frame = target_frame + 4 + 24
    km.append((*CHAR["w"], mark_frame, 4))
    before = target_frame - 2
    after_target = target_frame + 4 + 10
    after_mark = mark_frame + 4 + 10
    total = after_mark + 30
    prefix = str(workdir / name)
    rc, paths, err = run_q88(romdir, SETTLE + km,
                              [("before", before), ("aftertarget", after_target), ("aftermark", after_mark)],
                              prefix, total)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    before_p, at_p, am_p = paths
    return {"rc": rc, "q1": diff_cells(before_p, at_p), "q3": diff_cells(at_p, am_p)}


def run_boundary_arm(romdir: str, name: str, workdir: Path):
    prep, port, bit, hold = BOUNDARY_ARMS[name]
    km, end = build_tokens(prep)
    target_frame = end + 24 - 8
    km.append((port, bit, target_frame, hold))
    mark_frame = target_frame + hold + 24
    km.append((*CHAR["w"], mark_frame, 4))
    before = target_frame + hold + 10 - 2
    after = mark_frame + 4 + 10
    total = after + 30
    prefix = str(workdir / name)
    rc, paths, err = run_q88(romdir, SETTLE + km, [("after", before), ("mark", after)], prefix, total)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    a, m = paths
    return {"rc": rc, "mark_diff": diff_cells(a, m)}


def run_s1g_arm(romdir: str, name: str, workdir: Path, settle_after: int = 250):
    tokens = S1G_ARMS[name]
    km, end = build_tokens(tokens)
    if len(km) >= 2:
        pport, pbit, pfr, phold = km[-2]
        port, bit, fr, hold = km[-1]
        km[-1] = (port, bit, pfr + phold + 24, hold)
    last_fr = km[-1][2]
    before = last_fr - 2
    after = last_fr + km[-1][3] + settle_after
    total = after + 30
    prefix = str(workdir / name)
    rc, paths, err = run_q88(romdir, SETTLE + km, [("before", before), ("after", after)], prefix, total)
    if rc != 0:
        return {"rc": rc, "err_tail": err[-300:]}
    before_p, after_p = paths
    nb_before = nonblank_rows(before_p)
    nb_after = nonblank_rows(after_p)
    new_rows = {r: c for r, c in nb_after.items() if nb_before.get(r, 0) == 0}
    sigs = {str(r): row_sig(after_p, r) for r in new_rows}
    return {"rc": rc, "new_row_sigs": sigs}


def run_arm(romdir: str, name: str, workdir: Path):
    if name in MID_ARMS:
        return run_mid_arm(romdir, name, workdir)
    if name in BOUNDARY_ARMS:
        return run_boundary_arm(romdir, name, workdir)
    if name in S1G_ARMS:
        return run_s1g_arm(romdir, name, workdir)
    if name in S1H_SWEEP_ARMS:
        return run_s1h_sweep_arm(romdir, name, workdir)
    if name in S1H_LANDING_ARMS:
        return run_s1h_landing_arm(romdir, name, workdir)
    raise SystemExit(f"未知の腕: {name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom-dir", required=True)
    ap.add_argument("--arm", default="all", help="腕名、または 'all'")
    ap.add_argument("--workdir", required=True, help="写しを書く作業ディレクトリ(リポジトリ外)")
    args = ap.parse_args()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    names = ALL_ARM_NAMES if args.arm == "all" else [args.arm]
    result = {}
    for name in names:
        result[name] = run_arm(args.rom_dir, name, workdir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

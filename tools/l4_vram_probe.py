#!/usr/bin/env python3
"""PC88Behavior: M7 段階1の器具その3 — テキストVRAMの写しと範囲指定書き込み
記録から、画面本文を1文字も出さずに目印文字列の位置・属性・書き込みの
形だけを取り出す解析道具。

入力:
  --vram-dump PATH ...   --vram-dump が書いた生バイナリ（F3C8-FF7F、
                         3000バイト＝1行120バイト(文字80+属性40)×25行）。
                         複数指定可。
  --marker STR           目印文字列（ASCII、既定 "Q7Z"）
  --mem-write-log PATH   --mem-write-log が書いたテキスト記録（任意）
  --iolog PATH           tools/*.iolog.txt 形式のI/Oログ（任意、.gz可）

起点: 行(row0)・桁(col0)は 0始まり（N88-BASIC の LOCATE x,y に合わせる。
リファレンスマニュアル 2-135）。番地は addr = 0xF3C8 + row0*120 + col0。
出力には常に origin=0 とこの式を明記する。

出力してよいもの（これ以外は出さない。CLAUDE.md 禁止事項7 を厳守）:
  1. 目印の出現位置 (行row0, 桁col0, 番地) の一覧
  2. 目印を含む行の属性域40バイト(16進)
  3. 目印を含まない行について、属性域が「目印の無い行で最も多い並び」と
     同じかどうかの真偽と件数（並び自体はハードウェア設定値なので出してよい）
  4. 書き込み記録の要約（番地範囲ごとの件数、連続書き込みの長さ分布、
     発行元PCの一覧と件数、フレームごとの件数）。値(value)は出さない。
     ただし目印そのものを書いた連続書き込みは、番地・PC・フレームに限り
     「目印の書き込み」として出してよい。
  5. I/Oログのうち DMA/CRTC 関係ポート(0x50/0x51, 0x60-0x68)へのOUTの列
     (ポート番号・値・PC・seq・frame。これはハードウェア設定値であって
     画面本文ではない)

文字域(0-79バイト目)の生バイト値そのものは、目印一致判定にしか使わず、
一致しなかった範囲もマーカー以外の値も一切出力しない。

差分モード（M7 段階1の器具その4。キー割り当て測定用）:
  --diff-before PATH --diff-after PATH
                         押す前・押した後の写し(2枚1組)を比較する。

  出してよいもの（これ以外は出さない）:
    1. 文字域で値が変わったセルの一覧: (row0, col0, addr)
    2. そのうち押す前が空白(0x20)だったセルについてだけ、押した後の
       文字コード(16進)
    3. 押す前が空白でなかったセルが変わった場合は、そのセルの
       (row0, col0, addr) と「前が空白でない」印だけ。前後の値そのもの
       (画面本文)は出さない
    4. 属性域で変わったバイトの (row0, 属性域内位置0-39, addr) と前後の値
       (属性はハードウェアの設定値であって画面本文ではないので出してよい)
    5. 変化件数の合計(文字域・属性域それぞれ)

  --count-only-rows ROW0[,ROW0...]（M7 段階1の器具その4追補。
      l4-s1b Q2 の SHIFT 修飾でファンクションキー表示行が動く問題への対応）
                         指定した行(0始まり、カンマ区切り複数可)で変わった
                         セルは、文字コードも位置も一切出さず、その行ごとの
                         変化件数(文字域・属性域それぞれ)だけを出す。
                         ファンクションキー表示の文字はROMのデータ表であり
                         この測定では扱わないため。見出しに指定した行番号を
                         明記する。指定しなければ従来どおり(全行を通常の
                         差分として扱う)。

自己検査: tools/screen_content_leak_selftest.sh に合成データでの検査を
追加してある（本ツール分。差分モードも含む）。単体でも下記で素朴に
確認できる:
    python3 tools/l4_vram_probe.py --vram-dump <dump> [--marker Q7Z] \\
        [--mem-write-log <log>] [--iolog <iolog>] [--json]
    python3 tools/l4_vram_probe.py --diff-before <before> --diff-after <after> [--json]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = 0xF3C8
ROWS = 25
COLS = 80
STRIDE = 120
ATTR_BYTES = 40
TOTAL_BYTES = ROWS * STRIDE  # 3000

MEMLOG_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s*$"
)
MEMLOG_RANGE_RE = re.compile(r"^range\s*:\s*([0-9A-Fa-f]{4})-([0-9A-Fa-f]{4})\s*$")

IOLOG_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+"
    r"([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2}|--)\s+([0-9A-Fa-f]{4})\s*$"
)

# 対象ポート(絶対番地4桁表記)。CRTC: 0x50/0x51。DMA: 0x60-0x68。
TARGET_PORTS = {f"{p:04X}" for p in [0x50, 0x51]} | {
    f"{p:04X}" for p in range(0x60, 0x69)
}


def _open_maybe_gz(path: str):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


# ---- 1. VRAM写しの読み込みと目印検出 --------------------------------------


def load_vram_dump(path: str) -> bytes:
    data = Path(path).read_bytes()
    if len(data) != TOTAL_BYTES:
        raise ValueError(
            f"{path}: サイズが {TOTAL_BYTES} バイトでない (実際 {len(data)})"
        )
    return data


def char_rows(data: bytes) -> list[bytes]:
    """各行の文字域(先頭80バイト)だけを抜き出す。属性域には触れない。"""
    return [data[r * STRIDE : r * STRIDE + COLS] for r in range(ROWS)]


def attr_rows(data: bytes) -> list[bytes]:
    return [data[r * STRIDE + COLS : r * STRIDE + COLS + ATTR_BYTES] for r in range(ROWS)]


def find_marker_occurrences(data: bytes, marker: bytes) -> list[dict]:
    """行の文字域だけを連結した平坦列上で目印を探す。行またぎも自然に
    扱える(連結列に切れ目が無いため)。0件なら空リストを返す。"""
    if not marker:
        return []
    rows = char_rows(data)
    flat = b"".join(rows)  # 2000バイト、文字域のみ
    occurrences = []
    start = 0
    while True:
        idx = flat.find(marker, start)
        if idx < 0:
            break
        row0 = idx // COLS
        col0 = idx % COLS
        # screen_content_leak_selftest.sh 専用の故障注入(陰性対照用)。既定では
        # 無効。起点(0始まり)を取り違えた実装を模して +1 した値を返す——
        # f2(既知位置の陽性対照)がその取り違えを実際に検出できるかを
        # 確かめるためだけに使う。
        if os.environ.get("Q88MEASURE_FAULT_OFFSET_ORIGIN_VRAM_PROBE"):
            row0 += 1
            col0 += 1
        addr = BASE + row0 * STRIDE + col0
        spans_rows = (col0 + len(marker)) > COLS
        occurrences.append(
            {
                "row0": row0,  # 0始まり(LOCATE x,y に合わせる)
                "col0": col0,  # 0始まり(LOCATE x,y に合わせる)
                "addr": f"{addr:04X}",
                "spans_row_boundary": spans_rows,
            }
        )
        start = idx + 1  # 重なりも見つける
    return occurrences


def analyze_dump(path: str, marker: bytes) -> dict:
    data = load_vram_dump(path)
    rows = char_rows(data)
    occs = find_marker_occurrences(data, marker)
    marker_rows = set()
    for o in occs:
        marker_rows.add(o["row0"])
        if o["spans_row_boundary"]:
            marker_rows.add(o["row0"] + 1)  # 次の行(0始まり)も目印を含む

    attrs = attr_rows(data)
    attr_hex = [a.hex().upper() for a in attrs]

    non_marker_attr_hex = [attr_hex[r] for r in range(ROWS) if r not in marker_rows]
    mode_attr = None
    mode_count = 0
    if non_marker_attr_hex:
        counter = Counter(non_marker_attr_hex)
        mode_attr, mode_count = counter.most_common(1)[0]

    non_marker_detail = []
    match_count = 0
    mismatch_count = 0
    for r in range(ROWS):
        if r in marker_rows:
            continue
        is_match = mode_attr is not None and attr_hex[r] == mode_attr
        if is_match:
            match_count += 1
        else:
            mismatch_count += 1
        non_marker_detail.append({"row0": r, "matches_mode": is_match})

    marker_row_attrs = [
        {"row0": r, "attr_hex": attr_hex[r]} for r in sorted(marker_rows)
    ]

    result = {
        "path": path,
        "origin": 0,
        "addr_formula": "addr = 0xF3C8 + row0*120 + col0",
        "marker": marker.decode("ascii", errors="replace"),
        "occurrences": occs,
        "occurrence_count": len(occs),
        "marker_row_attrs": marker_row_attrs,
        "non_marker_attr_mode": mode_attr,
        "non_marker_attr_mode_count": mode_count,
        "non_marker_match_count": match_count,
        "non_marker_mismatch_count": mismatch_count,
        "non_marker_rows": non_marker_detail,
    }

    # screen_content_leak_selftest.sh 専用の故障注入(陰性対照用)。既定では
    # 環境変数が無いので何もしない。設定すると、目印の無い行の文字域を
    # そのまま出力へ混ぜる——検査器(この自己検査そのもの)が実際に本文漏れを
    # 検出できるかを確かめるための対照。
    if os.environ.get("Q88MEASURE_FAULT_LEAK_VRAM_PROBE"):
        result["_debug_non_marker_char_rows"] = [
            rows[r].decode("latin-1") for r in range(ROWS) if r not in marker_rows
        ]

    return result


# ---- 1b. 差分モード(押す前/押した後の写しの比較) ---------------------------


def diff_vram_dumps(
    before_path: str, after_path: str, count_only_rows: "set[int] | None" = None
) -> dict:
    """押す前・押した後の写しを比較し、変化したセルの位置だけを返す。

    文字域: 変化した (row0, col0, addr) は必ず返すが、値そのものは
    「押す前が空白(0x20)だった」場合に限り after 側の文字コードだけを返す。
    それ以外(押す前が空白でなかった)は位置と印だけで、前後の値は出さない
    (起動画面などの本文を出さないため)。
    属性域: 変化した (row0, 属性域内位置0-39, addr) と前後の値を返す
    (属性はハードウェアの設定値であって画面本文ではない)。

    count_only_rows: 指定した行(0始まり)は、文字コードも位置も一切出さず、
    その行の変化件数(文字域・属性域それぞれ)だけを別枠(count_only_summary)
    に集計する。ファンクションキー表示行など、ROMのデータ表にあたる文字を
    扱わないための出口(l4-s1b Q2 SHIFT追補)。
    """
    before = load_vram_dump(before_path)
    after = load_vram_dump(after_path)
    count_only_rows = count_only_rows or set()
    # screen_content_leak_selftest.sh 専用の故障注入(陰性対照用)。既定では
    # 無効。設定すると --count-only-rows の指定を無視して通常の差分として
    # 扱う——検査器(この自己検査そのもの)が「指定行が本当に伏せられて
    # いるか」を実際に検出できるかを確かめるための対照。
    if os.environ.get("Q88MEASURE_FAULT_IGNORE_COUNT_ONLY_ROWS"):
        count_only_rows = set()

    char_changes = []
    char_change_total = 0
    count_only_char = {r: 0 for r in count_only_rows}
    for row in range(ROWS):
        base_row = row * STRIDE
        for col in range(COLS):
            idx = base_row + col
            b_before = before[idx]
            b_after = after[idx]
            if b_before == b_after:
                continue
            char_change_total += 1
            if row in count_only_rows:
                count_only_char[row] += 1
                continue
            addr = BASE + row * STRIDE + col
            entry = {"row0": row, "col0": col, "addr": f"{addr:04X}"}
            if b_before == 0x20:
                entry["was_blank"] = True
                entry["char_after"] = f"{b_after:02X}"
            else:
                entry["was_blank"] = False
            char_changes.append(entry)

    attr_changes = []
    attr_change_total = 0
    count_only_attr = {r: 0 for r in count_only_rows}
    for row in range(ROWS):
        base_row = row * STRIDE + COLS
        for pos in range(ATTR_BYTES):
            idx = base_row + pos
            a_before = before[idx]
            a_after = after[idx]
            if a_before == a_after:
                continue
            attr_change_total += 1
            if row in count_only_rows:
                count_only_attr[row] += 1
                continue
            addr = BASE + row * STRIDE + COLS + pos
            attr_changes.append(
                {
                    "row0": row,
                    "pos0": pos,
                    "addr": f"{addr:04X}",
                    "before": f"{a_before:02X}",
                    "after": f"{a_after:02X}",
                }
            )

    result = {
        "before_path": before_path,
        "after_path": after_path,
        "origin": 0,
        "addr_formula": "addr = 0xF3C8 + row0*120 + col0 (文字域は col0=0-79、"
        "属性域は addr = 0xF3C8 + row0*120 + 80 + pos0、pos0=0-39)",
        "char_change_note": "char_after は押す前が空白(0x20)だったセルのみ。"
        "それ以外は was_blank=false のみで前後の値は出さない。"
        "count_only_rows に指定した行は文字コードも位置も出さず件数のみ。",
        "count_only_rows": sorted(count_only_rows),
        "char_changes": char_changes,
        "attr_changes": attr_changes,
        "char_change_count": char_change_total,
        "attr_change_count": attr_change_total,
        "count_only_summary": [
            {
                "row0": r,
                "char_change_count": count_only_char[r],
                "attr_change_count": count_only_attr[r],
            }
            for r in sorted(count_only_rows)
        ],
    }

    # screen_content_leak_selftest.sh 専用の故障注入(陰性対照用)。既定では
    # 無効。設定すると「前が空白でなかったセル」の前後の値もそのまま
    # 出す——検査器(この自己検査そのもの)が実際に本文漏れを検出できるかを
    # 確かめるための対照。analyze_dump() の同名フラグと役割を揃えてある。
    if os.environ.get("Q88MEASURE_FAULT_LEAK_VRAM_PROBE"):
        debug = []
        for row in range(ROWS):
            base_row = row * STRIDE
            for col in range(COLS):
                idx = base_row + col
                b_before = before[idx]
                b_after = after[idx]
                if b_before != b_after and b_before != 0x20:
                    debug.append(
                        {
                            "row0": row,
                            "col0": col,
                            "before": f"{b_before:02X}",
                            "after": f"{b_after:02X}",
                        }
                    )
        result["_debug_non_blank_before_values"] = debug

    return result


# ---- 2. mem-write-log の要約 -----------------------------------------------


def parse_mem_write_log(path: str):
    events = []
    range_lo = range_hi = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = MEMLOG_RANGE_RE.match(line.strip())
            if m:
                range_lo, range_hi = m.group(1), m.group(2)
                continue
            m = MEMLOG_ROW_RE.match(line)
            if not m:
                continue
            seq, frame, pc, addr, value = m.groups()
            events.append(
                {
                    "seq": int(seq),
                    "frame": int(frame),
                    "pc": pc.upper(),
                    "addr": int(addr, 16),
                    "value": int(value, 16),
                }
            )
    events.sort(key=lambda e: e["seq"])
    return events, range_lo, range_hi


def contiguous_blocks(events: list[dict]) -> list[list[dict]]:
    """seq順に並んだイベントのうち、番地が+1ずつ連続する塊(ブロック転送
    らしさ)をまとめる。"""
    blocks: list[list[dict]] = []
    cur: list[dict] = []
    prev_addr = None
    for e in events:
        if cur and prev_addr is not None and e["addr"] == prev_addr + 1:
            cur.append(e)
        else:
            if cur:
                blocks.append(cur)
            cur = [e]
        prev_addr = e["addr"]
    if cur:
        blocks.append(cur)
    return blocks


def find_marker_writes(blocks: list[list[dict]], marker: bytes) -> list[dict]:
    """連続番地ブロックの中に、値の並びが目印と一致する窓があれば
    「目印の書き込み」として番地・PC・フレームだけ返す(値は返さない)。"""
    found = []
    n = len(marker)
    if n == 0:
        return found
    for block in blocks:
        vals = [e["value"] for e in block]
        for i in range(0, len(vals) - n + 1):
            if bytes(vals[i : i + n]) == marker:
                window = block[i : i + n]
                found.append(
                    {
                        "addr_start": f"{window[0]['addr']:04X}",
                        "addr_end": f"{window[-1]['addr']:04X}",
                        "pc": window[0]["pc"],
                        "frame_start": window[0]["frame"],
                        "frame_end": window[-1]["frame"],
                    }
                )
    return found


def addr_range_bucket(addr: int) -> str:
    lo = (addr // 0x100) * 0x100
    return f"{lo:04X}-{lo + 0xFF:04X}"


def summarize_mem_write_log(path: str, marker: bytes) -> dict:
    events, range_lo, range_hi = parse_mem_write_log(path)
    range_counts = Counter(addr_range_bucket(e["addr"]) for e in events)
    blocks = contiguous_blocks(events)
    block_len_dist = Counter(len(b) for b in blocks)
    pc_counts = Counter(e["pc"] for e in events)
    frame_counts = Counter(e["frame"] for e in events)
    marker_writes = find_marker_writes(blocks, marker)

    result = {
        "path": path,
        "range": f"{range_lo}-{range_hi}" if range_lo else None,
        "event_count": len(events),
        "addr_range_counts": dict(sorted(range_counts.items())),
        "block_length_distribution": dict(sorted(block_len_dist.items())),
        "pc_counts": dict(
            sorted(pc_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "frame_counts": dict(sorted(frame_counts.items())),
        "marker_writes": marker_writes,
    }

    # screen_content_leak_selftest.sh 専用の故障注入(陰性対照用)。既定では
    # 無効。設定すると全イベントの value をそのまま出す——検査器が
    # 「値を出していないか」を実際に検出できるかを確かめるための対照。
    if os.environ.get("Q88MEASURE_FAULT_LEAK_VRAM_PROBE"):
        result["_debug_values"] = [f"{e['value']:02X}" for e in events]

    return result


# ---- 3. I/Oログ中のDMA/CRTC関係ポート ---------------------------------------


def summarize_iolog_ports(path: str) -> dict:
    rows = []
    cur_cpu = None
    with _open_maybe_gz(path) as f:
        for line in f:
            if line.startswith("# main"):
                cur_cpu = "main"
                continue
            if line.startswith("# sub"):
                cur_cpu = "sub"
                continue
            if line.startswith("#") or not line.strip():
                continue
            m = IOLOG_ROW_RE.match(line)
            if not m:
                continue
            seq, clock, frame, cpu, kind, port, value_s, pc = m.groups()
            port_u = port.upper()
            if kind != "OUT":
                continue
            # ポートは4桁表記(例 0050, 0060)。下位バイトで対象ポートか判定する
            # (表記ゆれ対策)。
            try:
                low = f"{int(port_u, 16) & 0xFF:04X}"
            except ValueError:
                continue
            if port_u not in TARGET_PORTS and low not in TARGET_PORTS:
                continue
            port_u = low if low in TARGET_PORTS else port_u
            rows.append(
                {
                    "seq": int(seq),
                    "frame": int(frame),
                    "cpu": cur_cpu or cpu,
                    "port": port_u,
                    "value": None if value_s == "--" else value_s.upper(),
                    "pc": pc.upper(),
                }
            )
    return {"path": path, "out_events": rows, "count": len(rows)}


# ---- 出力 -------------------------------------------------------------


def render_text(result: dict) -> str:
    lines = []
    diff = result.get("vram_diff")
    if diff:
        lines.append(
            f"[vram-diff] before={diff['before_path']} after={diff['after_path']}"
            f" origin=0 addr_formula={diff['addr_formula']}"
        )
        lines.append(f"  note: {diff['char_change_note']}")
        lines.append(
            f"  char_change_count={diff['char_change_count']}"
            f" attr_change_count={diff['attr_change_count']}"
        )
        if diff.get("count_only_rows"):
            lines.append(f"  count_only_rows={diff['count_only_rows']}")
            for s in diff["count_only_summary"]:
                lines.append(
                    f"    count_only row0={s['row0']}"
                    f" char_change_count={s['char_change_count']}"
                    f" attr_change_count={s['attr_change_count']}"
                )
        for c in diff["char_changes"]:
            if c["was_blank"]:
                lines.append(
                    f"    char row0={c['row0']} col0={c['col0']} addr={c['addr']}"
                    f" was_blank=true char_after={c['char_after']}"
                )
            else:
                lines.append(
                    f"    char row0={c['row0']} col0={c['col0']} addr={c['addr']}"
                    f" was_blank=false"
                )
        for a in diff["attr_changes"]:
            lines.append(
                f"    attr row0={a['row0']} pos0={a['pos0']} addr={a['addr']}"
                f" before={a['before']} after={a['after']}"
            )
    for d in result.get("vram_dumps", []):
        lines.append(f"[vram-dump] {d['path']} origin=0 addr_formula={d['addr_formula']}")
        lines.append(f"  marker={d['marker']!r} occurrences={d['occurrence_count']}")
        for o in d["occurrences"]:
            lines.append(
                f"    row0={o['row0']} col0={o['col0']} addr={o['addr']}"
                f" spans_row_boundary={o['spans_row_boundary']}"
            )
        for mr in d["marker_row_attrs"]:
            lines.append(f"  marker_row0 {mr['row0']}: attr={mr['attr_hex']}")
        lines.append(
            f"  non_marker_attr_mode={d['non_marker_attr_mode']}"
            f" mode_count={d['non_marker_attr_mode_count']}"
            f" match={d['non_marker_match_count']}"
            f" mismatch={d['non_marker_mismatch_count']}"
        )
    for w in result.get("mem_write_logs", []):
        lines.append(f"[mem-write-log] {w['path']} range={w['range']} events={w['event_count']}")
        lines.append(f"  addr_range_counts={w['addr_range_counts']}")
        lines.append(f"  block_length_distribution={w['block_length_distribution']}")
        lines.append(f"  pc_counts={w['pc_counts']}")
        lines.append(f"  frame_counts={w['frame_counts']}")
        for mw in w["marker_writes"]:
            lines.append(f"  marker_write {mw}")
    for io in result.get("iolog", []):
        lines.append(f"[iolog] {io['path']} dma/crtc OUT count={io['count']}")
        for ev in io["out_events"]:
            lines.append(
                f"  seq={ev['seq']} frame={ev['frame']} cpu={ev['cpu']}"
                f" port={ev['port']} value={ev['value']} pc={ev['pc']}"
            )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vram-dump", action="append", default=[], help="写しファイル(複数可)")
    ap.add_argument("--marker", default="Q7Z", help="目印文字列(ASCII, 既定 Q7Z)")
    ap.add_argument("--mem-write-log", action="append", default=[], help="書き込み記録ファイル(複数可)")
    ap.add_argument("--iolog", action="append", default=[], help="I/Oログファイル(複数可、.gz可)")
    ap.add_argument("--diff-before", default=None, help="差分モード: 押す前の写し")
    ap.add_argument("--diff-after", default=None, help="差分モード: 押した後の写し")
    ap.add_argument(
        "--count-only-rows",
        default=None,
        help="差分モード: 指定した行(0始まり、カンマ区切り複数可)は"
        "文字コード・位置を出さず件数のみ出す(例: 19)",
    )
    ap.add_argument("--json", action="store_true", help="JSONで出力する(既定は人が読む要約)")
    # 陰性対照専用の故障注入。既定では無効。screen_content_leak_selftest.sh
    # が「検査に検出力があるか」を確かめるためだけに使う。
    args = ap.parse_args()

    if bool(args.diff_before) != bool(args.diff_after):
        ap.error("--diff-before と --diff-after は両方指定すること")

    if not (
        args.vram_dump
        or args.mem_write_log
        or args.iolog
        or (args.diff_before and args.diff_after)
    ):
        ap.error(
            "--vram-dump / --mem-write-log / --iolog / "
            "--diff-before+--diff-after のいずれかが必要"
        )

    marker = args.marker.encode("ascii")

    result = {
        "marker": args.marker,
        "vram_dumps": [analyze_dump(p, marker) for p in args.vram_dump],
        "mem_write_logs": [summarize_mem_write_log(p, marker) for p in args.mem_write_log],
        "iolog": [summarize_iolog_ports(p) for p in args.iolog],
    }
    if args.diff_before and args.diff_after:
        count_only_rows = set()
        if args.count_only_rows:
            count_only_rows = {int(x) for x in args.count_only_rows.split(",") if x.strip()}
        result["vram_diff"] = diff_vram_dumps(
            args.diff_before, args.diff_after, count_only_rows
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

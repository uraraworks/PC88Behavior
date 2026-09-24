#!/usr/bin/env python3
"""m6f-c 追補2(docs/notes/m6f-c-addendum2-blank-disk-in-drive2.md)向けの
共通部品。FDCコマンド列（analyze_write_path.parse_commands の出力）を
装置番号（param_values[0] の下位2ビット）で仕分ける。

ドライブ1に参照ディスク（公式diskAの使い捨て複製、書き込み保護は解除
しない）、ドライブ2に自作の空媒体を入れて測るため、測定ドライバ
tools/measure_m6fc.sh はこの関数を使って reads/writes/write_data_count へ
**装置番号1だけ**を入れ、装置番号0（ドライブ1）の件数は
drive1_read_count/drive1_write_count として別に数える
（追補2 §2 の2・3）。

値（セクタの中身）は一切扱わない。扱うのは座標(C,H,R)と件数だけ。
"""
from __future__ import annotations

from typing import Any, Iterable


def split_by_drive(commands: Iterable[Any], stim: int) -> dict[str, Any]:
    """stim(刺激フレーム)以降のREAD DATA(0x06)/WRITE DATA(0x05)コマンドを
    装置番号(param_values[0] & 3)で仕分ける。

    戻り値:
      reads/writes: 装置番号1(ドライブ2)だけのセクタ座標列 {"c","h","r"}
      write_data_count: 装置番号1へのWRITE DATAコマンド件数（コマンド単位、
        セクタ単位ではない）
      drive1_read_count/drive1_write_count: 装置番号0(ドライブ1)の
        READ DATA/WRITE DATAコマンド件数
    """
    reads: list[dict[str, int]] = []
    writes: list[dict[str, int]] = []
    write_data_count = 0
    drive1_read_count = 0
    drive1_write_count = 0
    for c in commands:
        if c.frame < stim or c.param_values is None or len(c.param_values) < 4:
            continue
        device = c.param_values[0] & 3
        base_c, base_h, base_r = c.param_values[1], c.param_values[2], c.param_values[3]
        if c.opcode == 0x06:  # READ DATA
            if device == 0:
                drive1_read_count += 1
                continue
            if device != 1:
                continue
            nsec = max(1, (c.result_bytes - 7) // 256) if c.result_bytes > 7 else 1
            for i in range(nsec):
                reads.append({"c": base_c, "h": base_h, "r": base_r + i})
        elif c.opcode == 0x05:  # WRITE DATA
            if device == 0:
                drive1_write_count += 1
                continue
            if device != 1:
                continue
            write_data_count += 1
            nsec = max(1, (c.data_bytes // 256)) if c.data_bytes else 1
            for i in range(nsec):
                writes.append({"c": base_c, "h": base_h, "r": base_r + i})
        # READ DATA/WRITE DATA以外は装置番号にかかわらず仕分けの対象にしない。
    return {
        "reads": reads,
        "writes": writes,
        "write_data_count": write_data_count,
        "drive1_read_count": drive1_read_count,
        "drive1_write_count": drive1_write_count,
    }

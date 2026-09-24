#!/usr/bin/env python3
"""tools/m6fc_fdc_by_drive.py の単体自己検査。合成の Command 相当の
オブジェクトだけを使い、公式ROM・公式ディスク・実iologには触れない。

装置番号0と1のFDCコマンドが混ざった入力を split_by_drive に渡し、
reads/writes/write_data_count には装置番号1だけが入り、装置番号0は
drive1_read_count/drive1_write_count という別欄の件数にしか現れない
ことを確かめる（m6f-c追補2 §2の2・3）。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from m6fc_fdc_by_drive import split_by_drive  # noqa: E402


@dataclass
class FakeCommand:
    opcode: int
    frame: int
    param_values: list[int] | None
    data_bytes: int = 0
    result_bytes: int = 7


rc = 0


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def ng(msg: str) -> None:
    global rc
    print(f"NG: {msg}")
    rc = 1


# 装置番号0(ドライブ1)と1(ドライブ2)のWRITE DATA/READ DATAが混ざった入力。
# param_values[0]の下位2ビットが装置番号。C,H,Rはparam_values[1..3]。
commands = [
    # 刺激より前: すべて無視される。
    FakeCommand(0x05, frame=100, param_values=[1, 0, 0, 1], data_bytes=256),
    # 装置番号0(ドライブ1)へのWRITE DATA×2、READ DATA×1。
    FakeCommand(0x05, frame=800, param_values=[0, 1, 0, 1], data_bytes=256),
    FakeCommand(0x05, frame=810, param_values=[0, 1, 0, 2], data_bytes=512),
    FakeCommand(0x06, frame=820, param_values=[0, 1, 0, 3], result_bytes=263),
    # 装置番号1(ドライブ2)へのWRITE DATA×1(2セクタ)、READ DATA×1。
    FakeCommand(0x05, frame=830, param_values=[1, 18, 1, 14], data_bytes=512),
    FakeCommand(0x06, frame=840, param_values=[1, 5, 0, 9], result_bytes=263),
    # 装置番号が3ビット目にも立っている(US1=1)場合も下位2ビットで仕分ける。
    FakeCommand(0x05, frame=850, param_values=[5, 2, 1, 4], data_bytes=256),
    # param_valuesが無い/短いコマンドは無視される(取りこぼしではなく除外)。
    FakeCommand(0x05, frame=860, param_values=None),
    FakeCommand(0x08, frame=870, param_values=[1, 0, 0, 0]),  # READ/WRITE以外
]

result = split_by_drive(commands, stim=700)

if result["writes"] == [
    {"c": 18, "h": 1, "r": 14}, {"c": 18, "h": 1, "r": 15},
    {"c": 2, "h": 1, "r": 4},
]:
    ok("writesに装置番号1だけが入った(2セクタ分割・US1混在も含む)")
else:
    ng(f"writesの内容が想定と不一致: {result['writes']}")

if result["reads"] == [{"c": 5, "h": 0, "r": 9}]:
    ok("readsに装置番号1だけが入った")
else:
    ng(f"readsの内容が想定と不一致: {result['reads']}")

if result["write_data_count"] == 2:
    ok("write_data_countは装置番号1のコマンド件数(2件)")
else:
    ng(f"write_data_countが想定と不一致: {result['write_data_count']}")

if result["drive1_read_count"] == 1 and result["drive1_write_count"] == 2:
    ok("装置番号0(ドライブ1)の件数がdrive1_read_count/drive1_write_countに分離された")
else:
    ng(f"drive1_*の件数が想定と不一致: read={result['drive1_read_count']} "
       f"write={result['drive1_write_count']}")

# 陰性対照: 装置番号で絞らずに全件をwritesへ入れる(壊れた実装)と、
# 装置番号0の分まで混ざってしまうことを確認する（検出力の裏取り）。
naive_writes = []
for c in commands:
    if c.frame < 700 or c.param_values is None or len(c.param_values) < 4 or c.opcode != 0x05:
        continue
    naive_writes.append({"c": c.param_values[1], "h": c.param_values[2], "r": c.param_values[3]})
if len(naive_writes) != len(result["writes"]):
    ok(f"陰性対照: 装置番号で絞らない素朴な実装は件数が変わる"
       f"(素朴={len(naive_writes)} 正しい={len(result['writes'])})")
else:
    ng("陰性対照: 装置番号で絞らなくても件数が変わらない(検出力なし)")

print()
if rc == 0:
    print("全項目 OK")
else:
    print("NG あり")
sys.exit(rc)

#!/usr/bin/env bash
# G7: m6i-a解析器の合成入力自己検査。エミュレータは起動しない。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYZE="$REPO/tools/analyze_m6ia_main_sub.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; rc=1; }

python3 - "$WORK" <<'PY'
from __future__ import annotations
import pathlib
import sys

work = pathlib.Path(sys.argv[1])
canary = "M6IA_SCREEN_BODY_CANARY_7f91"


def memlog(path: pathlib.Path, sector: int, *, request=True, missing_pos=False,
           completion=True, fault=False):
    rows = []
    def add(addr, value):
        rows.append((len(rows) + 1, 1, 0x7000, addr, value))
    for addr in range(0xE000, 0xE007):
        add(addr, 0)
    if fault:
        add(0xE004, 1)
    if request:
        add(0xE000, 1)
    if request and not fault:
        data = [((sector * 57 + i * 7 + 13) & 0xFF) for i in range(256)]
        for i, value in enumerate(data):
            if missing_pos and i == 127:
                continue
            add(0xDF00 + i, value)
        add(0xE001, 1)
        if completion:
            add(0xE002, 1)
    with path.open("w", encoding="utf-8") as fp:
        fp.write("# synthetic memlog\nrange     : DF00-E038\n\n")
        fp.write("# seq frame pc addr value\n")
        for seq, frame, pc, addr, value in rows:
            fp.write(f"{seq:6d} {frame:7d}  {pc:04X}  {addr:04X}   {value:02X}\n")
        fp.write(f"# 取りこぼし: 0件 / 総イベント数: {len(rows)}件\n")


def iolog(path: pathlib.Path, sector: int, *, request=True, fault=False):
    rows = []
    clock = 0
    def add(cpu, kind, port, value):
        nonlocal clock
        clock += 1
        rows.append((clock, clock, 1, cpu, kind, port, value, 0x4000))
    if request:
        for value in (0x02, 0, 0, 0, sector, 0x06):
            add("main", "OUT", 0xFD, value)
        if not fault:
            add("main", "IN", 0xFC, 0xC0)
            add("main", "OUT", 0xFD, 0x12)
            for i in range(256):
                add("main", "IN", 0xFC, (sector * 57 + i * 7 + 13) & 0xFF)
            add("sub", "OUT", 0xFB, 0x06)
            for value in (0, 0, 0, sector, 1, 16, 0x1B, 0xFF):
                add("sub", "OUT", 0xFB, value)
            for _ in range(263):
                add("sub", "IN", 0xFB, 0)
    with path.open("w", encoding="utf-8") as fp:
        fp.write("# synthetic iolog\n# main\n")
        for row in rows:
            seq, clk, frame, cpu, kind, port, value, pc = row
            fp.write(f"{seq:6d} {clk:7d} {frame:6d}  {cpu:<4}  {kind:<4}  "
                     f"{port:04X}   {value:02X}   {pc:04X}\n")
        fp.write("# 取りこぼし: 0件 / 総イベント数: 1件\n\n")
        fp.write("# sub\n# 取りこぼし: 0件 / 総イベント数: 1件\n")


def report(path: pathlib.Path):
    path.write_text(
        "# synthetic report\n[測定終了時のテキスト画面]\n"
        f"   2| q{canary}\n\n", encoding="utf-8")


def make(name, sector=1, **kwargs):
    memlog(work / f"{name}.mem.txt", sector, **kwargs)
    iolog(work / f"{name}.io.txt", sector,
          request=kwargs.get("request", True), fault=kwargs.get("fault", False))
    report(work / f"{name}.report.txt")


make("a0", 1)
make("a1", 2)
make("no_request", 1, request=False)
make("missing_pos", 1, missing_pos=True)
make("no_completion", 1, completion=False)
make("fault_ok", 1, fault=True)
make("fault_missing", 1, request=False)
PY

run_case() {
  local arm="$1" name="$2"
  local out="$WORK/${name}.out" err="$WORK/${name}.err"
  python3 "$ANALYZE" --arm "$arm" --memlog "$WORK/${name}.mem.txt" \
    --iolog "$WORK/${name}.io.txt" --report "$WORK/${name}.report.txt" \
    >"$out" 2>"$err"
}

if run_case A0 a0 && run_case A1 a1; then
  if python3 - "$WORK/a0.out" "$WORK/a1.out" <<'PY'
import json, sys
a = json.loads(open(sys.argv[1], encoding="utf-8").read())
b = json.loads(open(sys.argv[2], encoding="utf-8").read())
raise SystemExit(0 if a["receive_sha256"] != b["receive_sha256"] else 1)
PY
  then ok "異なる2セクタのSHA-256を識別"; else ng "異なるSHAを識別できない"; fi
else
  ng "正常なA0/A1合成入力が通らない"
fi

if run_case A0 no_request; then ng "要求run欠落を通した"; else ok "要求run欠落を不合格として検出"; fi
if run_case A0 missing_pos; then ng "受信1位置欠落を通した"; else ok "受信1位置欠落を不合格として検出"; fi
if run_case A0 no_completion; then ng "完了印欠落を通した"; else ok "完了印欠落を不合格として検出"; fi
if run_case A3 fault_missing; then ng "故障注入マーカー欠落を通した"; else ok "故障注入マーカー欠落を不合格として検出"; fi
if run_case A3 fault_ok; then ok "故障注入マーカーありの陰性対照を検出済みとして受理"; else ng "故障注入の陽性対照が通らない"; fi

if grep -R -q 'M6IA_SCREEN_BODY_CANARY_7f91' "$WORK"/*.out "$WORK"/*.err; then
  ng "画面本文カナリアが標準出力または標準エラーへ漏れた"
else
  ok "画面本文・データ列を標準出力／標準エラーへ出さない"
fi

if [ "$rc" -eq 0 ]; then
  echo "G7: rc=0"
else
  echo "G7: rc=1" >&2
fi
exit "$rc"

#!/usr/bin/env bash
# tools/ext_bank_selftest.sh — 拡張ROMバンク(4th ROM)の土台の自己検査。
# **公式ROMは要らない**（自作ROMだけで完結する）。
#
# 根拠: docs/spec/ext-rom-bank.md。
#
# 検査:
#   1. 通常ビルド（--enable-ext-bank-selftestを付けない）が壊れないこと、
#      N88_0.ROM〜N88_3.ROM(各8KB)が生成されること、各バンクの中身が
#      土台どおり(試験エントリ1つ+FILL埋め)であること。
#   2. 自己検査ビルド（--enable-ext-bank-selftest）: 常駐部からEXT_BANK_CALL
#      経由でバンク0-3を呼び、それぞれ期待値(0xB0-0xB3)が返ること
#      （常駐部からの呼び出し）。窓の中(run.asm相当)に置いたプローブ経由の
#      呼び出しも成功すること（窓の中からの呼び出し）。割り込みを
#      有効にしたまま200回連続で呼んでも全数一致すること（多数回呼び出し）。
#      バンク0の絶対番地試験(CALL/JP/LD A,(nn)、EXT_BANK0_ABS_TEST_ENTRY)が
#      ORG 0x6000起点で正しく動くこと。バンク0の試験ルーチンが常駐の
#      単精度演算(MBF_ADD)をCALLして1.0+2.0=3.0を正しく返すこと
#      (EXT_BANK0_MBF_TEST_ENTRY、docs/spec/ext-rom-bank.md 第2節 制約3)。
#      結果はRAM(E8C0-E8D0)をmem-write-logで読む。画面へは一切出さない。
#   3. 陰性対照（--inject-ext-bank-no-org-fault）: bank0.asmのORG 0x6000/
#      0x6010を0始まりへ書き換えて組み立てたバンクで、絶対番地試験が
#      実際に不一致を検出すること(検出力の確認)。
#   4. 陰性対照（--inject-ext-bank-window-fault）: 中継ルーチンを窓の中へ
#      INCLUDE順序ごと移した故障注入ビルドで、ビルド時検査
#      (check_ext_bank_relay_below_window)がSystemExitで落ちること。
#   5. 陰性対照（--inject-ext-bank-mbf-addr-fault）: bank0.asmへ渡す常駐
#      MBF_ADDの番地をわざとMBF_SUBへ取り違えたビルドで、MBF自己検査が
#      実際に不一致を検出すること(密結合がズレた場合の検出力の確認)。
#   6. 既存の tools/l3_main_selftest.sh・tools/conform_l4.sh・
#      tools/check_rom_version_reserved.shが引き続きOKであること
#      (拡張ROMバンクの追加がL1タイミング・既存配置を壊していない)。
#
# 使い方: tools/ext_bank_selftest.sh

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
BUILD="$REPO/src/build_main_rom.py"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
fail() { echo "NG: $1" >&2; FAILED=1; }

FAILED=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi
make -s -C "$REPO/tools/harness/frontend" || exit 1

# -----------------------------------------------------------------------
say "1. 通常ビルド（--enable-ext-bank-selftestは付けない）とバンクROMの中身"
NORMAL_ROM="$WORK/rom_normal"
if ! python3 "$BUILD" "$NORMAL_ROM" >"$WORK/build_normal.txt" 2>&1; then
  fail "build_main_rom.py(通常)が失敗"; cat "$WORK/build_normal.txt" >&2
fi
for i in 0 1 2 3; do
  f="$NORMAL_ROM/N88_${i}.ROM"
  if [ ! -f "$f" ]; then fail "N88_${i}.ROM が無い"; continue; fi
  size="$(wc -c < "$f" | tr -d ' ')"
  if [ "$size" != "8192" ]; then fail "N88_${i}.ROM のサイズが8192でない($size)"; fi
done
python3 - "$NORMAL_ROM" << 'PYEOF' || FAILED=1
import pathlib, sys
outdir = pathlib.Path(sys.argv[1])
ok = True
for i in range(4):
    data = (outdir / f"N88_{i}.ROM").read_bytes()
    expect_head = bytes([0x3E, 0xB0 + i, 0xC9])  # LD A,0xB0+i / RET
    if data[:3] != expect_head:
        print(f"NG: N88_{i}.ROM の先頭3バイトが想定と違う: {data[:3].hex()} != {expect_head.hex()}")
        ok = False
    if i == 0:
        # bank0だけ0x10-0x1Cに絶対番地試験ルーチン(EXT_BANK0_ABS_TEST_ENTRY)、
        # 0x30-0x6Fに常駐MBF_ADD呼び出し試験ルーチン(EXT_BANK0_MBF_TEST_ENTRY、
        # いずれもsrc/ext_bank/bank0.asm)があるため、そこだけ除外してFILLを
        # 確認する。ルーチンの中身そのものはtools/ext_bank_selftest.sh 2節
        # (実行結果)で検査する。
        rest = data[3:0x10] + data[0x1D:0x30] + data[0x70:]
    else:
        rest = data[3:]
    if any(b != 0x00 for b in rest):
        print(f"NG: N88_{i}.ROM の埋め草(0x00)以外の余剰バイトがある")
        ok = False
if ok:
    print("OK: N88_0.ROM〜N88_3.ROM は各8192バイト、先頭が試験エントリ、残りはFILL(0x00、"
          "bank0の絶対番地試験ルーチン分を除く)")
sys.exit(0 if ok else 1)
PYEOF

# -----------------------------------------------------------------------
say "2. 自己検査ビルド（--enable-ext-bank-selftest）: 常駐部・窓の中からの呼び出し、多数回呼び出し"
SELFTEST_ROM="$WORK/rom_selftest"
if ! python3 "$BUILD" "$SELFTEST_ROM" --enable-ext-bank-selftest >"$WORK/build_selftest.txt" 2>&1; then
  fail "build_main_rom.py(selftest)が失敗"; cat "$WORK/build_selftest.txt" >&2
fi

"$FRONTEND" --core "$CORE" --rom-dir "$SELFTEST_ROM" --frames 200 \
    --mem-write-log "$WORK/ext_bank.memlog.txt" --mem-write-range E8C0-E8D0 \
    >"$WORK/ext_bank.stdout.txt" 2>"$WORK/ext_bank.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(拡張ROMバンク自己検査)が失敗"; cat "$WORK/ext_bank.stderr.txt" >&2
fi

read -r V0 V1 V2 V3 PASS WINCALL LOOP_DONE LOOP_OK ABS_OK ABS_VAL MBF_OK <<< "$(python3 - "$WORK/ext_bank.memlog.txt" << 'PYEOF'
import re, sys
last = {}
for line in open(sys.argv[1]):
    m = re.match(r'\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})', line)
    if m:
        last[m.group(4).upper()] = m.group(5)
addrs = ["E8C0", "E8C1", "E8C2", "E8C3", "E8C4", "E8C5", "E8C6", "E8C7", "E8CE", "E8CF", "E8D0"]
print(" ".join(last.get(a, "FF") for a in addrs))
PYEOF
)"
echo "VAL0-3=$V0,$V1,$V2,$V3 PASS=$PASS WINCALL=$WINCALL LOOP_DONE=$LOOP_DONE LOOP_OK=$LOOP_OK ABS_OK=$ABS_OK ABS_VAL=$ABS_VAL MBF_OK=$MBF_OK"

if [ "$V0" = "B0" ] && [ "$V1" = "B1" ] && [ "$V2" = "B2" ] && [ "$V3" = "B3" ] && [ "$PASS" = "04" ]; then
  echo "OK: 常駐部からEXT_BANK_CALL経由でバンク0-3を呼び、全て期待値が返った"
else
  fail "常駐部からの呼び出しが期待値と不一致(VAL0-3=$V0,$V1,$V2,$V3 PASS=$PASS)"
fi

if [ "$WINCALL" = "01" ]; then
  echo "OK: 窓の中(run部相当)のプローブからEXT_BANK_CALLを呼んでも正しく戻った"
else
  fail "窓の中からの呼び出し(EXT_BANK_WINCALL_PROBE)が失敗(WINCALL=$WINCALL)"
fi

if [ "$LOOP_DONE" = "01" ] && [ "$LOOP_OK" = "01" ]; then
  echo "OK: 割り込みを有効にしたまま200回連続でEXT_BANK_CALLを呼んでも全数一致した"
else
  fail "多数回呼び出し試験(EXT_BANK_LOOP_TEST)が未完了または不一致(LOOP_DONE=$LOOP_DONE LOOP_OK=$LOOP_OK)"
fi

if [ "$ABS_OK" = "01" ] && [ "$ABS_VAL" = "C5" ]; then
  echo "OK: バンク0の絶対番地試験(CALL/JP/LD A,(nn))がORG 0x6000起点で正しく動いた"
else
  fail "バンク0の絶対番地試験が期待値と不一致(ABS_OK=$ABS_OK ABS_VAL=$ABS_VAL)"
fi

if [ "$MBF_OK" = "01" ]; then
  echo "OK: バンク0の試験ルーチンが常駐の単精度演算(MBF_ADD)をCALLし、1.0+2.0=3.0が正しく返った"
else
  fail "バンク0からの常駐MBF_ADD呼び出しが失敗(MBF_OK=$MBF_OK)"
fi

# -----------------------------------------------------------------------
say "3. 陰性対照（--inject-ext-bank-no-org-fault）: bank0.asmのORGを外すと絶対番地試験が落ちること"
NOORG_ROM="$WORK/rom_noorg"
if ! python3 "$BUILD" "$NOORG_ROM" --enable-ext-bank-selftest --inject-ext-bank-no-org-fault \
    >"$WORK/build_noorg.txt" 2>&1; then
  fail "build_main_rom.py(ORG故障注入)が失敗（ビルド自体が落ちるのは想定外）"
  cat "$WORK/build_noorg.txt" >&2
else
  "$FRONTEND" --core "$CORE" --rom-dir "$NOORG_ROM" --frames 200 \
      --mem-write-log "$WORK/ext_bank_noorg.memlog.txt" --mem-write-range E8C0-E8D0 \
      >"$WORK/ext_bank_noorg.stdout.txt" 2>"$WORK/ext_bank_noorg.stderr.txt"
  if [ $? -ne 0 ]; then
    fail "q88measure(ORG故障注入)が失敗"; cat "$WORK/ext_bank_noorg.stderr.txt" >&2
  fi
  read -r NOORG_ABS_OK NOORG_ABS_VAL <<< "$(python3 - "$WORK/ext_bank_noorg.memlog.txt" << 'PYEOF'
import re, sys
last = {}
for line in open(sys.argv[1]):
    m = re.match(r'\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})', line)
    if m:
        last[m.group(4).upper()] = m.group(5)
print(last.get("E8CE", "FF"), last.get("E8CF", "FF"))
PYEOF
)"
  echo "ABS_OK=$NOORG_ABS_OK ABS_VAL=$NOORG_ABS_VAL"
  if [ "$NOORG_ABS_OK" != "01" ]; then
    echo "OK(検出力): ORGを外すと絶対番地試験が実際に不一致になった(ABS_VAL=$NOORG_ABS_VAL != C5)"
  else
    fail "ORGを外しても絶対番地試験がOKのままだった(検査に検出力が無い)"
  fi
fi

# -----------------------------------------------------------------------
say "4. 陰性対照（--inject-ext-bank-window-fault）: 中継ルーチンを窓の中へ移すと、ビルド時検査が落ちること"
FAULT_ROM="$WORK/rom_fault"
if python3 "$BUILD" "$FAULT_ROM" --inject-ext-bank-window-fault >"$WORK/build_fault.txt" 2>&1; then
  fail "陰性対照ビルドが成功してしまった(検査に検出力が無い)"
  cat "$WORK/build_fault.txt" >&2
else
  if grep -q "窓の中" "$WORK/build_fault.txt" && grep -q "EXT_BANK_CALL" "$WORK/build_fault.txt"; then
    echo "OK: --inject-ext-bank-window-faultはビルド時検査(check_ext_bank_relay_below_window)で落ちた"
    cat "$WORK/build_fault.txt"
  else
    fail "陰性対照ビルドは失敗したが、想定と違う理由で落ちた可能性がある"
    cat "$WORK/build_fault.txt" >&2
  fi
fi

# -----------------------------------------------------------------------
say "5. 陰性対照（--inject-ext-bank-mbf-addr-fault）: 常駐MBF_ADDの番地をMBF_SUBへ取り違えると、MBF自己検査が落ちること"
MBFFAULT_ROM="$WORK/rom_mbffault"
if ! python3 "$BUILD" "$MBFFAULT_ROM" --enable-ext-bank-selftest --inject-ext-bank-mbf-addr-fault \
    >"$WORK/build_mbffault.txt" 2>&1; then
  fail "build_main_rom.py(MBF番地取り違え故障注入)が失敗（ビルド自体が落ちるのは想定外）"
  cat "$WORK/build_mbffault.txt" >&2
else
  "$FRONTEND" --core "$CORE" --rom-dir "$MBFFAULT_ROM" --frames 200 \
      --mem-write-log "$WORK/ext_bank_mbffault.memlog.txt" --mem-write-range E8C0-E8D0 \
      >"$WORK/ext_bank_mbffault.stdout.txt" 2>"$WORK/ext_bank_mbffault.stderr.txt"
  if [ $? -ne 0 ]; then
    fail "q88measure(MBF番地取り違え故障注入)が失敗"; cat "$WORK/ext_bank_mbffault.stderr.txt" >&2
  fi
  MBFFAULT_MBF_OK="$(python3 - "$WORK/ext_bank_mbffault.memlog.txt" << 'PYEOF'
import re, sys
last = {}
for line in open(sys.argv[1]):
    m = re.match(r'\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})', line)
    if m:
        last[m.group(4).upper()] = m.group(5)
print(last.get("E8D0", "FF"))
PYEOF
)"
  echo "MBF_OK=$MBFFAULT_MBF_OK"
  if [ "$MBFFAULT_MBF_OK" != "01" ]; then
    echo "OK(検出力): 番地を取り違えるとMBF自己検査が実際に不一致になった(MBF_OK=$MBFFAULT_MBF_OK)"
  else
    fail "番地を取り違えてもMBF自己検査がOKのままだった(検査に検出力が無い)"
  fi
fi

# -----------------------------------------------------------------------
say "6. 既存の自己検査・適合検査が引き続きOKであること"
if bash "$REPO/tools/l3_main_selftest.sh" >"$WORK/l3_main_selftest.txt" 2>&1; then
  echo "OK: tools/l3_main_selftest.sh はrc=0"
else
  fail "tools/l3_main_selftest.sh がNG"
  tail -40 "$WORK/l3_main_selftest.txt" >&2
fi

if bash "$REPO/tools/conform_l4.sh" >"$WORK/conform_l4.txt" 2>&1; then
  echo "OK: tools/conform_l4.sh はrc=0"
else
  fail "tools/conform_l4.sh がNG"
  tail -40 "$WORK/conform_l4.txt" >&2
fi

if bash "$REPO/tools/check_rom_version_reserved.sh" >"$WORK/romver.txt" 2>&1; then
  echo "OK: tools/check_rom_version_reserved.sh はrc=0"
else
  fail "tools/check_rom_version_reserved.sh がNG"
  tail -40 "$WORK/romver.txt" >&2
fi

# -----------------------------------------------------------------------
echo
if [ "$FAILED" -eq 0 ]; then
  echo "ext_bank_selftest: OK"
  exit 0
else
  echo "ext_bank_selftest: NG"
  exit 1
fi

#!/usr/bin/env bash
# tools/l3_main_selftest.sh — M7段階2a/2b: 自作main ROM(N88.ROM)がディスク無しで
# 自作バナー→Ok→カーソル表示・キー入力・行入力まで出すことの自己検査。
# **公式ROMは要らない**（L1適合の比較先だけ、既にリポジトリにある測定記録
# measurements/l1-boot-io.iolog.txt.gz を使う。これは verify_l1.sh と同じ扱い）。
#
# 組み立て: src/build_main_rom.py（src/l1_ipl/make_ipl_rom.py の発行命令(L1)
# + src/l3_main/screen.asm・keyboard.asm・key_table_gen.asm(画面出力・キー入力)
# を tools/asm/z80text.py で1本に組む）。
#
# 検査（段階2a、1-5）:
#   1. バナー行・Ok行が期待の行・桁に出ている（docs/spec/l3-main.md 第2節の
#      番地の式どおり）。自作ROMの画面内容なので本文を見てよい
#      （CLAUDE.md 禁止事項7の対象は公式ROM/測定の画面本文）。
#   2. 属性域が既定の並び（この実装が選んだ全ゼロ、src/l3_main/screen.asm
#      冒頭コメント参照）になっている。
#   3. スクロール: 表示行数を超える出力（--extra-lines）で、120×19=2280バイトの
#      書き写し＋末尾120バイトの再クリアが1つの連続書き込み(2400バイト)として
#      F3C8起点で複数回観測される（docs/spec/l3-main.md 第5節）。
#   4. L1適合（tools/verify_l1.sh と同じ判定基盤、tools/cmp_io.py）。
#      段階2bでカーソルを追従させた結果、CRTCカーソル位置パラメータ
#      (OUT 0x50、周期内4・5番目のX/Y)は自作ROMでは実際のプロンプト位置
#      （バナー・Ok表示後の行・桁）になり、公式測定の固定値(22,1)と
#      一致しない——docs/spec/l1-ipl.md 第3節「毎フレーム、カーソルを
#      (22,1)に置き直している」（アイドル状態の公式BASICプロンプトの
#      位置）のとおり、この値は**画面の中身**で決まるので、別の画面を
#      出す自作ROMで一致しないのは当然であり、検査を緩める理由には
#      ならない。加えて実測すると、付録Aの初期化区間の末尾7件(344-350行)
#      が②定常状態と同じ7件周期の1周分そのもの（350は周期7の倍数で、
#      境目がちょうど1周の終わりに来る）であり、そこにも同じカーソル
#      パラメータが現れる。そこで検査を2つに分ける（cmp_io.pyの
#      --ignore-value-at 4,5 で、その2位置だけをvalue比較から外す。
#      ポート・件数・周期・IN 40無しは従来どおり適合条件のまま）:
#        4a. 初期化350件（①）: 末尾7件(344-350)のカーソルパラメータ
#            2箇所だけがvalue比較の対象外（該当箇所はport一致のみ確認）。
#            **それ以外(1-343件目)は従来どおり完全一致**——「7件に1件が
#            たまたま同じ位相」というだけで①全体から除外するのではなく、
#            l1-ipl.md 付録Aで特定した末尾1周分の窓だけに限定する
#            （tools/cmp_io.py の report_mismatch の ignore_window_start
#            引数。全体に位相条件をばらまくと無関係な位置が検出漏れに
#            なるため）。
#        4b. 定常状態（②③）: ポートの並び・件数・7件周期の一致は
#            要求したまま、OUT 0x50のカーソル位置パラメータ(周期内
#            4・5番目)だけをvalue比較から外す。それ以外の値（周期内
#            1-3・6-7番目、および③のIN 40無し）は従来どおり比較する。
#      以前はこの検査全体をNGのまま通し、tools/run_all_selftests.sh側で
#      l3_main_selftest.sh全体の期待rcを0→1にしていたが、それでは
#      他の検査(1-3,5-10)が今後壊れても「期待どおりの失敗」として
#      素通りしてしまう欠陥があった。4a/4bへの分割で期待rcを0に戻せる
#      （run_all_selftests.sh側のコメント・変更点も参照）。
#      検査11-13でこの分割自体の検出力を故障注入により確かめる
#      （$WORK/normal.iolog.txt をawkで直接改変し、cmp_io.pyへ渡す。
#      ROMの再ビルドは不要）。
#   5. 故障注入: 番地の式を1バイトずらした変種（--inject-address-fault）では
#      検査1が確実に落ちることを確かめる（検出力の陰性対照）。
#
# 検査（段階2b、6-10。docs/spec/l3-main.md 第8〜10節、キー入力・行入力）:
#   6. tools/gen_l3_key_table.py --check — キーコード表が第10節の要約表
#      （変化なし/別コード/書かない/未判定の件数）と一致すること。
#   7. --key-matrix でのキー直押し: 無修飾(Q=0x71)・CAPS(Q→0x51)・
#      GRPH(Q→0x9C)・RETURN(改行してOkのみ、文字は書かない)を確認する。
#   8. --type での行入力: エコーの位置・文字、カーソル追従のI/O列
#      （--io-log、OUT 0x50 が入力後の桁・行になる）を確認する。
#   9. 故障注入: キーコード表のQのエントリを変えた変種
#      （--inject-key-table-fault）でキー直押しの結果が期待とずれることを
#      確かめる（検出力の陰性対照）。
#  10. 故障注入: カーソル追従のROW出力を1ずらした変種
#      （--inject-cursor-fault）で--typeのカーソルI/O列が期待とずれることを
#      確かめる（検出力の陰性対照）。
#  11. 故障注入: 定常状態の非カーソル値(位置1番目、port 0031)を書き換えた
#      変種で4bがNGになることを確かめる（検出力の陰性対照）。
#  12. 故障注入: 初期化区間の非カーソル値(1件目、port 0053)を書き換えた
#      変種で4aがNGになることを確かめる（検出力の陰性対照）。
#  13. 故障注入: 定常状態のカーソル値(位置4番目、port 0050)だけを書き換えて
#      も4bはOKのままであることを確かめる（外した範囲がそこだけである
#      ことの確認）。
#
# 使い方: tools/l3_main_selftest.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
BASE_IOLOG="$REPO/measurements/l1-boot-io.iolog.txt.gz"
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
if [ ! -f "$BASE_IOLOG" ]; then
  echo "基準の測定記録が無い: $BASE_IOLOG" >&2; exit 1
fi

# -----------------------------------------------------------------------
say "1. 通常ビルド（extra-lines=0）"
NORMAL_ROM="$WORK/rom_normal"
python3 "$BUILD" "$NORMAL_ROM" >"$WORK/build_normal.txt" 2>&1 || { fail "build_main_rom.py(通常)が失敗"; cat "$WORK/build_normal.txt" >&2; }
cat "$WORK/build_normal.txt"

say "2. バナー・Ok・属性域の検査（VRAM写し）"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 90 \
    --vram-dump "$WORK/normal.vram.bin" --vram-dump-at 89 \
    >"$WORK/normal.stdout.txt" 2>"$WORK/normal.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(通常)が失敗"; cat "$WORK/normal.stderr.txt" >&2
fi

python3 - "$WORK/normal.vram.bin" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
STRIDE = 120
COLS = 80
BANNER_LEN = len("PC88Behavior v0.1")  # src/l3_main/screen.asm BANNER_TXT と同じ(自作文言)
OK_LEN = len("Ok")                      # 同 OK_TXT

def row_text(row):
    base = row * STRIDE
    return data[base:base + COLS]

def row_attr(row):
    base = row * STRIDE + COLS
    return data[base:base + 40]

ok = True

t0 = row_text(0)
if t0[0] == 0x20:
    print("NG: バナー行(row0)がcol0から始まっていない"); ok = False
if any(b == 0x20 for b in t0[:1]) is False and t0[BANNER_LEN] != 0x20:
    print("NG: バナー行の長さがBANNER_LENと合わない"); ok = False

t1 = row_text(1)
if t1[0] == 0x20:
    print("NG: Ok行(row1)がcol0から始まっていない"); ok = False
if t1[OK_LEN] != 0x20:
    print("NG: Ok行の長さがOK_LENと合わない"); ok = False

for row in (0, 1, 5, 19):
    a = row_attr(row)
    if any(a):
        print(f"NG: row{row}の属性域が既定の並び(全ゼロ)になっていない"); ok = False

if ok:
    print("OK: バナー・Ok・属性域(既定の並び)")
else:
    sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "画面出力の検査"

# -----------------------------------------------------------------------
say "3. スクロールの検査（extra-lines=25 で20行を超えさせる）"
SCROLL_ROM="$WORK/rom_scroll"
python3 "$BUILD" "$SCROLL_ROM" --extra-lines 25 >"$WORK/build_scroll.txt" 2>&1 || { fail "build_main_rom.py(scroll)が失敗"; cat "$WORK/build_scroll.txt" >&2; }

"$FRONTEND" --core "$CORE" --rom-dir "$SCROLL_ROM" --frames 90 \
    --mem-write-log "$WORK/scroll.memlog.txt" --mem-write-range F3C8-FF80 \
    >"$WORK/scroll.stdout.txt" 2>"$WORK/scroll.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(scroll)が失敗"; cat "$WORK/scroll.stderr.txt" >&2
fi

python3 - "$WORK/scroll.memlog.txt" <<'PYEOF'
import re, sys
pat = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s*$")
addrs = []
for line in open(sys.argv[1]):
    m = pat.match(line)
    if m:
        addrs.append(int(m.group(4), 16))

runs = []
start = prev = None
for a in addrs:
    if prev is None or a != prev + 1:
        if start is not None:
            runs.append(prev - start + 1)
        start = a
    prev = a
if start is not None:
    runs.append(prev - start + 1)

# 120*(ROWS-1) + 120(最終行の再クリア) = 2400 バイトの連続書き込みが
# 初期化(全画面クリア)1回 + スクロール回数ぶん、複数回現れるはず。
big = [r for r in runs if r >= 2400]
if len(big) < 2:
    print(f"NG: 2400バイト以上の連続書き込みが{len(big)}回しか無い(初期化+スクロールで2回以上のはず)")
    sys.exit(1)
print(f"OK: 2400バイト連続書き込み {len(big)} 回観測（初期化1回＋スクロール{len(big)-1}回）")
PYEOF
[ $? -ne 0 ] && fail "スクロールの検査"

# -----------------------------------------------------------------------
say "4. L1適合の検査（4a初期化＝完全一致 ／ 4b定常状態＝カーソル位置以外）"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 60 \
    --io-log "$WORK/normal.iolog.txt" \
    >"$WORK/normal_l1.stdout.txt" 2>"$WORK/normal_l1.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(L1用)が失敗"; cat "$WORK/normal_l1.stderr.txt" >&2
fi

# 4a(①初期化350件の完全一致)・4b(②定常状態、カーソル位置(周期内4・5番目)
# だけをvalue比較から外す)は、cmp_io.pyの--init/--cycleが①→②の順に
# 判定して最初の不一致を報告する1回の呼び出しで両方見られる
# （①は--ignore-value-atの対象外＝常に完全一致）。出力の「① 初期化区間」
# 「② 定常状態」の文言で4a/4bどちらの不一致かを見分ける。
python3 "$REPO/tools/cmp_io.py" "$BASE_IOLOG" "$WORK/normal.iolog.txt" \
    --init 350 --cycle 7 --ignore-value-at 4,5 >"$WORK/l1_conform.txt" 2>&1
L1_RC=$?
cat "$WORK/l1_conform.txt"
if [ $L1_RC -ne 0 ]; then
  if grep -q "① 初期化区間" "$WORK/l1_conform.txt"; then
    fail "L1適合 4a(初期化350件の完全一致)。docs/spec/l1-ipl.md 付録Aの区間で食い違い"
  else
    fail "L1適合 4b(定常状態。カーソル位置(周期内4・5番目)以外での食い違い)"
  fi
else
  echo "OK: L1適合 4a(初期化350件完全一致)・4b(定常状態、カーソル位置以外完全一致)"
fi

# -----------------------------------------------------------------------
say "5. 故障注入（番地の式を1バイトずらす。検査1が落ちることを確かめる）"
FAULT_ROM="$WORK/rom_fault"
python3 "$BUILD" "$FAULT_ROM" --inject-address-fault >"$WORK/build_fault.txt" 2>&1 || { fail "build_main_rom.py(fault)が失敗"; cat "$WORK/build_fault.txt" >&2; }

"$FRONTEND" --core "$CORE" --rom-dir "$FAULT_ROM" --frames 90 \
    --vram-dump "$WORK/fault.vram.bin" --vram-dump-at 89 \
    >"$WORK/fault.stdout.txt" 2>"$WORK/fault.stderr.txt"
if [ $? -ne 0 ]; then
  fail "q88measure(fault)が失敗"; cat "$WORK/fault.stderr.txt" >&2
fi

python3 - "$WORK/fault.vram.bin" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
row0 = data[0:80]
# 故障注入(番地+1)がかかっていれば、col0は空白のまま(バナーがcol1から始まる)はず。
if row0[0] == 0x20:
    print("OK(検出力): 故障注入がかかると検査1どおりcol0が空白になり、正常判定と区別できた")
    sys.exit(0)
else:
    print("NG(検出力不足): 故障注入してもcol0が空白のままにならず、正常な場合と区別できない")
    sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "故障注入の検出力"

# -----------------------------------------------------------------------
say "6. キーコード表の検査（tools/gen_l3_key_table.py --check）"
python3 "$REPO/tools/gen_l3_key_table.py" --check
[ $? -ne 0 ] && fail "gen_l3_key_table.py --check"

# -----------------------------------------------------------------------
say "7. キー直押し（--key-matrix）: 無修飾・CAPS・GRPH・RETURN"
# 待機後にバナー・Okの表示が終わっている前提で、行2(row0=2)のcol0を見る
# (SCREEN_MAIN: banner→NEWLINE→Ok→NEWLINEでVAR_ROW=2,VAR_COL=0になる)。
check_key() {
  local label="$1"; shift
  local expect_hex="$1"; shift
  local dump="$WORK/km_${label}.vram.bin"
  "$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 300 "$@" \
      --vram-dump "$dump" --vram-dump-at 250 \
      >"$WORK/km_${label}.stdout.txt" 2>"$WORK/km_${label}.stderr.txt"
  if [ $? -ne 0 ]; then fail "q88measure(key:$label)が失敗"; cat "$WORK/km_${label}.stderr.txt" >&2; return; fi
  python3 - "$dump" "$expect_hex" "$label" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
expect = int(sys.argv[2], 16)
label = sys.argv[3]
got = data[2*120]
if got == expect:
    print(f"OK: {label} row2col0=0x{got:02X}（期待どおり）")
else:
    print(f"NG: {label} row2col0=0x{got:02X}（期待0x{expect:02X}）"); sys.exit(1)
PYEOF
  [ $? -ne 0 ] && fail "キー直押し($label)"
}
# Q(04H:1) 無修飾→0x71（l3-main.md第9節）
check_key "base_Q" 0x71 --key-matrix 0x04:1:60:10
# CAPS(0AH:7)保持+Q→0x51（第10節、大文字化）
check_key "caps_Q" 0x51 --key-matrix 0x0A:7:50:40 --key-matrix 0x04:1:60:10
# GRPH(08H:4)保持+Q→0x9C（第10節）
check_key "grph_Q" 0x9C --key-matrix 0x08:4:50:40 --key-matrix 0x04:1:60:10
# CTRL(08H:7)保持+Q→無視（第10節、Qは「無」＝書かない）。row2col0は空白のまま
check_key "ctrl_Q_ignored" 0x20 --key-matrix 0x08:7:50:40 --key-matrix 0x04:1:60:10
# RETURN(01H:7)単独→文字は書かない。改行してOkが出るのでrow3にOkが現れる
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 300 --key-matrix 0x01:7:60:10 \
    --vram-dump "$WORK/km_return.vram.bin" --vram-dump-at 250 \
    >"$WORK/km_return.stdout.txt" 2>"$WORK/km_return.stderr.txt"
if [ $? -ne 0 ]; then fail "q88measure(key:return)が失敗"; cat "$WORK/km_return.stderr.txt" >&2; fi
python3 - "$WORK/km_return.vram.bin" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
row2 = data[2*120:2*120+2]
row3 = data[3*120:3*120+2]
ok = row2 == b"  " and row3 == b"Ok"
print(("OK" if ok else "NG") + f": RETURN row2={row2!r} row3={row3!r}（期待: row2は空白のまま、row3にOk）")
sys.exit(0 if ok else 1)
PYEOF
[ $? -ne 0 ] && fail "RETURNキーの検査"

# -----------------------------------------------------------------------
say "8. 行入力（--type \"ab\"）: エコー位置・カーソル追従のI/O列"
TYPE_ROM_IOLOG="$WORK/type.iolog.txt"
"$FRONTEND" --core "$CORE" --rom-dir "$NORMAL_ROM" --frames 260 --type "ab" --type-at 60 \
    --vram-dump "$WORK/type.vram.bin" --vram-dump-at 250 --io-log "$TYPE_ROM_IOLOG" \
    >"$WORK/type.stdout.txt" 2>"$WORK/type.stderr.txt"
if [ $? -ne 0 ]; then fail "q88measure(type)が失敗"; cat "$WORK/type.stderr.txt" >&2; fi
python3 - "$WORK/type.vram.bin" "$TYPE_ROM_IOLOG" <<'PYEOF'
import re, sys
data = open(sys.argv[1], "rb").read()
row2 = data[2*120:2*120+2]
ok = row2 == b"ab"
print(("OK" if ok else "NG") + f": エコー row2={row2!r}（期待 b'ab'）")
if not ok:
    sys.exit(1)
pat = re.compile(r"OUT\s+0050\s+([0-9A-Fa-f]{2})")
vals = pat.findall(open(sys.argv[2]).read())
last_pair = vals[-2:]
if last_pair == ["02", "02"]:
    print(f"OK: カーソル追従 最後のOUT(50)組={last_pair}（col=2,row=2）")
else:
    print(f"NG: カーソル追従 最後のOUT(50)組={last_pair}（期待 ['02','02']）")
    sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "行入力の検査"

# -----------------------------------------------------------------------
say "9. 故障注入（キーコード表のQのエントリを変える。検査7が落ちることを確かめる）"
KTFAULT_ROM="$WORK/rom_ktfault"
python3 "$BUILD" "$KTFAULT_ROM" --inject-key-table-fault >"$WORK/build_ktfault.txt" 2>&1 || { fail "build_main_rom.py(ktfault)が失敗"; cat "$WORK/build_ktfault.txt" >&2; }
"$FRONTEND" --core "$CORE" --rom-dir "$KTFAULT_ROM" --frames 300 --key-matrix 0x04:1:60:10 \
    --vram-dump "$WORK/ktfault.vram.bin" --vram-dump-at 250 \
    >"$WORK/ktfault.stdout.txt" 2>"$WORK/ktfault.stderr.txt"
if [ $? -ne 0 ]; then fail "q88measure(ktfault)が失敗"; cat "$WORK/ktfault.stderr.txt" >&2; fi
python3 - "$WORK/ktfault.vram.bin" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
got = data[2*120]
if got != 0x71:
    print(f"OK(検出力): 表の故障注入がかかると row2col0=0x{got:02X}(期待0x71と不一致)になり区別できた")
    sys.exit(0)
else:
    print("NG(検出力不足): 表を故障注入しても検査7と区別できない"); sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "キーコード表の故障注入の検出力"

# -----------------------------------------------------------------------
say "10. 故障注入（カーソル追従のROW出力を1ずらす。検査8が落ちることを確かめる）"
CURSORFAULT_ROM="$WORK/rom_cursorfault"
python3 "$BUILD" "$CURSORFAULT_ROM" --inject-cursor-fault >"$WORK/build_cursorfault.txt" 2>&1 || { fail "build_main_rom.py(cursorfault)が失敗"; cat "$WORK/build_cursorfault.txt" >&2; }
"$FRONTEND" --core "$CORE" --rom-dir "$CURSORFAULT_ROM" --frames 260 --type "ab" --type-at 60 \
    --io-log "$WORK/cursorfault.iolog.txt" \
    >"$WORK/cursorfault.stdout.txt" 2>"$WORK/cursorfault.stderr.txt"
if [ $? -ne 0 ]; then fail "q88measure(cursorfault)が失敗"; cat "$WORK/cursorfault.stderr.txt" >&2; fi
python3 - "$WORK/cursorfault.iolog.txt" <<'PYEOF'
import re, sys
pat = re.compile(r"OUT\s+0050\s+([0-9A-Fa-f]{2})")
vals = pat.findall(open(sys.argv[1]).read())
last_pair = vals[-2:]
if last_pair != ["02", "02"]:
    print(f"OK(検出力): カーソル故障注入がかかると最後のOUT(50)組={last_pair}(期待['02','02']と不一致)になり区別できた")
    sys.exit(0)
else:
    print("NG(検出力不足): カーソルを故障注入しても検査8と区別できない"); sys.exit(1)
PYEOF
[ $? -ne 0 ] && fail "カーソル追従の故障注入の検出力"

# -----------------------------------------------------------------------
# 検査11-13: cmp_io.py --ignore-value-at 自体の検出力（4a/4bの分割が
# 正しく効いていることの確認）。$WORK/normal.iolog.txt（検査4で作成済み）
# をawkで直接改変し、ROMの再ビルド無しでcmp_io.pyへ渡す。
CMP_ARGS=(--init 350 --cycle 7 --ignore-value-at 4,5)

mutate_out_nth_value() {
  # main節のN件目のOUT行のvalue列($7)をnewvalに書き換えた版を作る。
  local infile="$1" outfile="$2" n="$3" newval="$4"
  awk -v n="$n" -v newval="$newval" '
    $4=="main" && $5=="OUT" { c++; if (c==n) $7=newval }
    { print }
  ' "$infile" > "$outfile"
}

say "11. cmp_io.pyの検出力（定常状態の非カーソル値(位置1番目, port 0031)を書き換え。4bがNGになることを確かめる）"
mutate_out_nth_value "$WORK/normal.iolog.txt" "$WORK/mut_steady_noncursor.iolog.txt" 351 18
python3 "$REPO/tools/cmp_io.py" "$BASE_IOLOG" "$WORK/mut_steady_noncursor.iolog.txt" "${CMP_ARGS[@]}" >"$WORK/mut11.txt" 2>&1
RC11=$?
if [ $RC11 -ne 0 ] && grep -q "② 定常状態" "$WORK/mut11.txt"; then
  echo "OK(検出力): 位置1番目(非カーソル)を変えると④b相当がNG(rc=${RC11}、②で不一致)になり区別できた"
else
  fail "検査11: 非カーソル値の改変が検出されない(rc=$RC11)"; cat "$WORK/mut11.txt"
fi

say "12. cmp_io.pyの検出力（初期化区間の非カーソル値(1件目, port 0053)を書き換え。4aがNGになることを確かめる）"
mutate_out_nth_value "$WORK/normal.iolog.txt" "$WORK/mut_init_noncursor.iolog.txt" 1 EE
python3 "$REPO/tools/cmp_io.py" "$BASE_IOLOG" "$WORK/mut_init_noncursor.iolog.txt" "${CMP_ARGS[@]}" >"$WORK/mut12.txt" 2>&1
RC12=$?
if [ $RC12 -ne 0 ] && grep -q "① 初期化区間" "$WORK/mut12.txt"; then
  echo "OK(検出力): 初期化区間1件目(非カーソル)を変えると④a相当がNG(rc=${RC12}、①で不一致)になり区別できた"
else
  fail "検査12: 初期化区間の改変が検出されない(rc=$RC12)"; cat "$WORK/mut12.txt"
fi

say "13. cmp_io.pyの検出力（定常状態のカーソル値(位置4番目, port 0050)だけを書き換え。4bはOKのままであることを確かめる）"
mutate_out_nth_value "$WORK/normal.iolog.txt" "$WORK/mut_steady_cursor.iolog.txt" 354 FF
python3 "$REPO/tools/cmp_io.py" "$BASE_IOLOG" "$WORK/mut_steady_cursor.iolog.txt" "${CMP_ARGS[@]}" >"$WORK/mut13.txt" 2>&1
RC13=$?
if [ $RC13 -eq 0 ]; then
  echo "OK: カーソル位置(位置4番目)だけの改変ではrc=0のまま（外した範囲が本当にそこだけであることを確認）"
else
  fail "検査13: カーソル位置だけの改変でNGになった(rc=$RC13)。除外範囲が狭すぎる"; cat "$WORK/mut13.txt"
fi

# -----------------------------------------------------------------------
echo
if [ "$FAILED" -eq 0 ]; then
  echo "l3_main_selftest: OK"
  exit 0
else
  echo "l3_main_selftest: NG"
  exit 1
fi

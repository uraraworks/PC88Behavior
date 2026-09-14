#!/usr/bin/env bash
# 発行元PC（--mem-write-log の pc 列）が「本当にその書き込みを発行した
# 命令の先頭番地か」を、番地まで決め打ちで検査する自己検査。
#
# mem_write_log_selftest.sh は発行元PCについて「単調非減少」「全件が別の
# PC」という構造的な性質しか見ていない（ROM内の具体的な番地までは検査
# していない）。本検査は tools/asm/z80text.py（自作アセンブラ）で組んだ
# 試験ROMの --list から、各命令の先頭番地を機械的に取り出し（手で書き
# 写さない）、それを --mem-write-log の実測 pc 列と番地ごとに突き合わせる。
#
# 対象命令: LD (HL),A / LD (nn),A / LD (nn),HL(2バイト書き込み) /
#          LD (IX+d),n・LD (IY+d),A(DD/FD前置き) /
#          SET b,(IX+d)(DD CB d op形) / LD (nn),IX(DD 22 nn nn) /
#          LDIR(反復1命令が複数バイトを書く) / PUSH BC / CALL nn / RST /
#          EX (SP),HL
#
# 割り込み受付時のスタックへの積み込み（命令ではない）については、
# 別セクションで make_test_rom.py --enable-int の HALT ループを使い、
# 「受理直前に実行完了していた命令（＝HALTの先頭番地）」が発行元PCとして
# 記録されることを実測して仕様として確認する（intlog_selftest.sh が
# 確認済みの ret_pc=HALT_ADDR+1 と辻褄が合うことも併せて確認する）。
#
# 故障注入: 前置き追跡の状態機械をわざと壊す環境変数
# Q88MEASURE_FAULT_IGNORE_PREFIX=1（tools/patches/0014-mem-write-log.patch
# 側に自己検査専用として追加した q88h_fault_ignore_prefix()）を使い、
# DD/FD 系命令だけ期待PCとの比較がNGになり、それ以外は影響を受けない
# ことを確認する。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
Z80TEXT="$REPO/tools/asm/z80text.py"
MAKE_TEST_ROM="$REPO/tools/harness/make_test_rom.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-memwritepc.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR"

# ===========================================================================
# 第1部: 直線コード＋制御命令(PUSH/CALL/RST/EX)の発行元PCを番地まで検査
# ===========================================================================

# --- 試験ROMをz80text.pyで組む --------------------------------------------
# 各命令の直後にコメントでタグ(; TAG_xxx)を付け、--list からそのタグの
# 行の先頭番地を機械的に拾う(後段のpython)。書き込み先番地(C000台)は
# 自分で選んだ定数であって、ROMの内容とは無関係。
cat > "$WORK/n88.asm" <<'ASM'
    org 0000h
    jp START

    org 0020h
RSTVEC:
    ld a,88h
    ld (0C041h),a       ; TAG_RSTVEC_WRITE
    ret

    org 2000h
SRC:
    db 010h,020h,030h,040h

    org 2010h
SUB:
    ld a,77h
    ld (0C040h),a       ; TAG_SUB_WRITE
    ret

    org 2100h
START:
    ld sp,0FFFFh
    ld hl,0C000h
    ld a,11h
    ld (hl),a           ; TAG_LD_xHL_A
    ld a,22h
    ld (0C001h),a       ; TAG_LD_xNN_A
    ld hl,03344h
    ld (0C002h),hl      ; TAG_LD_xNN_HL
    ld ix,0C010h
    ld (ix+0),55h       ; TAG_LD_xIXD_N
    ld iy,0C011h
    ld a,66h
    ld (iy+0),a         ; TAG_LD_xIYD_A
    ld ix,0C012h
    set 3,(ix+0)        ; TAG_SET_xIXD
    ld ix,0C020h
    ld (0C020h),ix      ; TAG_LD_xNN_IX
    ld hl,SRC
    ld de,0C030h
    ld bc,4
    ldir                ; TAG_LDIR
    ld sp,0C060h
    ld hl,09988h
    ex (sp),hl          ; TAG_EX_xSP_HL
    ld sp,0C071h
    push bc             ; TAG_PUSH_BC
    ld sp,0C081h
    call SUB            ; TAG_CALL_SUB
    ld sp,0C091h
    rst 20h             ; TAG_RST_20H
END:
    jr END

    org 07fffh
    db 0
ASM

cat > "$WORK/disk.asm" <<'ASM'
    org 0000h
    jr $

    org 07ffh
    db 0
ASM

mkdir -p "$WORK/rom"
python3 "$Z80TEXT" "$WORK/n88.asm"  -o "$WORK/rom/N88.ROM"  --list "$WORK/n88.lst" \
  || ng "N88.ROMの組み立てに失敗"
python3 "$Z80TEXT" "$WORK/disk.asm" -o "$WORK/rom/DISK.ROM" || ng "DISK.ROMの組み立てに失敗"
[ "$(wc -c < "$WORK/rom/N88.ROM")"  -eq 32768 ] || ng "N88.ROMのサイズが32768バイトでない"
[ "$(wc -c < "$WORK/rom/DISK.ROM")" -eq 2048  ] || ng "DISK.ROMのサイズが2048バイトでない"
ok "試験ROMをz80text.pyで組み立てた(N88.ROM 32768B / DISK.ROM 2048B)"

# --- 期待列をリストから機械的に構築 -----------------------------------------
# 各TAGの命令先頭番地は --list の出力から拾う(手で書き写さない)。
# 書き込み先番地は自分で選んだ定数(この asm 自体に書いてある値)なので、
# ここで定数として使ってよい——ROM内部の秘匿情報ではなく自分の設計。
python3 - "$WORK/n88.lst" "$WORK/expected.tsv" <<'PYEOF'
import re, sys

lst_path, out_path = sys.argv[1], sys.argv[2]

tag_pc = {}
tag_re = re.compile(r'^([0-9A-Fa-f]{4})\s+.*;\s*(TAG_\w+)\s*$')
for line in open(lst_path, encoding="utf-8"):
    m = tag_re.match(line.rstrip("\n"))
    if m:
        addr, tag = m.group(1).upper(), m.group(2)
        if tag in tag_pc:
            raise SystemExit(f"タグ重複: {tag}")
        tag_pc[tag] = addr

required = [
    "TAG_LD_xHL_A", "TAG_LD_xNN_A", "TAG_LD_xNN_HL", "TAG_LD_xIXD_N",
    "TAG_LD_xIYD_A", "TAG_SET_xIXD", "TAG_LD_xNN_IX", "TAG_LDIR",
    "TAG_EX_xSP_HL", "TAG_PUSH_BC", "TAG_CALL_SUB", "TAG_RST_20H",
    "TAG_SUB_WRITE", "TAG_RSTVEC_WRITE",
]
missing = [t for t in required if t not in tag_pc]
if missing:
    raise SystemExit(f"リストにタグが見つからない: {missing}")

# (書き込み先番地の並び, 対応するタグ) — 番地は自分で選んだ定数。
groups = [
    (["C000"],                     "TAG_LD_xHL_A"),
    (["C001"],                     "TAG_LD_xNN_A"),
    (["C002", "C003"],             "TAG_LD_xNN_HL"),
    (["C010"],                     "TAG_LD_xIXD_N"),
    (["C011"],                     "TAG_LD_xIYD_A"),
    (["C012"],                     "TAG_SET_xIXD"),
    (["C020", "C021"],             "TAG_LD_xNN_IX"),
    (["C030", "C031", "C032", "C033"], "TAG_LDIR"),
    (["C060", "C061"],             "TAG_EX_xSP_HL"),
    (["C070", "C06F"],             "TAG_PUSH_BC"),
    (["C080", "C07F"],             "TAG_CALL_SUB"),
    (["C040"],                     "TAG_SUB_WRITE"),
    (["C090", "C08F"],             "TAG_RST_20H"),
    (["C041"],                     "TAG_RSTVEC_WRITE"),
]

with open(out_path, "w") as f:
    for addrs, tag in groups:
        for addr in addrs:
            f.write(f"{addr}\t{tag_pc[tag]}\t{tag}\n")
PYEOF
EXPECTED_N="$(wc -l < "$WORK/expected.tsv" | tr -d ' ')"
[ "$EXPECTED_N" -eq 23 ] || ng "期待列の件数が23件でない(実際=${EXPECTED_N})。addr/valueの設計を見直すこと"
ok "命令ごとの期待PCをリストから機械的に取得(書き込み${EXPECTED_N}件ぶん)"

# --- 実測 -------------------------------------------------------------------
RANGE_LO=C000
RANGE_HI=C0FF
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 5 \
  --mem-write-log "$WORK/mwl.txt" --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  --out "$WORK/trace.txt" \
  >"$WORK/positive.stdout" 2>"$WORK/positive.stderr" \
  || ng "陽性対照の実行が失敗した"

[ -f "$WORK/mwl.txt" ] || ng "--mem-write-log の出力ファイルが作られていない"
grep -q '取りこぼし: 0件' "$WORK/mwl.txt" || ng "取りこぼしが0件でない"

awk '/^[[:space:]]*[0-9]+[[:space:]]/{print $4"\t"$3}' "$WORK/mwl.txt" > "$WORK/actual.tsv"
ACTUAL_N="$(wc -l < "$WORK/actual.tsv" | tr -d ' ')"
[ "$ACTUAL_N" -eq 23 ] || ng "C000-C0FF範囲の書き込み件数が23件でない(実際=${ACTUAL_N})。想定していない書き込みが混入している可能性"
ok "範囲内の書き込み件数が想定どおり23件(余分な書き込みが混入していない)"

# --- 番地ごとに期待PCと突き合わせ -------------------------------------------
python3 - "$WORK/expected.tsv" "$WORK/actual.tsv" <<'PYEOF' || ng "番地ごとの発行元PCが期待と一致しない箇所がある(詳細は上記)"
import sys
expected_path, actual_path = sys.argv[1:3]

expected = {}
for line in open(expected_path):
    addr, pc, tag = line.rstrip("\n").split("\t")
    expected[addr] = (pc, tag)

actual = {}
for line in open(actual_path):
    addr, pc = line.rstrip("\n").split("\t")
    actual.setdefault(addr, []).append(pc)

bad = []
for addr, (exp_pc, tag) in expected.items():
    got = actual.get(addr)
    if got is None:
        bad.append(f"{addr}({tag}): 記録が無い")
        continue
    if len(got) != 1:
        bad.append(f"{addr}({tag}): 記録が{len(got)}件(1件のはず)")
        continue
    if got[0] != exp_pc:
        bad.append(f"{addr}({tag}): pc={got[0]} != 期待{exp_pc}")

if bad:
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
PYEOF
ok "全13命令・23件の書き込みで、発行元PCが命令の先頭番地(リストから取得)と番地ごとに一致"

# ===========================================================================
# 第2部: 割り込み受付時のスタック積み込みのPCを実測し、仕様として記録
# ===========================================================================
mkdir -p "$WORK/introm"
python3 "$MAKE_TEST_ROM" "$WORK/introm" --enable-int >"$WORK/introm_gen.txt"
HALT_ADDR="$(grep -oE 'HALT_ADDR=0x[0-9A-Fa-f]+' "$WORK/introm_gen.txt" | cut -d= -f2)"
HALT_ADDR_HEX="$(printf '%04X' "$((HALT_ADDR))")"

# IM1受理時のRST 0038hはSP(既定0xFFFF)を--SPしてPCを積むので、
# 書き込み先はFFFD/FFFEになる。
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/introm" --frames 60 \
  --mem-write-log "$WORK/mwl_int.txt" --mem-write-range FFFD-FFFF \
  --out "$WORK/trace_int.txt" \
  >"$WORK/int.stdout" 2>"$WORK/int.stderr" \
  || ng "割り込みROMの実行が失敗した"

grep -q '取りこぼし: 0件' "$WORK/mwl_int.txt" || ng "割り込みROM実行で取りこぼしが0件でない"

python3 - "$WORK/mwl_int.txt" "$HALT_ADDR_HEX" <<'PYEOF' || ng "割り込み受理時のスタック積み込みのPC検査に失敗した"
import re, sys
path, halt_addr_hex = sys.argv[1], sys.argv[2].upper()
expect_ret_pc = (int(halt_addr_hex, 16) + 1) & 0xFFFF

rows = []
for line in open(path):
    m = re.match(r'^\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s*$', line)
    if m:
        seq, frame, pc, addr, value = m.groups()
        rows.append((int(frame), pc.upper(), addr.upper(), int(value, 16)))

if not rows:
    print("割り込みROM実行でFFFD-FFFF範囲の記録が1件も無い", file=sys.stderr)
    sys.exit(1)

# 発行元PCが全件HALT_ADDRであること。
bad_pc = [r for r in rows if r[1] != halt_addr_hex]
if bad_pc:
    print(f"発行元PCがHALT_ADDR({halt_addr_hex})でない書き込みがある: {bad_pc[:5]}", file=sys.stderr)
    sys.exit(1)

# フレームごとにFFFD(下位)/FFFE(上位)が対で入り、
# 戻り番地(HALT_ADDR+1)を再構成できること(intlogのret_pcと辻褄が合うことの
# 独立な裏付け)。
by_frame = {}
for frame, pc, addr, value in rows:
    by_frame.setdefault(frame, {})[addr] = value

bad_ret = []
for frame, m in by_frame.items():
    if "FFFD" not in m or "FFFE" not in m:
        bad_ret.append(f"frame={frame}: FFFD/FFFEが揃っていない({m})")
        continue
    ret_pc = m["FFFD"] | (m["FFFE"] << 8)
    if ret_pc != expect_ret_pc:
        bad_ret.append(f"frame={frame}: 再構成した戻り番地0x{ret_pc:04X} != 期待0x{expect_ret_pc:04X}")

if bad_ret:
    print("\n".join(bad_ret), file=sys.stderr)
    sys.exit(1)

n_frames = len(by_frame)
if n_frames < 10:
    print(f"割り込み受理イベントが少なすぎる(frame数={n_frames})", file=sys.stderr)
    sys.exit(1)

print(f"OK: {len(rows)}件({n_frames}フレームぶん)すべて発行元PC=HALT_ADDR、"
      f"戻り番地の再構成もHALT_ADDR+1と一致")
PYEOF
ok "割り込み受付(IM1)時のスタック積み込みは、直前に完了していた命令(HALT)の先頭番地を発行元PCとして記録する(実測・仕様として確認)"

# ===========================================================================
# 第3部: 故障注入 — DD/FD前置き追跡を無効化すると、DD/FD系だけNGになる
# ===========================================================================
Q88MEASURE_FAULT_IGNORE_PREFIX=1 "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --frames 5 --mem-write-log "$WORK/mwl_fault.txt" \
  --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  >/dev/null 2>"$WORK/fault.stderr" \
  || ng "故障注入版の実行が失敗した"

awk '/^[[:space:]]*[0-9]+[[:space:]]/{print $4"\t"$3}' "$WORK/mwl_fault.txt" > "$WORK/actual_fault.tsv"

python3 - "$WORK/expected.tsv" "$WORK/actual_fault.tsv" <<'PYEOF' || ng "故障注入(Q88MEASURE_FAULT_IGNORE_PREFIX)の検出に失敗した"
import sys
expected_path, actual_path = sys.argv[1:3]

expected = {}
for line in open(expected_path):
    addr, pc, tag = line.rstrip("\n").split("\t")
    expected[addr] = (pc, tag)

actual = {}
for line in open(actual_path):
    addr, pc = line.rstrip("\n").split("\t")
    actual[addr] = pc

# DD/FD前置きを使う命令(発行元PCが化けるはず)
prefixed_tags = {"TAG_LD_xIXD_N", "TAG_LD_xIYD_A", "TAG_SET_xIXD", "TAG_LD_xNN_IX"}

mismatched_prefixed = set()
unexpected_mismatch = []
for addr, (exp_pc, tag) in expected.items():
    got = actual.get(addr)
    if got is None:
        print(f"{addr}({tag}): 故障注入版で記録が消えた(想定外)", file=sys.stderr)
        sys.exit(1)
    if got != exp_pc:
        if tag in prefixed_tags:
            mismatched_prefixed.add(tag)
        else:
            unexpected_mismatch.append(f"{addr}({tag}): pc={got} != 期待{exp_pc}(DD/FD前置きを使わない命令なのに不一致)")

if unexpected_mismatch:
    print("\n".join(unexpected_mismatch), file=sys.stderr)
    sys.exit(1)

if mismatched_prefixed != prefixed_tags:
    missing = prefixed_tags - mismatched_prefixed
    print(f"故障注入したのにPCが期待どおりのまま(検出漏れ)のDD/FD系命令がある: {missing}", file=sys.stderr)
    sys.exit(1)

print(f"OK: 故障注入でDD/FD系4命令({sorted(mismatched_prefixed)})だけがPC不一致になり、"
      f"それ以外の命令は影響を受けない")
PYEOF
ok "故障注入(DD/FD前置きを数えない)でDD/FD系命令のみ発行元PCがNGになることを確認"

ok "全項目合格"

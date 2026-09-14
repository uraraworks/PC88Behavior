#!/usr/bin/env bash
# q88measure --key-matrix の末端自己検査（公式ROM不要）。
#
# M7段階1の器具その2「キーマトリクスのビットを直接押す器具」の検査。
# 自作の試験ROM（tools/asm/z80text.py で組む）が、main側キースキャン
# ポート 00h〜0Eh を毎ループ IN して 0xC000〜0xC00E に書き写す。
# --mem-write-log でその書き込みを記録し、--key-matrix で指定した
# PORT:BIT が指定フレームの間だけ0になり、他は変わらないことを確かめる。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
Z80TEXT="$REPO/tools/asm/z80text.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-keymatrix.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR"

# --- 自作試験ROMを z80text.py で組む ---------------------------------------
# main側: ポート00h〜0Eh(key_scan相当)を毎ループ全部INし、0xC000〜0xC00Eへ
# そのまま書き写す無限ループ。この命令列・番地・ポート番号はすべて自作の
# 選択であり、公式ROMの内容とは無関係（禁止事項1〜4に抵触しない）。
cat > "$WORK/n88.asm" <<'ASM'
    org 0000h
LOOP:
    in a,(00h)
    ld (0c000h),a
    in a,(01h)
    ld (0c001h),a
    in a,(02h)
    ld (0c002h),a
    in a,(03h)
    ld (0c003h),a
    in a,(04h)
    ld (0c004h),a
    in a,(05h)
    ld (0c005h),a
    in a,(06h)
    ld (0c006h),a
    in a,(07h)
    ld (0c007h),a
    in a,(08h)
    ld (0c008h),a
    in a,(09h)
    ld (0c009h),a
    in a,(0ah)
    ld (0c00ah),a
    in a,(0bh)
    ld (0c00bh),a
    in a,(0ch)
    ld (0c00ch),a
    in a,(0dh)
    ld (0c00dh),a
    in a,(0eh)
    ld (0c00eh),a
    jr LOOP

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
python3 "$Z80TEXT" "$WORK/n88.asm"  -o "$WORK/rom/N88.ROM"  || ng "N88.ROMの組み立てに失敗"
python3 "$Z80TEXT" "$WORK/disk.asm" -o "$WORK/rom/DISK.ROM" || ng "DISK.ROMの組み立てに失敗"
[ "$(wc -c < "$WORK/rom/N88.ROM")"  -eq 32768 ] || ng "N88.ROMのサイズが32768バイトでない"
[ "$(wc -c < "$WORK/rom/DISK.ROM")" -eq 2048  ] || ng "DISK.ROMのサイズが2048バイトでない"
ok "試験ROMをz80text.pyで組み立てた(N88.ROM 32768B / DISK.ROM 2048B)"

RANGE_LO=C000
RANGE_HI=C00E
FRAMES=60

# --- 陽性: 単独ビット押下(port00 bit0, frame20 hold6) ----------------------
# 同時押し検査(port01 bit0+bit1, frame40 hold5)も同じ実行に混ぜる
# (別ウィンドウなので互いに干渉しない)。
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames "$FRAMES" \
  --mem-write-log "$WORK/mwl.txt" --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  --key-matrix 0x00:0x00:20:6 \
  --key-matrix 0x01:0x00:40:5 \
  --key-matrix 0x01:0x01:40:5 \
  --out "$WORK/trace.txt" \
  >"$WORK/positive.stdout" 2>"$WORK/positive.stderr" \
  || ng "陽性対照の実行が失敗した"

grep -q '取りこぼし: 0件' "$WORK/mwl.txt" || ng "取りこぼしが0件でない"

# 見出し/報告に実際の書き換え記録(frame・port・bit・前後の値)が出ていること
grep -q 'frame=20.*port=00 bit=0.*press.*key_scan\[00\]' "$WORK/trace.txt" \
  || ng "報告に単独ビット押下の書き換え記録(frame=20)が無い"
grep -q 'frame=26.*port=00 bit=0.*release.*key_scan\[00\]' "$WORK/trace.txt" \
  || ng "報告に単独ビット解放の書き換え記録(frame=26)が無い"
grep -q 'frame=40.*port=01 bit=0.*press' "$WORK/trace.txt" \
  || ng "報告に同時押し1本目(bit0, frame=40)の記録が無い"
grep -q 'frame=40.*port=01 bit=1.*press' "$WORK/trace.txt" \
  || ng "報告に同時押し2本目(bit1, frame=40)の記録が無い"
ok "報告(--out)にframe・port・bit・書き換え前後の値の記録が残る"

grep -q 'キーマトリクス押下: frame=20 port=00 bit=0' "$WORK/positive.stderr" \
  || ng "stderrに押下ログが無い"
grep -q 'キーマトリクス解放: frame=26 port=00 bit=0' "$WORK/positive.stderr" \
  || ng "stderrに解放ログが無い"
ok "stderrにも押下・解放のログが残る"

# --- 末端検査: 実際のRAM(0xC000/0xC001)の値をmem-write-logから追う --------
# ROMは毎フレーム何百回もこのループを回す(VSYNC待ちなし)ので、押下/解放の
# 境界フレームだけは「切り替わる直前の1件」が紛れることがある(フレーム
# 境界での取りこぼしと同型の現象——docs/notes/feedback_frame_gap...参照)。
# そのため判定は「各フレームの最後の値」を使う(境界フレーム以外は全件
# 一致することも別途確認し、紛れが境界の1フレームだけであることを縛る)。
awk '/^[[:space:]]*[0-9]+[[:space:]]/ {print $2, $4, $5}' "$WORK/mwl.txt" > "$WORK/allwrites.tsv"

check_window() {
  # $1=addr $2=mask(押されているとみなすビット) $3=press_frame $4=release_frame
  python3 - "$WORK/allwrites.tsv" "$1" "$2" "$3" "$4" <<'PYEOF'
import sys
path, addr, mask_s, press_s, release_s = sys.argv[1:6]
mask = int(mask_s, 0)
press, release = int(press_s), int(release_s)

by_frame = {}
for line in open(path):
    frame_s, a, value_s = line.split()
    if a != addr:
        continue
    by_frame.setdefault(int(frame_s), []).append(int(value_s, 16))

ok = True
if not by_frame:
    print(f"{addr}: 記録が無い", file=sys.stderr); ok = False
for frame, values in sorted(by_frame.items()):
    pressed = press <= frame < release
    last_ok = ((values[-1] & mask) == 0) if pressed else ((values[-1] & mask) == mask)
    if not last_ok:
        print(f"{addr} frame={frame}: 最後の値0x{values[-1]:02X}が"
              f"{'押下中' if pressed else '非押下'}の期待と不一致", file=sys.stderr)
        ok = False
    # 境界フレーム(press/release)以外は全件一致するはず(取りこぼし境界以外での
    # 紛れは許さない)
    if frame not in (press, release):
        bad = [v for v in values if ((v & mask) == 0) != pressed]
        if bad:
            print(f"{addr} frame={frame}: 境界でないのに不一致な値がある: "
                  f"{[hex(v) for v in bad]}", file=sys.stderr)
            ok = False
if press not in by_frame or release not in by_frame:
    print(f"{addr}: 押下/解放の境界フレーム自体の記録が無い", file=sys.stderr); ok = False
sys.exit(0 if ok else 1)
PYEOF
}

check_window C000 0x01 20 26 || ng "port00(bit0)の押下/解放ウィンドウが実測値と一致しない"
ok "port00 bit0が指定フレーム(20-25)の間だけ0で、他は1のまま(末端のRAM値で確認)"

check_window C001 0x03 40 45 || ng "port01(同時押しbit0+bit1)のウィンドウが実測値と一致しない"
ok "port01 bit0+bit1が同時に指定フレーム(40-44)の間だけ0(同時押し)"

# 他のポート(C002-C00E)は値が終始一定であること(意図しない変化が無い)
for addr in C002 C003 C004 C005 C006 C007 C008 C009 C00A C00B C00C C00D C00E; do
  n_uniq="$(awk -v a="$addr" '/^[[:space:]]*[0-9]+[[:space:]]/ && $4==a {print $5}' "$WORK/mwl.txt" | sort -u | wc -l | tr -d ' ')"
  [ "$n_uniq" -le 1 ] || ng "port $addr の値が変化している(意図しない書き換え, 相異なる値=${n_uniq}種)"
done
ok "指定していない他ポート(C002-C00E)は値が終始不変"

# --- 故障注入: Q88MEASURE_FAULT_SKIP_KEY_MATRIX で書き換えを黙って飛ばす ---
Q88MEASURE_FAULT_SKIP_KEY_MATRIX=1 "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --frames "$FRAMES" \
  --mem-write-log "$WORK/mwl_fault.txt" --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  --key-matrix 0x00:0x00:20:6 \
  >/dev/null 2>"$WORK/fault.stderr" \
  || ng "故障注入版の実行が失敗した"

grep -q 'キーマトリクス押下' "$WORK/fault.stderr" && ng "故障注入したのに押下ログが出た"
awk '/^[[:space:]]*[0-9]+[[:space:]]/ && $4=="C000" {print $5}' "$WORK/mwl_fault.txt" | sort -u > "$WORK/fault_vals.txt"
[ "$(wc -l < "$WORK/fault_vals.txt")" -le 1 ] || ng "故障注入したのにport00の値が変化した"
if [ -s "$WORK/fault_vals.txt" ]; then
  FAULT_VAL="$(cat "$WORK/fault_vals.txt")"
  python3 -c "import sys; v=int('$FAULT_VAL',16); sys.exit(0 if (v & 1)==1 else 1)" \
    || ng "故障注入したのにbit0が0になった"
fi
ok "故障注入(Q88MEASURE_FAULT_SKIP_KEY_MATRIX)で書き換えが黙って飛ばされる"

# --- 引数エラー: 範囲外のPORT/BIT ------------------------------------------
set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 10 \
  --key-matrix 0x0F:0:5:2 >/dev/null 2>"$WORK/badport.stderr"
badport_rc=$?
set -e
[ "$badport_rc" -ne 0 ] || ng "範囲外PORT(0x0F)を弾けない"
grep -q -- 'PORT は0x00-0x0Eの範囲外' "$WORK/badport.stderr" || ng "範囲外PORTの分類メッセージが無い"
ok "範囲外PORT(0x0F)は引数エラーになる(rc=${badport_rc})"

set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 10 \
  --key-matrix 0x00:8:5:2 >/dev/null 2>"$WORK/badbit.stderr"
badbit_rc=$?
set -e
[ "$badbit_rc" -ne 0 ] || ng "範囲外BIT(8)を弾けない"
grep -q -- 'BIT は0-7の範囲外' "$WORK/badbit.stderr" || ng "範囲外BITの分類メッセージが無い"
ok "範囲外BIT(8)は引数エラーになる(rc=${badbit_rc})"

# --- --type との同時指定は禁止 ---------------------------------------------
set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 10 \
  --key-matrix 0x00:0x00:5:2 --type "A" >/dev/null 2>"$WORK/mix.stderr"
mix_rc=$?
set -e
[ "$mix_rc" -ne 0 ] || ng "--key-matrixと--typeの同時指定を弾けない"
grep -q -- '--key-matrix と --type は同時指定できない' "$WORK/mix.stderr" \
  || ng "併用禁止の分類メッセージが無い"
ok "--key-matrixと--typeの同時指定はエラーになる"

ok "全項目合格"

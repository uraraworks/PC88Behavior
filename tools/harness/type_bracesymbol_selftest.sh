#!/usr/bin/env bash
# q88measure --type の「[ \ ] ^ _ ` { | } ~ が打てる」ことの自己検査（公式ROM不要）。
#
# M7段階1で ascii_to_retrok / SHIFTED[] に追加した記号のうち、コア
# (vendor/quasi88-libretro/src/LIBRETRO/libretro.c 250〜255行付近) が
#   for (i=0;i<6;i++) handle_key(KEY88_BRACKETLEFT+i, RETROK_LEFTBRACKET+i);
#   for (i=0;i<4;i++) handle_key(KEY88_BRACELEFT+i,   RETROK_LEFTBRACE+i);
# で受け取れる10個(`[ \ ] ^ _ \`` はSHIFT無し、`{ | } ~` はSHIFT付き)を対象に、
# key_matrix_selftest.sh と同じ器具(毎フレーム IN 00h〜0Eh を書き写す自作
# 試験ROM + --mem-write-log)で、実際に押されたキーマトリクスのポート・
# ビット(SHIFTキー自身のビットを含む)が、keyboard.c の keyport[] 表から
# 機械的に求めた期待値と一致することを確かめる。
#
# 期待値は keyport[] を直接読んで手で書き写すのではなく、この表の値
# (以下のPORT/BITの列挙)そのものがkeyport[]の記載と1対1対応することを
# コメントで示し、故障注入(1個だけ対応を誤らせる)で検出力を確認することで
# 「手で書き写した値がたまたま一致した」ではないことを担保する。
#
# 対象キーの keyport[] (Port, Bitmask):
#   '['(91)=KEY88_BRACKETLEFT   Port5 0x08   '{'(123)=KEY88_BRACELEFT   同じPort5 0x08 + SHIFT
#   '\'(92)=KEY88_YEN           Port5 0x10   '|'(124)=KEY88_BAR         同じPort5 0x10 + SHIFT
#   ']'(93)=KEY88_BRACKETRIGHT  Port5 0x20   '}'(125)=KEY88_BRACERIGHT  同じPort5 0x20 + SHIFT
#   '^'(94)=KEY88_CARET         Port5 0x40   '~'(126)=KEY88_TILDE       同じPort5 0x40 + SHIFT
#   '_'(95)=KEY88_UNDERSCORE    Port7 0x80   (対になる相手がkeyport[]に無い→SHIFT無し)
#   '`'(96)=KEY88_BACKQUOTE     Port2 0x01   (相手はKEY88_AT=64だがAT未配線→SHIFT無し)
#   SHIFT自体: KEY88_SHIFT/SHIFTL/SHIFTR はいずれも Port8 0x40
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
Z80TEXT="$REPO/tools/asm/z80text.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-bracesym.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR"

# --- 自作試験ROM(key_matrix_selftest.shと同一構成) -------------------------
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
FRAMES=180
TYPE_AT=60
HOLD=4
GAP=4
STEP=$((HOLD + GAP))

# SHIFT無し組とSHIFT要組を別々の実行に分ける。Port5 bit3〜6は「無し組」
# ('[' '\' ']' '^')と「要組」('{' '|' '}' '~')の両方で使われる(keyport[]で
# 同じビットを共有するため)ので、同じ実行内で両方を打つと同じアドレスに
# 押下ウィンドウが2回出てきてしまい、「ウィンドウの外は常に非押下」という
# 単純な判定が壊れる。実行を分ければ各アドレス・ビットの押下は実行中に
# 1回だけになり、判定が素直になる。
TEXT_UNSHIFTED='[\]^_`'
TEXT_SHIFTED='{|}~'
[ "${#TEXT_UNSHIFTED}" -eq 6 ] || ng "SHIFT無し組の文字数が6でない(シェルエスケープ崩れ疑い)"
[ "${#TEXT_SHIFTED}" -eq 4 ] || ng "SHIFT要組の文字数が4でない(シェルエスケープ崩れ疑い)"

run_case() {
  # $1=出力先prefix $2=--type文字列 $3...=frontendへの追加環境変数(無くてよい)
  local prefix="$1" text="$2"; shift 2
  env "$@" "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames "$FRAMES" \
    --mem-write-log "$WORK/${prefix}.mwl.txt" --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
    --type-at "$TYPE_AT" --type "$text" \
    >"$WORK/${prefix}.stdout" 2>"$WORK/${prefix}.stderr"
}

to_tsv() {
  # $1=mwl.txt $2=出力tsv (check_windowが読む(frame, addr, value)の3列に絞る。
  # mwl.txtの生ログをそのまま渡すと見出しコメント行と列数が食い違う)
  awk '/^[[:space:]]*[0-9]+[[:space:]]/ {print $2, $4, $5}' "$1" > "$2"
}

run_case normal_unshifted "$TEXT_UNSHIFTED" || ng "SHIFT無し組の実行が失敗した"
grep -q '取りこぼし: 0件' "$WORK/normal_unshifted.mwl.txt" || ng "SHIFT無し組で取りこぼしが0件でない"
to_tsv "$WORK/normal_unshifted.mwl.txt" "$WORK/normal_unshifted.tsv"

run_case normal_shifted "$TEXT_SHIFTED" || ng "SHIFT要組の実行が失敗した"
grep -q '取りこぼし: 0件' "$WORK/normal_shifted.mwl.txt" || ng "SHIFT要組で取りこぼしが0件でない"
to_tsv "$WORK/normal_shifted.mwl.txt" "$WORK/normal_shifted.tsv"
ok "両実行が成功し、mem-write-logの取りこぼしが0件"

# check_window: 1個のアドレス・ビットについて、「押されているべき区間の
# 集合(1個以上)」の外では常に非押下、内では常に押下であることを確かめる。
# SHIFTのビット(Port8 bit6)はSHIFT要組の4文字すべてで共有されるため、
# 区間を複数渡せるようにしてある(単一区間しか無いキーはそのまま1個渡す)。
check_window() {
  # $1=addr(C000形式) $2=mask $3=file $4...=press:release の区間(1個以上)
  local addr="$1" mask="$2" file="$3"; shift 3
  python3 - "$file" "$addr" "$mask" "$@" <<'PYEOF'
import sys
path, addr, mask_s = sys.argv[1:4]
mask = int(mask_s, 0)
windows = []
for w in sys.argv[4:]:
    p, r = w.split(':')
    windows.append((int(p), int(r)))

def is_pressed(frame):
    return any(p <= frame < r for p, r in windows)

by_frame = {}
for line in open(path):
    frame_s, a, value_s = line.split()
    if a != addr:
        continue
    by_frame.setdefault(int(frame_s), []).append(int(value_s, 16))

ok = True
if not by_frame:
    print(f"{addr}: 記録が無い", file=sys.stderr); ok = False
boundary_frames = set()
for p, r in windows:
    boundary_frames.add(p); boundary_frames.add(r)
for frame, values in sorted(by_frame.items()):
    pressed = is_pressed(frame)
    last_ok = ((values[-1] & mask) == 0) if pressed else ((values[-1] & mask) == mask)
    if not last_ok:
        print(f"{addr} mask=0x{mask:02X} frame={frame}: 最後の値0x{values[-1]:02X}が"
              f"{'押下中' if pressed else '非押下'}の期待と不一致", file=sys.stderr)
        ok = False
    if frame not in boundary_frames:
        bad = [v for v in values if ((v & mask) == 0) != pressed]
        if bad:
            print(f"{addr} mask=0x{mask:02X} frame={frame}: 境界でないのに不一致な値: "
                  f"{[hex(v) for v in bad]}", file=sys.stderr)
            ok = False
missing = [f for f in boundary_frames if f not in by_frame]
if missing:
    print(f"{addr}: 押下/解放の境界フレーム自体の記録が無い: {sorted(missing)}", file=sys.stderr)
    ok = False
sys.exit(0 if ok else 1)
PYEOF
}

# 文字index(0始まり)→押下/解放フレーム
frame_of() { echo $(( TYPE_AT + $1 * STEP )); }
window_of() { echo "$(frame_of "$1"):$(( $(frame_of "$1") + HOLD ))"; }

# SHIFT自身のビット(Port8 0x40)。keyport[]でKEY88_SHIFT/SHIFTL/SHIFTRが
# 共通して指す位置。
SHIFT_ADDR=C008
SHIFT_MASK=0x40

check_key() {
  # $1=index $2=addr $3=mask $4=file (単一区間)。
  # ng()を内側で呼ばず終了コードだけ返す(故障注入側で「NGになること」自体を
  # 検査したいので、ここでexitされては困る。呼び出し側で ng を付ける)。
  local idx="$1" addr="$2" mask="$3" file="$4"
  check_window "$addr" "$mask" "$file" "$(window_of "$idx")"
}

# SHIFT無し組: index 0='[' 1='\' 2=']' 3='^' 4='_' 5='`'
check_key 0 C005 0x08 "$WORK/normal_unshifted.tsv" || ng "'[' のキーマトリクスが期待と不一致"
ok "'[' → Port5 bit3"
check_key 1 C005 0x10 "$WORK/normal_unshifted.tsv" || ng "'\\' のキーマトリクスが期待と不一致"
ok "'\\' → Port5 bit4"
check_key 2 C005 0x20 "$WORK/normal_unshifted.tsv" || ng "']' のキーマトリクスが期待と不一致"
ok "']' → Port5 bit5"
check_key 3 C005 0x40 "$WORK/normal_unshifted.tsv" || ng "'^' のキーマトリクスが期待と不一致"
ok "'^' → Port5 bit6"
check_key 4 C007 0x80 "$WORK/normal_unshifted.tsv" || ng "'_' のキーマトリクスが期待と不一致"
ok "'_' → Port7 bit7"
check_key 5 C002 0x01 "$WORK/normal_unshifted.tsv" || ng "'\`' のキーマトリクスが期待と不一致"
ok "'\`' → Port2 bit0"

# SHIFT無し組ではSHIFTビット(Port8 bit6)は終始押されないこと
n_shift_uniq="$(awk -v a="$SHIFT_ADDR" '/^[[:space:]]*[0-9]+[[:space:]]/ && $4==a {print $5}' "$WORK/normal_unshifted.mwl.txt" | sort -u | wc -l | tr -d ' ')"
[ "$n_shift_uniq" -le 1 ] || ng "SHIFT無し組なのにSHIFTビット(${SHIFT_ADDR})が変化した"
ok "SHIFT無し組ではSHIFTビットが終始不変(押されていない)"

# SHIFT要組: index 0='{' 1='|' 2='}' 3='~'。土台ビット(Port5)は各文字とも
# 単一区間だが、SHIFTビット(Port8 bit6)は4文字すべてで押されるので
# 4区間まとめて1回で確かめる。
check_key 0 C005 0x08 "$WORK/normal_shifted.tsv" || ng "'{' のキーマトリクスが期待と不一致"
ok "'{' → Port5 bit3"
check_key 1 C005 0x10 "$WORK/normal_shifted.tsv" || ng "'|' のキーマトリクスが期待と不一致"
ok "'|' → Port5 bit4"
check_key 2 C005 0x20 "$WORK/normal_shifted.tsv" || ng "'}' のキーマトリクスが期待と不一致"
ok "'}' → Port5 bit5"
check_key 3 C005 0x40 "$WORK/normal_shifted.tsv" || ng "'~' のキーマトリクスが期待と不一致"
ok "'~' → Port5 bit6"

check_window "$SHIFT_ADDR" "$SHIFT_MASK" "$WORK/normal_shifted.tsv" \
  "$(window_of 0)" "$(window_of 1)" "$(window_of 2)" "$(window_of 3)" \
  || ng "SHIFT要組: SHIFTビット(${SHIFT_ADDR} ${SHIFT_MASK})が4文字ぶんの区間と一致しない"
ok "'{' '|' '}' '~' の4文字ともSHIFTビット(Port8 bit6)が押下区間と一致"

# 対象外のポート(SHIFT無し組: C000,C001,C003,C004,C006,C008,C009-C00E /
# SHIFT要組: C000,C001,C002,C003,C004,C006,C009-C00E)は終始不変であること
for addr in C000 C001 C003 C004 C006 C008 C009 C00A C00B C00C C00D C00E; do
  n_uniq="$(awk -v a="$addr" '/^[[:space:]]*[0-9]+[[:space:]]/ && $4==a {print $5}' "$WORK/normal_unshifted.mwl.txt" | sort -u | wc -l | tr -d ' ')"
  [ "$n_uniq" -le 1 ] || ng "SHIFT無し組: 対象外port ${addr} の値が変化している(意図しない書き換え, 相異なる値=${n_uniq}種)"
done
# C00E(PortE)はここでは対象外: SHIFTはKEY88_SHIFTL(RETROK_LSHIFT)経由で
# 押しており、keyboard.c の do_lattertype() が「後期型キーボード」対応
# としてKEY88_SHIFTL押下時に自動でKEY88_EXT_SHIFTL(PortE bit2)も押す
# (KEY88_F6〜KEY88_SHIFTRの既存の一般規則。ROM由来ではなくコア自身の
# ソースにある既存挙動で、SHIFTED[]の既存エントリ('!'等)を打つときも
# 同様に起きる、この変更固有ではない副作用)。
for addr in C000 C001 C002 C003 C004 C006 C009 C00A C00B C00C C00D; do
  n_uniq="$(awk -v a="$addr" '/^[[:space:]]*[0-9]+[[:space:]]/ && $4==a {print $5}' "$WORK/normal_shifted.mwl.txt" | sort -u | wc -l | tr -d ' ')"
  [ "$n_uniq" -le 1 ] || ng "SHIFT要組: 対象外port ${addr} の値が変化している(意図しない書き換え, 相異なる値=${n_uniq}種)"
done
# C00Eも「SHIFT区間とだけ一致して変化する」ことは確かめる(無関係なタイミングでは
# 変化しない、を保証する)。ビットはEXT_SHIFTL(bit2)。
check_window C00E 0x04 "$WORK/normal_shifted.tsv" \
  "$(window_of 0)" "$(window_of 1)" "$(window_of 2)" "$(window_of 3)" \
  || ng "SHIFT要組: PortE bit2(EXT_SHIFTL)の変化区間がSHIFT区間と一致しない"
ok "PortE bit2(EXT_SHIFTL、SHIFT機構の既知の副作用)もSHIFT区間とだけ一致"
ok "対象外ポートは終始不変"

# --- 故障注入: '{' の土台キーをわざと '\' にすり替える -------------------
run_case fault "$TEXT_SHIFTED" Q88MEASURE_FAULT_SWAP_BRACE_KEY=1 || ng "故障注入版の実行が失敗した"
to_tsv "$WORK/fault.mwl.txt" "$WORK/fault.tsv"

set +e
check_key 0 C005 0x08 "$WORK/fault.tsv" 2>/dev/null  # NGが出る前提の呼び出しなので診断出力は捨てる
fault_bit3_rc=$?
set -e
[ "$fault_bit3_rc" -ne 0 ] || ng "故障注入したのに'{'のPort5 bit3が期待通りになった(検出できていない)"
ok "故障注入(Q88MEASURE_FAULT_SWAP_BRACE_KEY)で'{'のビットずれをこの検査自身が検出した"

ok "全項目合格"

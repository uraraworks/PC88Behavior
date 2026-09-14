#!/usr/bin/env bash
# テキストVRAMの写し（M7 段階1の器具1、--vram-dump/--vram-dump-at）の自己検査。
#
# 公式ROMは不要。自作 L1 IPL（src/l1_ipl/make_ipl_rom.py --font-sample）が
# テキストVRAMへ書く既知のバイト列を、実際にハーネスで走らせて写し取り、
# 生成器の規則から独立に計算した期待値と一致することを確かめる。
#
# 期待値の求め方について: emit_font_sample() が「どの文字コードをどのセルに
# 書いたか」（0x20始まり、80桁×3行、余りは空白0x20で埋め、属性は全て0）は
# 両者が合意する必要がある取り決め（テストパターンの約束であって、検証したい
# データではない）なので、tools/l2_verify_pixels.py の code_at_cell() と同じ
# 考え方でこのファイル自身が独立に再実装する（実行結果を手で書き写さない）。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-vramdump.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR"

mkdir -p "$WORK/rom"
python3 "$REPO/src/l1_ipl/make_ipl_rom.py" "$WORK/rom" --font-sample >"$WORK/gen.txt"

FRAME=30   # 起動シーケンスが終わって font_sample の書き込みが済んでいる十分先のフレーム

# --- 期待値の独立計算（emit_font_sample の取り決めを再実装。バイト列は書き写さない） ---
#
# emit_font_sample() は a.xor_a()（A=0）をアトリビュート/文字コード書き込みの
# 外側で1回だけ呼び、各行の「アトリビュート40バイトを書く」ループは
# その時点のAの値をそのまま書く（Z80アキュムレータの状態をそのまま反映）。
# つまり実際に0で埋まるのは1行目のアトリビュートだけで、2行目以降は
# 直前の行の最後の文字コードが漏れて入る——docstringの「明示的に0クリア」は
# 1行目にしか成り立たない。これは自分で実測して初めて分かったこと
# （最初は docstring どおり全行0だと仮定して期待値を書いたところ、
# 2行目以降のアトリビュート域と3行目前半の文字域で不一致になった）。
# ここでは実際に生成されるバイト列を当てるのが目的なので、docstringの
# 主張ではなく実際の命令の並びをアキュムレータの状態遷移として再現する。
python3 - "$WORK/expected.bin" <<'PYEOF'
import sys
COLS, STRIDE, ATTR_BYTES, ROWS = 80, 120, 40, 3
CODE_FIRST, CODE_COUNT, PAD = 0x20, 0x100 - 0x20, 0x20
buf = bytearray(ROWS * STRIDE)
a_reg = 0   # a.xor_a() は行ループの外で1回だけ
idx = 0
for r in range(ROWS):
    base = r * STRIDE
    for i in range(ATTR_BYTES):
        buf[base + COLS + i] = a_reg   # その時点のAをそのまま書く
    for c in range(COLS):
        code = (CODE_FIRST + idx) if idx < CODE_COUNT else PAD
        a_reg = code
        buf[base + c] = a_reg
        idx += 1
open(sys.argv[1], "wb").write(bytes(buf))
PYEOF
[ "$(wc -c < "$WORK/expected.bin" | tr -d ' ')" = "360" ] || ng "期待値生成のバイト数がおかしい"
ok "期待値を生成器の規則から独立に計算（360バイト = 3行 x 120）"

# --- 陽性: 1件指定。フレームどおりに書き出され、先頭360バイトが期待値と一致 ---
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 60 \
  --vram-dump "$WORK/vram.bin" --vram-dump-at "$FRAME" \
  --out "$WORK/trace.txt" \
  >"$WORK/positive.stdout" 2>"$WORK/positive.stderr" \
  || ng "陽性対照の実行が失敗した"

[ -f "$WORK/vram.bin" ] || ng "--vram-dump の出力ファイルが作られていない（1件指定なのでパスそのまま）"
[ "$(wc -c < "$WORK/vram.bin" | tr -d ' ')" = "3000" ] || ng "写しのバイト数が3000でない（F3C8-FF7F、両端含む）"
[ -f "$WORK/vram.bin.info.txt" ] || ng "見出し(info.txt)が作られていない"
grep -q "^frame: $FRAME\$" "$WORK/vram.bin.info.txt" || ng "見出しにフレーム番号が無い"
grep -q '^timing: retro_run() 呼び出しの直前$' "$WORK/vram.bin.info.txt" || ng "見出しにタイミングの記録が無い"
grep -q '^range: F3C8-FF7F' "$WORK/vram.bin.info.txt" || ng "見出しに範囲の記録が無い"
ok "1件指定でパスそのまま・3000バイト・見出し(frame/timing/range)を確認"

head -c 360 "$WORK/vram.bin" > "$WORK/vram_head360.bin"
cmp -s "$WORK/vram_head360.bin" "$WORK/expected.bin" \
  || ng "写しの先頭360バイトが独立計算した期待値と一致しない"
ok "写しの該当位置(F3C8起点3行ぶん)が生成器の意図したバイト列と一致"

# --- 陽性: 複数フレーム指定でファイル名にフレーム番号が差し込まれる規則 ---
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 60 \
  --vram-dump "$WORK/multi.bin" --vram-dump-at 10 \
  --vram-dump "$WORK/multi.bin" --vram-dump-at "$FRAME" \
  >"$WORK/multi.stdout" 2>"$WORK/multi.stderr" \
  || ng "複数指定の実行が失敗した"
[ -f "$WORK/multi.f000010.bin" ] || ng "2件目以降でフレーム番号がファイル名へ差し込まれていない(frame=10)"
[ -f "$WORK/multi.f000030.bin" ] || ng "2件目以降でフレーム番号がファイル名へ差し込まれていない(frame=30)"
[ ! -f "$WORK/multi.bin" ] || ng "複数件指定なのに素のパスへも書かれている(規則が効いていない)"
ok "件数2以上のときはファイル名へフレーム番号を差し込む規則を確認"

# --- 出力先の安全策: リポジトリ内(tmp/以外)は拒否 ---
set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 5 \
  --vram-dump "$REPO/measurements/should_not_write.bin" --vram-dump-at 1 \
  >/dev/null 2>"$WORK/unsafe.stderr"
unsafe_rc=$?
set -e
[ "$unsafe_rc" -ne 0 ] || ng "リポジトリ内(tmp/以外)への出力を拒否できない"
[ ! -e "$REPO/measurements/should_not_write.bin" ] || {
  rm -f "$REPO/measurements/should_not_write.bin"
  ng "拒否されたはずなのにファイルが作られていた"
}
grep -q 'リポジトリ内 (tmp/ 以外) を指している' "$WORK/unsafe.stderr" \
  || ng "拒否メッセージの分類が無い"
ok "リポジトリ内(tmp/以外)への出力先を拒否"

# --- 出力先の安全策: リポジトリ内の tmp/ 配下は許可 ---
mkdir -p "$REPO/tmp"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 5 \
  --vram-dump "$REPO/tmp/vram_selftest_probe.bin" --vram-dump-at 1 \
  >/dev/null 2>"$WORK/tmpok.stderr" \
  || { cat "$WORK/tmpok.stderr" >&2; ng "tmp/配下への出力が拒否された(許可されるべき)"; }
[ -f "$REPO/tmp/vram_selftest_probe.bin" ] || ng "tmp/配下へ書けていない"
rm -f "$REPO/tmp/vram_selftest_probe.bin" "$REPO/tmp/vram_selftest_probe.bin.info.txt"
ok "リポジトリ内の tmp/ 配下への出力は許可"

# --- 故障注入: 写しの1バイトを化けさせる（環境変数、既定offなので通常は無害） ---
Q88MEASURE_FAULT_CORRUPT_VRAM_DUMP=1 "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --frames 60 --vram-dump "$WORK/corrupt.bin" --vram-dump-at "$FRAME" \
  >/dev/null 2>"$WORK/corrupt.stderr" \
  || ng "故障注入版の実行が失敗した"
head -c 360 "$WORK/corrupt.bin" > "$WORK/corrupt_head360.bin"
if cmp -s "$WORK/corrupt_head360.bin" "$WORK/expected.bin"; then
  ng "故障注入(1バイト化け)後も期待値と一致してしまい、検査が検出できていない"
fi
ok "故障注入(1バイト化け)により期待値との比較がNGになることを確認"

ok "全項目合格"

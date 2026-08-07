#!/usr/bin/env bash
# tools/verify_l2.sh — 自作 L2 フォント(半角ANK+セミグラフィック)の検証。**公式 ROM は要らない。**
#
# docs/spec/l2-font.md 第2版 5節（適合条件）②の2項目に加え、
# 「バッファに届いた ≠ 画面に出た」を埋めるための4節目を実行する:
#   1. 生成器(src/l2_font/make_font_rom.py)が出したビットパターンと、
#      独立実装(tools/l2_verify_independent.py)で組み直したビットパターンが
#      一致すること（「意図した字形が入っていること」の検査）
#   2. 生成した FONT.ROM を計測ハーネスに読ませ、font_mem（実際に画面へ出る
#      唯一のバッファ、l2-font.md 1節）まで欠落・混入なく届くことを CRC32 で
#      確認すること（tools/harness/fontsrc_selftest.sh と同じ仕組みを、
#      合成パターンではなく実際に使う FONT.ROM で行う）
#   3. （新規）自作IPL「フォント見本」（src/l1_ipl/make_ipl_rom.py --font-sample）
#      を実際に走らせ、画面ピクセルのスナップショットを取り、FONT.ROM から
#      独立に組み立てた期待ビットマップと突き合わせる
#      （tools/l2_verify_pixels.py。font_memより先の末端＝実際に描画された
#      ピクセルまで見る）
#
# 使い方: tools/verify_l2.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_UNSCII="$(cd "$REPO/.." && pwd)/vendor/unscii"
VENDOR_CORE="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="${TMPDIR:-/tmp}/pc88h-verify-l2.$$"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK"

HEX="$VENDOR_UNSCII/unscii-8.hex"
if [ ! -f "$HEX" ]; then
  echo "unscii-8.hex が無い。先に tools/fetch_unscii.sh を実行すること" >&2
  exit 1
fi

say "1. FONT.ROM を生成（--selftest 込み）"
mkdir -p "$WORK/fontout"
python3 "$REPO/src/l2_font/make_font_rom.py" "$WORK/fontout" --unscii-hex "$HEX" --selftest
FONT_ROM="$WORK/fontout/FONT.ROM"

say "2. 独立実装との突き合わせ（生成器 vs. 別経路で組み直したビットパターン）"
python3 "$REPO/tools/l2_verify_independent.py" "$FONT_ROM" --unscii-hex "$HEX"

say "2b. わざと壊して不一致になることを確認（検査が独立であることの実測）"
if python3 "$REPO/tools/l2_verify_independent.py" "$FONT_ROM" --unscii-hex "$HEX" \
     --break-independent-path > "$WORK/break.txt" 2>&1; then
  echo "NG: わざと壊したのに一致してしまった（検査に検出力が無い）" >&2
  cat "$WORK/break.txt" >&2
  exit 1
fi
echo "OK: わざと壊した独立実装は不一致で失敗した（検査の検出力を確認）"
cat "$WORK/break.txt"

CORE="$(ls "$VENDOR_CORE"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo
  echo "計測ハーネスが未取得のため、3節（font_memまでの到達確認）はスキップする。" >&2
  echo "先に tools/setup_harness.sh を実行すれば全項目を検証できる。" >&2
  say "ここまでの結果"
  echo "合格（1・2・2bのみ。ハーネス未取得のため3は未実施）"
  exit 0
fi

say "3. font_mem までの到達確認（tools/harness/fontsrc_selftest.sh と同じ仕組み）"
make -s -C "$REPO/tools/harness/frontend"

mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom" > "$WORK/romgen.txt"
cp "$FONT_ROM" "$WORK/rom/FONT.ROM"

EXPECTED="$(python3 - "$FONT_ROM" <<'PYEOF'
import sys, zlib
data = open(sys.argv[1], "rb").read()
ank, graph = data[:2048], data[2048:]
print("%08X" % (zlib.crc32(ank) & 0xFFFFFFFF))
print("%08X" % (zlib.crc32(graph) & 0xFFFFFFFF))
PYEOF
)"
EXP_ANK="$(echo "$EXPECTED" | sed -n 1p)"
EXP_GRAPH="$(echo "$EXPECTED" | sed -n 2p)"
echo "期待CRC32（このFONT.ROM自身から計算）: ANK=$EXP_ANK GRAPH=$EXP_GRAPH"

FONTLOG="$WORK/fontlog.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" --rom-dir "$WORK/rom" --frames 4 \
  --out "$WORK/trace.txt" --font-log "$FONTLOG" \
  2> "$WORK/stderr.txt" || { echo "q88measure 失敗:"; cat "$WORK/stderr.txt"; exit 1; }
cat "$FONTLOG"

ANK_LINE="$(grep 'font_mem  ANK' "$FONTLOG" || true)"
GRAPH_LINE="$(grep 'font_mem  GRAPH' "$FONTLOG" || true)"

if ! printf '%s\n' "$ANK_LINE" | grep -q 'ROM_FILE'; then
  echo "NG: font_mem ANK が ROM_FILE でない: $ANK_LINE" >&2; exit 1
fi
GOT_ANK="$(printf '%s\n' "$ANK_LINE" | awk '{print $NF}')"
if [ "$GOT_ANK" != "$EXP_ANK" ]; then
  echo "NG: font_mem ANK の CRC32 不一致 (got=$GOT_ANK want=$EXP_ANK)" >&2; exit 1
fi
echo "OK: font_mem ANK の CRC32 が一致（$GOT_ANK） ＝ FONT.ROMのANK面が欠落・混入なく届いている"

if ! printf '%s\n' "$GRAPH_LINE" | grep -q 'ROM_FILE'; then
  echo "NG: font_mem GRAPH が ROM_FILE でない: $GRAPH_LINE" >&2; exit 1
fi
GOT_GRAPH="$(printf '%s\n' "$GRAPH_LINE" | awk '{print $NF}')"
if [ "$GOT_GRAPH" != "$EXP_GRAPH" ]; then
  echo "NG: font_mem GRAPH の CRC32 不一致 (got=$GOT_GRAPH want=$EXP_GRAPH)" >&2; exit 1
fi
echo "OK: font_mem GRAPH の CRC32 が一致（$GOT_GRAPH） ＝ FONT.ROMのGRAPH面が欠落・混入なく届いている"

say "4. 画面ピクセルまでの到達確認（font_memより先の末端）"
mkdir -p "$WORK/pxrom"
python3 "$REPO/src/l1_ipl/make_ipl_rom.py" "$WORK/pxrom" --font-sample > "$WORK/iplgen.txt"
cp "$FONT_ROM" "$WORK/pxrom/FONT.ROM"

SHOT="$WORK/shot.ppm"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" --rom-dir "$WORK/pxrom" --frames 60 \
  --screenshot "$SHOT" \
  2> "$WORK/shot_stderr.txt" || { echo "q88measure(スクリーンショット) 失敗:"; cat "$WORK/shot_stderr.txt"; exit 1; }
grep -q 'スクリーンショットを書き出した' "$WORK/shot_stderr.txt" || {
  echo "NG: スクリーンショットが書き出されなかった（コアに機能が無い可能性）" >&2
  cat "$WORK/shot_stderr.txt" >&2
  exit 1
}

python3 "$REPO/tools/l2_verify_pixels.py" --font-rom "$FONT_ROM" --screenshot "$SHOT"

say "4b. わざと壊して不一致になることを確認（画面比較の検出力の実測）"
if python3 "$REPO/tools/l2_verify_pixels.py" --font-rom "$FONT_ROM" --screenshot "$SHOT" \
     --break-expected > "$WORK/pxbreak.txt" 2>&1; then
  echo "NG: わざと壊したのに一致してしまった（画面比較に検出力が無い）" >&2
  cat "$WORK/pxbreak.txt" >&2
  exit 1
fi
echo "OK: わざと1文字ぶん潰した期待ビットマップは、実際の画面と不一致で検出された"
cat "$WORK/pxbreak.txt"

say "合格"
echo "1) 生成器と独立実装の再構成が完全一致（かつ、わざと壊すと不一致で検出できることを確認）"
echo "2) 実際に生成した FONT.ROM の内容が font_mem（画面へ出る唯一のバッファ）まで"
echo "   欠落・混入なく届くことを CRC32 で実測確認した"
echo "3) 自作IPLのフォント見本を実際に走らせ、画面ピクセルが FONT.ROM から独立に"
echo "   組み立てた期待どおりであることを確認した（縦2倍・下4ラインの空白を含む）"
echo "   （わざと1文字潰すと不一致で検出できることも確認済み）"
echo "   スクリーンショット: $SHOT （このスクリプト終了時に削除される。手元で見たい場合は"
echo "   --screenshot 付きで q88measure を直接実行すること）"

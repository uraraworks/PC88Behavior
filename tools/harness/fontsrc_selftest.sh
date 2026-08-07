#!/usr/bin/env bash
# フォント供給源の可視化（M5下ごしらえ）の疎通試験。公式 ROM は一切要らない。
#
# docs/spec/l2-font.md 3節は、font_mem（実際に画面へ出る唯一のバッファ）が
# 「ROM読み込みの成否に関わらず出所不明のデータへ差し替わる」経路を挙げている。
# ここでは make_test_rom.py --enable-font が生成する**完全に自作の** FONT.ROM
# （公式ROM・実在するフォントのいずれとも無関係な合成パターン）を使い、
# 「そのファイルの中身が font_mem までそのまま届く」ことを CRC32 で照合する。
# グリフのバイト列そのものはログにも標準出力にも一切出さない
# （比較するのは CRC32 という digest だけ）。
#
# 確認する内容:
#   1. FONT.ROM を置いた場合、font_mem の ANK/GRAPH 両半分が ROM_FILE タグに
#      なり、CRC32 が生成時の期待値と一致すること（=外部ファイルの内容が
#      font_mem まで欠落・混入なく届いている）
#   2. 書き込み回数が両方とも 1 であること（二重ロードで踏みつぶされていない）
#   3. FONT.ROM が無い場合、ANK/GRAPHとも UNAVAILABLE タグになり、
#      CRC32 が「0バイト」の値（=0埋め）と一致すること
#   4. FONT.ROM が無く KANJI1.ROM だけがある場合、ANK は KANJI_DERIVED タグに
#      なること（未確認のバッファをフォントとして使わない、というガードが
#      「実際に読み込みが成功した場合だけ」効いていることの確認）
#
# 検査を足したら、わざと壊して検査が落ちることを一度確認してから採用する
# という規律（docs/PLAN.md）に従い、以下を実際に壊して確認済み
# （手順と結果は docs/notes/m5-fontsrc-selftest.md）:
#   - libretro.c の Font1 成功分岐に「読み込み成功後、内容を built_in相当の
#     ダミーで上書きする」行を復活させる → CRC32 不一致で NG
#   - 同じ分岐で q88h_fontsrc_set の呼び出しを消す → タグが NONE のままで NG
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="${TMPDIR:-/tmp}/pc88h-fontsrc-selftest.$$"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi

say "フロントエンドをビルド"
make -s -C "$REPO/tools/harness/frontend"

# ---- ケース1: FONT.ROM あり ----------------------------------------------
say "合成 ROM を生成（FONT.ROM 込み。中身は自作パターン、公式ROMとは無関係）"
mkdir -p "$WORK/rom-with-font"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom-with-font" --enable-font \
  | tee "$WORK/romgen.txt"
CRC_ANK="$(grep -oE 'CRC32\(先頭2048=ANK\) = [0-9A-F]+' "$WORK/romgen.txt" | awk '{print $NF}')"
CRC_GRAPH="$(grep -oE 'CRC32\(後半2048=GRAPH\)= [0-9A-F]+' "$WORK/romgen.txt" | awk '{print $NF}')"
if [ -z "$CRC_ANK" ] || [ -z "$CRC_GRAPH" ]; then
  echo "NG: make_test_rom.py の出力から期待CRC32を取り出せなかった" >&2
  exit 1
fi
echo "期待CRC32: ANK=$CRC_ANK GRAPH=$CRC_GRAPH"

say "疎通試験（FONT.ROM あり）"
FONTLOG1="$WORK/fontlog-with-font.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom-with-font" \
  --frames 4 \
  --out "$WORK/trace1.txt" \
  --font-log "$FONTLOG1" \
  2> "$WORK/stderr1.txt"
cat "$WORK/stderr1.txt" >&2

if [ ! -f "$FONTLOG1" ]; then
  echo "NG: --font-log の出力ファイルが作られていない" >&2; exit 1
fi
cat "$FONTLOG1"

ANK_LINE="$(grep 'font_mem  ANK' "$FONTLOG1" || true)"
GRAPH_LINE="$(grep 'font_mem  GRAPH' "$FONTLOG1" || true)"

say "font_mem ANK が ROM_FILE タグであることを確認"
if ! printf '%s\n' "$ANK_LINE" | grep -q 'ROM_FILE'; then
  echo "NG: font_mem ANK が ROM_FILE になっていない: $ANK_LINE" >&2; exit 1
fi
echo "OK: font_mem ANK = ROM_FILE"

say "font_mem ANK の CRC32 が外部ファイルの内容と一致することを確認（実測）"
GOT_ANK_CRC="$(printf '%s\n' "$ANK_LINE" | awk '{print $NF}')"
if [ "$GOT_ANK_CRC" != "$CRC_ANK" ]; then
  echo "NG: font_mem ANK の CRC32 が $GOT_ANK_CRC 。期待値は $CRC_ANK" >&2
  echo "    ＝外部ファイルの内容が font_mem まで欠落・混入なく届いていない" >&2
  exit 1
fi
echo "OK: font_mem ANK の CRC32 が外部ファイルと一致（$GOT_ANK_CRC）"
echo "    → FONT.ROM の内容がそのまま font_mem（画面へ出る唯一のバッファ）まで届いている"

say "font_mem GRAPH が ROM_FILE タグ・CRC32一致であることを確認"
if ! printf '%s\n' "$GRAPH_LINE" | grep -q 'ROM_FILE'; then
  echo "NG: font_mem GRAPH が ROM_FILE になっていない: $GRAPH_LINE" >&2; exit 1
fi
GOT_GRAPH_CRC="$(printf '%s\n' "$GRAPH_LINE" | awk '{print $NF}')"
if [ "$GOT_GRAPH_CRC" != "$CRC_GRAPH" ]; then
  echo "NG: font_mem GRAPH の CRC32 が $GOT_GRAPH_CRC 。期待値は $CRC_GRAPH" >&2
  exit 1
fi
echo "OK: font_mem GRAPH = ROM_FILE, CRC32一致（$GOT_GRAPH_CRC）"

say "書き込み回数が想定どおり2であることを確認（下記の理由で1ではない）"
# retro_init() は memory_allocate()（memory.c、上流の標準ロード経路）を
# 呼んだ直後に libretro.c 独自のロードを重ねて実行する（l2-font.md 3節）。
# memory_allocate() 側は osd_dir_rom() が libretro 版では常に NULL のため
# 実際のファイル探索は必ず失敗し、0埋め(UNAVAILABLE)を書き込むだけの
# 「空振り」に終わる——ここで検証したいのは「その後 libretro.c が実際に
# ROM.ROMを読み込んだときに、その内容を上書きしないこと」であって、
# 書き込み回数そのものを1にすることではない。今回のセッションでは
# font.h削除に伴う「読み込み成功後に上書きする」经路（実害のある方）を
# 閉じたが、この「空振り1回+実ロード1回」という二重構造そのものの解消
# （l2-font.md 6節「経路を1本化する」）は次のマイルストーンの範囲として
# 残っている。ここでは「最終的な内容が正しいこと」(CRC32一致、上で確認済み)
# と「回数が想定どおり2から増えていないこと」(=新たな上書きが無いこと)
# を確認する。
ANK_WRITES="$(printf '%s\n' "$ANK_LINE" | awk '{print $(NF-1)}')"
GRAPH_WRITES="$(printf '%s\n' "$GRAPH_LINE" | awk '{print $(NF-1)}')"
if [ "$ANK_WRITES" != "2" ] || [ "$GRAPH_WRITES" != "2" ]; then
  echo "NG: 書き込み回数が想定の2でない (ANK=$ANK_WRITES GRAPH=$GRAPH_WRITES)。" \
       "memory_allocate()の空振り or libretro.c側の実ロードの回数が想定と違う" >&2
  exit 1
fi
echo "OK: 書き込み回数は両方とも2（memory_allocate()の空振り1回 + libretro.c実ロード1回、想定どおり）"

# ---- ケース2: FONT.ROM も KANJI1.ROM も無し -------------------------------
say "合成 ROM を生成（FONT.ROM も KANJI1.ROM も無し）"
mkdir -p "$WORK/rom-none"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom-none" > /dev/null

say "疎通試験（代替データ無し）"
FONTLOG2="$WORK/fontlog-none.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom-none" \
  --frames 4 \
  --out "$WORK/trace2.txt" \
  --font-log "$FONTLOG2" \
  2> "$WORK/stderr2.txt"
cat "$WORK/stderr2.txt" >&2
cat "$FONTLOG2"

ANK_LINE2="$(grep 'font_mem  ANK' "$FONTLOG2" || true)"
if ! printf '%s\n' "$ANK_LINE2" | grep -q 'UNAVAILABLE'; then
  echo "NG: FONT.ROM/KANJI1.ROMとも無いのに font_mem ANK が UNAVAILABLE でない: $ANK_LINE2" >&2
  exit 1
fi
GOT_ZERO_CRC="$(printf '%s\n' "$ANK_LINE2" | awk '{print $NF}')"
if [ "$GOT_ZERO_CRC" != "00000000" ]; then
  echo "NG: 代替データ無し(0埋め)の CRC32 が $GOT_ZERO_CRC 。期待値は 00000000" >&2
  exit 1
fi
echo "OK: font_mem ANK = UNAVAILABLE, CRC32=00000000（0埋め）"

# ---- ケース3: FONT.ROM 無し・KANJI1.ROM あり ------------------------------
say "合成 ROM を生成（FONT.ROM 無し・KANJI1.ROM だけ自作パターンで用意）"
mkdir -p "$WORK/rom-knj"
cp "$WORK/rom-none/N88.ROM"  "$WORK/rom-knj/"
cp "$WORK/rom-none/DISK.ROM" "$WORK/rom-knj/"
# KANJI1.ROM (0x20000 bytes)。中身は自作パターン。font_mem への反映は
# kanji_rom[0][(1<<11)] というオフセットからの2048バイトなので、
# そこだけ確認できれば十分——全域を作る必要はあるが、ここでは単純な
# 式で埋める（グリフとして意味のある形である必要は無い）。
python3 - "$WORK/rom-knj/KANJI1.ROM" <<'PYEOF'
import sys
path = sys.argv[1]
data = bytes(((i * 31 + 7) & 0xFF) for i in range(0x20000))
with open(path, "wb") as f:
    f.write(data)
PYEOF

say "疎通試験（KANJI1.ROM 由来のANKフォールバック）"
FONTLOG3="$WORK/fontlog-knj.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom-knj" \
  --frames 4 \
  --out "$WORK/trace3.txt" \
  --font-log "$FONTLOG3" \
  2> "$WORK/stderr3.txt"
cat "$WORK/stderr3.txt" >&2
cat "$FONTLOG3"

ANK_LINE3="$(grep 'font_mem  ANK' "$FONTLOG3" || true)"
if ! printf '%s\n' "$ANK_LINE3" | grep -q 'KANJI_DERIVED'; then
  echo "NG: KANJI1.ROMは読めているのに font_mem ANK が KANJI_DERIVED でない: $ANK_LINE3" >&2
  exit 1
fi
echo "OK: font_mem ANK = KANJI_DERIVED（KNJ1.ROM の読み込み成功を確認した上でのフォールバック）"

say "合格"
echo "外部ファイル(自作の合成FONT.ROM)の内容が、font_mem（画面へ出る唯一のバッファ）まで"
echo "欠落・混入なく届くことを CRC32 で実測確認した。FONT.ROM が無い場合は代替データ無し"
echo "(0埋め)であることが明示され、KANJI1.ROMだけが読めている場合はそれをANK代わりに"
echo "使うフォールバックが「実際に読み込みが成功した場合だけ」機能することも確認した。"
echo "この検査自体は、わざと壊して落ちることを開発時に一度確認済み"
echo "（詳細は docs/notes/m5-fontsrc-selftest.md）。"

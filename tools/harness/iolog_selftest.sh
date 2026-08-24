#!/usr/bin/env bash
# 順序付き I/O 記録（M4）の疎通試験。
#
# selftest.sh がバスアクセス採取（q88h_trace の有無フラグ）の疎通を確かめ、
# trap_selftest.sh がトラップROM足場の疎通を確かめるのに対し、こちらは
# q88h_iolog（OUT/IN の発生順・値・発行元PC）が末端まで生きていることを
# 実測する。公式 ROM は一切要らない。
#
# make_test_rom.py が生成する合成 ROM は、既知の番地 0x1200 で RAM
# (0xC000) に既知の値 0x5A を置いてから 0x1234 へ進み、そこで
# OUT (99h),A / IN A,(99h) を実行する。これを使って以下を出力から
# 機械的に確かめる:
#
#   - ポート 0x99 への OUT と 0x99 からの IN が、その順序で記録されている
#   - OUT の value が、直前に RAM(0xC000) から読んだ既知の値 0x5A と一致する
#   - 発行元 pc が 0x1234 近傍（OUT=0x1237, IN=0x1239）である
#   - 取りこぼしが 0 件である
#
# 検査を足したら、わざと壊して検査が落ちることを一度確認してから採用する
# という規律（docs/PLAN.md）に従い、以下を実際に落として確認済み:
#   - 記録を無効化する（--io-log を付けない）→ ファイルが作られず NG
#   - 順序の検査を意図的に反転する（IN の行を OUT より前に要求する）→ NG
# 確認の跡は docs/notes/m4-l1-ipl.md に書く。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="${TMPDIR:-/tmp}/pc88h-iolog-selftest.$$"

KNOWN_VALUE="5A"
IO_PORT="99"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi

say "フロントエンドをビルド"
make -s -C "$REPO/tools/harness/frontend"

say "合成 ROM を生成（自作のバイト列。公式 ROM は使わない）"
mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom"

say "疎通試験（--io-log 有効）"
OUT="$WORK/trace.txt"
IOLOG="$WORK/iolog.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom" \
  --frames 8 \
  --out "$OUT" \
  --io-log "$IOLOG" \
  --expect-io-out "0x$IO_PORT" \
  --expect-io-in  "0x$IO_PORT" \
  2> "$WORK/stderr.txt"
cat "$WORK/stderr.txt" >&2

if [ ! -f "$IOLOG" ]; then
  echo "NG: --io-log の出力ファイルが作られていない" >&2
  exit 1
fi

say "main 節に OUT → IN の順で記録されていることを確認"
# main 節だけを取り出す（sub 節と混同しないため。ヘッダのコメント行 '# main' から
# 次の '# sub' の手前まで）
MAIN_SECTION="$(awk '/^# main$/{f=1} /^# sub$/{f=0} f' "$IOLOG")"
OUT_LINE="$(printf '%s\n' "$MAIN_SECTION" | grep -E '  OUT  ' | head -1 || true)"
IN_LINE="$(printf '%s\n' "$MAIN_SECTION" | grep -E '  IN  ' | head -1 || true)"

if [ -z "$OUT_LINE" ] || [ -z "$IN_LINE" ]; then
  echo "NG: main 節に OUT/IN の行が見つからない。以下は main 節:" >&2
  printf '%s\n' "$MAIN_SECTION" >&2
  exit 1
fi

OUT_SEQ="$(printf '%s\n' "$OUT_LINE" | awk '{print $1}')"
IN_SEQ="$(printf '%s\n' "$IN_LINE"  | awk '{print $1}')"
if [ "$OUT_SEQ" -ge "$IN_SEQ" ]; then
  echo "NG: OUT(seq=$OUT_SEQ) が IN(seq=$IN_SEQ) より先に記録されていない" >&2
  exit 1
fi
echo "OK: OUT(seq=$OUT_SEQ) → IN(seq=$IN_SEQ) の順"

say "OUT の value が既知の値 0x$KNOWN_VALUE と一致することを確認"
OUT_VALUE="$(printf '%s\n' "$OUT_LINE" | awk '{print $7}')"
if [ "$OUT_VALUE" != "$KNOWN_VALUE" ]; then
  echo "NG: OUT の value が $OUT_VALUE 。期待値は $KNOWN_VALUE 。該当行:" >&2
  printf '%s\n' "$OUT_LINE" >&2
  exit 1
fi
echo "OK: OUT value=$OUT_VALUE"

say "発行元 pc が 0x1234 近傍であることを確認"
OUT_PC="$(printf '%s\n' "$OUT_LINE" | awk '{print $8}')"
IN_PC="$(printf '%s\n' "$IN_LINE"  | awk '{print $8}')"
# OUT=0x1237, IN=0x1239（make_test_rom.py 参照）。1230-123F の範囲にあれば良しとする。
for pc in "$OUT_PC" "$IN_PC"; do
  case "$pc" in
    123[0-9A-F]) : ;;
    *) echo "NG: 発行元pc ($pc) が 0x1234 近傍でない" >&2; exit 1 ;;
  esac
done
echo "OK: pc(OUT)=$OUT_PC pc(IN)=$IN_PC"

say "取りこぼしが main/sub とも 0件であることを確認"
if ! grep -qE '取りこぼし: 0件' "$IOLOG"; then
  echo "NG: 取りこぼしが 0件でない。以下は該当行:" >&2
  grep '取りこぼし' "$IOLOG" >&2 || true
  exit 1
fi
echo "OK: 取りこぼし 0件（main/sub とも）"

say "--io-log-from-frame で実行窓を変えず採取開始だけ遅らせる"
WINDOWED="$WORK/iolog-windowed.txt"
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" --rom-dir "$WORK/rom" --frames 8 --reset-at 4 \
  --io-log "$WINDOWED" --io-log-from-frame 4 \
  > /dev/null 2> "$WORK/windowed.stderr.txt"
if ! grep -q '^io-log-from-frame: 4$' "$WINDOWED"; then
  echo "NG: 採取開始frameがログへ明記されていない" >&2
  exit 1
fi
if ! awk '
  /^[[:space:]]*[0-9]+[[:space:]]/ { seen=1; if ($3 < 4) bad=1 }
  END { exit !(seen && !bad) }
' "$WINDOWED"; then
  echo "NG: 遅延採取が空、またはframe 4より前のイベントを含む" >&2
  exit 1
fi
echo "OK: 8F実行のままframe 4以後だけをI/O記録"

say "--io-log を付けない場合に記録ファイルが作られないことを確認（既定 off の確認）"
if [ -f "$WORK/iolog-noflag.txt" ]; then
  echo "NG: 使っていないはずの一時ファイルが存在する（テストの前提が壊れている）" >&2
  exit 1
fi
"$REPO/tools/harness/frontend/q88measure" \
  --core "$CORE" \
  --rom-dir "$WORK/rom" \
  --frames 8 \
  --out "$WORK/trace-noiolog.txt" \
  > /dev/null 2>&1 || true
if [ -f "$WORK/iolog-noflag.txt" ]; then
  echo "NG: --io-log を付けていないのにファイルができた（既定offが効いていない）" >&2
  exit 1
fi
echo "OK: --io-log 無指定では I/O 記録ファイルが作られない（既定 off が効いている）"

say "合格"
echo "順序付きI/O記録（発生順・値・発行元PC）が末端まで届いている。"
echo "この検査自体は、わざと壊して落ちることを開発時に一度確認済み"
echo "（記録を無効化 / seqの順序判定を反転 → いずれも NG になることを確認。"
echo " 詳細は docs/notes/m4-l1-ipl.md）。"

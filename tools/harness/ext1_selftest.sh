#!/usr/bin/env bash
# ext1（拡張ROMバンク測定、docs/notes/ext1-rom-bank-preregistration.md 改訂1）の
# 器具自己検査。本走の前に必ずこれを通す。公式ROMは一切使わない。
#
# G1: 既存の --mem-write-log / --int-log 自己検査を同じHEADで再実行する。
# G1b: 自作ROM(rom_ra、切替なし)を数フレームだけ走らせ、B1の期待値
#      (main側の既知パターン 0xE0/0xE1/0xC7) がRAMマーカーに出ることを
#      確かめる（陽性対照、器具の疎通確認）。
# G6: バンク1とバンク3のファイルを入れ替えたROMディレクトリで同じ手順を
#     走らせ、読み取り結果が「入れ替わって見える」ことを確認する
#     （故障注入——判定の検出力そのものを確かめる）。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-ext1-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

source "$REPO/tools/lib_l3_measure.sh"

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(find_l3_core)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"
ensure_l3_frontend || ng "フロントエンドのビルドに失敗した"

echo "== G1: 既存の計測フック自己検査を同じHEADで再実行 =="
bash "$REPO/tools/harness/mem_write_log_selftest.sh" || ng "mem_write_log_selftest.sh 失敗"
ok "mem_write_log_selftest.sh"
bash "$REPO/tools/harness/intlog_selftest.sh" || ng "intlog_selftest.sh 失敗"
ok "intlog_selftest.sh"

echo "== G1b: rom_ra 疎通確認(陽性対照) =="
python3 "$REPO/tools/harness/make_ext_rom_test.py" "$WORK/rom_ra" --arm ra >"$WORK/gen_ra.log"

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_ra" --frames 30 \
  --mem-write-log "$WORK/ra.memlog.txt" \
  --mem-write-range 0xC100-0xC134 --mem-write-from-frame 0 \
  --out "$WORK/ra.report.txt" >"$WORK/ra.run.log" 2>&1 \
  || ng "rom_ra の実行に失敗($WORK/ra.run.log 参照)"

# mem-write-log から最終値を拾う（同一addrへの最後の書き込みが最終状態）
h="$(awk '$4=="C100"{v=$5} END{print v}' "$WORK/ra.memlog.txt")"
t="$(awk '$4=="C101"{v=$5} END{print v}' "$WORK/ra.memlog.txt")"
r="$(awk '$4=="C102"{v=$5} END{print v}' "$WORK/ra.memlog.txt")"
[ "$h" = "E0" ] || ng "G1b: B1 head期待E0、実際=${h:-なし}"
[ "$t" = "E1" ] || ng "G1b: B1 tail期待E1、実際=${t:-なし}"
[ "$r" = "C7" ] || ng "G1b: B1 romver期待C7、実際=${r:-なし}"
ok "G1b: rom_ra 疎通確認(B1 head=$h tail=$t romver=$r)"

echo "== G6: バンク1/3入れ替えによる故障注入 =="
python3 "$REPO/tools/harness/make_ext_rom_test.py" "$WORK/rom_swap" --arm ra \
  --swap-banks 1 3 >"$WORK/gen_swap.log"

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_swap" --frames 30 \
  --mem-write-log "$WORK/swap.memlog.txt" \
  --mem-write-range 0xC100-0xC134 --mem-write-from-frame 0 \
  --out "$WORK/swap.report.txt" >"$WORK/swap.run.log" 2>&1 \
  || ng "rom_swap の実行に失敗($WORK/swap.run.log 参照)"

# RB2_BASE=0xC110, 1バンクあたり3バイト(head,tail,romver)。
# バンク1の領域=C113-C115, バンク3の領域=C119-C11B。
b1h="$(awk '$4=="C113"{v=$5} END{print v}' "$WORK/swap.memlog.txt")"
b3h="$(awk '$4=="C119"{v=$5} END{print v}' "$WORK/swap.memlog.txt")"
[ "$b1h" = "A3" ] || ng "G6: 入れ替え後バンク1位置の期待A3、実際=${b1h:-なし}(検出できていない)"
[ "$b3h" = "A1" ] || ng "G6: 入れ替え後バンク3位置の期待A1、実際=${b3h:-なし}(検出できていない)"
ok "G6: バンク入れ替えを検出できた(バンク1位置=${b1h} バンク3位置=${b3h}、正常時はA1/A3)"

echo
echo "ext1_selftest.sh: 全項目OK"

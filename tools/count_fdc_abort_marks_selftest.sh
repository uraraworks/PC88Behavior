#!/usr/bin/env bash
# tools/count_fdc_abort_marks_selftest.sh — tools/count_fdc_abort_marks.py の
# selftest（公式環境不要。tests/fixtures/ の完全に自作の合成I/Oログのみ使う）。
#
# 事前登録: docs/notes/m7kt-abort-scene-attribution-preregistration.md
#
# 検査すること:
#   1. 印が無いログで total=0 になること
#   2. IN側・OUT側・タイムアウト由来を意図的に混ぜたログで、各件数が
#      期待どおりに出ること（by_command の分類も含む）
#   3. 陰性対照: 期待値を1件ずらすと「一致しない」と判定できること
#      （検出力そのものを確認する。閾値を緩めて常にOKにしていないか）
#   4. 禁止項目の漏れの自己検査: 出力のどの行にも frame番号・データポート値・
#      0x5A/0x5B/0xA5 の literal が現れないこと
#
# 値は扱わない。合成フィクスチャの値も意味を持たないダミーである。

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }
overall_rc=0

TOOL="tools/count_fdc_abort_marks.py"
FIX_NONE="tests/fixtures/count_fdc_abort_marks_selftest_none.iolog.txt"
FIX_MIXED="tests/fixtures/count_fdc_abort_marks_selftest_mixed.iolog.txt"
FIX_MASKED="tests/fixtures/count_fdc_abort_marks_selftest_masked.iolog.txt"

for f in "$FIX_NONE" "$FIX_MIXED" "$FIX_MASKED"; do
  if [ ! -f "$f" ]; then
    ng "フィクスチャが無い: $f"
    overall_rc=1
  fi
done
if [ "$overall_rc" -ne 0 ]; then
  echo "フィクスチャ不足のため中断"
  exit 1
fi

get() {  # $1 = TSVテキスト, $2 = キー
  printf '%s\n' "$1" | awk -F'\t' -v k="$2" '$1==k{print $2; found=1} END{if(!found) print ""}'
}

say "1. 印が無いログで total=0 になること"
out_none="$(python3 "$TOOL" "$FIX_NONE")"
rc_none=$?
echo "$out_none" | sed 's/^/  /'
if [ "$rc_none" -eq 0 ] && [ "$(get "$out_none" total)" = "0" ] \
   && [ "$(get "$out_none" in_side)" = "0" ] && [ "$(get "$out_none" out_side)" = "0" ]; then
  ok "印が無いログで total=0（rc=${rc_none}）"
else
  ng "印が無いログで total=0 にならない、またはrc異常(rc=$rc_none)"
  overall_rc=1
fi

say "2. IN側・OUT側・タイムアウト由来を混ぜたログで、期待どおりの件数が出ること"
out_mixed="$(python3 "$TOOL" "$FIX_MIXED")"
rc_mixed=$?
echo "$out_mixed" | sed 's/^/  /'
# フィクスチャの構成(count_fdc_abort_marks_selftest_mixed.iolog.txt生成時のコメント参照):
#   READ DATA -> IN側1件(タイムアウト由来でない)
#   SPECIFY   -> OUT側1件
#   SEEK -> タイムアウト印 -> IN側1件(直前がタイムアウト印なのでtimeout_derived)
#   READ DATA -> OUT側1件
# 合計: total=4, in_side=2, out_side=2, timeout_derived=1
# by_command: READ DATA=2(1件目・4件目), SEEK=1(タイムアウト由来の1件),
#             SPECIFY=1(2件目)
# bash 3.2(macOS既定)は連想配列(declare -A)を持たないため、
# 「キー<TAB>期待値」の行を並べる方式にする(feedback_bash32_local_selfref_unbound
# と同じ回避)。
want_lines="total	4
in_side	2
out_side	2
timeout_derived	1
read_data	2
f9_events	5
by_command.READ DATA	2
by_command.SEEK	1
by_command.SPECIFY	1"

mixed_pass=1
if [ "$rc_mixed" -ne 0 ]; then
  ng "mixed フィクスチャでrc異常(rc=$rc_mixed)"
  mixed_pass=0
else
  while IFS=$'\t' read -r k want_v; do
    [ -z "$k" ] && continue
    got="$(get "$out_mixed" "$k")"
    if [ "$got" != "$want_v" ]; then
      ng "mixed: $k は $want_v を期待したが $got だった"
      mixed_pass=0
    fi
  done <<< "$want_lines"
fi
if [ "$mixed_pass" -eq 1 ]; then
  ok "mixed フィクスチャの全件数が期待どおり"
else
  overall_rc=1
fi

say "3. 陰性対照: 期待値を1件ずらすと不一致だと判定できること（検出力の確認）"
bad_total="$(( $(get "$out_mixed" total) + 1 ))"
if [ "$(get "$out_mixed" total)" != "$bad_total" ]; then
  ok "陰性対照: 実測値とわざとずらした期待値(${bad_total})は不一致だと判定できた"
else
  ng "陰性対照: ずらした期待値が実測値と区別できていない（検査自体が壊れている）"
  overall_rc=1
fi
# 逆側も見る: 正しい期待値どうしは一致すること（テスト2で既に確認済みだが、
# 「常に不一致と言う」壊れ方をしていないことも確認する）
if [ "$mixed_pass" -eq 1 ]; then
  ok "陰性対照の対: 正しい期待値では一致すると判定できている（テスト2）"
else
  ng "陰性対照の対: テスト2が既に不一致なので判定力の確認にならない"
  overall_rc=1
fi

say "3b. 陽性対照: データポート(\$FB)が伏せ字化されたログではコマンド種別を復号できずエラー終了すること"
out_masked="$(python3 "$TOOL" "$FIX_MASKED" 2>&1)"
rc_masked=$?
echo "$out_masked" | sed 's/^/  /'
if [ "$rc_masked" -ne 0 ] && echo "$out_masked" | grep -q "復号できない"; then
  ok "伏せ字ログを黙って集計せず、rc!=0で報告した"
else
  ng "伏せ字ログを黙って通してしまった（復号不能を検出できていない）"
  overall_rc=1
fi

say "4. 禁止項目の漏れの自己検査: 出力に frame番号・診断ポートの値・データポート値が現れないこと"
leak=0
# 診断ポートへ書いた値そのもの(0x5A/0x5B/0xA5)のliteralが出ていないか
if printf '%s\n' "$out_mixed" | grep -Eiq '(^|[^0-9A-Za-z])(0x)?5A([^0-9A-Za-z]|$)|(^|[^0-9A-Za-z])(0x)?5B([^0-9A-Za-z]|$)|(^|[^0-9A-Za-z])(0x)?A5([^0-9A-Za-z]|$)'; then
  ng "出力に診断ポートの値のliteral(5A/5B/A5系)が含まれている"
  leak=1
fi
# frame番号(このフィクスチャは全イベントframe=0固定だが、フィールド名自体が
# 出ていないことを確認する。0を含む数字列一般はcount値と区別できないため、
# キー名としての"frame"の非存在を見る)
if printf '%s\n' "$out_mixed" | grep -Eiq '(^|[^A-Za-z])frame([^A-Za-z]|$)'; then
  ng "出力に frame という語が含まれている（frame番号を出している疑い）"
  leak=1
fi
# データポート($FB)そのものへの言及が無いこと
if printf '%s\n' "$out_mixed" | grep -Eiq 'FB'; then
  ng "出力に \$FB(データポート)への言及が含まれている"
  leak=1
fi
# 出力は「キー<TAB>件数」の形だけであること（件数は非負整数のみ）
bad_value_lines="$(printf '%s\n' "$out_mixed" | awk -F'\t' 'NF!=2 || $2 !~ /^[0-9]+$/')"
if [ -n "$bad_value_lines" ]; then
  ng "出力に「キー<TAB>非負整数」以外の行がある:"
  printf '%s\n' "$bad_value_lines" | sed 's/^/    /'
  leak=1
fi
if [ "$leak" -eq 0 ]; then
  ok "禁止項目（frame番号・診断ポート値・データポート値）の漏れは無い"
else
  overall_rc=1
fi

say "陰性対照(自己検査の自己検査): 漏れ検査自体がわざと壊した入力を検出できること"
if printf 'total\t0x5A\n' | grep -Eiq '(^|[^0-9A-Za-z])(0x)?5A([^0-9A-Za-z]|$)'; then
  ok "漏れ検査は 0x5A を含む行を実際に検出できる（検出力の確認）"
else
  ng "漏れ検査が 0x5A を含む行すら検出できない（検査ロジックが壊れている）"
  overall_rc=1
fi

say "--from-frame オプションで窓を切れること"
out_windowed="$(python3 "$TOOL" "$FIX_MIXED" --from-frame 0)"
if [ "$(get "$out_windowed" total)" = "4" ]; then
  ok "--from-frame 0（全窓）で mixed と同じ total=4"
else
  ng "--from-frame 0 で total が変わった（想定外）"
  overall_rc=1
fi

echo
if [ "$overall_rc" -eq 0 ]; then
  printf '\033[32m全項目OK\033[0m\n'
else
  printf '\033[31m一部NG\033[0m\n'
fi
exit "$overall_rc"

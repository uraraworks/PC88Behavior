#!/usr/bin/env bash
# tools/run_all_selftests.sh — selftest群を LC_ALL=C と LC_ALL=ja_JP.UTF-8 の
# 両方で実行し、結果(終了コード)が一致するかどうかを一覧にする。
#
# 背景: UTF-8ロケールのbashは識別子をマルチバイト単位で解釈するため、
# シェルスクリプト中の「$var（」のような書き方は、Cロケールでは正しく
# 動いてもUTF-8ロケールでは変数名を吸い込んで壊れる(docs/notes/参照)。
# これまでの回帰確認はすべてCロケールで行っていたため、この種の不具合を
# 一度も検出できていなかった。本スクリプトは「両ロケールで同じ結果になる」
# ことを毎回機械的に確認し、同じ見落としを繰り返さないための仕組み。
#
# 使い方: tools/run_all_selftests.sh
# どれか1つでも「ロケール間で結果が異なる」または「両方NG」があれば
# 終了コード1。

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# 公式ROM・公式ディスクが要る適合テスト層は、私物が無い環境では
# 「未実行」であることを表に出す(黙って飛ばさない)。
SCRIPTS=(
  tools/check_cleanroom.sh
  tools/cmp_io_selftest.sh
  tools/redact_iolog_selftest.sh
  tools/analyzer_redaction_selftest.sh
  tools/refmeasure_selftest.sh
  tools/conform_l3.sh
  tools/verify_l1.sh
  tools/verify_l2.sh
  tools/verify_l3.sh
  tools/harness/clock_selftest.sh
  tools/harness/fontsrc_selftest.sh
  tools/harness/intlog_selftest.sh
  tools/harness/iolog_selftest.sh
  tools/harness/selftest.sh
  tools/harness/trap_selftest.sh
)

overall=0
printf '%-45s %6s %6s %s\n' "script" "C" "UTF-8" "判定"
printf '%-45s %6s %6s %s\n' "------" "-" "-----" "----"

for s in "${SCRIPTS[@]}"; do
  if [ ! -x "$s" ] && [ ! -f "$s" ]; then
    printf '%-45s %6s %6s %s\n' "$s" "-" "-" "見つからない"
    overall=1
    continue
  fi
  out_c="$(LC_ALL=C bash "$s" >/tmp/rst_c.$$ 2>&1; echo $?)"
  out_u="$(LC_ALL=ja_JP.UTF-8 bash "$s" >/tmp/rst_u.$$ 2>&1; echo $?)"
  if [ "$out_c" = "$out_u" ]; then
    verdict="OK(両方rc=$out_c)"
  else
    verdict="NG(C=$out_c UTF-8=$out_u 差あり)"
    overall=1
  fi
  printf '%-45s %6s %6s %s\n' "$s" "$out_c" "$out_u" "$verdict"
  rm -f /tmp/rst_c.$$ /tmp/rst_u.$$
done

exit "$overall"

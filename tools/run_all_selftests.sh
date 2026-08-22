#!/usr/bin/env bash
# tools/run_all_selftests.sh — selftest群を LC_ALL=C と LC_ALL=ja_JP.UTF-8 の
# 両方で実行し、(a) 両ロケールで結果が一致するか、(b) 結果が「宣言した
# 期待rc」と一致するか、を別々に判定する。
#
# 背景: UTF-8ロケールのbashは識別子をマルチバイト単位で解釈するため、
# シェルスクリプト中の「$var（」のような書き方は、Cロケールでは正しく
# 動いてもUTF-8ロケールでは変数名を吸い込んで壊れる(docs/notes/参照)。
#
# 過去の欠陥（2026-08-11 修正）: 以前のこのスクリプトは「両ロケールで
# rc が一致するか」しか見ておらず、「一致した rc が成功(0)かどうか」を
# 見ていなかった。そのため tools/check_cleanroom.sh が両ロケールで
# rc=1（NG）のまま "OK(両方rc=1)" と表示し、ラッパ全体も rc=0 で完走した。
# 結果、check_cleanroom.sh が NG のまま commit 85374ba が push された
# (docs/notes/locale-utf8-var-expansion-2026-08-11.md に詳細)。
#
# 今回の設計: スクリプトごとに「期待する終了コード」を宣言する。
#   - 通常のスクリプトは期待rc=0（失敗したら即NG）。
#   - tools/verify_l3.sh は長らく既知の未達成（L3不適合）で期待rc=1 と
#     宣言していたが、2026-08-18（m7ar）に rc=0 へ変えた。唯一のNGだった
#     「ディスク無しのネガティブコントロール（5.2条件4）」は、実は
#     **この自己検証層では判定できない**条件だったことが2×2の実測で
#     分かったため（数えていたのは試験用mainドライバの性質で、同じ
#     ドライバでは公式サブROMも20万件規模を出す）。判定は
#     tools/conform_l3.sh の「適合条件4のネガティブコントロール」へ
#     移した（公式main + 自作サブROM、陽性対照つき）。**条件を消したの
#     ではなく、判定できる層へ移した**。根拠は
#     docs/notes/m7ar-negative-control-attribution.md。
#
# 失敗の条件（どちらか一方でも該当したら該当スクリプトはNG、ラッパはrc=1）:
#   1. C ロケールと UTF-8 ロケールで rc が異なる（ロケール不一致）
#   2. rc が「宣言した期待rc」と異なる（想定と違う結果）
#
# わざと壊して検出力を確認するための自己検査は
# tools/run_all_selftests_selftest.sh を参照（このラッパ自体の selftest）。
#
# 使い方: tools/run_all_selftests.sh

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# 公式ROM・公式ディスクが要る適合テスト層は、私物が無い環境では
# 「未実行」であることを表に出す(黙って飛ばさない)。
#
# 各行は "script:期待rc"。期待rc=0 が「成功が正常」、それ以外は
# 「その終了コードが正常」という明示的な宣言。
SCRIPTS_EXPECTED=(
  "tools/check_cleanroom.sh:0"
  "tools/cmp_io_selftest.sh:0"
  "tools/cmp_fdc_sectors_selftest.sh:0"
  "tools/redact_iolog_selftest.sh:0"
  "tools/analyzer_redaction_selftest.sh:0"
  "tools/analyze_sub_fe_selftest.sh:0"
  "tools/analyze_boot_exchange_selftest.sh:0"
  "tools/analyze_run_boundary_selftest.sh:0"
  "tools/analyze_record_boundaries_selftest.sh:0"
  "tools/analyze_request_kinds_selftest.sh:0"
  "tools/analyze_k00_variants_selftest.sh:0"
  "tools/check_k00_rule_equivalence_selftest.sh:0"
  "tools/check_k00_completion_metrics_selftest.sh:0"
  "tools/analyze_post_read_response_selftest.sh:0"
  "tools/refmeasure_selftest.sh:0"
  "tools/subrom_fetch_window_selftest.sh:0"
  "tools/observed_request_decision_selftest.sh:0"
  "tools/analyze_write_path_selftest.sh:0"
  "tools/diag_post_bulk_selftest.sh:0"
  "tools/conform_l3.sh:0"
  "tools/diag_l3_mixed.sh:0"
  "tools/verify_l1.sh:0"
  "tools/verify_l2.sh:0"
  "tools/verify_l3.sh:0"
  "tools/harness/clock_selftest.sh:0"
  "tools/harness/fontsrc_selftest.sh:0"
  "tools/harness/intlog_selftest.sh:0"
  "tools/harness/iolog_selftest.sh:0"
  "tools/harness/romram_selftest.sh:0"
  "tools/harness/selftest.sh:0"
  "tools/harness/trap_selftest.sh:0"
  "tools/run_all_selftests_selftest.sh:0"
)

overall=0
printf '%-45s %6s %6s %8s %s\n' "script" "C" "UTF-8" "期待rc" "判定"
printf '%-45s %6s %6s %8s %s\n' "------" "-" "-----" "------" "----"

for entry in "${SCRIPTS_EXPECTED[@]}"; do
  s="${entry%%:*}"
  expected="${entry##*:}"

  if [ ! -x "$s" ] && [ ! -f "$s" ]; then
    printf '%-45s %6s %6s %8s %s\n' "$s" "-" "-" "$expected" "NG(見つからない)"
    overall=1
    continue
  fi

  rc_c="$(LC_ALL=C bash "$s" >/tmp/rst_c.$$ 2>&1; echo $?)"
  rc_u="$(LC_ALL=ja_JP.UTF-8 bash "$s" >/tmp/rst_u.$$ 2>&1; echo $?)"
  skip_c=0; skip_u=0
  case "$s" in
    */conform_l3.sh)
      grep -q "SKIP: 公式ROM・公式ディスクの環境変数が未設定" /tmp/rst_c.$$ && skip_c=1
      grep -q "SKIP: 公式ROM・公式ディスクの環境変数が未設定" /tmp/rst_u.$$ && skip_u=1
      ;;
  esac

  if [ "$skip_c" != "$skip_u" ]; then
    verdict="NG(本体SKIP状態がロケール間で不一致)"
    overall=1
  elif [ "$skip_c" = "1" ]; then
    verdict="SKIP(公式環境なし。本体未実行、自己検査のみrc=0)"
  elif [ "$rc_c" != "$rc_u" ]; then
    verdict="NG(ロケール不一致 C=$rc_c UTF-8=$rc_u)"
    overall=1
  elif [ "$rc_c" != "$expected" ]; then
    verdict="NG(期待rc=${expected} だが実際rc=${rc_c}。宣言を見直すか実装を直す)"
    overall=1
  elif [ "$expected" = "0" ]; then
    verdict="OK"
  else
    verdict="OK(想定内の失敗。rc=$expected を正常として宣言済み)"
  fi

  printf '%-45s %6s %6s %8s %s\n' "$s" "$rc_c" "$rc_u" "$expected" "$verdict"
  if [ "$rc_c" != "$expected" ] || [ "$rc_u" != "$expected" ] || [ "$skip_c" != "$skip_u" ]; then
    echo "  --- Cロケール出力（末尾20行） ---"
    tail -20 /tmp/rst_c.$$
    echo "  --- UTF-8ロケール出力（末尾20行） ---"
    tail -20 /tmp/rst_u.$$
  fi
  rm -f /tmp/rst_c.$$ /tmp/rst_u.$$
done

if [ "$overall" != "0" ]; then
  echo
  echo "NG: 上記のいずれかがロケール不一致または期待rcとの不一致。詳細は表を参照。"
fi

exit "$overall"

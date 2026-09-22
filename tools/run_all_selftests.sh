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
  "tools/analyze_sub_interrupt_shape_selftest.sh:0"
  "tools/analyze_boot_exchange_selftest.sh:0"
  "tools/analyze_boot_start_order_selftest.sh:0"
  "tools/analyze_common_clock_three_questions_selftest.sh:0"
  "tools/analyze_run_boundary_selftest.sh:0"
  "tools/run_cutter_positive_selftest.sh:0"
  "tools/analyze_run_cutter_attribution_selftest.sh:0"
  "tools/boundary_match_rule_search_selftest.sh:0"
  "tools/run_length6_protocol_axis_selftest.sh:0"
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
  "tools/compare_l3_entry_fdc_selftest.sh:0"
  "tools/analyze_error_exchange_shape_selftest.sh:0"
  "tools/analyze_no_disk_branch_order_selftest.sh:0"
  "tools/analyze_no_disk_signals_selftest.sh:0"
  "tools/check_shell_declaration_dependencies_selftest.sh:0"
  "tools/measure_no_disk_signals_selftest.sh:0"
  "tools/search_error_response_candidate_selftest.sh:0"
  "tools/error_response_bit6_attribution_selftest.sh:0"
  "tools/no_disk_response_attribution_selftest.sh:0"
  "tools/response_ready_sweep_selftest.sh:0"
  "tools/response_ready_rom_selftest.sh:0"
  "tools/early_response_rom_selftest.sh:0"
  "tools/sub_interrupt_intervention_selftest.sh:0"
  "tools/main_interrupt_intervention_selftest.sh:0"
  "tools/sub_cpu_mode_selftest.sh:0"
  "tools/analyze_no_disk_timing_selftest.sh:0"
  "tools/verify_error_response_bit6_attribution.sh:0"
  "tools/compare_drive_request_runs_selftest.sh:0"
  "tools/verify_drive_byte2_attribution.sh:0"
  "tools/diag_post_bulk_selftest.sh:0"
  "tools/analyze_second_channel_structure_selftest.sh:0"
  "tools/search_second_channel_rules_selftest.sh:0"
  "tools/check_5635_origin_structure_selftest.sh:0"
  "tools/check_l3_screen_output_selftest.sh:0"
  "tools/check_l3_entry_screen_selftest.sh:0"
  "tools/l3_entry_expected_fault_selftest.sh:0"
  "tools/conform_l3.sh:0"
  # tools/conform_l4.sh(l4-c1b 打鍵エコー適合の場面固定)は conform_l3.sh と
  # 違い、公式環境(PC88_REF_ROM_DIR)が無くても自作main ROM側の照合が
  # tests/conformance/expected_l4_echo.tsv と照合して完走しrc=0を返す設計
  # なので、SKIP判定の特別扱いは不要(conform_l3.shのSKIP注記のような分岐は
  # 無く、常に期待rc=0)。
  "tools/conform_l4.sh:0"
  "tools/diag_l3_mixed.sh:0"
  "tools/verify_l1.sh:0"
  "tools/verify_l2.sh:0"
  "tools/verify_l3.sh:0"
  "tools/harness/clock_selftest.sh:0"
  "tools/harness/disk2_selftest.sh:0"
  "tools/harness/insert_disk2_selftest.sh:0"
  "tools/harness/fontsrc_selftest.sh:0"
  "tools/harness/intlog_selftest.sh:0"
  "tools/harness/iolog_capacity_selftest.sh:0"
  "tools/harness/iolog_selftest.sh:0"
  "tools/harness/vram_dump_selftest.sh:0"
  "tools/harness/mem_write_log_selftest.sh:0"
  "tools/harness/key_matrix_selftest.sh:0"
  "tools/harness/type_untypable_selftest.sh:0"
  "tools/harness/type_bracesymbol_selftest.sh:0"
  "tools/harness/romram_selftest.sh:0"
  "tools/harness/selftest.sh:0"
  "tools/harness/trap_selftest.sh:0"
  "tools/run_all_selftests_selftest.sh:0"
  "tools/count_fdc_abort_marks_selftest.sh:0"
  "tools/make_l3_testdisk_selftest.sh:0"
  "tools/asm/z80text_selftest.sh:0"
  "tools/asm/asm_selftest.sh:0"
  # M7段階2b（2026-09-15）でカーソルをプロンプトの実位置に追従させた直後、
  # 一時的にこの行の期待rcを0→1にしていた（検査4のL1適合が、定常状態の
  # CRTCカーソル位置(OUT 0x50)が実際の入力位置になり公式測定の固定値
  # (22,1)と食い違ってNGになったため）。しかしこれでは
  # l3_main_selftest.shの他の検査(1-3,5-10)が今後壊れても「期待どおりの
  # 失敗」として素通りしてしまい、自己検査として機能しなくなる欠陥が
  # あった。
  #
  # そこで検査4自体をtools/cmp_io.pyの--ignore-value-atで分割し
  # （4a初期化350件=完全一致のまま、4b定常状態=カーソル位置パラメータ
  # (周期内4・5番目)だけをvalue比較から外し、ポート・件数・周期は
  # 従来どおり適合条件のまま比較する。docs/spec/l1-ipl.md 第3節の
  # 「毎フレーム、カーソルを(22,1)に置き直している」＝画面の中身で
  # 決まる値なので、別の画面を出す自作ROMで一致しないのは当然、
  # それ以外はすべて公式測定と一致させる、という判断。
  # tools/l3_main_selftest.sh 検査4のコメント参照）、期待rcを0に戻した。
  "tools/l3_main_selftest.sh:0"
  "tools/main_sub_link_selftest.sh:0"
  "tools/analyze_m6ia_main_sub_selftest.sh:0"
  # 第16節(スクリーンエディタ・編集キー)・第17節(RETURNによる行の読み直し)
  # の自己検査。公式ROM不要（自作ROMだけで動かす）。
  "tools/l3_screen_editor_selftest.sh:0"
  # M7段階3準備（2026-09-15）。マニュアルテキスト(refs/manual.txt、私物)が
  # 無い環境ではSKIPで即rc=0になる（tools/l4_extract_keywords_selftest.sh
  # 内のSKIPメッセージ参照）。
  "tools/l4_extract_keywords_selftest.sh:0"
  # M7段階3a（2026-09-15）。src/l4_basic/keywords.tsv（リポジトリに同梱、
  # 私物依存なし）だけを入力にするのでSKIPは無く、常にrc=0を期待する。
  "tools/l4_token_table_selftest.sh:0"
  # M7段階3b（2026-09-15）。BASICの核(直接モードPRINT)。公式ROM不要、
  # 自作main ROMだけで完結するのでSKIPは無く、常にrc=0を期待する。
  "tools/l4_basic_selftest.sh:0"
  # M7段階4 事前登録（2026-09-15）。GW-BASIC(MIT公開ソース)数値部の予測器
  # tools/l4_mbf_oracle.py。ROM・私物なしで完結するのでSKIPは無く、
  # 常にrc=0を期待する。
  "tools/l4_mbf_oracle_selftest.sh:0"
  # M7段階4 事前登録v2（2026-09-15）。命令単位で四則演算を再現した予測器
  # tools/l4_mbf_oracle_v2.py。ROM・私物なしで完結するのでSKIPは無く、
  # 常にrc=0を期待する。
  "tools/l4_mbf_oracle_v2_selftest.sh:0"
  # M7段階4a-1（2026-09-15）。単精度MBF四則演算・符号反転・比較・整数変換
  # (src/l4_basic/mbf_single.asm)を実際にZ80として実行し、予測器v2と
  # バイト単位で突き合わせる。自作の空ROMをq88measureで走らせるだけで
  # 公式ROM・私物は不要なのでSKIPは無く、常にrc=0を期待する。
  "tools/l4_mbf_z80_selftest.sh:0"
  # M7段階5 事前登録準備（2026-09-15）。l4-s5a(LISTの出力行)用の分類器
  # tools/l4_list_classify.py。合成VRAM写しだけで完結するので公式ROM・
  # 私物は不要、SKIPは無く常にrc=0を期待する。
  "tools/l4_list_classify_selftest.sh:0"
  # M7段階5a（2026-09-15）。プログラムモード(行の入力・保存・LIST・NEW、
  # src/l4_basic/program.asm)。docs/spec/l4-program.md 第1版の観測例を
  # そのまま期待値にした自作ROM単体の検査。公式ROM・私物は不要なので
  # SKIPは無く、常にrc=0を期待する。
  "tools/l4_program_selftest.sh:0"
  # M7段階5終盤（2026-09-16）。l4-c5(代表プログラム集の適合場面)用の
  # 打鍵計画・記録器 tools/l4_program_typeplan.py・
  # tools/l4_program_conform_record.py。合成VRAM写しだけで完結するので
  # 公式ROM・私物は不要、SKIPは無く常にrc=0を期待する。
  "tools/l4_program_conform_selftest.sh:0"
  # M7段階5c-1（2026-09-16）。N88.ROM 0x79D7(QUASI88の機種判定番地、
  # vendor/quasi88-libretro/src/memory.h ROM_VERSION)が埋め草のまま
  # 固定されていることの検査。ビルドだけで完結するので公式ROM・私物は
  # 不要、SKIPは無く常にrc=0を期待する。
  "tools/check_rom_version_reserved.sh:0"
  # 拡張ROMバンク(4th ROM)の土台(docs/spec/ext-rom-bank.md)。ビルドと
  # q88measureのmem-write-logだけで完結するので公式ROM・私物は不要、
  # SKIPは無く常にrc=0を期待する。
  "tools/ext_bank_selftest.sh:0"
  # 2026-09-20追記: 拡張ROMバンク0のSQR本体(EXT_BANK0_SQR_ENTRY、
  # docs/spec/l4-program.md 第4.16b節実装メモ)を実際にZ80として実行し、
  # 予測器tools/l4_mbf_oracle_v10_m9.pyとバイト単位で突き合わせる。
  # 公式ROM・私物は不要、SKIPは無く常にrc=0を期待する。
  "tools/l4_sqr_bank_selftest.sh:0"
  # 2026-09-20追記: SQRのBASIC呼び出し経路(interp.asm FTNF_DO_SQR→
  # EXT_BANK_CALL→bank0 EXT_BANK0_SQR_ENTRY)のend-to-end検査
  # (tools/l4_sqr_bank_selftest.shはバンクルーチン単体の照合であり
  # この経路のハング〈l4-c8で発見、docs/notes/l4-c8-transcendental-
  # conformance-scene-results.md〉を検出できなかった)。陰性対照
  # (--inject-ext-bank-bcde-fault)つき。公式ROM・私物は不要、SKIPは
  # 無く常にrc=0を期待する。
  "tools/l4_sqr_endtoend_selftest.sh:0"
  # 2026-09-20追記: 拡張ROMバンク0のSIN/COS/TAN本体(EXT_BANK0_SIN_ENTRY/
  # COS_ENTRY/TAN_ENTRY、docs/spec/l4-program.md 第4.16a節、`l4-s6b`〜
  # `l4-s6g`で確定した候補M9)を実際にZ80として実行し、予測器
  # tools/l4_mbf_oracle_v10_m9.pyとバイト単位で突き合わせる。公式ROM・
  # 私物は不要、SKIPは無く常にrc=0を期待する。
  "tools/l4_sincos_bank_selftest.sh:0"
  # 2026-09-20追記: SIN/COS/TANのBASIC呼び出し経路(interp.asm
  # FTNF_DO_SIN/COS/TAN→EXT_BANK_CALL→bank0 EXT_BANK0_*_ENTRY)の
  # end-to-end検査(l4_sqr_endtoend_selftest.shと同じ設計、単体照合だけ
  # では検出できないハングの再発防止)。陰性対照(--inject-ext-bank-
  # bcde-fault)つき。公式ROM・私物は不要、SKIPは無く常にrc=0を期待する。
  "tools/l4_sincos_endtoend_selftest.sh:0"
  # 2026-09-20追記: 拡張ROMバンク0のATN/EXP/LOG本体(EXT_BANK0_ATN_ENTRY/
  # EXP_ENTRY/LOG_ENTRY、docs/spec/l4-program.md 第4.16b節、`l4-s6h`で
  # 確定したround-half-away丸め)を実際にZ80として実行し、予測器
  # tools/l4_mbf_oracle_v10_m9.pyとバイト単位で突き合わせる。公式ROM・
  # 私物は不要、SKIPは無く常にrc=0を期待する。
  "tools/l4_atnexplog_bank_selftest.sh:0"
  # 2026-09-20追記: ATN/EXP/LOGのBASIC呼び出し経路(interp.asm
  # FTNF_DO_ATN/EXP/LOG→EXT_BANK_CALL→bank0 EXT_BANK0_*_ENTRY)の
  # end-to-end検査(l4_sincos_endtoend_selftest.shと同じ設計、単体照合
  # だけでは検出できないハングの再発防止。log(0)〈Illegal function
  # call、interp.asm側でEXT_BANK_CALLへ行く前に弾く経路〉の腕も含む)。
  # 陰性対照(--inject-ext-bank-bcde-fault)つき。公式ROM・私物は不要、
  # SKIPは無く常にrc=0を期待する。
  "tools/l4_atnexplog_endtoend_selftest.sh:0"
  # VSYNCハンドラのレジスタ非退避の潜在不具合の再現・修正検査
  # (ext_bank開発時に発覚。docs/spec/ext-rom-bank.md参照)。ビルドと
  # q88measureのmem-write-logだけで完結するので公式ROM・私物は不要、
  # SKIPは無く常にrc=0を期待する。
  "tools/vsync_regcheck_selftest.sh:0"
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
    */verify_drive_byte2_attribution.sh)
      grep -q "SKIP: 公式ROM・公式ディスクの環境変数が未設定" /tmp/rst_c.$$ && skip_c=1
      grep -q "SKIP: 公式ROM・公式ディスクの環境変数が未設定" /tmp/rst_u.$$ && skip_u=1
      ;;
    */verify_error_response_bit6_attribution.sh)
      grep -q "SKIP: PC88_ERROR_RESPONSE_OPT_IN未設定" /tmp/rst_c.$$ && skip_c=1
      grep -q "SKIP: PC88_ERROR_RESPONSE_OPT_IN未設定" /tmp/rst_u.$$ && skip_u=1
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

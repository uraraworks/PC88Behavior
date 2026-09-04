# tools/lib_screen_data_disks.sh — tools/screen_data_disks.sh が使う関数群。
#
# tools/lib_l3_measure.sh・tools/lib_screen_boot_disks.sh と同じ流儀で、
# source される「関数の置き場」だけにする（トップレベルで副作用を起こさない）。
# こう切り出す理由も同じ: tools/screen_data_disks_selftest.sh から公式ROM・
# 実ディスク無しで各関数を直接検査できるようにするため。
#
# 使い方:
#   REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
#   source "$REPO/tools/lib_screen_boot_disks.sh"   # list_disk_basenames等を先に
#   source "$REPO/tools/lib_screen_data_disks.sh"

# -----------------------------------------------------------------------
# $1 = REPO のルート
# $2 = q88measure --out の report ファイル
#
# tools/check_l3_screen_output.py を --report 単独（比較なし）で呼び、
# 出力される line_count=/char_count=/sha256= の3行を
# "line_count<TAB>char_count<TAB>sha256" の1行にまとめて返す。
# 画面本文そのものは一切扱わない（check_l3_screen_output.py が本文を
# 出さない設計であることに依存している。二重実装しない）。
# 失敗時（画面節が無い等）は空文字を返す。
# -----------------------------------------------------------------------
read_screen_signature() {
  local repo="$1" report="$2"
  local tool="$repo/tools/check_l3_screen_output.py"
  local out lc cc sha
  if ! out="$(python3 "$tool" --report "$report" 2>/dev/null)"; then
    echo ""
    return 1
  fi
  lc="$(printf '%s\n' "$out" | awk -F'=' '$1=="line_count"{print $2}')"
  cc="$(printf '%s\n' "$out" | awk -F'=' '$1=="char_count"{print $2}')"
  sha="$(printf '%s\n' "$out" | awk -F'=' '$1=="sha256"{print $2}')"
  if [ -z "$lc" ] || [ -z "$cc" ] || [ -z "$sha" ]; then
    echo ""
    return 1
  fi
  printf '%s\t%s\t%s\n' "$lc" "$cc" "$sha"
}

# -----------------------------------------------------------------------
# $1 = REPO のルート
# $2 = iolog のパス
# $3 = --after-frame に渡すframe番号
#
# tools/count_fdc_commands_after_frame.py を呼び、打鍵後の窓に絞った
# FDC READ DATA発行件数だけを返す（値は一切扱わない。件数のみ）。
# 解析不能なら空文字を返す。
# -----------------------------------------------------------------------
read_read_data_count() {
  local repo="$1" iolog="$2" after_frame="$3"
  local tool="$repo/tools/count_fdc_commands_after_frame.py"
  local out
  if ! out="$(python3 "$tool" --iolog "$iolog" --after-frame "$after_frame" 2>/dev/null)"; then
    echo ""
    return 1
  fi
  printf '%s\n' "$out" | awk -F'=' '$1=="read_data_count"{print $2}'
}

# -----------------------------------------------------------------------
# 判定規則（事前に固定。参照P・参照Nの署名を見てから候補ごとの数値を
# 見て後付けで閾値を作らない。参照P・参照Nの「形」を基準に使うだけ）:
#
#   引数: cand_line cand_char cand_read  refP_line refP_char refP_sha
#         refN_line refN_char refN_sha  cand_sha
#
#   - 読める:         cand_read > 0 かつ cand_line > refN_line
#       （打鍵後にFDC READ DATAが発行され、かつ「B:無し」のエラー画面
#         より行数が多い＝ディレクトリ相当の内容が表示されたとみなす）
#   - 読めない:       画面が参照Nと同じ形（行数・文字数が一致）
#       （「B:無し」のときと見分けが付かないエラー画面という意味であり、
#         READ DATA件数は問わない。SHAまで一致すれば全く同じエラー画面）
#   - どちらとも言えない: 上記のいずれにも当てはまらない
#       （例: 行数はrefNより多いがREAD DATAが0件＝内容が出たのに打鍵後の
#         読み出しが確認できない食い違い、逆にREAD DATAはあるが行数が
#         refN以下、行数がrefNより少ない、など。無理に2値へ寄せない）
# -----------------------------------------------------------------------
classify_data_disk() {
  local cand_line="$1" cand_char="$2" cand_read="$3" cand_sha="$4"
  local refp_line="$5" refp_char="$6" refp_sha="$7"
  local refn_line="$8" refn_char="$9" refn_sha="${10}"

  if [ -z "$cand_line" ] || [ -z "$cand_read" ]; then
    echo "どちらとも言えない"
    return 0
  fi

  if [ "$cand_line" = "$refn_line" ] && [ "$cand_char" = "$refn_char" ]; then
    echo "読めない"
    return 0
  fi
  if [ "$cand_read" -gt 0 ] 2>/dev/null && [ "$cand_line" -gt "$refn_line" ] 2>/dev/null; then
    echo "読める"
    return 0
  fi
  echo "どちらとも言えない"
}

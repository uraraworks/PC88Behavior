#!/usr/bin/env bash
# tools/diag_l3_mixed.sh — 混成ROM実行のI/O列を、公式基準ログと
# ポート/pcレベルで突き合わせ、最初に食い違ったイベントを診断する。
#
# 背景: tools/conform_l3.sh の混成ROM適合テスト（公式main ROM一式 +
# 自作サブROM(DISK.ROM)で公式ディスクを起動）は、main が IN $FD で
# 受け取る値の列（docs/spec/l3-subrom.md 5.2節条件1）でしか判定しない。
# 直近の実走結果は「main/IN/00FD に該当するイベントが0件」——つまり
# データ転送以前、$FE/$FF のハンドシェイク段階で食い違っている。
# このスクリプトはその**最初の構造的な食い違い**を、値を一切見ずに
# (cpu, 方向IN/OUT, ポート, pc) の4項目だけで特定する。
#
# 添字を厳密に揃えた比較には欠陥があった: ポーリングループ（例:
# 1.13節のSEND前$FE待ち）の回数はタイミング依存で、公式と自作で
# 回数が違うだけでも添字がずれて以降すべてが「分岐」に見えてしまう。
# 既定は連続する同一の比較キーを畳み込んでから比較し、回数の差は
# 「回数差」として分岐と切り離して報告する
# （tools/diag_l3_mixed.py のモジュールdocstring参照）。
#
# 比較キーに sub の pc を含めていたことにも欠陥があった: sub の pc は
# 自作サブROM自身が発行した番地であり、公式サブROMの番地と一致する
# 道理がない（docs/spec/l3-subrom.md 1.14節・5.1節：サブ内部実装は
# 自由で、pc は実装目標にならない）。この欠陥のせいで、実走で方向・
# ポート・スピン回数まで公式と完全一致していたsub側の起動順序が
# 「構造的一致プレフィックス0件」と誤報されたことがある。既定では
# sub の比較キーから pc を除外する（main は両側とも公式 main ROM
# なので pc も一致すべきで、従来どおり含める）。表示には pc を
# 「参考」として残す。旧来どおり sub でも pc を含めたい場合は
# tools/diag_l3_mixed.py --sub-pc を使う。
#
# クリーンルーム規律: 比較キーに value を含めない。これは
# CLAUDE.md 禁止事項5（データポートの値列を伏せる）を守った状態の
# ログに対してのみ行う——測定直後の生ログは必ず tools/redact_iolog.py
# を通してから比較・保存する（下記フロー参照）。伏せ字済みログを
# ポート/pcだけで比較するのは、公式ディスクの中身を見ることにならない
# （docs/notes/log-container-vs-payload 系の整理と同じ: ポート単位で
# 「事実」と「中身」を分け、中身の経路だけ伏せてある）。
#
# 測定本体（混成ROMディレクトリ構築 + q88measure実行）は
# tools/conform_l3.sh の混成ステップと共通化してある
# （tools/lib_l3_measure.sh の run_l3_mixed_measurement。二重実装しない）。
#
# フロー:
#   1. 測定（--from-log 指定時、または環境変数未設定時はSKIP）
#   2. tools/redact_iolog.py を必ず適用（既に伏せてあれば無変更・冪等）
#   3. 伏せ字済みログを --out で指定したディレクトリ（既定はmktemp）に保存
#      （リポジトリ内には保存しない。再測定なしで解析を繰り返せるように
#      するため。パスは必ず表示する）
#   4. tools/diag_l3_mixed.py で公式基準ログ(measurements/m6g-d0-boot-run1.
#      iolog.txt.gz。既にリポジトリ内で伏せ字済み)と突き合わせる
#
# 「検出力の自己検査」（下記）は公式環境の有無に関わらず常に実行する。
#
# 使い方:
#   tools/diag_l3_mixed.sh                                    # 自己検査のみ
#   PC88_REF_ROM_DIR=... PC88_REF_DISK_DIR=... \
#       tools/diag_l3_mixed.sh [--out DIR]                     # 実測して解析
#   tools/diag_l3_mixed.sh --from-log /path/to/mixed.iolog.txt [--out DIR]
#                                                                # 再測定せず解析だけ

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"

DIAG="$REPO/tools/diag_l3_mixed.py"
REDACT="$REPO/tools/redact_iolog.py"
REF_LOG="$REPO/measurements/m6g-d0-boot-run1.iolog.txt.gz"
SELFTEST_REF="$REPO/tests/fixtures/diag_l3_mixed_selftest_ref.iolog.txt"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }

usage() {
  cat <<'EOF'
使い方: tools/diag_l3_mixed.sh [--out DIR] [--from-log PATH] [--brief|--full]

  --out DIR       伏せ字済みログの保存先（省略時は mktemp。パスを表示する。
                   リポジトリ内には保存しない）
  --from-log PATH 既存の iolog を使い、混成ROMの再測定を飛ばす
                   （PC88_REF_ROM_DIR / PC88_REF_DISK_DIR 不要。既に
                   redact_iolog.py 済みのログをそのまま渡してよい——
                   本スクリプトが再度適用しても冪等）
  --brief         出力を絞る（既定）。「検出力の自己検査」は失敗した項目
                   以外を1行に畳み、本番診断は tools/diag_l3_mixed.py
                   --brief を使う（分岐点前後の窓を前後5件にし、基準側
                   ＝公式ログ側＝毎回同一の連長上位5件・末尾10件を省く）。
                   一致プレフィックス・分岐点・回数差（[要注意]含む）・
                   片側限定ポート一覧は省かない
  --full          従来どおりの全量表示に戻す（--brief の反対。自己検査は
                   全項目の詳細を出し、本番診断は tools/diag_l3_mixed.py
                   --full を使う）

環境変数（--from-log 未指定時のみ必要）:
  PC88_REF_ROM_DIR   公式ROMの置き場
  PC88_REF_DISK_DIR  diskA(N88_FE.D88) の置き場

「検出力の自己検査」は常に実行する（環境変数の有無に関わらない）。

比較の既定はスピン畳み込み比較（連続する同一の比較キーをランレングス
圧縮してから比較。ポーリング回数の差は分岐にせず、別立てで「回数差」
として報告する）。比較キーは main が (kind,port,pc)、sub は既定で
(kind,port) のみ——sub の pc は自作サブROM自身の番地であり公式と
一致する道理がないため（docs/spec/l3-subrom.md 1.14節・5.1節）。
旧来どおり sub でも pc を比較キーに含めたい場合は
tools/diag_l3_mixed.py --sub-pc を使う。添字を厳密に揃えた旧来の
比較（cpu を問わず pc を含める）は tools/diag_l3_mixed.py --strict
で個別に呼び出せる。

畳み込み後の連長（スピン回数）が大きい上位5件・各ログの末尾10件は
分岐の有無・位置と無関係に常に表示する（無限スピンの実際の停止位置を
見るため。分岐点前後の窓だけでは分岐が起きない側のスピンが見えない）。
--brief（既定）では基準側（毎回同一ログ）だけこれを省く。混成側は
実行のたびに変わるので --brief でも常に出す。

前回の実走ログを再測定せずに解析し直す例（既定の --brief で診断）:
  tools/diag_l3_mixed.sh --from-log \
      ~/pc88-diag/diag-l3-mixed-d0-boot.20260812-083834.iolog.redacted.txt

自己検査の詳細や基準側の連長上位5件・末尾10件まで含めた従来どおりの
全量出力が欲しい場合:
  tools/diag_l3_mixed.sh --full --from-log \
      ~/pc88-diag/diag-l3-mixed-d0-boot.20260812-083834.iolog.redacted.txt
EOF
}

OUT_DIR=""
FROM_LOG=""
BRIEF=1
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT_DIR="${2:-}"; shift 2 ;;
    --from-log) FROM_LOG="${2:-}"; shift 2 ;;
    --brief) BRIEF=1; shift ;;
    --full) BRIEF=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "エラー: 不明な引数: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ ! -f "$SELFTEST_REF" ]; then
  echo "エラー: 自己検査用の入力が無い: $SELFTEST_REF" >&2
  exit 2
fi
if [ ! -f "$REF_LOG" ]; then
  echo "エラー: 公式基準ログが無い: $REF_LOG" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

overall_rc=0

# -----------------------------------------------------------------------
# 検出力の自己検査（公式環境なしで常に回せる。合成フィクスチャのみ使用）
#
#   a. 完全一致のコピー             → 構造的分岐なし
#   b. 途中1件のポートを書き換え     → その通し番号が構造的分岐点として報告される
#   c. 片方を途中で打ち切り          → 打ち切り位置が構造的分岐点として検出される
#   d. スピン回数だけが違う          → 構造的分岐なし・かつ回数差として報告される
#   e. 畳み込んでも構造が違う        → その位置が構造的分岐点として検出される
#   f. 一方が無限ループ（極端な回数） → 回数差として目立つ形（[要注意]）で報告される
#   g. main/sub同じ行でpcだけ違う    → sub「分岐なし」・main「分岐あり」を1回の
#                                      呼び出しで両方確認する（sub比較キーがpcを
#                                      含んでいないことの検出、片方だけでは不十分）
#   h. 巨大スピンを含むログ          → 畳み込み後「連長上位5件」にそれが現れる
#   i. 畳み込み後「末尾10件」        → 実際のログ末尾を反映している
#   j. --brief でも異常が落ちない    → 分岐点・回数差・[要注意]は --brief でも出る
#   k. --brief と --full の判定一致  → 終了コード(rc)は表示量に関わらず同じ
#   l. 自己検査が落ちたら --brief でも詳細が出る → run_check の表示条件そのものの検査
#
# 「わざと壊して検出できることを確かめてから信用する」がこのリポジトリの
# 規律（CLAUDE.md / feedback_measure_the_end_not_the_signal.md）。
# d/e/f は、既定のスピン畳み込み比較（コミット時点で追加）が
# 「タイミング差を分岐扱いしない」ことと「本当の構造的分岐は見逃さない」
# ことの両方を満たすかを検査する。片方だけの確認では不十分
# （ポーリング回数差を分岐なしと誤判定しても、回数差として報告されて
# いなければ「揺れを黙って握り潰しただけ」になる）。g/h/iは「sub側pc除外」
# 「連長上位5件」「末尾10件」の検出力を検査する。j/k/lは今回追加した
# --brief（既定を絞る出力）が、異常検出情報を黙って握り潰していないか
# ・表示量が変わるだけで判定を変えていないかを検査する
# （実装前にコードをわざと壊してj/k/lが落ちることを確認し、その後
# 復元して通ることを確認済み）。
#
# 各検査は check_X 関数として定義し、run_check がその結果を見て
# 表示するかどうかを決める: 成功時は --brief では表示を畳み（1行の
# 総合サマリにのみ現れる）、失敗時は --brief でも従来どおり詳細
# （ヘッダ行・ok/ng・食い違い内容）を出す（下の run_check 参照）。
# -----------------------------------------------------------------------
say "検出力の自己検査（比較ロジックをわざと壊して検出できるか）"
selftest_rc=0
FAILED_CHECKS=()

# run_check: 1項目分の検査関数 $2 を実行し、その出力を $WORK/check_$1.log に
# 溜める。--brief（既定）では成功した項目の出力を表示しない
# （最終的な1行サマリだけが判断材料になる。毎回同じ「OK」を10行以上
# 見せても情報は増えないため）。失敗した項目は --brief でも必ず表示する
# （「情報を隠すのではなく、毎回同じで意味を持たない部分を省く」の原則。
# 異常に関わる情報を brief で落とすのは禁止）。
run_check() {
  local id="$1" fn="$2"
  local logfile="$WORK/check_${id}.log"
  "$fn" > "$logfile" 2>&1
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    FAILED_CHECKS+=("$id")
  fi
  if [ "$BRIEF" -eq 0 ] || [ "$rc" -ne 0 ]; then
    cat "$logfile"
  fi
  return "$rc"
}

# main セクションの2件目 (IN 00FE 01 3002) を N 回連続に複製する
# ヘルパ。d/e/f のスピン合成フィクスチャ生成に使う。他の行・sub節は
# 変えない。seq 列はキー比較に使わないので振り直さない。
gen_line2_spin() {
  local want="$1" outfile="$2"
  awk -v want="$want" '
    /^# main$/ { in_main=1; print; next }
    /^# sub$/  { in_main=0; print; next }
    {
      if (in_main == 1) {
        stripped = $0
        gsub(/^[ \t]+|[ \t]+$/, "", stripped)
        if (stripped == "" || substr(stripped, 1, 1) == "#") { print; next }
        cnt++
        if (cnt == 2) { for (i = 0; i < want; i++) print; next }
        print; next
      }
      print
    }
  ' "$SELFTEST_REF" > "$outfile"
}

cp "$SELFTEST_REF" "$WORK/st_a.txt"

# b: main セクションの5件目 (OUT 00FF 09 3005) のポートを 00FC に書き換える。
#    通し番号5件目（0-indexed 4）で分岐するはず。
sed 's/00FF   09   3005/00FC   09   3005/' "$SELFTEST_REF" > "$WORK/st_b.txt"

# c: main セクションを先頭6件で打ち切る（全10件のうち後半4件を落とす）。
awk '
  /^# main$/ { in_main=1; print; next }
  /^# sub$/  { in_main=0; print; next }
  {
    if (in_main == 1) {
      stripped = $0
      gsub(/^[ \t]+|[ \t]+$/, "", stripped)
      if (stripped == "" || substr(stripped, 1, 1) == "#") { print; next }
      main_count++
      if (main_count <= 6) print
      next
    }
    print
  }
' "$SELFTEST_REF" > "$WORK/st_c.txt"

check_a() {
  echo "  -- a. 完全一致のコピー → 分岐なしのはず --"
  # h/i が基準側の連長上位5件・末尾10件を再利用するので --full で呼ぶ
  # （--brief では基準側のそれが省かれるため。a 自身の判定は brief/full
  # どちらでも変わらない項目のみを見ている）。
  out_a="$(python3 "$DIAG" --full "$SELFTEST_REF" "$WORK/st_a.txt" 2>"$WORK/a.err")"
  rc_a=$?
  n_nodiff_a="$(printf '%s\n' "$out_a" | grep -c "分岐なし")"
  if [ "$rc_a" -eq 0 ] && [ "$n_nodiff_a" -eq 2 ]; then
    ok "自己検査a: main/sub とも分岐なしと正しく判定された（rc=0）"
    return 0
  else
    ng "自己検査a: 完全一致のはずが分岐ありと判定された（rc=${rc_a}）"
    printf '%s\n' "$out_a" | sed 's/^/       /'
    cat "$WORK/a.err" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_b() {
  local b_ok=1
  echo "  -- b. 途中1件のポートを書き換え → 通し番号5件目が分岐点のはず --"
  out_b="$(python3 "$DIAG" "$SELFTEST_REF" "$WORK/st_b.txt" 2>"$WORK/b.err")"
  rc_b=$?
  if [ "$rc_b" -eq 1 ] && printf '%s\n' "$out_b" | grep -q "最初の構造的分岐点: 畳み込み後 通し番号 5 件目"; then
    ok "自己検査b: 書き換えた5件目が正しく分岐点として検出された（rc=1）"
  else
    ng "自己検査b: 書き換えた箇所が分岐点として検出されなかった（rc=${rc_b}）"
    printf '%s\n' "$out_b" | sed 's/^/       /'
    selftest_rc=1
    b_ok=0
  fi
  # 書き換えで新設した (OUT,00FC) が「混成側にのみ現れるポート」として
  # 出ることも確認する（ポート内訳・片側限定ポートの検出力）。
  if printf '%s\n' "$out_b" | grep -A5 "混成側にはあるが公式側に一度も現れない" | grep -q "OUT.*00FC"; then
    ok "自己検査b-2: 混成側だけに現れる (OUT,00FC) が一覧に出た"
  else
    ng "自己検査b-2: 混成側だけに現れる (OUT,00FC) が一覧に出なかった"
    selftest_rc=1
    b_ok=0
  fi
  [ "$b_ok" -eq 1 ]
}

check_c() {
  echo "  -- c. 片方を途中で打ち切り → 打ち切り位置(7件目)が分岐点のはず --"
  out_c="$(python3 "$DIAG" "$SELFTEST_REF" "$WORK/st_c.txt" 2>"$WORK/c.err")"
  rc_c=$?
  if [ "$rc_c" -eq 1 ] && printf '%s\n' "$out_c" | grep -q "最初の構造的分岐点: 畳み込み後 通し番号 7 件目"; then
    ok "自己検査c: 打ち切り位置(7件目)が正しく分岐点として検出された（rc=1）"
    return 0
  else
    ng "自己検査c: 打ち切りが分岐点として検出されなかった（rc=${rc_c}）"
    printf '%s\n' "$out_c" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_strict() {
  echo "  -- (strict) --strict で厳密比較モードが健在なことを確認 --"
  out_bs="$(python3 "$DIAG" --strict "$SELFTEST_REF" "$WORK/st_b.txt" 2>"$WORK/bs.err")"
  rc_bs=$?
  if [ "$rc_bs" -eq 1 ] && printf '%s\n' "$out_bs" | grep -q "最初の分岐点(厳密比較): 通し番号 5 件目"; then
    ok "自己検査strict: --strict は旧来どおり添字5件目で分岐を報告する（rc=1）"
    return 0
  else
    ng "自己検査strict: --strict の厳密比較が機能していない（rc=${rc_bs}）"
    printf '%s\n' "$out_bs" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_d() {
  echo "  -- d. スピン回数だけが違う(基準4回/混成2回) → 構造的分岐なし・かつ回数差として報告 --"
  gen_line2_spin 4 "$WORK/st_d_ref.txt"
  gen_line2_spin 2 "$WORK/st_d_mixed.txt"
  out_d="$(python3 "$DIAG" "$WORK/st_d_ref.txt" "$WORK/st_d_mixed.txt" 2>"$WORK/d.err")"
  rc_d=$?
  d_ok=1
  if [ "$rc_d" -eq 0 ] && printf '%s\n' "$out_d" | grep -q "構造的分岐なし"; then
    :
  else
    d_ok=0
  fi
  if printf '%s\n' "$out_d" | grep -E -q "pc=3002.*基準=4回.*混成=2回"; then
    :
  else
    d_ok=0
  fi
  if [ "$d_ok" -eq 1 ]; then
    ok "自己検査d: スピン回数差(4回/2回)を構造的分岐にせず、かつ回数差として報告した"
    return 0
  else
    ng "自己検査d: スピン回数差の扱いが誤り（構造的分岐なし・回数差報告の両方を満たさなかった、rc=${rc_d}）"
    printf '%s\n' "$out_d" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_e() {
  echo "  -- e. 畳み込んでも構造が違う(両側スピン3回+片側のみポート変更) → 構造的分岐点として検出 --"
  gen_line2_spin 3 "$WORK/st_e_ref.txt"
  gen_line2_spin 3 "$WORK/st_e_mixed_base.txt"
  sed 's/00FF   09   3005/00FC   09   3005/' "$WORK/st_e_mixed_base.txt" > "$WORK/st_e_mixed.txt"
  out_e="$(python3 "$DIAG" "$WORK/st_e_ref.txt" "$WORK/st_e_mixed.txt" 2>"$WORK/e.err")"
  rc_e=$?
  if [ "$rc_e" -eq 1 ] && printf '%s\n' "$out_e" | grep -q "最初の構造的分岐点: 畳み込み後 通し番号 5 件目"; then
    ok "自己検査e: スピンに紛れても構造の食い違い(5件目)を正しく検出した（rc=1）"
    return 0
  else
    ng "自己検査e: 畳み込みが本当の構造分岐を握り潰した（rc=${rc_e}）"
    printf '%s\n' "$out_e" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_f() {
  echo "  -- f. 一方が無限ループ(基準50000回/混成3回) → 回数差が[要注意]として目立つ形で報告 --"
  gen_line2_spin 50000 "$WORK/st_f_ref.txt"
  gen_line2_spin 3 "$WORK/st_f_mixed.txt"
  # h が基準側/混成側の連長上位5件を再利用するので --full で呼ぶ。
  out_f="$(python3 "$DIAG" --full "$WORK/st_f_ref.txt" "$WORK/st_f_mixed.txt" 2>"$WORK/f.err")"
  rc_f=$?
  f_ok=1
  if [ "$rc_f" -eq 0 ] && printf '%s\n' "$out_f" | grep -q "構造的分岐なし"; then
    :
  else
    f_ok=0
  fi
  if printf '%s\n' "$out_f" | grep -q "要注意" && \
     printf '%s\n' "$out_f" | grep -E -q "pc=3002.*基準=50000回.*混成=3回"; then
    :
  else
    f_ok=0
  fi
  if [ "$f_ok" -eq 1 ]; then
    ok "自己検査f: 極端な回数差(50000回/3回)を[要注意]として目立つ形で報告した"
    return 0
  else
    ng "自己検査f: 極端な回数差が目立つ形で報告されなかった（rc=${rc_f}）"
    printf '%s\n' "$out_f" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_g() {
  echo "  -- g. main/subの同じ行でpcだけ違う → sub「分岐なし」・main「分岐あり」を1回で確認 --"
  # main 3件目 (OUT 00FF 0E 3003) と sub 3件目 (IN 00FF 0E 4003) の pc だけを
  # 書き換える。kind/port/連長は変えない。main は pc も比較キーに含むので
  # 分岐扱いになるはず、sub は pc を比較キーから外しているので分岐なしの
  # はず——この非対称性そのものが検査対象（片方だけの確認では、sub側の
  # pc除外が「効いていない」場合でも見逃す。CLAUDE.md「わざと壊して確認」）。
  sed -e 's/OUT   00FF   0E   3003/OUT   00FF   0E   3999/' \
      -e 's/IN    00FF   0E   4003/IN    00FF   0E   4999/' \
      "$SELFTEST_REF" > "$WORK/st_g_mixed.txt"
  out_g="$(python3 "$DIAG" "$SELFTEST_REF" "$WORK/st_g_mixed.txt" 2>"$WORK/g.err")"
  rc_g=$?
  g_ok=1
  main_block_g="$(printf '%s\n' "$out_g" | awk '/^===== main =====/{f=1} /^===== sub =====/{f=0} f')"
  sub_block_g="$(printf '%s\n' "$out_g" | awk '/^===== sub =====/{f=1} f')"
  if [ "$rc_g" -eq 1 ] && printf '%s\n' "$main_block_g" | grep -q "最初の構造的分岐点: 畳み込み後 通し番号 3 件目"; then
    :
  else
    g_ok=0
  fi
  if printf '%s\n' "$sub_block_g" | grep -q "構造的分岐なし"; then
    :
  else
    g_ok=0
  fi
  if [ "$g_ok" -eq 1 ]; then
    ok "自己検査g: main(pc込み)は分岐あり・sub(pc除外)は分岐なしを1回の呼び出しで確認した（rc=${rc_g}）"
    return 0
  else
    ng "自己検査g: sub側のpc除外が効いていないか、main側のpc比較が壊れている（rc=${rc_g}）"
    printf '%s\n' "$out_g" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_h() {
  echo "  -- h. 巨大スピンを含むログ → 畳み込み後「連長上位5件」にそれが現れる --"
  # f と同じ合成フィクスチャ(基準50000回/混成3回、--full)を再利用し、
  # [要注意]の回数差一覧ではなく「連長上位5件」の欄にそれが現れることを
  # 別に検査する（分岐点の前後窓だけでは見えない位置に出る想定の機能
  # なので、分岐が無いケースでも表示されることを見る）。
  h_ok=1
  if printf '%s\n' "$out_f" | awk '/^===== main =====/{f=1} /^===== sub =====/{f=0} f' | \
     grep -A6 "基準側 畳み込み後 連長上位5件" | grep -E -q "pc=3002 x50000"; then
    :
  else
    h_ok=0
  fi
  if printf '%s\n' "$out_f" | awk '/^===== main =====/{f=1} /^===== sub =====/{f=0} f' | \
     grep -A6 "混成側 畳み込み後 連長上位5件" | grep -E -q "pc=3002 x3"; then
    :
  else
    h_ok=0
  fi
  if [ "$h_ok" -eq 1 ]; then
    ok "自己検査h: 巨大スピン(50000回)が連長上位5件に現れた"
    return 0
  else
    ng "自己検査h: 巨大スピンが連長上位5件に現れなかった"
    printf '%s\n' "$out_f" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_i() {
  echo "  -- i. 畳み込み後「末尾10件」→ 実際のログ末尾を反映している --"
  # a(完全一致コピー、--full)の結果を再利用する。main末尾は port=00F3
  # pc=300A、sub末尾は port=00FC pc=4007(参考表示)。分岐が無いケースでも
  # 末尾欄が出ること・その中身が本当に末尾であることの両方を見る。
  i_ok=1
  if printf '%s\n' "$out_a" | awk '/^===== main =====/{f=1} /^===== sub =====/{f=0} f' | \
     grep -A11 "基準側 畳み込み後 末尾10件" | grep -q "port=00F3 pc=300A"; then
    :
  else
    i_ok=0
  fi
  if printf '%s\n' "$out_a" | awk '/^===== sub =====/{f=1} f' | \
     grep -A8 "混成側 畳み込み後 末尾10件" | grep -q "port=00FC pc=4007"; then
    :
  else
    i_ok=0
  fi
  if [ "$i_ok" -eq 1 ]; then
    ok "自己検査i: 末尾10件がログの実際の末尾(main:00F3/300A, sub:00FC/4007)を反映していた"
    return 0
  else
    ng "自己検査i: 末尾10件がログ末尾を反映していなかった"
    printf '%s\n' "$out_a" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_j() {
  echo "  -- j. --brief でも異常が落ちないこと(分岐点・回数差・[要注意]) --"
  # b(1件書き換えで分岐検出)と f と同じ合成フィクスチャ(基準50000回/
  # 混成3回)を、明示的に --brief を付けて流し直す。tools/diag_l3_mixed.py
  # 自体の --brief が「構造的一致プレフィックス・分岐点・回数差
  # ([要注意]含む)・片側限定ポート一覧は省かない」設計になっているかを
  # 検査する（本スクリプトの自己検査表示の畳み込みとは別の対象）。
  out_j1="$(python3 "$DIAG" --brief "$SELFTEST_REF" "$WORK/st_b.txt" 2>"$WORK/j1.err")"
  rc_j1=$?
  out_j2="$(python3 "$DIAG" --brief "$WORK/st_f_ref.txt" "$WORK/st_f_mixed.txt" 2>"$WORK/j2.err")"
  rc_j2=$?
  j_ok=1
  if [ "$rc_j1" -eq 1 ] && printf '%s\n' "$out_j1" | grep -q "最初の構造的分岐点: 畳み込み後 通し番号 5 件目"; then
    :
  else
    j_ok=0
  fi
  if [ "$rc_j2" -eq 0 ] && printf '%s\n' "$out_j2" | grep -q "要注意" && \
     printf '%s\n' "$out_j2" | grep -E -q "pc=3002.*基準=50000回.*混成=3回"; then
    :
  else
    j_ok=0
  fi
  if [ "$j_ok" -eq 1 ]; then
    ok "自己検査j: tools/diag_l3_mixed.py --brief でも分岐点・回数差・[要注意]が落ちなかった"
    return 0
  else
    ng "自己検査j: --brief で異常検出情報が落ちた"
    printf '%s\n' "$out_j1" | sed 's/^/       /'
    printf '%s\n' "$out_j2" | sed 's/^/       /'
    selftest_rc=1
    return 1
  fi
}

check_k() {
  echo "  -- k. --brief と --full で判定(終了コード)が一致すること --"
  python3 "$DIAG" --brief "$SELFTEST_REF" "$WORK/st_b.txt" >/dev/null 2>"$WORK/k1.err"
  rc_k1_brief=$?
  python3 "$DIAG" --full  "$SELFTEST_REF" "$WORK/st_b.txt" >/dev/null 2>"$WORK/k2.err"
  rc_k1_full=$?
  python3 "$DIAG" --brief "$SELFTEST_REF" "$WORK/st_a.txt" >/dev/null 2>"$WORK/k3.err"
  rc_k2_brief=$?
  python3 "$DIAG" --full  "$SELFTEST_REF" "$WORK/st_a.txt" >/dev/null 2>"$WORK/k4.err"
  rc_k2_full=$?
  if [ "$rc_k1_brief" -eq "$rc_k1_full" ] && [ "$rc_k2_brief" -eq "$rc_k2_full" ]; then
    ok "自己検査k: --brief と --full で終了コードが一致した（分岐あり側 rc=${rc_k1_brief}／分岐なし側 rc=${rc_k2_brief}）"
    return 0
  else
    ng "自己検査k: --brief と --full で終了コードが食い違った（分岐あり側 brief=${rc_k1_brief}/full=${rc_k1_full}、分岐なし側 brief=${rc_k2_brief}/full=${rc_k2_full}）"
    selftest_rc=1
    return 1
  fi
}

check_l() {
  echo "  -- l. 自己検査が落ちたときは --brief でもその詳細が出ること --"
  # 本番の検査項目を実際に失敗させるのではなく、run_check の表示条件
  # そのもの（BRIEF=1でも失敗項目はcatする）を、わざと失敗するダミー
  # 検査関数を通して検査する。selftest_rc・FAILED_CHECKSを汚さないよう
  # サブシェル(command substitution)の中で実行する。
  local marker="DUMMY_NG_DETAIL_$$"
  check_dummy_for_l() {
    ng "自己検査dummy(l用・わざと失敗): marker=${marker}"
    return 1
  }
  local captured
  captured="$(BRIEF=1 run_check dummy_l check_dummy_for_l)"
  if printf '%s\n' "$captured" | grep -q "$marker"; then
    ok "自己検査l: BRIEF=1 でも失敗項目の詳細(run_checkの表示条件)が出力された"
    return 0
  else
    ng "自己検査l: BRIEF=1 で失敗項目の詳細が出力されなかった（run_checkの表示条件が壊れている）"
    selftest_rc=1
    return 1
  fi
}

run_check a      check_a
run_check b      check_b
run_check c      check_c
run_check strict check_strict
run_check d      check_d
run_check e      check_e
run_check f      check_f
run_check g      check_g
run_check h      check_h
run_check i      check_i
run_check j      check_j
run_check k      check_k
run_check l      check_l

if [ "$selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査: 全項目OK（a〜l）"
else
  ng "検出力の自己検査: 失敗した項目がある（このスクリプト自体を信用できない状態）: ${FAILED_CHECKS[*]:-}"
fi
overall_rc=$(( overall_rc || selftest_rc ))

# -----------------------------------------------------------------------
# 本番: 測定 → 伏せ字 → 保存 → 突き合わせ
# -----------------------------------------------------------------------
say "本番診断（混成ROMのI/O列を公式基準ログと突き合わせる）"

MIXED_RAW=""

if [ -n "$FROM_LOG" ]; then
  if [ ! -f "$FROM_LOG" ]; then
    echo "エラー: --from-log で指定したファイルが無い: $FROM_LOG" >&2
    exit 1
  fi
  echo "  --from-log 指定: 再測定を飛ばして $FROM_LOG を使う"
  MIXED_RAW="$FROM_LOG"
elif [ -z "${PC88_REF_ROM_DIR:-}" ] || [ -z "${PC88_REF_DISK_DIR:-}" ]; then
  cat <<'EOF'
  SKIP: 公式ROM・公式ディスクの環境変数が未設定、かつ --from-log も未指定。

  本番診断には以下のいずれかが要る。
    (a) PC88_REF_ROM_DIR / PC88_REF_DISK_DIR を設定して実測する
    (b) --from-log で既存の iolog（tools/conform_l3.sh 実行時の
        混成ステップの出力など）を指定する

  使い方の例:
    PC88_REF_ROM_DIR=/path/to/rom PC88_REF_DISK_DIR=/path/to/disk \
        tools/diag_l3_mixed.sh --out /path/to/save-dir

  上の「検出力の自己検査」は公式環境が無くても常に実行しており、
  そちらの結果はこのSKIPと無関係に独立して判定済み。
EOF
  echo
  if [ "$overall_rc" -eq 0 ]; then
    echo "diag_l3_mixed: 自己検査OK・本番診断はSKIP"
  else
    echo "diag_l3_mixed: 自己検査で失敗あり（本番診断はSKIP）"
  fi
  exit "$overall_rc"
else
  DISK="$PC88_REF_DISK_DIR/N88_FE.D88"
  echo "  混成ROM(公式main ROM一式 + 自作サブROM)でdiskA起動を実測"
  echo "  （tools/conform_l3.sh の混成ステップと同条件: frames 1800）"
  if ! run_l3_mixed_measurement "$PC88_REF_ROM_DIR" "$DISK" "$WORK" "$WORK/mixed.live.iolog.txt"; then
    exit 1
  fi
  MIXED_RAW="$WORK/mixed.live.iolog.txt"
fi

say "伏せ字を適用（tools/redact_iolog.py。既に伏せてあれば無変更・冪等）"
case "$MIXED_RAW" in
  *.gz) gzip -dc "$MIXED_RAW" > "$WORK/mixed.plain.txt" || exit 1 ;;
  *)    cp "$MIXED_RAW" "$WORK/mixed.plain.txt" ;;
esac
if ! python3 "$REDACT" --in-place "$WORK/mixed.plain.txt"; then
  echo "エラー: redact_iolog.py の実行に失敗した" >&2
  exit 1
fi

if [ -n "$OUT_DIR" ]; then
  mkdir -p "$OUT_DIR" || { echo "エラー: --out ディレクトリを作れない: $OUT_DIR" >&2; exit 1; }
else
  OUT_DIR="$(mktemp -d)"
fi
SAVED_LOG="$OUT_DIR/diag-l3-mixed-d0-boot.$(date +%Y%m%d-%H%M%S).iolog.redacted.txt"
cp "$WORK/mixed.plain.txt" "$SAVED_LOG"
echo "  伏せ字済みログを保存した（再測定なしで解析を繰り返せる。リポジトリ外）:"
echo "    $SAVED_LOG"

say "公式基準ログ($REF_LOG)と(cpu,方向,ポート,pc)だけで突き合わせ"
# 注: この診断ツールは適合/不適合の合否判定はしない（それは
# tools/conform_l3.sh の役目）。ここで分岐が見つかるのは
# 「今まさに調べたい」想定どおりの結果なので、diag_l3_mixed.py の
# 戻り値(分岐あり=1)を overall_rc には混ぜない。selftest の合否だけが
# このスクリプト自体の終了コードを決める。
if [ "$BRIEF" -eq 1 ]; then
  python3 "$DIAG" --brief "$REF_LOG" "$SAVED_LOG"
else
  python3 "$DIAG" --full "$REF_LOG" "$SAVED_LOG"
fi
diag_rc=$?
echo
if [ "$diag_rc" -eq 0 ]; then
  echo "  診断結果: (cpu,方向,ポート,pc) の列に分岐なし"
else
  echo "  診断結果: 分岐あり（上記の通し番号・前後イベント・ポート別内訳を参照）"
fi

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "diag_l3_mixed: 自己検査OK。本番診断の結果は上記参照（合否判定はしない）"
else
  echo "diag_l3_mixed: 自己検査で失敗あり（上記参照）"
fi
exit "$overall_rc"

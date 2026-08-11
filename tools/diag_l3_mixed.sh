#!/usr/bin/env bash
# tools/diag_l3_mixed.sh — 混成ROM実行のI/O列を、公式基準ログと
# ポート/pcレベルで突き合わせ、最初に食い違ったイベントを診断する。
#
# 背景: tools/conform_l3.sh の混成ROM適合テスト（公式main ROM一式 +
# 自作サブROM(DISK.ROM)で公式ディスクを起動）は、main が IN $FD で
# 受け取る値の列（docs/spec/l3-subrom.md 5.2節条件1）でしか判定しない。
# 直近の実走結果は「main/IN/00FD に該当するイベントが0件」——つまり
# データ転送以前、$FE/$FF のハンドシェイク段階で食い違っている。
# このスクリプトはその**最初の食い違ったイベント**を、値を一切見ずに
# (cpu, 方向IN/OUT, ポート, pc) の4項目だけで特定する。
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
使い方: tools/diag_l3_mixed.sh [--out DIR] [--from-log PATH]

  --out DIR       伏せ字済みログの保存先（省略時は mktemp。パスを表示する。
                   リポジトリ内には保存しない）
  --from-log PATH 既存の iolog を使い、混成ROMの再測定を飛ばす
                   （PC88_REF_ROM_DIR / PC88_REF_DISK_DIR 不要）

環境変数（--from-log 未指定時のみ必要）:
  PC88_REF_ROM_DIR   公式ROMの置き場
  PC88_REF_DISK_DIR  diskA(N88_FE.D88) の置き場

「検出力の自己検査」は常に実行する（環境変数の有無に関わらない）。
EOF
}

OUT_DIR=""
FROM_LOG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT_DIR="${2:-}"; shift 2 ;;
    --from-log) FROM_LOG="${2:-}"; shift 2 ;;
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
#   a. 完全一致のコピー           → 分岐なし
#   b. 途中1件のポートを書き換え   → その通し番号が分岐点として報告される
#   c. 片方を途中で打ち切り        → 打ち切り位置が分岐点として検出される
#
# 「わざと壊して検出できることを確かめてから信用する」がこのリポジトリの
# 規律（CLAUDE.md / feedback_measure_the_end_not_the_signal.md）。
# -----------------------------------------------------------------------
say "検出力の自己検査（比較ロジックをわざと壊して検出できるか）"
selftest_rc=0

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

echo "  -- a. 完全一致のコピー → 分岐なしのはず --"
out_a="$(python3 "$DIAG" "$SELFTEST_REF" "$WORK/st_a.txt" 2>"$WORK/a.err")"
rc_a=$?
n_nodiff_a="$(printf '%s\n' "$out_a" | grep -c "分岐なし")"
if [ "$rc_a" -eq 0 ] && [ "$n_nodiff_a" -eq 2 ]; then
  ok "自己検査a: main/sub とも分岐なしと正しく判定された（rc=0）"
else
  ng "自己検査a: 完全一致のはずが分岐ありと判定された（rc=${rc_a}）"
  printf '%s\n' "$out_a" | sed 's/^/       /'
  cat "$WORK/a.err" | sed 's/^/       /'
  selftest_rc=1
fi

echo "  -- b. 途中1件のポートを書き換え → 通し番号5件目が分岐点のはず --"
out_b="$(python3 "$DIAG" "$SELFTEST_REF" "$WORK/st_b.txt" 2>"$WORK/b.err")"
rc_b=$?
if [ "$rc_b" -eq 1 ] && printf '%s\n' "$out_b" | grep -q "最初の分岐点: 通し番号 5 件目"; then
  ok "自己検査b: 書き換えた5件目が正しく分岐点として検出された（rc=1）"
else
  ng "自己検査b: 書き換えた箇所が分岐点として検出されなかった（rc=${rc_b}）"
  printf '%s\n' "$out_b" | sed 's/^/       /'
  selftest_rc=1
fi
# 書き換えで新設した (OUT,00FC) が「混成側にのみ現れるポート」として
# 出ることも確認する（ポート内訳・片側限定ポートの検出力）。
if printf '%s\n' "$out_b" | grep -A5 "混成側にはあるが公式側に一度も現れない" | grep -q "OUT.*00FC"; then
  ok "自己検査b-2: 混成側だけに現れる (OUT,00FC) が一覧に出た"
else
  ng "自己検査b-2: 混成側だけに現れる (OUT,00FC) が一覧に出なかった"
  selftest_rc=1
fi

echo "  -- c. 片方を途中で打ち切り → 打ち切り位置(7件目)が分岐点のはず --"
out_c="$(python3 "$DIAG" "$SELFTEST_REF" "$WORK/st_c.txt" 2>"$WORK/c.err")"
rc_c=$?
if [ "$rc_c" -eq 1 ] && printf '%s\n' "$out_c" | grep -q "最初の分岐点: 通し番号 7 件目"; then
  ok "自己検査c: 打ち切り位置(7件目)が正しく分岐点として検出された（rc=1）"
else
  ng "自己検査c: 打ち切りが分岐点として検出されなかった（rc=${rc_c}）"
  printf '%s\n' "$out_c" | sed 's/^/       /'
  selftest_rc=1
fi

if [ "$selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査: 全項目OK"
else
  ng "検出力の自己検査: 失敗した項目がある（このスクリプト自体を信用できない状態）"
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
python3 "$DIAG" "$REF_LOG" "$SAVED_LOG"
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

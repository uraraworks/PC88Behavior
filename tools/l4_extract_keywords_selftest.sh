#!/usr/bin/env bash
# tools/l4_extract_keywords_selftest.sh — tools/l4_extract_keywords.py の自己検査
#
# マニュアルのOCRテキストは私物（refs/manual.txt。本リポジトリの外、
# CLAUDE.md「パスの扱い」）なので、無い環境では検査そのものを実行できない。
# その場合は黙ってSKIPせず、SKIPであることを目立つ形で報告する
# （docs/notes/feedback系「SKIPが合格の顔」を踏まない）。
#
# ある環境では以下を確認する:
#   (a) 再実行しても同じTSVになる（sha256一致・決定的）
#   (b) コミット済み src/l4_basic/keywords.tsv と一致する
#   (c) 語(word列)に重複が無い
#   (d) 故障注入: 入力の1行をわざと壊すと、出力（sha256）が変わる
#       （検査器が「何も見ていない」だけで一致していないことを確認する）
#
# 使い方: tools/l4_extract_keywords_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1、環境が無ければ SKIP でも 0。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXTRACT="$SCRIPT_DIR/l4_extract_keywords.py"
COMMITTED="$REPO_ROOT/src/l4_basic/keywords.tsv"

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

if [ -z "${PC88_REF_MANUAL_TXT:-}" ]; then
  echo "SKIP: マニュアルテキストなし＝未検査（PC88_REF_MANUAL_TXT未設定）"
  exit 0
fi
if [ ! -f "$PC88_REF_MANUAL_TXT" ]; then
  echo "SKIP: マニュアルテキストなし＝未検査（PC88_REF_MANUAL_TXT=$PC88_REF_MANUAL_TXT が見つからない）"
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

RUN1="$WORK/run1.tsv"
RUN2="$WORK/run2.tsv"

if ! PC88_REF_MANUAL_TXT="$PC88_REF_MANUAL_TXT" python3 "$EXTRACT" > "$RUN1" 2>"$WORK/err1.txt"; then
  fail "抽出スクリプトの実行に失敗した ($(cat "$WORK/err1.txt"))"
  exit 1
fi
if ! PC88_REF_MANUAL_TXT="$PC88_REF_MANUAL_TXT" python3 "$EXTRACT" > "$RUN2" 2>"$WORK/err2.txt"; then
  fail "抽出スクリプトの2回目の実行に失敗した"
  exit 1
fi

# (a) 決定性
if cmp -s "$RUN1" "$RUN2"; then
  pass "(a) 再実行しても同じTSVになる（決定的）"
else
  fail "(a) 再実行するとTSVが変わった（決定的でない）"
fi

# (b) コミット済みTSVと一致
if [ ! -f "$COMMITTED" ]; then
  fail "(b) コミット済み $COMMITTED が見当たらない"
else
  if cmp -s "$RUN1" "$COMMITTED"; then
    pass "(b) コミット済み src/l4_basic/keywords.tsv と一致する"
  else
    fail "(b) コミット済み src/l4_basic/keywords.tsv と食い違う（マニュアルの版が変わったか、スクリプトが未反映）"
  fi
fi

# (c) 語の重複が無い
DUPS="$(grep -v '^#' "$RUN1" | awk -F'\t' '{print $1}' | sort | uniq -d)"
if [ -z "$DUPS" ]; then
  pass "(c) 語(word列)に重複が無い"
else
  fail "(c) 語が重複している: $(echo "$DUPS" | tr '\n' ' ')"
fi

# (d) 故障注入: 入力の1行を壊すと出力が変わることを確認する
#     （抽出器が入力を実際に見ているかの陰性対照。
#     docs/notes 系「対照と故障注入の作法」を踏まえる）
MUTANT="$WORK/manual_mutant.txt"
# "ABS" を「命令語ではない別の文字列」に一箇所だけ書き換える。
# sedの1回限定置換で最初の出現だけを壊す。
python3 - "$PC88_REF_MANUAL_TXT" "$MUTANT" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8", errors="replace").read()
# 第2章目次の "ABS" を1箇所だけ壊す（先頭の見出し直後の出現）。
idx = text.find("A B S")
if idx == -1:
    idx = text.find("ABS")
if idx == -1:
    sys.exit(1)
mutated = text[:idx] + "ZZZ" + text[idx + 3:]
open(dst, "w", encoding="utf-8").write(mutated)
PYEOF
if [ -s "$MUTANT" ]; then
  MUTRUN="$WORK/mutant_run.tsv"
  if PC88_REF_MANUAL_TXT="$MUTANT" python3 "$EXTRACT" > "$MUTRUN" 2>"$WORK/err3.txt"; then
    if cmp -s "$RUN1" "$MUTRUN"; then
      fail "(d) 故障注入（ABSを1箇所破壊）しても出力が変わらなかった＝検査に検出力が無い"
    else
      pass "(d) 故障注入で出力が変わることを確認した（検出力あり）"
    fi
  else
    # 抽出自体が失敗する（章マーカーを壊してしまった等）のも
    # 「入力を見て反応している」証拠として許容する。
    pass "(d) 故障注入で抽出が失敗した＝入力を見て反応している"
  fi
else
  fail "(d) 故障注入用のミュータント生成に失敗した（ABSが見つからない）"
fi

if [ "$FAIL" -eq 0 ]; then
  echo "l4_extract_keywords_selftest: 全項目OK"
  exit 0
else
  echo "l4_extract_keywords_selftest: NG項目あり"
  exit 1
fi

#!/usr/bin/env bash
# tools/l4_token_table_selftest.sh — src/l4_basic/make_token_table.py の自己検査
#
# 入力は src/l4_basic/keywords.tsv（189語）のみ。外部の私物（マニュアル・ROM）
# には一切依存しないので、SKIPは無い（常に実行できる）。
#
# 確認する項目:
#   (a) 再実行しても同じ出力になる（決定的）
#   (b) 再生成した出力がコミット済み src/l4_basic/tokens.{tsv,asm} と一致する
#   (c) keywords.tsv の全語が表にある（過不足なし）
#   (d) 番号（トークン）に重複が無い
#   (e) 表の並びが大文字ASCII辞書順であること
#   (f) 0x80〜0xFE に127語、拡張(0xFF+)に残り全部が入っていること
#   (g) 故障注入1: keywords.tsvの1語を書き換えると出力が変わる
#   (h) 故障注入2: 番号を重複させた変種を作ると (d) の検査がNGを検出する
#
# 使い方: tools/l4_token_table_selftest.sh
# 全項目OKなら終了コード0、1つでも落ちたら1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GEN="$REPO_ROOT/src/l4_basic/make_token_table.py"
KEYWORDS="$REPO_ROOT/src/l4_basic/keywords.tsv"
COMMITTED_TSV="$REPO_ROOT/src/l4_basic/tokens.tsv"
COMMITTED_ASM="$REPO_ROOT/src/l4_basic/tokens.asm"

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 生成の実行（2回） -------------------------------------------------
RUN1_TSV="$WORK/run1.tsv"; RUN1_ASM="$WORK/run1.asm"
RUN2_TSV="$WORK/run2.tsv"; RUN2_ASM="$WORK/run2.asm"

if ! python3 "$GEN" --keywords "$KEYWORDS" --tokens-tsv "$RUN1_TSV" --asm "$RUN1_ASM" \
    >"$WORK/gen1.out" 2>"$WORK/gen1.err"; then
  fail "生成スクリプトの実行に失敗した ($(cat "$WORK/gen1.err"))"
  echo "l4_token_table_selftest: NG項目あり"
  exit 1
fi
if ! python3 "$GEN" --keywords "$KEYWORDS" --tokens-tsv "$RUN2_TSV" --asm "$RUN2_ASM" \
    >"$WORK/gen2.out" 2>"$WORK/gen2.err"; then
  fail "生成スクリプトの2回目の実行に失敗した"
  echo "l4_token_table_selftest: NG項目あり"
  exit 1
fi

# (a) 決定性
if cmp -s "$RUN1_TSV" "$RUN2_TSV" && cmp -s "$RUN1_ASM" "$RUN2_ASM"; then
  pass "(a) 再実行しても同じ出力になる（決定的）"
else
  fail "(a) 再実行すると出力が変わった（決定的でない）"
fi

# (b) コミット済み出力と一致
if [ ! -f "$COMMITTED_TSV" ] || [ ! -f "$COMMITTED_ASM" ]; then
  fail "(b) コミット済み src/l4_basic/tokens.tsv または tokens.asm が見当たらない"
else
  if cmp -s "$RUN1_TSV" "$COMMITTED_TSV" && cmp -s "$RUN1_ASM" "$COMMITTED_ASM"; then
    pass "(b) コミット済み src/l4_basic/tokens.{tsv,asm} と一致する"
  else
    fail "(b) コミット済み出力と食い違う（keywords.tsvの版が変わったか、生成が未反映）"
  fi
fi

# --- (c)〜(f) 性質チェック（Python）------------------------------------
# 検査そのものを使い回せるよう、1本のPythonスクリプトを標準入力ではなく
# 一時ファイルに書き、$1=keywords.tsv $2=tokens.tsv を取って
# "OK - ..." / "NG - ..." を1行ずつ出し、1つでもNGなら終了コード1にする。
CHECKER="$WORK/checker.py"
cat > "$CHECKER" <<'PYEOF'
import sys

keywords_path, tokens_path = sys.argv[1], sys.argv[2]

def read_words(path):
    words = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if cols and cols[0]:
                words.append(cols[0])
    return words

def read_table(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 2:
                print(f"NG - 表の行形式が不正: {line!r}")
                sys.exit(1)
            entries.append((cols[0], cols[1]))
    return entries

kw_words = read_words(keywords_path)
table = read_table(tokens_path)
table_words = [w for w, _ in table]
table_tokens = [t for _, t in table]

fail = False

# (c) 過不足なし
if set(kw_words) != set(table_words) or len(kw_words) != len(table_words):
    print(f"NG - (c) keywords.tsvと表の語集合が一致しない（keywords={len(kw_words)}件, 表={len(table_words)}件）")
    fail = True
else:
    print(f"OK - (c) keywords.tsvの全語（{len(kw_words)}件）が表にあり過不足がない")

# (d) 番号の重複が無い
dups = [t for t in set(table_tokens) if table_tokens.count(t) > 1]
if dups:
    print(f"NG - (d) 番号が重複している: {dups}")
    fail = True
else:
    print("OK - (d) 番号（トークン）に重複が無い")

# (e) 大文字ASCII辞書順
if table_words == sorted(table_words):
    print("OK - (e) 表の並びが大文字ASCII辞書順になっている")
else:
    print("NG - (e) 表の並びが辞書順になっていない")
    fail = True

# (f) 0x80-0xFEに127語、拡張に残り全部
n = len(table_words)
n_first_expected = min(n, 127)
first_tokens = table_tokens[:n_first_expected]
rest_tokens = table_tokens[n_first_expected:]
ok_first = all(len(t.split(" ")) == 1 for t in first_tokens)
expected_first_values = [f"0x{0x80+i:02X}" for i in range(n_first_expected)]
ok_first_values = (first_tokens == expected_first_values)
ok_rest = True
for i, t in enumerate(rest_tokens):
    parts = t.split(" ")
    expected = ["0xFF", f"0x{0x80+i:02X}"]
    if parts != expected:
        ok_rest = False
        break
if ok_first and ok_first_values and ok_rest:
    print(f"OK - (f) 1バイト範囲(0x80-0xFE)に{n_first_expected}語、拡張(0xFF+)に残り{len(rest_tokens)}語")
else:
    print(f"NG - (f) 範囲の割り当てが規則どおりでない（1バイト側OK={ok_first and ok_first_values}, 拡張側OK={ok_rest}）")
    fail = True

sys.exit(1 if fail else 0)
PYEOF

if python3 "$CHECKER" "$KEYWORDS" "$RUN1_TSV" > "$WORK/check1.out" 2>&1; then
  CHECK_RC=0
else
  CHECK_RC=1
fi
cat "$WORK/check1.out"
if [ "$CHECK_RC" -ne 0 ]; then
  FAIL=1
fi

# --- (g) 故障注入1: keywords.tsvの1語を書き換えると出力が変わる --------
# sedの範囲アドレス"0,/re/"はGNU拡張でBSD sed(macOS)には無いため、
# 移植性のためPythonで最初の1箇所だけ書き換える。
MUTANT_KW="$WORK/keywords_mutant.tsv"
python3 - "$KEYWORDS" "$MUTANT_KW" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
target = "ABS\t"
idx = text.find("\n" + target)
if idx == -1:
    sys.exit(1)
idx += 1
mutated = text[:idx] + "ZZZMUT\t" + text[idx + len(target):]
open(dst, "w", encoding="utf-8").write(mutated)
PYEOF
if cmp -s "$KEYWORDS" "$MUTANT_KW"; then
  fail "(g) 故障注入用の変異を作れなかった（ABS行が見つからない）"
else
  MUT_TSV="$WORK/mutant.tsv"; MUT_ASM="$WORK/mutant.asm"
  if python3 "$GEN" --keywords "$MUTANT_KW" --tokens-tsv "$MUT_TSV" --asm "$MUT_ASM" \
      >"$WORK/genm.out" 2>"$WORK/genm.err"; then
    if cmp -s "$RUN1_TSV" "$MUT_TSV"; then
      fail "(g) keywords.tsvを1語書き換えても出力が変わらなかった＝検出力が無い"
    else
      pass "(g) 故障注入（ABSを書き換え）で出力が変わることを確認した（検出力あり）"
    fi
  else
    fail "(g) 変異入力での生成が失敗した（想定外）"
  fi
fi

# --- (h) 故障注入2: 番号を重複させた変種を作ると(d)の検査がNGを検出する -
DUP_TSV="$WORK/dup.tsv"
# 先頭2行(コメント除く)の番号を同じ値に揃えて、意図的に重複を作る。
python3 - "$RUN1_TSV" "$DUP_TSV" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().splitlines()
out = []
data_idx = []
for i, line in enumerate(lines):
    if line and not line.startswith("#"):
        data_idx.append(i)
if len(data_idx) < 2:
    sys.exit(1)
i0, i1 = data_idx[0], data_idx[1]
w0, t0 = lines[i0].split("\t")
w1, t1 = lines[i1].split("\t")
lines[i1] = f"{w1}\t{t0}"  # 2行目の番号を1行目と同じにする
open(dst, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PYEOF
if [ -s "$DUP_TSV" ]; then
  if python3 "$CHECKER" "$KEYWORDS" "$DUP_TSV" > "$WORK/checkdup.out" 2>&1; then
    fail "(h) 番号を重複させた変種でも検査がOKを返した＝(d)に検出力が無い"
    cat "$WORK/checkdup.out"
  else
    if grep -q "^NG - (d)" "$WORK/checkdup.out"; then
      pass "(h) 番号重複の変種で(d)の検査がNGを検出した（検出力あり）"
    else
      fail "(h) 変種はNGになったが(d)以外の理由だった（想定外）: $(cat "$WORK/checkdup.out")"
    fi
  fi
else
  fail "(h) 重複変種の生成に失敗した"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "l4_token_table_selftest: 全項目OK"
  exit 0
else
  echo "l4_token_table_selftest: NG項目あり"
  exit 1
fi

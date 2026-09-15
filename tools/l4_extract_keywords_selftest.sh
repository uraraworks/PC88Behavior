#!/usr/bin/env bash
# tools/l4_extract_keywords_selftest.sh — 語の一覧v2の自己検査。
#
# v1（tools/l4_extract_keywords.py、目次からの機械抽出、189語）はマニュアルの
# 目次の見出しであって命令語一覧ではなかった（docs/notes/l4-keywords-extraction.md
# 「v2 — 資料1「予約語」への切り替え」）。v2は資料1「N88-BASIC/N88-日本語BASICの
# 予約語」（資-1、PDF 377頁）を2人が独立に画像から書き起こし
# （src/l4_basic/reserved_words_transcript.tsv＝A本・
#  src/l4_basic/reserved_words_transcript_b.tsv＝B本）、突き合わせて
# A本（190語）を正とし、src/l4_basic/make_keywords.py が機械的に
# src/l4_basic/keywords.tsv を作る。このファイル名のまま中身をv2用に
# 差し替えた（tools/run_all_selftests.sh の登録名を変えずに済ませるため）。
#
# 確認する項目:
#   0. A本/B本の突き合わせ（rsv_compare.pyと同じ論理の再現）:
#      位置ごとの一致・不一致・片方だけを数える。期待は
#      一致=189・不一致=0・片方だけ=1（3段目32番LOG、B本の読み落とし）
#   (a) コミット済み keywords.tsv の全190語が、マニュアルOCRテキストの
#       資料1該当範囲（前後10行、NFKC正規化・空白除去、I→!の読み替えを
#       許す）に部分文字列として現れる。マニュアルテキストが無い環境
#       （PC88_REF_MANUAL_TXT未設定）ではSKIPでrc=0（このチェックのみ）
#   (b) 語であることの検査: '/'（長さ1の語＝除算記号そのものは除く）・
#       '...'・空白（GO TOのみ許可）・全角文字（unicodedata.east_asian_width
#       がF/Wの文字）・小文字を含まない
#   (c) 語の重複が無い
#   (d) 語数がちょうど190
#   故障注入1: (b)に '/' を含む項目（複数語結合の疑いがある形）を1つ
#     混ぜると (b) がNGになる
#   故障注入2: make_keywords.pyの再生成が入力(reserved_words_transcript.tsv)
#     と決定的に対応していること（1行書き換えると出力が変わる）
#
# 使い方: tools/l4_extract_keywords_selftest.sh
# 全項目OKなら終了コード0、1つでも落ちたら1（(a)のSKIPは合否に数えない）。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MAKE_KEYWORDS="$REPO_ROOT/src/l4_basic/make_keywords.py"
TRANSCRIPT_A="$REPO_ROOT/src/l4_basic/reserved_words_transcript.tsv"
TRANSCRIPT_B="$REPO_ROOT/src/l4_basic/reserved_words_transcript_b.tsv"
COMMITTED="$REPO_ROOT/src/l4_basic/keywords.tsv"

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 0. A本/B本の突き合わせ（rsv_compare.pyと同じ論理の再現） -------------
CHECKER0="$WORK/compare.py"
cat > "$CHECKER0" <<'PYEOF'
import sys

def load(path):
    rows = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or line.startswith("col\t"):
                continue
            cols = (line.split("\t") + ["", "", "", ""])[:4]
            col, row, word, conf = cols
            rows[(int(col), int(row))] = (word.strip(), conf.strip())
    return rows

a = load(sys.argv[1])
b = load(sys.argv[2])
keys = sorted(set(a) | set(b))
agree = differ = only = 0
detail = []
for k in keys:
    wa = a.get(k, ("",))[0]
    wb = b.get(k, ("",))[0]
    if k not in a or k not in b:
        only += 1
        detail.append((k, "片方だけ"))
        continue
    if wa == wb:
        agree += 1
    else:
        differ += 1
        detail.append((k, "不一致"))
print(f"A={len(a)} B={len(b)} 和={len(keys)} 一致={agree} 不一致={differ} 片方だけ={only}")
for k, why in detail:
    print(f"  {why} 段{k[0]}-{k[1]}")
sys.exit(0)
PYEOF
COMPARE_OUT="$(python3 "$CHECKER0" "$TRANSCRIPT_A" "$TRANSCRIPT_B")"
echo "$COMPARE_OUT"
if echo "$COMPARE_OUT" | head -1 | grep -q "一致=189 不一致=0 片方だけ=1"; then
  pass "0. A本/B本の突き合わせが期待どおり（一致189・不一致0・片方だけ1）"
else
  fail "0. A本/B本の突き合わせが期待と食い違う"
fi

# --- (a) マニュアルOCRテキストでの裏づけ ----------------------------------
if [ -z "${PC88_REF_MANUAL_TXT:-}" ] || [ ! -f "${PC88_REF_MANUAL_TXT:-/dev/null}" ]; then
  echo "SKIP: (a) マニュアルテキストなし＝未検査（PC88_REF_MANUAL_TXT未設定または不在）"
else
  MANUAL_DIR="$(cd "$(dirname "$PC88_REF_MANUAL_TXT")" && pwd)"
  CHECKER_A="$WORK/check_a.py"
  cat > "$CHECKER_A" <<'PYEOF'
import sys, unicodedata, pathlib

keywords_path, manual_dir = sys.argv[1], sys.argv[2]
refs = pathlib.Path(manual_dir)
# 資料1該当行（調査担当の報告、rsv_compare.pyと同じ値）
LINES = {"manual_squashed.txt": 1479, "manual.txt": 1110}
SPAN = 10

def window(fname, center):
    p = refs / fname
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8", errors="replace").splitlines()
    lo, hi = max(0, center - 1 - SPAN), min(len(t), center + SPAN)
    w = "".join(t[lo:hi])
    return unicodedata.normalize("NFKC", w).replace(" ", "").replace("　", "")

wins = [window(f, c) for f, c in LINES.items()]
wins = [w for w in wins if w]
if not wins:
    print("NG - (a) 参照テキストが1つも読めなかった")
    sys.exit(1)

words = []
with open(keywords_path, encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if cols and cols[0]:
            words.append(cols[0])

miss = []
for w in words:
    stripped = w.replace(" ", "")  # GO TO のような空白入り語をウィンドウ側と揃える
    variants = {stripped, stripped.replace("I", "!")}
    if not any(any(v in win for v in variants) for win in wins):
        miss.append(w)

if miss:
    print(f"NG - (a) テキストに現れない語が{len(miss)}件: {miss}")
    sys.exit(1)
print(f"OK - (a) 全{len(words)}語がマニュアルOCRテキストの資料1該当範囲に現れる（I→!の読み替えを許す）")
sys.exit(0)
PYEOF
  if python3 "$CHECKER_A" "$COMMITTED" "$MANUAL_DIR"; then
    :
  else
    FAIL=1
  fi
fi

# --- (b)〜(d) 性質チェック（Python）----------------------------------------
CHECKER_BCD="$WORK/check_bcd.py"
cat > "$CHECKER_BCD" <<'PYEOF'
import sys, unicodedata

keywords_path = sys.argv[1]
EXPECTED_COUNT = 190
ALLOWED_SPACE_WORDS = {"GO TO"}

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

def is_wordlike(w):
    if "..." in w:
        return False, "'...'を含む"
    if "/" in w and len(w) > 1:
        return False, "'/'を含む(複数語結合の疑い)"
    if any(ch.isspace() for ch in w) and w not in ALLOWED_SPACE_WORDS:
        return False, "空白を含む"
    if any(unicodedata.east_asian_width(ch) in ("F", "W") for ch in w):
        return False, "全角文字を含む"
    if any(ch.islower() for ch in w):
        return False, "小文字を含む(目次見出しの残骸の疑い)"
    return True, ""

words = read_words(keywords_path)
fail = False

# (b) 語であることの検査
bad = [(w, is_wordlike(w)[1]) for w in words if not is_wordlike(w)[0]]
if bad:
    print(f"NG - (b) 語の形をしていない項目がある: {bad}")
    fail = True
else:
    print(f"OK - (b) 全{len(words)}語が語の形をしている(記号は'/'単体等の妥当な単独語のみ許可)")

# (c) 重複なし
dups = sorted({w for w in words if words.count(w) > 1})
if dups:
    print(f"NG - (c) 語が重複している: {dups}")
    fail = True
else:
    print("OK - (c) 語の重複が無い")

# (d) 語数
if len(words) == EXPECTED_COUNT:
    print(f"OK - (d) 語数が{EXPECTED_COUNT}である")
else:
    print(f"NG - (d) 語数が{len(words)}(期待{EXPECTED_COUNT})")
    fail = True

sys.exit(1 if fail else 0)
PYEOF
if python3 "$CHECKER_BCD" "$COMMITTED" > "$WORK/bcd.out" 2>&1; then
  BCD_RC=0
else
  BCD_RC=1
fi
cat "$WORK/bcd.out"
[ "$BCD_RC" -ne 0 ] && FAIL=1

# --- 故障注入1: (b)に'/'を含む項目を混ぜるとNGになる -----------------------
FAULT1="$WORK/keywords_fault_slash.tsv"
cp "$COMMITTED" "$FAULT1"
printf 'IF/THEN/ELSE\t9\t99\tテスト用の故障注入\n' >> "$FAULT1"
if python3 "$CHECKER_BCD" "$FAULT1" > "$WORK/fault1.out" 2>&1; then
  fail "故障注入1: '/'を含む項目を混ぜても(b)がNGを検出しなかった"
  cat "$WORK/fault1.out"
else
  if grep -q "^NG - (b)" "$WORK/fault1.out"; then
    pass "故障注入1: '/'を含む項目を混ぜると(b)がNGを検出した（検出力あり）"
  else
    fail "故障注入1: NGにはなったが(b)以外の理由だった: $(cat "$WORK/fault1.out")"
  fi
fi

# --- 故障注入2: make_keywords.pyの再生成が入力と決定的に対応する -----------
MUTANT_TRANSCRIPT="$WORK/transcript_mutant.tsv"
python3 - "$TRANSCRIPT_A" "$MUTANT_TRANSCRIPT" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
target = "\t1\tABS\tsure"
idx = text.find(target)
if idx == -1:
    sys.exit(1)
mutated = text[:idx] + "\t1\tZZZMUT\tsure" + text[idx + len(target):]
open(dst, "w", encoding="utf-8").write(mutated)
PYEOF
if cmp -s "$TRANSCRIPT_A" "$MUTANT_TRANSCRIPT"; then
  fail "故障注入2: 変異用テキストを作れなかった（ABS行が見つからない）"
else
  RUN1="$WORK/gen1.tsv"; RUN_MUT="$WORK/gen_mut.tsv"
  if python3 "$MAKE_KEYWORDS" --transcript "$TRANSCRIPT_A" --out "$RUN1" >/dev/null 2>&1 \
     && python3 "$MAKE_KEYWORDS" --transcript "$MUTANT_TRANSCRIPT" --out "$RUN_MUT" >/dev/null 2>&1; then
    if cmp -s "$RUN1" "$RUN_MUT"; then
      fail "故障注入2: 書き起こしを1語書き換えても出力が変わらなかった＝検出力が無い"
    else
      pass "故障注入2: 書き起こしを1語書き換えると出力が変わることを確認した（検出力あり）"
    fi
  else
    fail "故障注入2: 生成スクリプトの実行に失敗した"
  fi
  # 併せて再実行の決定性とコミット済みファイルとの一致も確認する。
  if cmp -s "$RUN1" "$COMMITTED"; then
    pass "make_keywords.pyの再生成がコミット済みkeywords.tsvと一致する（決定的）"
  else
    fail "make_keywords.pyの再生成がコミット済みkeywords.tsvと食い違う"
  fi
fi

if [ "$FAIL" -eq 0 ]; then
  echo "l4_extract_keywords_selftest: 全項目OK"
  exit 0
else
  echo "l4_extract_keywords_selftest: NG項目あり"
  exit 1
fi

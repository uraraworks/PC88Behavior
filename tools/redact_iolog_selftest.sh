#!/usr/bin/env bash
# tools/redact_iolog_selftest.sh — tools/redact_iolog.py 自体を検査する。
#
# CLAUDE.md / docs/notes の方針どおり、検査器を信用してよいのは
# わざと壊して検出できることを確かめた後だけ（tools/cmp_io_selftest.sh の
# 作法を踏襲）。公式ROM不要。フィクスチャは全て自作の合成データで、
# 公式ディスクの実データは一切使わない。
#
# 使い方: tools/redact_iolog_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REDACT="$SCRIPT_DIR/redact_iolog.py"
HASH="$SCRIPT_DIR/hash_io_stream.py"
CMP="$SCRIPT_DIR/cmp_io.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 合成フィクスチャ（公式データ不使用）---------------------------------
# データポート($FB/$FC/$FD)と制御ポート($FA/$FE)を混ぜる。main/sub両CPU、
# IN/OUT両方向、旧形式(7列)・新形式(8列・clock付き)の両方を含める。
FIXTURE="$WORK/fixture.iolog.txt"
cat > "$FIXTURE" <<'EOF'
# 合成テスト用iolog（自作。公式データ不使用）
core      : (テスト用ダミー)
frames    : 100

# main
# seq    clock   frame  cpu   kind  port  value  pc
     1       1      0  main  IN    00FA   80   1000
     2       2      0  main  OUT   00FD   5A   1004
     3       3      0  main  IN    00FD   3C   1008
     4       4      0  main  IN    00FE   01   100C
     5       5      0  main  OUT   00FF   0F   1010

# sub
# seq  frame  cpu   kind  port  value  pc
     1      0  sub   IN    00FA   00   2000
     2      1  sub   OUT   00FB   77   2004
     3      2  sub   IN    00FC   88   2008
     4      3  sub   OUT   00FC   99   200C
     5      4  sub   IN    00FE   02   2010
EOF

# 期待値（伏せる前）: main/00FD/OUT = ["5A"], main/00FD/IN = ["3C"],
#                     sub/00FB/OUT = ["77"], sub/00FC/IN = ["88"], sub/00FC/OUT = ["99"]

REDACTED="$WORK/redacted.iolog.txt"
python3 "$REDACT" "$FIXTURE" > "$REDACTED" 2>"$WORK/redact.err"
if [[ $? -ne 0 ]]; then
    fail "a. redact_iolog.py の実行に失敗: $(cat "$WORK/redact.err")"
else
    # データポートの値が消えていること
    if grep -qE '^\s*2\s+2\s+0\s+main\s+OUT\s+00FD\s+--\s' "$REDACTED" \
        && grep -qE '^\s*3\s+3\s+0\s+main\s+IN\s+00FD\s+--\s' "$REDACTED" \
        && grep -qE '^\s*2\s+1\s+sub\s+OUT\s+00FB\s+--\s' "$REDACTED"; then
        pass "a. データポート(\$FD/\$FB)の value が伏せられている"
    else
        fail "a. データポートの value が伏せられていない"
    fi
    # 制御ポートの値が残っていること
    if grep -qE '^\s*1\s+1\s+0\s+main\s+IN\s+00FA\s+80\s' "$REDACTED" \
        && grep -qE '^\s*4\s+4\s+0\s+main\s+IN\s+00FE\s+01\s' "$REDACTED" \
        && grep -qE '^\s*5\s+4\s+sub\s+IN\s+00FE\s+02\s' "$REDACTED"; then
        pass "a. 制御ポート(\$FA/\$FE)の value は残っている"
    else
        fail "a. 制御ポートの value まで消えてしまっている（過剰マスク）"
    fi
fi

# --- b. 伏せ字後ファイルからデータポートの値を復元できない ------------------
IN_FD_VALUES="$(python3 "$HASH" "$REDACTED" --cpu main --port FD --kind IN 2>/dev/null | awk -F'\t' '$1=="count"{print $2}')"
# hash_io_stream.py は値そのものを出さないので、cmp_io.py --port FD --kind IN
# で直接抜き出して "--" になっていることを見る。
python3 "$CMP" "$FIXTURE" "$REDACTED" --cpu main --port FD --kind IN >/dev/null 2>"$WORK/cmp_fd.log"
if grep -q '値が違う' "$WORK/cmp_fd.log" 2>/dev/null || ! python3 "$CMP" "$FIXTURE" "$REDACTED" --cpu main --port FD --kind IN >/dev/null 2>/dev/null; then
    pass "b. 伏せ字後の \$FD/IN は元の値と一致しない（復元できない）"
else
    fail "b. 伏せ字後の \$FD/IN が元の値と一致してしまっている"
fi

# --- c. 末尾の記録ハッシュが hash_io_stream.py の出力と一致する -------------
ORIG_FD_OUT_HASH="$(python3 "$HASH" "$FIXTURE" --cpu main --port FD --kind OUT --name t 2>/dev/null | awk -F'\t' '{print $6}')"
FOOTER_FD_OUT_HASH="$(grep -E '^# main\s+00FD\s+OUT\s' "$REDACTED" | awk -F'\t' '{print $5}')"
if [[ -n "$ORIG_FD_OUT_HASH" && "$ORIG_FD_OUT_HASH" == "$FOOTER_FD_OUT_HASH" ]]; then
    pass "c. 末尾記録の main/00FD/OUT ハッシュが hash_io_stream.py の出力と一致"
else
    fail "c. ハッシュ不一致 (hash_io_stream=$ORIG_FD_OUT_HASH / footer=$FOOTER_FD_OUT_HASH)"
fi

ORIG_FB_OUT_HASH="$(python3 "$HASH" "$FIXTURE" --cpu sub --port FB --kind OUT --name t 2>/dev/null | awk -F'\t' '{print $6}')"
FOOTER_FB_OUT_HASH="$(grep -E '^# sub\s+00FB\s+OUT\s' "$REDACTED" | awk -F'\t' '{print $5}')"
if [[ -n "$ORIG_FB_OUT_HASH" && "$ORIG_FB_OUT_HASH" == "$FOOTER_FB_OUT_HASH" ]]; then
    pass "c. 末尾記録の sub/00FB/OUT ハッシュが hash_io_stream.py の出力と一致"
else
    fail "c. ハッシュ不一致 (hash_io_stream=$ORIG_FB_OUT_HASH / footer=$FOOTER_FB_OUT_HASH)"
fi

# --- d. 冪等性: 2回かけても同じ結果 ----------------------------------------
REDACTED2="$WORK/redacted2.iolog.txt"
python3 "$REDACT" "$REDACTED" > "$REDACTED2" 2>"$WORK/redact2.err"
if diff -q "$REDACTED" "$REDACTED2" >/dev/null 2>&1; then
    pass "d. 2回かけても結果が変わらない（冪等）"
else
    fail "d. 2回目で結果が変化した（冪等性が崩れている）"
fi

# --- e. gzip版と非圧縮版でcmp_io.py/hash_io_stream.pyの出力が完全一致 -------
REDACTED_GZ="$WORK/redacted.iolog.txt.gz"
gzip -c "$REDACTED" > "$REDACTED_GZ"

CMP_PLAIN_OUT="$(python3 "$CMP" "$REDACTED" "$REDACTED" --cpu main 2>&1)"
CMP_GZ_OUT="$(python3 "$CMP" "$REDACTED_GZ" "$REDACTED_GZ" --cpu main 2>&1)"
CMP_MIX_OUT="$(python3 "$CMP" "$REDACTED" "$REDACTED_GZ" --cpu main 2>&1)"
if [[ "$CMP_PLAIN_OUT" == "$CMP_GZ_OUT" && $? -eq 0 ]] && python3 "$CMP" "$REDACTED" "$REDACTED_GZ" --cpu main >/dev/null 2>&1; then
    pass "e. cmp_io.py: gzip版/非圧縮版で出力が一致し、相互比較も一致判定になる"
else
    fail "e. cmp_io.py: gzip版と非圧縮版で挙動が異なる"
fi

HASH_PLAIN="$(python3 "$HASH" "$REDACTED" --cpu sub --port FC --kind IN 2>&1)"
HASH_GZ="$(python3 "$HASH" "$REDACTED_GZ" --cpu sub --port FC --kind IN 2>&1)"
if [[ "$HASH_PLAIN" == "$HASH_GZ" ]]; then
    pass "e. hash_io_stream.py: gzip版/非圧縮版で出力が一致"
else
    fail "e. hash_io_stream.py: gzip版と非圧縮版で出力が異なる ($HASH_PLAIN / $HASH_GZ)"
fi

# --- f. 検出力の確認: わざと壊して落ちることを見る --------------------------
# f-1. --ports "" で対象ポートを空にすると、データポートの値が伏せられない
#      ままになる。a.の判定基準（マスクされているか）がこれを正しく
#      「壊れている」と判定できることを確認する。
BROKEN="$WORK/broken.iolog.txt"
python3 "$REDACT" --ports "" "$FIXTURE" > "$BROKEN" 2>"$WORK/broken.err"
if grep -qE '^\s*2\s+2\s+0\s+main\s+OUT\s+00FD\s+5A\s' "$BROKEN"; then
    pass "f. --ports \"\" で伏せなかった場合、a.の判定基準が元の値の残存を検出できる"
else
    fail "f. --ports \"\" を指定しても \$FD の値が伏せられてしまった（--ports指定が無視されている）"
fi

# f-2. --ports を通常指定に戻すと再び伏せられる（f-1がツール自体の壊れでは
#      なく、意図的な壊し方だけで再現することの確認）
RESTORED="$WORK/restored.iolog.txt"
python3 "$REDACT" --ports 00FB,00FC,00FD "$FIXTURE" > "$RESTORED" 2>"$WORK/restored.err"
if grep -qE '^\s*2\s+2\s+0\s+main\s+OUT\s+00FD\s+--\s' "$RESTORED"; then
    pass "f. --ports を明示指定すれば通常どおり伏せられる（f-1は指定の効果であることの確認）"
else
    fail "f. --ports を明示指定しても伏せられない（ツール自体が壊れている）"
fi

# f-3. 制御ポートまで対象に含めると、制御ポートの値も消える
#      （「伏せてよいのはデータポートだけ」というa.の後半判定の検出力確認）
OVERMASK="$WORK/overmask.iolog.txt"
python3 "$REDACT" --ports 00FB,00FC,00FD,00FA,00FE "$FIXTURE" > "$OVERMASK" 2>"$WORK/overmask.err"
if grep -qE '^\s*1\s+1\s+0\s+main\s+IN\s+00FA\s+--\s' "$OVERMASK"; then
    pass "f. --ports に制御ポートを加えると実際に消える（a.後半判定の検出力確認）"
else
    fail "f. 制御ポートを対象に加えても消えなかった（--ports指定が反映されていない）"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
    echo "==> 全項目 OK"
    exit 0
else
    echo "==> 一部 NG"
    exit 1
fi

#!/usr/bin/env bash
# tools/cmp_io_selftest.sh — tools/cmp_io.py 自体を検査する。
#
# CLAUDE.md / docs/notes の方針どおり、検査器を信用してよいのは
# わざと壊して検出できることを確かめた後だけ。公式 ROM 不要。
#
# 使い方: tools/cmp_io_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CMP="$SCRIPT_DIR/cmp_io.py"
SEED="$REPO_ROOT/measurements/l1-boot-io.iolog.txt"

if [[ ! -f "$SEED" ]]; then
    echo "エラー: 種ファイルが無い: $SEED" >&2
    exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# main 節・OUT 行の総数を数えておく（種ファイルは 560 件のはず）
OUT_COUNT="$(awk '$3=="main" && $4=="OUT" {c++} END{print c+0}' "$SEED")"
if [[ "$OUT_COUNT" -lt 3 ]]; then
    echo "エラー: 種ファイルの OUT 件数が少なすぎる（$OUT_COUNT）" >&2
    exit 2
fi

# --- テスト1: 同一ファイル同士 → 一致 ---------------------------------
cp "$SEED" "$WORK/t1.txt"
python3 "$CMP" "$SEED" "$WORK/t1.txt" >"$WORK/t1.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]] && grep -q "一致（OUT" "$WORK/t1.out"; then
    pass "1. 同一ファイル同士 → 一致（終了コード0）"
else
    fail "1. 同一ファイル同士 → 一致（終了コード0） rc=$rc"
    cat "$WORK/t1.out"
fi

# --- テスト2: OUT の値を1つ書き換える → 不一致、位置も一致 -----------
TARGET_N=200  # 560件中の適当な中間位置
awk -v n="$TARGET_N" '
    BEGIN{c=0}
    {
        if ($3=="main" && $4=="OUT") {
            c++
            if (c==n) { $6 = "ZZ" }
        }
        print
    }
' OFS=' ' "$SEED" > "$WORK/t2.txt"
python3 "$CMP" "$SEED" "$WORK/t2.txt" >"$WORK/t2.out" 2>&1
rc=$?
reported="$(grep -oE '[0-9]+ 件目で食い違い' "$WORK/t2.out" | grep -oE '^[0-9]+')"
if [[ $rc -eq 1 ]] && [[ "$reported" == "$TARGET_N" ]] && grep -q "値が違う" "$WORK/t2.out"; then
    pass "2. OUT の値を1つ書き換える → 不一致、かつ位置($TARGET_N件目)を正しく指す"
else
    fail "2. OUT の値を1つ書き換える → 不一致（報告位置=$reported, 期待=$TARGET_N, rc=$rc）"
    cat "$WORK/t2.out"
fi

# --- テスト3: OUT を1件削除する（末尾）→ 不一致「対象に足りない」 ---
awk -v n="$OUT_COUNT" '
    BEGIN{c=0}
    {
        if ($3=="main" && $4=="OUT") {
            c++
            if (c==n) next
        }
        print
    }
' OFS=' ' "$SEED" > "$WORK/t3.txt"
python3 "$CMP" "$SEED" "$WORK/t3.txt" >"$WORK/t3.out" 2>&1
rc=$?
if [[ $rc -eq 1 ]] && grep -q "対象に足りない" "$WORK/t3.out"; then
    pass "3. OUT を1件削除する → 不一致（「対象に足りない」）"
else
    fail "3. OUT を1件削除する → 不一致（「対象に足りない」） rc=$rc"
    cat "$WORK/t3.out"
fi

# --- テスト4: OUT を1件挿入する（末尾）→ 不一致「余分」 --------------
awk -v n="$OUT_COUNT" '
    BEGIN{c=0}
    {
        print
        if ($3=="main" && $4=="OUT") {
            c++
            if (c==n) { print "999999 999 main OUT 00FF AB FFFF" }
        }
    }
' OFS=' ' "$SEED" > "$WORK/t4.txt"
python3 "$CMP" "$SEED" "$WORK/t4.txt" >"$WORK/t4.out" 2>&1
rc=$?
if [[ $rc -eq 1 ]] && grep -q "余分" "$WORK/t4.out"; then
    pass "4. OUT を1件挿入する → 不一致（「余分」）"
else
    fail "4. OUT を1件挿入する → 不一致（「余分」） rc=$rc"
    cat "$WORK/t4.out"
fi

# --- テスト5: OUT を2件入れ替える → 不一致 -----------------------------
N1=100
N2=150
awk -v n1="$N1" -v n2="$N2" '
    BEGIN{c=0}
    {
        if ($3=="main" && $4=="OUT") {
            c++
            if (c==n1) { port1=$5; val1=$6 }
            if (c==n2) { port2=$5; val2=$6 }
        }
        line[NR]=$0
        cnt[NR]=($3=="main" && $4=="OUT") ? c : 0
    }
    END {
        for (i=1;i<=NR;i++) {
            $0=line[i]
            if (cnt[i]==n1) { $5=port2; $6=val2 }
            else if (cnt[i]==n2) { $5=port1; $6=val1 }
            print
        }
    }
' OFS=' ' "$SEED" > "$WORK/t5.txt"
python3 "$CMP" "$SEED" "$WORK/t5.txt" >"$WORK/t5.out" 2>&1
rc=$?
reported5="$(grep -oE '[0-9]+ 件目で食い違い' "$WORK/t5.out" | grep -oE '^[0-9]+')"
if [[ $rc -eq 1 ]] && [[ "$reported5" == "$N1" ]]; then
    pass "5. OUT を2件入れ替える → 不一致（最初の食い違い=$N1件目）"
else
    fail "5. OUT を2件入れ替える → 不一致（報告位置=$reported5, 期待=$N1, rc=$rc）"
    cat "$WORK/t5.out"
fi

# --- テスト6: 同一ポート連続 IN の回数だけ変える → 既定では一致 -------
# main 節、最初に現れる IN の直後にもう1行同じ IN を複製して回数を水増しする。
awk '
    BEGIN{done=0}
    {
        print
        if (!done && $3=="main" && $4=="IN") {
            print
            done=1
        }
    }
' "$SEED" > "$WORK/t6.txt"
python3 "$CMP" "$SEED" "$WORK/t6.txt" >"$WORK/t6.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]]; then
    pass "6. 同一ポート連続 IN の回数を変える → 既定モードでは一致のまま"
else
    fail "6. 同一ポート連続 IN の回数を変える → 既定モードでは一致のまま rc=$rc"
    cat "$WORK/t6.out"
fi

# --- テスト7: テスト6の入力を --with-in で比較しても一致 --------------
python3 "$CMP" "$SEED" "$WORK/t6.txt" --with-in >"$WORK/t7.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]]; then
    pass "7. 同上の入力を --with-in で比較しても一致（畳んでいるため）"
else
    fail "7. 同上の入力を --with-in で比較しても一致（畳んでいるため） rc=$rc"
    cat "$WORK/t7.out"
fi

# --- テスト8: --with-in で IN の最後の値を書き換える → 不一致 --------
# main 節で最初に現れる IN 行の値だけを変える（畳んだ後もその値が残るはず）。
awk '
    BEGIN{done=0}
    {
        if (!done && $3=="main" && $4=="IN") { $6="ZZ"; done=1 }
        print
    }
' OFS=' ' "$SEED" > "$WORK/t8.txt"
python3 "$CMP" "$SEED" "$WORK/t8.txt" --with-in >"$WORK/t8.out" 2>&1
rc=$?
if [[ $rc -eq 1 ]]; then
    pass "8. --with-in で IN の最後の値を書き換える → 不一致（畳んだ後も値を見ている）"
else
    fail "8. --with-in で IN の最後の値を書き換える → 不一致（畳んだ後も値を見ている） rc=$rc"
    cat "$WORK/t8.out"
fi

# --- テスト9: 空ファイル同士 → エラー（無言の「一致」にならない） ----
: > "$WORK/empty1.txt"
: > "$WORK/empty2.txt"
python3 "$CMP" "$WORK/empty1.txt" "$WORK/empty2.txt" >"$WORK/t9.out" 2>&1
rc=$?
if [[ $rc -eq 2 ]]; then
    pass "9. 空ファイル同士 → エラー（終了コード2、無言の一致にならない）"
else
    fail "9. 空ファイル同士 → エラー（終了コード2、無言の一致にならない） rc=$rc"
    cat "$WORK/t9.out"
fi

echo
if [[ $FAIL -eq 0 ]]; then
    echo "全項目 OK"
else
    echo "失敗した項目がある"
fi
exit $FAIL

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
SEED_GZ="$REPO_ROOT/measurements/l1-boot-io.iolog.txt.gz"

if [[ ! -f "$SEED_GZ" ]]; then
    echo "エラー: 種ファイルが無い: $SEED_GZ" >&2
    exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 2026-08-10、measurements/*.iolog.txt を gzip 化した（docs/notes/
# disclosure-2026-08-10.md）。cmp_io.py は .gz を透過的に読めるが、この
# スクリプトは以下で awk により種ファイルを直接改変して壊れ方のテストを
# 作るため、$WORK に展開した平文コピーを SEED として使う（リポジトリには
# 書き戻さない。$WORK は trap で削除される作業ディレクトリのみ）。
SEED="$WORK/seed.l1-boot-io.iolog.txt"
gunzip -c "$SEED_GZ" > "$SEED"

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

# =====================================================================
# 2段階判定（--init / --cycle）の検査
#
# 第6節の適合条件は「初期化 350 件の完全一致 ／ 以降 7 件周期・回数は問わない」
# の2段階。列全体を突き合わせる既定モードでは ② が扱えないので足した機能。
#
# **物差しの誤りは実装の誤りより見つけにくい**（仕様書 第6節の但し書き）。
# 以下は全て「わざと壊して落ちること」を確かめる形にしてある。
# =====================================================================
INIT_N=350
CYCLE_M=7

# 定常状態の 7 件（第3節・付録A 末尾）。挿入テストで使う。
CYCLE_LINES=(
    "999999 999 main OUT 0031 19 FFFF"
    "999999 999 main OUT 00E4 01 FFFF"
    "999999 999 main OUT 0051 81 FFFF"
    "999999 999 main OUT 0050 16 FFFF"
    "999999 999 main OUT 0050 01 FFFF"
    "999999 999 main OUT 00E4 FF FFFF"
    "999999 999 main OUT 0031 19 FFFF"
)

# --- テスト10: 種ファイル同士を2段階判定 → 一致 -----------------------
python3 "$CMP" "$SEED" "$WORK/t1.txt" --init $INIT_N --cycle $CYCLE_M >"$WORK/t10.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]] && grep -q "① 初期化区間 $INIT_N 件が完全一致" "$WORK/t10.out"; then
    pass "10. 2段階判定で同一ファイル同士 → 一致"
else
    fail "10. 2段階判定で同一ファイル同士 → 一致 rc=$rc"
    cat "$WORK/t10.out"
fi

# --- テスト11: 定常状態を1周ぶん延ばす → 一致（周回数を問わない）------
# これが通らないと、速い実装が「速いというだけで」不合格になる。
# 既定モードでは同じ入力が「余分」で不一致になることも併せて確かめる。
{
    awk -v n="$OUT_COUNT" 'BEGIN{c=0}
        { print
          if ($3=="main" && $4=="OUT") { c++; if (c==n) exit } }' "$SEED"
    printf '%s\n' "${CYCLE_LINES[@]}"
    awk -v n="$OUT_COUNT" 'BEGIN{c=0;p=0}
        { if (p) print
          if ($3=="main" && $4=="OUT") { c++; if (c==n) p=1 } }' "$SEED"
} > "$WORK/t11.txt"
python3 "$CMP" "$SEED" "$WORK/t11.txt" --init $INIT_N --cycle $CYCLE_M >"$WORK/t11.out" 2>&1
rc=$?
python3 "$CMP" "$SEED" "$WORK/t11.txt" >"$WORK/t11b.out" 2>&1
rc_default=$?
if [[ $rc -eq 0 ]] && [[ $rc_default -eq 1 ]] && grep -q "余分" "$WORK/t11b.out"; then
    pass "11. 定常状態を1周延ばす → 2段階では一致（既定モードでは「余分」で不一致）"
else
    fail "11. 定常状態を1周延ばす → 2段階では一致 rc=$rc / 既定 rc=$rc_default"
    cat "$WORK/t11.out"; cat "$WORK/t11b.out"
fi

# --- テスト12: 定常区間の値を1件書き換える → 不一致 -------------------
BREAK12=400   # 350 件目より後ろ = 定常区間
awk -v n="$BREAK12" 'BEGIN{c=0}
    { if ($3=="main" && $4=="OUT") { c++; if (c==n) $6="ZZ" } ; print }' \
    OFS=' ' "$SEED" > "$WORK/t12.txt"
python3 "$CMP" "$SEED" "$WORK/t12.txt" --init $INIT_N --cycle $CYCLE_M >"$WORK/t12.out" 2>&1
rc=$?
if [[ $rc -eq 1 ]] && grep -q "対象側: $BREAK12 件目が周期から外れる" "$WORK/t12.out"; then
    pass "12. 定常区間の値を1件書き換える → 不一致（$BREAK12 件目を正しく指す）"
else
    fail "12. 定常区間の値を1件書き換える → 不一致（$BREAK12 件目） rc=$rc"
    cat "$WORK/t12.out"
fi

# --- テスト13: 初期化区間の値を1件書き換える → ① で不一致 ------------
BREAK13=200   # 350 件目より前 = 初期化区間
awk -v n="$BREAK13" 'BEGIN{c=0}
    { if ($3=="main" && $4=="OUT") { c++; if (c==n) $6="ZZ" } ; print }' \
    OFS=' ' "$SEED" > "$WORK/t13.txt"
python3 "$CMP" "$SEED" "$WORK/t13.txt" --init $INIT_N --cycle $CYCLE_M >"$WORK/t13.out" 2>&1
rc=$?
reported13="$(grep -oE '[0-9]+ 件目で食い違い' "$WORK/t13.out" | grep -oE '^[0-9]+')"
if [[ $rc -eq 1 ]] && [[ "$reported13" == "$BREAK13" ]] && grep -q "① 初期化区間" "$WORK/t13.out"; then
    pass "13. 初期化区間の値を1件書き換える → ① で不一致（$BREAK13 件目）"
else
    fail "13. 初期化区間の値を1件書き換える → ① で不一致（報告位置=$reported13, rc=$rc）"
    cat "$WORK/t13.out"
fi

# --- テスト14: 定常状態が1周も無い → 不一致 ---------------------------
# 「初期化までは合っているが定常状態に入る前に落ちた」記録を
# 黙って通さないこと。周期の端数を許す実装なので、ここは明示的に検査する。
TRUNC=$((INIT_N + CYCLE_M - 1))
awk -v n="$TRUNC" 'BEGIN{c=0}
    { if ($3=="main" && $4=="OUT") { c++; if (c>n) next } ; print }' \
    OFS=' ' "$SEED" > "$WORK/t14.txt"
python3 "$CMP" "$SEED" "$WORK/t14.txt" --init $INIT_N --cycle $CYCLE_M >"$WORK/t14.out" 2>&1
rc=$?
if [[ $rc -eq 1 ]] && grep -q "対象側: 定常状態が 1 周も回っていない" "$WORK/t14.out"; then
    pass "14. 定常状態が1周も無い（$TRUNC 件で打ち切り）→ 不一致"
else
    fail "14. 定常状態が1周も無い（$TRUNC 件で打ち切り）→ 不一致 rc=$rc"
    cat "$WORK/t14.out"
fi

# --- テスト15: --init と --cycle の片方だけ → 使い方の誤り ------------
python3 "$CMP" "$SEED" "$WORK/t1.txt" --init $INIT_N >"$WORK/t15.out" 2>&1
rc=$?
if [[ $rc -eq 2 ]]; then
    pass "15. --init だけ指定 → 使い方の誤り（終了コード2）"
else
    fail "15. --init だけ指定 → 使い方の誤り（終了コード2） rc=$rc"
    cat "$WORK/t15.out"
fi

# =====================================================================
# 条件③（第3版・第6節）の検査
#
# 「定常状態（初期化 N 件目より後）に IN 40 が現れないこと」。
# VRTC ポーリングで組んだ実装は①②を満たしたまま③で落ちる、というのが
# 仕様書の狙いなので、③ を検出できない物差しを足しても意味がない。
# **わざと壊して落ちることを確認する。**
# =====================================================================

# --- テスト16: 定常状態に IN 40 を1件挿入する → ③ で不一致 ------------
# 350件目の OUT の直後（定常状態の入口）に IN 0040 を割り込ませる。
awk -v n="$INIT_N" 'BEGIN{c=0}
    { print
      if ($3=="main" && $4=="OUT") {
          c++
          if (c==n) print "999999 999 main IN 0040 CC FFFF"
      } }' "$SEED" > "$WORK/t16.txt"
python3 "$CMP" "$SEED" "$WORK/t16.txt" --init $INIT_N --cycle $CYCLE_M >"$WORK/t16.out" 2>&1
rc=$?
if [[ $rc -eq 1 ]] && grep -q "IN 40 が現れる" "$WORK/t16.out"; then
    pass "16. 定常状態に IN 40 を挿入 → ③ で不一致"
else
    fail "16. 定常状態に IN 40 を挿入 → ③ で不一致 rc=$rc"
    cat "$WORK/t16.out"
fi

# --- テスト17: 初期化区間（350件目より前）に IN 40 を挿入 → 一致のまま -
# P2 の VRTC ポーリングは初期化区間の話であり、③ の対象外
# （境目より前は検査しない）。①②に影響しないことも併せて確認する。
awk 'BEGIN{c=0}
    { print
      if ($3=="main" && $4=="OUT") {
          c++
          if (c==200) print "999999 999 main IN 0040 CC FFFF"
      } }' "$SEED" > "$WORK/t17.txt"
python3 "$CMP" "$SEED" "$WORK/t17.txt" --init $INIT_N --cycle $CYCLE_M >"$WORK/t17.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]]; then
    pass "17. 初期化区間に IN 40 を挿入 → ③ の対象外なので一致のまま"
else
    fail "17. 初期化区間に IN 40 を挿入 → ③ の対象外なので一致のまま rc=$rc"
    cat "$WORK/t17.out"
fi

# --- テスト18: 定常状態に IN 40 が無ければ ③ も含めて一致すると明示する -
# 種ファイル同士（t1.txt）は VSYNC 割り込み駆動の公式版そのものなので、
# ③ の一致メッセージが出ることを確認する（10番の再確認だが③の文言を見る）。
python3 "$CMP" "$SEED" "$WORK/t1.txt" --init $INIT_N --cycle $CYCLE_M >"$WORK/t18.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]] && grep -q "IN 40 なし" "$WORK/t18.out"; then
    pass "18. 種ファイル同士 → ③ も含めて一致（IN 40 なしのメッセージが出る）"
else
    fail "18. 種ファイル同士 → ③ も含めて一致（IN 40 なしのメッセージが出る） rc=$rc"
    cat "$WORK/t18.out"
fi

# =====================================================================
# 8列形式（共通クロック列つき）のパース検査
#
# docs/notes/m6-conformance.md の経緯: 0010-shared-clock.patch 導入後の
# ログは「seq clock frame cpu kind port value pc」の8列だが、当初の
# cmp_io.py は7列決め打ちで、m6c以降のログを一度も読めていなかった
# （未検出のまま放置されていた）。8列対応を足したので、そのことを
# わざと壊して検出する形で確かめる。
# =====================================================================
SEED2_GZ="$REPO_ROOT/measurements/m6g-d0-boot-run1.iolog.txt.gz"
if [[ ! -f "$SEED2_GZ" ]]; then
    echo "エラー: 8列形式の種ファイルが無い: $SEED2_GZ" >&2
    exit 2
fi
# SEED と同じ理由でWORKに展開した平文コピーを使う。このファイルは
# データポート($FB/$FC/$FD)を伏せ字済みなので、展開しても実データは
# 出てこない（伏せ字は redact_iolog.py が既に恒久適用している）。
SEED2="$WORK/seed2.m6g-d0-boot-run1.iolog.txt"
gunzip -c "$SEED2_GZ" > "$SEED2"
# main節・OUT行の総数（8列形式は $4=cpu $5=kind）
OUT_COUNT2="$(awk '$4=="main" && $5=="OUT" {c++} END{print c+0}' "$SEED2")"
if [[ "$OUT_COUNT2" -lt 3 ]]; then
    echo "エラー: 8列形式の種ファイルのOUT件数が少なすぎる（$OUT_COUNT2）" >&2
    exit 2
fi

# --- テスト19: 8列形式の同一ファイル同士（既定モード） → 一致 --------
cp "$SEED2" "$WORK/t19.txt"
python3 "$CMP" "$SEED2" "$WORK/t19.txt" --cpu main >"$WORK/t19.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]]; then
    pass "19. 8列形式(clock列つき)の同一ファイル同士 → 一致"
else
    fail "19. 8列形式(clock列つき)の同一ファイル同士 → 一致 rc=$rc"
    cat "$WORK/t19.out"
fi

# --- テスト20: clock列だけを全行ずらす → 比較には影響しない（一致のまま）
# clock は比較（port/value/kind）に使っていないので、値がずれていても
# 一致と判定されるはずである。ここが逆に落ちたら「clockを誤って
# 比較に使ってしまっている」というバグの検出になる。
awk 'BEGIN{OFS=" "}
    /^[0-9]/ && NF==8 { $2 = $2+999999 }
    { print }' "$SEED2" > "$WORK/t20.txt"
python3 "$CMP" "$SEED2" "$WORK/t20.txt" --cpu main >"$WORK/t20.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]]; then
    pass "20. clock列だけをずらす → 比較には無関係なので一致のまま"
else
    fail "20. clock列だけをずらす → 比較には無関係なので一致のまま rc=$rc"
    cat "$WORK/t20.out"
fi

# --- テスト21: 列数が9（壊れた行）→ 使い方の誤り（パースエラー） -----
awk 'NR==30 && NF==8 { print $0, "EXTRA"; next } { print }' "$SEED2" > "$WORK/t21.txt"
python3 "$CMP" "$SEED2" "$WORK/t21.txt" --cpu main >"$WORK/t21.out" 2>&1
rc=$?
if [[ $rc -eq 2 ]] && grep -q "列数が7でも8でもない" "$WORK/t21.out"; then
    pass "21. 列数が9の壊れた行 → パースエラー（終了コード2）"
else
    fail "21. 列数が9の壊れた行 → パースエラー（終了コード2） rc=$rc"
    cat "$WORK/t21.out"
fi

# =====================================================================
# --port/--kind（M6用の非周期・完全一致モード）の検査
#
# docs/spec/l3-subrom.md 5.3節: L1の「初期化N件＋周期M件」という型は
# M6のsub側バースト（一回限り・非周期）には当てはまらない。
# 「特定ポート・特定方向の列を丸ごと完全一致で見る」という条件を
# tools/cmp_io.py --port/--kind として足したので、わざと壊して検査する。
# =====================================================================

# --- テスト22: main の IN 00FD 列、同一ファイル同士 → 一致 -----------
python3 "$CMP" "$SEED2" "$WORK/t19.txt" --cpu main --port FD --kind IN >"$WORK/t22.out" 2>&1
rc=$?
if [[ $rc -eq 0 ]] && grep -q "一致" "$WORK/t22.out"; then
    pass "22. --port FD --kind IN、同一ファイル同士 → 一致"
else
    fail "22. --port FD --kind IN、同一ファイル同士 → 一致 rc=$rc"
    cat "$WORK/t22.out"
fi

# --- テスト23: IN 00FD の値を1件書き換える → 不一致 -------------------
# 8列形式: $4=cpu $5=kind $6=port $7=value
awk 'BEGIN{OFS=" "; c=0}
    { if ($4=="main" && $5=="IN" && $6=="00FD") { c++; if (c==3) $7="ZZ" }
      print }' "$SEED2" > "$WORK/t23.txt"
python3 "$CMP" "$SEED2" "$WORK/t23.txt" --cpu main --port FD --kind IN >"$WORK/t23.out" 2>&1
rc=$?
if [[ $rc -eq 1 ]] && grep -q "値が違う" "$WORK/t23.out"; then
    pass "23. IN 00FD の値を1件書き換える → --port/--kind で不一致検出"
else
    fail "23. IN 00FD の値を1件書き換える → --port/--kind で不一致検出 rc=$rc"
    cat "$WORK/t23.out"
fi

# --- テスト24: IN 00FD を1件削除する → 不一致「対象に足りない」 ------
awk -v n="9999999" 'BEGIN{OFS=" "; c=0; skip=-1}
    { if ($4=="main" && $5=="IN" && $6=="00FD") { c++ } }
    { if ($4=="main" && $5=="IN" && $6=="00FD" && c==3) next; print }' "$SEED2" > "$WORK/t24.txt"
python3 "$CMP" "$SEED2" "$WORK/t24.txt" --cpu main --port FD --kind IN >"$WORK/t24.out" 2>&1
rc=$?
if [[ $rc -eq 1 ]] && grep -q "対象に足りない\|値が違う" "$WORK/t24.out"; then
    pass "24. IN 00FD を1件削除する → --port/--kind で不一致検出"
else
    fail "24. IN 00FD を1件削除する → --port/--kind で不一致検出 rc=$rc"
    cat "$WORK/t24.out"
fi

# --- テスト25: --port だけ指定（--kind なし）→ 使い方の誤り ----------
python3 "$CMP" "$SEED2" "$WORK/t19.txt" --port FD >"$WORK/t25.out" 2>&1
rc=$?
if [[ $rc -eq 2 ]]; then
    pass "25. --port だけ指定 → 使い方の誤り（終了コード2）"
else
    fail "25. --port だけ指定 → 使い方の誤り（終了コード2） rc=$rc"
    cat "$WORK/t25.out"
fi

# --- テスト26: --port/--kind と --init/--cycle の併用 → 使い方の誤り --
python3 "$CMP" "$SEED2" "$WORK/t19.txt" --port FD --kind IN --init 10 --cycle 2 >"$WORK/t26.out" 2>&1
rc=$?
if [[ $rc -eq 2 ]]; then
    pass "26. --port/--kind と --init/--cycle の併用 → 使い方の誤り（終了コード2）"
else
    fail "26. --port/--kind と --init/--cycle の併用 → 使い方の誤り（終了コード2） rc=$rc"
    cat "$WORK/t26.out"
fi

echo
if [[ $FAIL -eq 0 ]]; then
    echo "全項目 OK"
else
    echo "失敗した項目がある"
fi
exit $FAIL

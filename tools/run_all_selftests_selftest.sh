#!/usr/bin/env bash
# tools/run_all_selftests_selftest.sh — tools/run_all_selftests.sh 自体の
# 検出力を確認する selftest。
#
# CLAUDE.md / docs/notes の方針どおり、「検査を足す」だけでは足りない。
# 検査が落ちたときに全体(ラッパのrc)が落ちることまで確認する。
# 2026-08-11 の欠陥（check_cleanroom.sh がNGのままラッパがrc=0で完走し、
# NGのままcommit 85374baがpushされた）の再発を防ぐための自己検査。
#
# 手口は既存のselftest群(tools/cmp_io_selftest.sh 等)と同じ:
# 作業用ディレクトリにダミースクリプトと、SCRIPTS_EXPECTED配列だけを
# 書き換えた run_all_selftests.sh のコピーを作り、期待どおりの
# rc になるかを確認する。追跡ファイルは変更しない。
#
# 検査項目:
#   f-1. 必ず失敗するダミーを足すと、ラッパはNG(rc=1)を返す
#   f-2. 必ず成功するダミーを足すと、ラッパはOK(rc=0)を返す
#   f-3. rc=1が正常(既知の未達成)なダミーを「期待rc=1」で宣言すると、
#        ラッパはOK(rc=0)を返す(想定内の失敗として扱われる)
#   f-4. 同じダミー(rc=1)を「期待rc=0」で誤って宣言すると、
#        ラッパはNG(rc=1)を返す(宣言と実際の食い違いを検出する)
#   f-5. conform_l3.shが公式本体をSKIPした場合、OKでなくSKIPと表示する
#   f-6. m6f-c: PC88_SELFTEST_EXCLUDE で指定した(登録済みの)ダミーは
#        実行されず、rcに影響しない(必ず失敗するダミーを除外するとOK)
#   f-7. m6f-c: PC88_SELFTEST_EXCLUDE に登録に無い名前を指定すると、
#        その名前がNGとして表に出てラッパはNG(rc=1)を返す
#        (打ち間違いで黙って通らないことの確認。陰性対照: 除外なしなら
#        同じダミー構成でOKになることも確認する)
#
# f-6・f-7 は make_variant が複数エントリの置換で使うawk実装（BWK awk）が
# -v の値に埋め込み改行を含めると失敗する制約があるため、既存のf-1〜f-5と
# 同じ「1エントリだけのvariant」を使い、環境変数だけで挙動を切り替える
# 軽い方法で検査する（本体を丸ごと回す必要はない）。
#
# 使い方: tools/run_all_selftests_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

# m6f-c: このselftest自身が「PC88_SELFTEST_EXCLUDE付きのrun_all_selftests.sh」
# から呼ばれると、環境変数がそのまま子プロセスへ継承されてしまう。以下の
# variant群は登録がDUMMY_*だけの小さな配列なので、継承された除外名
# （例: tools/harness/disk2_selftest.sh）が「登録に無い」としてNG化し、
# 本来rc=0になるべきf-2/f-3/f-5や、f-7の陰性対照(除外なし)が偽のNGになる
# （2026-09-24 実測、run_all_selftests.sh本体からの入れ子実行で発覚）。
# この selftest はその継承を受けない前提で書くので、ここで明示的に切る。
unset PC88_SELFTEST_EXCLUDE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="$SCRIPT_DIR/run_all_selftests.sh"

if [[ ! -f "$TARGET" ]]; then
    echo "エラー: 対象が無い: $TARGET" >&2
    exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail=0
pass() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()   { printf '  \033[31mNG\033[0m   %s\n' "$1"; fail=$((fail+1)); }

# --- ダミースクリプト群 --------------------------------------------------
DUMMY_FAIL="$WORK/dummy_fail.sh"
cat > "$DUMMY_FAIL" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$DUMMY_FAIL"

DUMMY_PASS="$WORK/dummy_pass.sh"
cat > "$DUMMY_PASS" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$DUMMY_PASS"

# 「必ず両ロケールでrc=1になる」ダミー(verify_l3.sh の代役)。
DUMMY_KNOWN_FAIL="$WORK/dummy_known_fail.sh"
cat > "$DUMMY_KNOWN_FAIL" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$DUMMY_KNOWN_FAIL"

mkdir -p "$WORK/tools"
DUMMY_CONFORM="$WORK/tools/conform_l3.sh"
cat > "$DUMMY_CONFORM" <<'EOF'
#!/usr/bin/env bash
echo '  SKIP: 公式ROM・公式ディスクの環境変数が未設定。'
exit 0
EOF
chmod +x "$DUMMY_CONFORM"

# --- 対象スクリプトの SCRIPTS_EXPECTED 配列だけを置き換えたコピーを作る --
# awk で "SCRIPTS_EXPECTED=(" ～ 対応する ")" の区間を丸ごと差し替える。
make_variant() {
    local out="$1"; shift
    local entries=("$@")
    awk -v repl="$(printf '  "%s"\n' "${entries[@]}")" '
        /^SCRIPTS_EXPECTED=\($/ { print "SCRIPTS_EXPECTED=("; print repl; skip=1; next }
        skip && /^\)$/ { print ")"; skip=0; next }
        skip { next }
        { print }
    ' "$TARGET" > "$out"
}

run_variant() {
    # 出力(値の列を含む可能性はないが念のため)は捨て、rcだけ見る。
    bash "$1" >/dev/null 2>&1
    echo $?
}

# f-1: 必ず失敗するダミーだけを足す → ラッパはNG
V1="$WORK/variant_fail.sh"
make_variant "$V1" "$DUMMY_FAIL:0"
rc1="$(run_variant "$V1")"
if [[ "$rc1" == "1" ]]; then
    pass "f-1. 必ず失敗するダミーを足すとラッパがNG(rc=1)を返した(=検出力あり)"
else
    ng "f-1. 必ず失敗するダミーを足したのにラッパがrc=$rc1(NGを検出できていない)"
fi

# f-5: 本体SKIPはrc=0でもOKと表示しない
V5="$WORK/variant_conform_skip.sh"
make_variant "$V5" "$DUMMY_CONFORM:0"
out5="$(bash "$V5" 2>&1)"; rc5=$?
if [[ "$rc5" == "0" ]] && grep -q 'SKIP(公式環境なし。本体未実行' <<<"$out5" \
   && ! grep "$DUMMY_CONFORM" <<<"$out5" | grep -q ' OK$'; then
    pass "f-5. 公式本体未実行はOKでなくSKIPと表示された"
else
    ng "f-5. 公式本体SKIPが結果表で識別できない(rc=$rc5)"
fi

# f-2: 必ず成功するダミーだけを足す → ラッパはOK
V2="$WORK/variant_pass.sh"
make_variant "$V2" "$DUMMY_PASS:0"
rc2="$(run_variant "$V2")"
if [[ "$rc2" == "0" ]]; then
    pass "f-2. 必ず成功するダミーを足すとラッパがOK(rc=0)を返した"
else
    ng "f-2. 必ず成功するダミーだけなのにラッパがrc=$rc2(誤検出)"
fi

# f-3: rc=1が正常なダミーを「期待rc=1」で宣言 → ラッパはOK(想定内の失敗)
V3="$WORK/variant_known_fail_declared_1.sh"
make_variant "$V3" "$DUMMY_KNOWN_FAIL:1"
rc3="$(run_variant "$V3")"
if [[ "$rc3" == "0" ]]; then
    pass "f-3. 期待rc=1と正しく宣言したダミー(実際rc=1)でラッパがOK(想定内の失敗として扱えた)"
else
    ng "f-3. 期待rc=1と宣言したのにラッパがrc=$rc3(想定内の失敗を扱えていない)"
fi

# f-4: 同じダミーを「期待rc=0」で誤って宣言 → ラッパはNG(食い違いを検出)
V4="$WORK/variant_known_fail_declared_0.sh"
make_variant "$V4" "$DUMMY_KNOWN_FAIL:0"
rc4="$(run_variant "$V4")"
if [[ "$rc4" == "1" ]]; then
    pass "f-4. 期待rc=0と誤って宣言したダミー(実際rc=1)でラッパがNGを返した(宣言と実際の食い違いを検出できた)"
else
    ng "f-4. 期待rcを実際と違えて宣言したのにラッパがrc=$rc4(食い違いを検出できていない)"
fi

# f-6: 必ず失敗するダミー1本を「除外」して実行 → ラッパはOK(rc=0)
V6="$WORK/variant_excluded_fail.sh"
make_variant "$V6" "$DUMMY_FAIL:0"
rc6_excluded="$(PC88_SELFTEST_EXCLUDE="$DUMMY_FAIL" bash "$V6" >/dev/null 2>&1; echo $?)"
rc6_included="$(bash "$V6" >/dev/null 2>&1; echo $?)"
if [[ "$rc6_excluded" == "0" ]] && [[ "$rc6_included" == "1" ]]; then
    pass "f-6. 除外指定したダミー(必ず失敗)は実行されずラッパがOK(rc=0)を返した(除外なしではNGになることも確認済み)"
else
    ng "f-6. 除外指定の効果を確認できない(除外時rc=${rc6_excluded}、除外なしrc=${rc6_included})"
fi

# f-7: PC88_SELFTEST_EXCLUDE に登録に無い名前を指定 → ラッパはNG(rc=1)。
# 陰性対照として、除外なし(同じ構成、必ず成功するダミーのみ)ならOKになる
# ことも確認する。
V7="$WORK/variant_unknown_exclude.sh"
make_variant "$V7" "$DUMMY_PASS:0"
UNKNOWN_NAME="$WORK/tools/not_registered_selftest.sh"
rc7_unknown="$(PC88_SELFTEST_EXCLUDE="$UNKNOWN_NAME" bash "$V7" >/dev/null 2>&1; echo $?)"
out7_unknown="$(PC88_SELFTEST_EXCLUDE="$UNKNOWN_NAME" bash "$V7" 2>&1)"
rc7_none="$(bash "$V7" >/dev/null 2>&1; echo $?)"
if [[ "$rc7_unknown" == "1" ]] && grep -q "NG(除外指定が登録に無い)" <<<"$out7_unknown" \
   && [[ "$rc7_none" == "0" ]]; then
    pass "f-7. 登録に無い除外名を指定するとNGとして表に出てラッパがNG(rc=1)を返した(陰性対照: 除外なしはOK)"
else
    ng "f-7. 登録に無い除外名の検出ができない(除外指定時rc=${rc7_unknown}、陰性対照rc=${rc7_none})"
fi

echo
if [[ "$fail" -eq 0 ]]; then
    echo "全項目 OK"
    exit 0
else
    echo "$fail 件 NG"
    exit 1
fi

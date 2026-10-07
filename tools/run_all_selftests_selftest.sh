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

# ===========================================================================
# 入力キャッシュ・ロケール絞り込み・静的検査（2026-10-07）
# 本物の228本ではなく、偽のリポジトリ($FK)に小さな偽スクリプトを置いて検査する。
# 偽リポジトリの tools/ には本物の run_all_selftests.sh（登録表だけ差し替えた
# コピー）・runall_cache.py・runall_hook を複製する。キャッシュも専用の場所。
#   g-1. 何も変えずに2回: 2回目は合格したものが全部 CACHED になる
#   g-2. 前回NGにした検査(必ず失敗する偽)は次回も必ず実行される（CACHEDにならない）
#   g-3. src/a の1ファイルに意味のない1バイト(コメント)を足す → それを読む検査
#        だけ再実行され、読まない検査(src/b だけ・何も読まない)は CACHED のまま
#   g-4. 再実行は UTF-8 だけの1ロケール（スクリプト本文が不変のとき）
#   g-5. tools/ の1ファイルを変える → 全部再実行
#   g-6. シェルが src を直接読む検査は、どの src 変更でも再実行される(安全側)
#        / PYTHONPATH を触る検査も安全側(src 全体依存)
#   g-7. 依存記録が壊れた/消えた(python 起動記録なし) → 安全側(src全体)で再実行
#   g-8. スクリプト本文を変える → その検査だけ2ロケール
#   g-9. $var 直後の全角文字を入れた偽スクリプト → 静的検査が NG（陰性対照: 直すとOK）
#   g-10. --no-cache は全部を2ロケールで実行する
#   g-11. 環境変数(PC88_REF_*)の指す内容が変わったら再実行される
# ===========================================================================
FK="$WORK/fk"
CACHE="$WORK/fk-cache"
mkdir -p "$FK/tools/runall_hook" "$FK/src/a" "$FK/src/b" "$FK/tests"
cp "$SCRIPT_DIR/runall_cache.py" "$FK/tools/runall_cache.py"
cp "$SCRIPT_DIR/runall_hook/sitecustomize.py" "$FK/tools/runall_hook/sitecustomize.py"
echo "alpha" > "$FK/src/a/x.txt"
echo "beta"  > "$FK/src/b/y.txt"

mk_py_script() {  # $1=名前 $2=読むsrcファイル(相対) $3=終了コード
    cat > "$FK/tools/$1" <<EOF
#!/usr/bin/env bash
REPO="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "\$REPO" <<'PY'
import sys
open(sys.argv[1] + "/$2").read()
PY
exit $3
EOF
}
mk_py_script t_a.sh   src/a/x.txt 0
mk_py_script t_b.sh   src/b/y.txt 0
mk_py_script t_fail.sh src/a/x.txt 1
printf '#!/usr/bin/env bash\nexit 0\n' > "$FK/tools/t_pure.sh"
cat > "$FK/tools/t_shell.sh" <<'EOF'
#!/usr/bin/env bash
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRCDIR="$REPO/src/b"
cat "$SRCDIR"/* > /dev/null
exit 0
EOF
cat > "$FK/tools/t_pp.sh" <<'EOF'
#!/usr/bin/env bash
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$REPO/tools" python3 -c "open('$REPO/src/a/x.txt').read()"
exit 0
EOF
cat > "$FK/tools/t_env.sh" <<'EOF'
#!/usr/bin/env bash
test -n "${PC88_REF_ROM_DIR:-}" && ls "$PC88_REF_ROM_DIR" >/dev/null
exit 0
EOF

# 登録表を差し替えた run_all_selftests.sh を $FK/tools に作る（python で置換）
fk_variant() {
    python3 - "$TARGET" "$FK/tools/run_all_selftests.sh" "$@" <<'PY'
import re, sys
src, dst, *entries = sys.argv[1:]
t = open(src).read()
body = "".join('  "%s"\n' % e for e in entries)
t = re.sub(r"(?ms)^SCRIPTS_EXPECTED=\(\n.*?^\)\n", "SCRIPTS_EXPECTED=(\n" + body + ")\n", t, count=1)
open(dst, "w").write(t)
PY
}
fk_run() {  # 引数: ラッパへのオプション。出力は $WORK/fk.out、rc を返す
    ( cd "$FK" && PC88_RUNALL_CACHE_DIR="$CACHE" bash tools/run_all_selftests.sh "$@" ) > "$WORK/fk.out" 2>&1
}
row() {  # $1=スクリプト名: その行
    grep -F "tools/$1 " "$WORK/fk.out" | head -1
}
exec_of() { row "$1" | grep -oE 'CACHED|2ロケール|UTF-8のみ' | head -1; }
unset PC88_REF_ROM_DIR PC88_REF_DISK_DIR PC88_REF_DISKB PC88_ERROR_RESPONSE_OPT_IN 2>/dev/null || true

fk_variant "tools/t_a.sh:0" "tools/t_b.sh:0" "tools/t_pure.sh:0" "tools/t_shell.sh:0" "tools/t_pp.sh:0"
fk_run; rc_g1=$?
ok1=1
for n in t_a.sh t_b.sh t_pure.sh t_shell.sh t_pp.sh; do
    [[ "$(exec_of $n)" == "2ロケール" ]] || ok1=0
done
fk_run; rc_g1b=$?
ok1b=1
for n in t_a.sh t_b.sh t_pure.sh t_shell.sh t_pp.sh; do
    [[ "$(exec_of $n)" == "CACHED" ]] || ok1b=0
done
if [[ $rc_g1 == 0 && $rc_g1b == 0 && $ok1 == 1 && $ok1b == 1 ]]; then
    pass "g-1. 何も変えずに2回: 1回目は全部実行、2回目は全部 CACHED（rc=0）"
else
    ng "g-1. キャッシュの再利用が期待どおりでない(rc=$rc_g1/$rc_g1b 初回=$ok1 2回目=$ok1b)"; sed 's/^/      /' "$WORK/fk.out" | head -20
fi

# g-2: 必ず失敗する偽は何度でも実行される
fk_variant "tools/t_a.sh:0" "tools/t_fail.sh:0"
fk_run; fk_run; rc_g2=$?
if [[ "$rc_g2" == "1" && "$(exec_of t_fail.sh)" != "CACHED" && -n "$(exec_of t_fail.sh)" && "$(exec_of t_a.sh)" == "CACHED" ]]; then
    pass "g-2. 前回NGの検査(必ず失敗する偽)は2回目も実行され、NGのまま(合格のa.shはCACHED)"
else
    ng "g-2. NGの検査の扱いが想定と違う(rc=$rc_g2 fail=$(exec_of t_fail.sh) a=$(exec_of t_a.sh))"; sed 's/^/      /' "$WORK/fk.out" | head -12
fi

# g-3/g-4/g-6: src/a に意味のないコメントを足す
fk_variant "tools/t_a.sh:0" "tools/t_b.sh:0" "tools/t_pure.sh:0" "tools/t_shell.sh:0" "tools/t_pp.sh:0"
fk_run
echo "# 意味のないコメント" >> "$FK/src/a/x.txt"
fk_run; rc_g3=$?
if [[ "$(exec_of t_a.sh)" == "UTF-8のみ" && "$(exec_of t_b.sh)" == "CACHED" \
   && "$(exec_of t_pure.sh)" == "CACHED" && "$(exec_of t_shell.sh)" != "CACHED" ]]; then
    pass "g-3. src/a の1ファイルにコメントを足すと、それを読む検査(と、src を直接読むため安全側に倒れる shell 検査)だけ再実行され、読まない検査(b・何も読まない)は CACHED のまま"
else
    ng "g-3. 再実行の範囲が想定と違う: a=$(exec_of t_a.sh) b=$(exec_of t_b.sh) pure=$(exec_of t_pure.sh) shell=$(exec_of t_shell.sh)"; sed 's/^/      /' "$WORK/fk.out" | head -12
fi
# g-4: その再実行は UTF-8 の1ロケール（t_a.sh の本文が不変）
if [[ "$(exec_of t_a.sh)" == "UTF-8のみ" ]]; then
    pass "g-4. 本文が前回の2ロケール合格時と同じ検査の再実行は UTF-8 の1ロケールだけ"
else
    ng "g-4. 再実行が UTF-8 のみになっていない: $(exec_of t_a.sh)"
fi
# g-6: src を直接読むシェル(t_shell)・PYTHONPATH を触る(t_pp)は安全側
echo "# 意味のない" >> "$FK/src/b/y.txt"
fk_run
if [[ "$(exec_of t_shell.sh)" != "CACHED" && -n "$(exec_of t_shell.sh)" \
   && "$(exec_of t_pp.sh)" != "CACHED" && -n "$(exec_of t_pp.sh)" \
   && "$(exec_of t_b.sh)" != "CACHED" && "$(exec_of t_pure.sh)" == "CACHED" ]]; then
    pass "g-6. シェルが src を直接読む検査・PYTHONPATH を触る検査は、読まないはずの src 変更でも再実行される(安全側)"
else
    ng "g-6. 安全側の再実行になっていない: shell=$(exec_of t_shell.sh) pp=$(exec_of t_pp.sh) b=$(exec_of t_b.sh) pure=$(exec_of t_pure.sh)"; sed 's/^/      /' "$WORK/fk.out" | head -12
fi

# g-7: 依存記録が壊れた(python の起動記録が無い) → 安全側。ヘルパを直接叩いて確かめる
fk_variant "tools/t_a.sh:0"
fk_run
PF="$WORK/g7.plan.json"
( cd "$FK" && PC88_RUNALL_CACHE_DIR="$CACHE" python3 tools/runall_cache.py plan tools/t_a.sh --plan-file "$PF" --no-lookup >/dev/null \
  && PC88_RUNALL_CACHE_DIR="$CACHE" python3 tools/runall_cache.py record --plan-file "$PF" --status pass --mode both --logs /dev/null >/dev/null )
ent_mode="$(python3 - "$CACHE" <<'PY'
import glob, json, sys
for p in glob.glob(sys.argv[1] + "/e-*.json"):
    e = json.load(open(p))
    if e["script"] == "tools/t_a.sh":
        print(e["dep_mode"])
PY
)"
echo "# もう1行" >> "$FK/src/b/y.txt"   # t_a.sh は src/b を読まない。記録が正常なら CACHED のまま
fk_run
r_full="$(exec_of t_a.sh)"
if [[ "$ent_mode" == "full" && "$r_full" != "CACHED" && -n "$r_full" ]]; then
    pass "g-7. python の起動記録が無い(依存記録が壊れた)と dep=full になり、読まないはずの src 変更でも再実行される(安全側)"
else
    ng "g-7. 壊れた依存記録の扱いが想定と違う(dep_mode=$ent_mode 再実行=$r_full)"
fi
# 陰性対照: 正常な記録なら同じ src/b 変更で t_a.sh は再実行されない
fk_run                                # 直前の実行で正常な記録に戻っている
echo "# もう1行" >> "$FK/src/b/y.txt"
fk_run
if [[ "$(exec_of t_a.sh)" == "CACHED" ]]; then
    pass "g-7'. (陰性対照)正常な記録なら同じ src/b 変更で t_a.sh は CACHED のまま"
else
    ng "g-7'. 陰性対照が成立しない: t_a=$(exec_of t_a.sh)"
fi

# g-5: tools/ の1ファイル(検査と無関係な付属ファイル)を変える → 全部再実行
fk_variant "tools/t_a.sh:0" "tools/t_b.sh:0" "tools/t_pure.sh:0" "tools/t_shell.sh:0" "tools/t_pp.sh:0"
fk_run
echo "x" >> "$FK/tools/unrelated.txt"
fk_run
ok5=1
for n in t_a.sh t_b.sh t_pure.sh t_shell.sh t_pp.sh; do
    e="$(exec_of $n)"; [[ -n "$e" && "$e" != "CACHED" ]] || ok5=0
done
if [[ $ok5 == 1 ]]; then
    pass "g-5. tools/ の1ファイルを変えると全部再実行される(本文が不変の検査は UTF-8 のみ)"
else
    ng "g-5. tools/ の変更で全部が再実行されていない"; sed 's/^/      /' "$WORK/fk.out" | head -12
fi

# g-8: スクリプト本文を変える → その検査だけ2ロケール
fk_run
echo "# 本文を変更" >> "$FK/tools/t_a.sh"
fk_run
if [[ "$(exec_of t_a.sh)" == "2ロケール" && "$(exec_of t_b.sh)" == "UTF-8のみ" ]]; then
    pass "g-8. スクリプト本文を変えた検査だけ2ロケール、他は UTF-8 のみ"
else
    ng "g-8. 2ロケールの条件が想定と違う: a=$(exec_of t_a.sh) b=$(exec_of t_b.sh)"
fi

# g-10: --no-cache は全部を2ロケールで実行する
fk_run --no-cache
ok10=1
for n in t_a.sh t_b.sh t_pure.sh t_shell.sh t_pp.sh; do [[ "$(exec_of $n)" == "2ロケール" ]] || ok10=0; done
if [[ $ok10 == 1 ]]; then
    pass "g-10. --no-cache は全部を2ロケールで実行した"
else
    ng "g-10. --no-cache の挙動が想定と違う"
fi

# g-11: 環境変数(PC88_REF_ROM_DIR)の指す内容が変わると再実行される
mkdir -p "$WORK/refrom"; echo one > "$WORK/refrom/f"
fk_variant "tools/t_env.sh:0" "tools/t_pure.sh:0"
export PC88_REF_ROM_DIR="$WORK/refrom"
fk_run; fk_run
c1="$(exec_of t_env.sh)"
echo two > "$WORK/refrom/f"
fk_run
c2="$(exec_of t_env.sh)"
unset PC88_REF_ROM_DIR
if [[ "$c1" == "CACHED" && -n "$c2" && "$c2" != "CACHED" ]]; then
    pass "g-11. PC88_REF_ROM_DIR の指す内容が変わると再実行される(変えなければ CACHED)"
else
    ng "g-11. 環境変数の指す内容の変化を検出できない(変更前=$c1 変更後=$c2)"
fi

# g-9: $var 直後の全角文字 → 静的検査が NG（陰性対照: ${var} なら OK）
fk_variant "tools/t_pure.sh:0"
printf '#!/usr/bin/env bash\nvar=1\necho "値（$var）です"\n' > "$FK/tools/t_lintbad.sh"
fk_run; rc_lint_bad=$?
if [[ "$rc_lint_bad" == "1" ]] && grep -q 'NG(\$変数の直後に非ASCII文字)' "$WORK/fk.out" && grep -q 't_lintbad.sh' "$WORK/fk.out"; then
    bad_ok=1
else
    bad_ok=0
fi
printf '#!/usr/bin/env bash\nvar=1\necho "値（${var}）です"\n' > "$FK/tools/t_lintbad.sh"
fk_run; rc_lint_good=$?
if [[ $bad_ok == 1 && "$rc_lint_good" == "0" ]]; then
    pass "g-9. \$var 直後の全角文字を静的検査が NG にした(陰性対照: \${var} に直すと OK)"
else
    ng "g-9. 静的検査の検出力が想定と違う(bad_ok=$bad_ok rc_good=$rc_lint_good)"; sed 's/^/      /' "$WORK/fk.out" | head -8
fi
rm -f "$FK/tools/t_lintbad.sh"

echo
if [[ "$fail" -eq 0 ]]; then
    echo "全項目 OK"
    exit 0
else
    echo "$fail 件 NG"
    exit 1
fi

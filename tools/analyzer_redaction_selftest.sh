#!/usr/bin/env bash
# tools/analyzer_redaction_selftest.sh — tools/analyze_sub_proto.py と
# tools/verify_analyzer_corruption.py が、2026-08-10の伏せ字化
# (docs/notes/disclosure-2026-08-10.md, `$FB`/`$FC`/`$FD` の value を `--` に
# 置換)に対して「無言で消える」のではなく「伏せ字である旨を明示する」ことを
# 検査する。
#
# CLAUDE.md / docs/notes の方針どおり、検査器を信用してよいのはわざと壊して
# 検出できることを確かめた後だけ（tools/redact_iolog_selftest.sh の作法を
# 踏襲）。公式ROM・公式ディスク不要。フィクスチャは全て自作の合成データ。
#
# 経緯: 2026-08-10、measurements/*.iolog.txt のデータポート value を伏せ字化
# したところ、tools/analyze_sub_proto.py 等の解析器が `$FC`/`$FD` のペアを
# 警告無しにレポートから丸ごと消していた（value列を2桁hex限定で正規表現
# マッチしていたため、伏せ字行がparse時点で無言でスキップされていた）。
# この検査は、その修正が入っていること・退行しても検出できることを確認する。
#
# 使い方: tools/analyzer_redaction_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZE="$SCRIPT_DIR/analyze_sub_proto.py"
VERIFY="$SCRIPT_DIR/verify_analyzer_corruption.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 合成フィクスチャ（公式データ不使用）-----------------------------------
# main OUT $FD -> sub IN $FC の値一致ペアを300件作る(8列・clock付きM6c形式)。
# UNMASKED は値そのまま、MASKED は同じ構造で value を `--` に伏せ字化した版
# （tools/redact_iolog.py が実際に出す書式と同じ固定文字列）。
gen_fixture() {
    local out="$1" masked="$2"
    {
        echo "core      : (テスト用ダミー・自作、公式データ不使用)"
        echo "frames    : 100"
        echo
        echo "# main"
        echo "# seq    clock   frame  cpu   kind  port  value  pc"
        for i in $(seq 0 299); do
            local clock=$((i * 2 + 1))
            local seq=$((i + 1))
            local val
            val=$(printf '%02X' $((i % 256)))
            if [[ "$masked" == "1" ]]; then val="--"; fi
            printf '%6d %7d %6d main  OUT   00FD   %s   1000\n' "$seq" "$clock" 0 "$val"
        done
        echo
        echo "# sub"
        echo "# seq    clock   frame  cpu   kind  port  value  pc"
        for i in $(seq 0 299); do
            local clock=$((i * 2 + 2))
            local seq=$((i + 1))
            local val
            val=$(printf '%02X' $((i % 256)))
            if [[ "$masked" == "1" ]]; then val="--"; fi
            printf '%6d %7d %6d sub   IN    00FC   %s   2000\n' "$seq" "$clock" 0 "$val"
        done
    } > "$out"
}

UNMASKED_IO="$WORK/unmasked.iolog.txt"
MASKED_IO="$WORK/masked.iolog.txt"
gen_fixture "$UNMASKED_IO" 0
gen_fixture "$MASKED_IO" 1

# intlog は Q3 が使うだけなので節ヘッダのみで足りる(0件でエラーにならない)。
INTLOG="$WORK/dummy.intlog.txt"
printf '# main\n# sub\n' > "$INTLOG"

# --- a. 伏せ字ログ: 解析器が伏せ字である旨を出力する ------------------------
MASKED_OUT="$WORK/masked_report.txt"
MASKED_ERR="$WORK/masked.err"
python3 "$ANALYZE" --iolog "$MASKED_IO" --intlog "$INTLOG" --out "$MASKED_OUT" 2>"$MASKED_ERR"

if grep -q '伏せ字' "$MASKED_ERR" 2>/dev/null; then
    pass "a. 伏せ字ログでは標準エラーに警告が出る"
else
    fail "a. 伏せ字ログでも標準エラーに警告が出ない: $(cat "$MASKED_ERR")"
fi

if grep -q '## 注記: 伏せ字' "$MASKED_OUT" \
    && grep -qE 'main OUT \$FD: 値が伏せ字のため300件を除外' "$MASKED_OUT"; then
    pass "a. レポートに伏せ字件数(300件)が明示される"
else
    fail "a. レポートに伏せ字件数が明示されない"
fi

# 伏せ字済みなので、Q1のFD->FCペアは値比較できず出現しないはず
# (黙って消えるのではなく、上の注記で「除外した」と説明されている状態)。
if grep -qE 'OUT 00FD .*-> IN 00FC:' "$MASKED_OUT"; then
    fail "a. 伏せ字済みのはずのFD->FCペアがQ1に値比較付きで出現した(伏せ字が効いていない)"
else
    pass "a. 伏せ字済みのFD->FCペアはQ1の値比較から除外されている(上の注記と整合)"
fi

# --- b. 伏せ字を含まないログ: 従来どおり値一致率が出る ----------------------
UNMASKED_OUT="$WORK/unmasked_report.txt"
UNMASKED_ERR="$WORK/unmasked.err"
python3 "$ANALYZE" --iolog "$UNMASKED_IO" --intlog "$INTLOG" --out "$UNMASKED_OUT" 2>"$UNMASKED_ERR"

if [[ ! -s "$UNMASKED_ERR" ]]; then
    pass "b. 伏せ字を含まないログでは警告が出ない"
else
    fail "b. 伏せ字を含まないログでも警告が出てしまった: $(cat "$UNMASKED_ERR")"
fi

if grep -q '(伏せ字のイベントは含まれていない)' "$UNMASKED_OUT"; then
    pass "b. レポートの注記が「伏せ字なし」と正しく判定している"
else
    fail "b. レポートの注記が「伏せ字なし」と判定していない"
fi

if grep -qE 'OUT 00FD .*-> IN 00FC:' "$UNMASKED_OUT" \
    && grep -qE '一致率 100\.0%' "$UNMASKED_OUT"; then
    pass "b. 伏せ字を含まないログでは値一致率(100%)が従来どおり出る"
else
    fail "b. 伏せ字を含まないログで値一致率が出ない(退行の疑い)"
fi

# --- c. 検出力の確認: 検出コードを無効化すると壊れて見えることを確認 --------
# 「$FB/$FC/$FDの value が2桁hex限定でないと行ごと無言で捨てる」という
# 修正前の状態を、正規表現を書き換えたコピーで再現する。真の伏せ字件数(300)を
# 知っている側(このテスト)が、壊れたコピーの出力ではそれを検出できない
# ことを確認する。
# tools/ 配下に置く(同名ディレクトリのcmp_io.pyをimportするため。
# sys.path.insert(0, __file__の親)に依存しているので別ディレクトリに置くと
# import に失敗する)。使い終わったらtrapで消す。
BROKEN_ANALYZE="$SCRIPT_DIR/.analyze_sub_proto_broken_selftest.py"
trap 'rm -rf "$WORK" "$BROKEN_ANALYZE"' EXIT
sed -E 's/\(\[0-9A-Fa-f\]\{2\}\|--\)/([0-9A-Fa-f]{2})/' "$ANALYZE" > "$BROKEN_ANALYZE"
if diff -q "$ANALYZE" "$BROKEN_ANALYZE" >/dev/null 2>&1; then
    fail "c. 壊れたコピーの生成に失敗した(sedが対象行にマッチしなかった。ANALYZE側の書式が変わった可能性)"
else
    BROKEN_OUT="$WORK/broken_report.txt"
    BROKEN_ERR="$WORK/broken.err"
    python3 "$BROKEN_ANALYZE" --iolog "$MASKED_IO" --intlog "$INTLOG" --out "$BROKEN_OUT" 2>"$BROKEN_ERR"

    # 修正前の挙動: 伏せ字行が丸ごとparse時点で無言スキップされるため、
    # masked辞書が空になり「伏せ字のイベントは含まれていない」という
    # *誤った*(実際には600件ある)結論を出す。これが「わざと壊す」の再現。
    if grep -q '(伏せ字のイベントは含まれていない)' "$BROKEN_OUT" \
        && [[ ! -s "$BROKEN_ERR" ]]; then
        pass "c. 検出コードを無効化すると、実際には伏せ字(300+300件)があるのに「伏せ字なし」と誤判定する退行を再現できた(=検出力がある証拠)"
    else
        fail "c. 検出コードを無効化しても誤判定が再現しなかった(このテスト自体が壊れているか、修正が想定と違う経路で効いている)"
    fi
fi

# --- d. verify_analyzer_corruption.py: 伏せ字ログでSKIP・非伏せ字ログでは走る --
VERIFY_MASKED_OUT="$WORK/verify_masked.txt"
python3 "$VERIFY" --iolog "$MASKED_IO" --intlog "$INTLOG" --workdir "$WORK/vac_masked" \
    > "$VERIFY_MASKED_OUT" 2>&1
if grep -q 'SKIP: (b) offset-value' "$VERIFY_MASKED_OUT"; then
    pass "d. verify_analyzer_corruption.py は伏せ字ログで(b)をSKIPする"
else
    fail "d. verify_analyzer_corruption.py が伏せ字ログで(b)をSKIPしなかった"
fi

VERIFY_UNMASKED_OUT="$WORK/verify_unmasked.txt"
python3 "$VERIFY" --iolog "$UNMASKED_IO" --intlog "$INTLOG" --workdir "$WORK/vac_unmasked" \
    > "$VERIFY_UNMASKED_OUT" 2>&1
if grep -q 'SKIP' "$VERIFY_UNMASKED_OUT"; then
    fail "d. verify_analyzer_corruption.py が非伏せ字ログでもSKIPしてしまった"
else
    if grep -q '(a) shuffle-clock' "$VERIFY_UNMASKED_OUT" && grep -q '(b) offset-value' "$VERIFY_UNMASKED_OUT"; then
        pass "d. verify_analyzer_corruption.py は非伏せ字ログでは(a)(b)とも通常どおり走る"
    else
        fail "d. verify_analyzer_corruption.py の非伏せ字ログでの出力に(a)(b)が見当たらない"
    fi
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
    echo "==> 全項目 OK"
    exit 0
else
    echo "==> 一部 NG"
    exit 1
fi

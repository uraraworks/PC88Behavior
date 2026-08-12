#!/usr/bin/env bash
# tools/analyze_run_boundary_selftest.sh — tools/analyze_run_boundary.py の
# 検出力を合成フィクスチャで検算する。
#
# 「不自然に揃った数字は観測系の故障を疑う」規律に基づき、docs/notes/
# m6n-run-boundary.md の中心的な所見（sub OUT $FF=0Cの直後の後継サイトは
# 必ず単一のOUT $FF語彙(RECV系/SEND系)へ至る）が、わざと壊した入力では
# 実際に崩れることを確認してから、実測ログへの適用結果を信用する。
# tools/analyze_sub_fe_selftest.sh の作法(合成フィクスチャ・a/b/c方式)を
# 踏襲する。公式ROM・公式ディスク不要、すべて自作の合成データ。
#
# 検査内容:
#   a. 正常フィクスチャ: main側3バイトSEND run(先頭のみ0Fあり)と、
#      sub側RECV完了直後の2つの後継サイト(pc=9100=直接次RECV再武装、
#      pc=9200=待ちループ経由で必ずSEND)を合成し、期待どおりの
#      「先頭0Fあり/継続0Fなし」「各サイトが単一語彙に至る」が出ることを
#      確認する。
#   b. 継続バイトにも0Fを混入: 検出力確認その1。継続バイトの直前にも
#      OUT $FF 0Fを追加すると、「継続 0Fなし」の比率が崩れることを確認する。
#   c. 後継サイトの行き先を混在させる: 検出力確認その2。pc=9100(直接再武装)
#      の後に一部だけSEND系$FFを混ぜると、「単一語彙」判定が
#      「複数語彙混在」に変わることを確認する。
#
# 使い方: tools/analyze_run_boundary_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZE="$SCRIPT_DIR/analyze_run_boundary.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 合成フィクスチャ生成(公式データ不使用) ---------------------------
# main側: 3バイトのSEND run(pc=37F4,3811,37F4。先頭だけOUT $FF 0Fを伴う)
#         を5回繰り返す。
# sub側: RECV完了(OUT $FF=0C)の直後に2種の後継サイトを交互に置く。
#   - pc=9100: 直後にOUT $FF=0B(RECV系, 直接再武装・待ちループなし)
#   - pc=9200: 直後にIN $FE(待ちループ)を経て、最終的にOUT $FF=09(SEND系)
gen_fixture() {
    local out="$1"
    {
        echo "core      : (テスト用ダミー・自作、公式データ不使用)"
        echo "frames    : 100"
        echo
        echo "# main"
        echo "# seq    clock   frame  cpu   kind  port  value  pc"
        local seq=0
        local clock=0
        for i in $(seq 0 4); do
            printf '%6d %7d %6d main  OUT   00FF   0F     3700\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d main  OUT   00FD   11     37F4\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d main  OUT   00FD   12     3811\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d main  OUT   00FD   13     37F4\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d main  IN    00FC   --     3880\n' $((++seq)) $((++clock)) 0
        done
        echo
        echo "# sub"
        echo "# seq    clock   frame  cpu   kind  port  value  pc"
        for i in $(seq 0 19); do
            printf '%6d %7d %6d sub   OUT   00FF   0C     0700\n' $((++seq)) $((++clock)) 0
            if (( i % 4 == 3 )); then
                # 4回に1回、待ちループ経由でSENDへ
                printf '%6d %7d %6d sub   IN    00FE   00     9200\n' $((++seq)) $((++clock)) 0
                printf '%6d %7d %6d sub   IN    00FE   02     9200\n' $((++seq)) $((++clock)) 0
                printf '%6d %7d %6d sub   OUT   00FF   09     0720\n' $((++seq)) $((++clock)) 0
            else
                # それ以外は直接次のRECVへ再武装
                printf '%6d %7d %6d sub   OUT   00FF   0B     9100\n' $((++seq)) $((++clock)) 0
            fi
        done
    } > "$out"
}

FIXTURE="$WORK/fixture.iolog.txt"
gen_fixture "$FIXTURE"

BASE_OUT="$WORK/base_report.txt"
python3 "$ANALYZE" --iolog "$FIXTURE" --out "$BASE_OUT" --label fixture >/dev/null

# --- a. 正常フィクスチャ ---------------------------------------------
if grep -q "first: {'0F あり': 5}" "$BASE_OUT"; then
    pass "a. SEND run先頭5件すべてで0Fありが検出される"
else
    fail "a. run先頭の0F検出が期待どおりでない: $(grep -A1 '## 1' "$BASE_OUT")"
fi

CONT_CHECK=$(python3 - "$BASE_OUT" <<'PYEOF'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"continuation: (\{[^\n]*\})", text)
print("OK" if (m and "'0F なし': 10" in m.group(1)) else "NG")
PYEOF
)
if [[ "$CONT_CHECK" == "OK" ]]; then
    pass "a. run継続バイト10件すべてで0Fなしが検出される"
else
    fail "a. run継続バイトの0F検出が期待どおりでない"
fi

if grep -A1 '次: OUT \$FF pc=9100' "$BASE_OUT" | grep -q "{'RECV系': 15}"; then
    pass "a. 直接再武装サイト(pc=9100)が単一語彙(RECV系15件)と判定される"
else
    fail "a. pc=9100の判定が期待どおりでない: $(grep -A1 '次: OUT \$FF pc=9100' "$BASE_OUT")"
fi

if grep -A1 '次: IN \$FE pc=9200' "$BASE_OUT" | grep -q "{'SEND系': 5}"; then
    pass "a. 待ちループ経由サイト(pc=9200)が単一語彙(SEND系5件)と判定される"
else
    fail "a. pc=9200の判定が期待どおりでない: $(grep -A1 '次: IN \$FE pc=9200' "$BASE_OUT")"
fi

# --- b. 検出力その1: 継続バイトにも0Fを混入させる -------------------------
sed 's/main  OUT   00FD   12     3811/main  OUT   00FF   0F     3700\n&/' "$FIXTURE" > "$WORK/b_fixture.iolog.txt"
# 上のsedは2バイト目(pc=3811)の直前に0Fを挿入しているが、実際にはこの
# 挿入行自体もseq/clock列がずれる。analyze_run_boundary.pyはseq/clockを
# 数値としてしか使わないため、重複clock自体は解析エラーにならないが、
# 「直前の窓」の判定基準(直前SEND/RECVイベントとの間)には影響しない
# (0Fの挿入位置がSEND runの内部にあるため)。
B_OUT="$WORK/b_report.txt"
python3 "$ANALYZE" --iolog "$WORK/b_fixture.iolog.txt" --out "$B_OUT" --label b >/dev/null

CONT_B=$(python3 - "$B_OUT" <<'PYEOF'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"continuation: (\{[^\n]*\})", text)
print(m.group(1) if m else "(none)")
PYEOF
)
if [[ "$CONT_B" != *"'0F なし': 10"* ]]; then
    pass "b. 継続バイトに0Fを混入させると継続0Fなしの比率が崩れる(検出力の確認): ${CONT_B}"
else
    fail "b. 継続バイトに0Fを混入させても検出結果が変わらなかった(検出力に疑いあり)"
fi

# --- c. 検出力その2: 直接再武装サイトの行き先を混在させる -----------------
# pc=9100直後のOUT $FF=0B(RECV系)のうち1件だけSEND系(09)に書き換える。
python3 - "$FIXTURE" "$WORK/c_fixture.iolog.txt" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().splitlines(keepends=True)
done = False
out = []
for line in lines:
    if not done and "9100" in line and "0B" in line:
        line = line.replace("0B     9100", "09     9100")
        done = True
    out.append(line)
open(dst, "w", encoding="utf-8").write("".join(out))
assert done, "置換対象が見つからなかった(フィクスチャの想定崩れ)"
PYEOF

C_OUT="$WORK/c_report.txt"
python3 "$ANALYZE" --iolog "$WORK/c_fixture.iolog.txt" --out "$C_OUT" --label c >/dev/null

C_LINE=$(grep -A1 '次: OUT \$FF pc=9100' "$C_OUT" | tail -1)
if [[ "$C_LINE" == *"'RECV系'"* && "$C_LINE" == *"'SEND系'"* ]]; then
    pass "c. pc=9100の行き先に1件だけSEND系を混ぜると単一語彙(RECV系のみ)が崩れ両方混在する(検出力の確認): ${C_LINE}"
else
    fail "c. 行き先を混在させても単一語彙判定のままだった(検出力に疑いあり): ${C_LINE}"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
    echo "==> 全項目 OK"
    exit 0
else
    echo "==> 一部 NG"
    exit 1
fi

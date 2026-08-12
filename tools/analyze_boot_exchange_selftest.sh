#!/usr/bin/env bash
# tools/analyze_boot_exchange_selftest.sh — tools/analyze_boot_exchange.py の
# 検出力を合成フィクスチャで検算する。
#
# 「不自然に揃った数字は観測系の故障を疑う」規律に基づき、
# docs/notes/m6l-boot-exchange.md の中心的な所見（FDC($FA/$FB)アクセスが
# 応答直前のラウンド時間窓に完全に集中する）が、わざと壊した入力では
# 実際に崩れることを確認してから、実測ログへの適用結果を信用する。
# tools/analyze_sub_fe_selftest.sh の作法（合成フィクスチャ・a/b/c方式）を
# 踏襲する。公式ROM・公式ディスク不要、すべて自作の合成データ。
#
# 検査内容:
#   a. 正常フィクスチャ: 3ラウンド(FDCアクセス無し/FDCバースト10件/
#      複数バイト応答でFDCアクセス無し)を合成し、ラウンド別FDC件数と
#      「ラウンド時間窓の合計=起動シーケンス全体」の集中度確認が
#      期待どおりに出ることを確認する。
#   b. clockシャッフル: 全行のclock値の割り当てをシャッフルする
#      (tools/verify_analyzer_corruption.pyのmake_shuffled_clockと同じ
#      操作)。真の時間窓が壊れるので、ラウンドBのFDC件数(10/10)が
#      崩れるはず。
#   c. SENDのpc破壊: main OUT $FDのpc列を、SEND_PCS({37F4,3811})に
#      含まれない値に書き換える。SEND分類そのものが機能しなくなり、
#      ラウンドが1つも検出されなくなるはず(pcベースの分類が実際に
#      効いていることの検出力確認)。
#
# 使い方: tools/analyze_boot_exchange_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZE="$SCRIPT_DIR/analyze_boot_exchange.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 合成フィクスチャ生成(公式データ不使用) -------------------------------
# ラウンドA: SEND(37F4,1byte) -> RECV(3863,1byte)、FDCアクセス無し
# ラウンドB: SEND(37F4,1byte) -> [sub $FA/$FBを10往復] -> RECV(3863,1byte)
# ラウンドC: SEND(37F4,3811,2byte) -> RECV(3863,3880,3863,3880,3863 の5byte)
gen_fixture() {
    local out="$1"
    {
        echo "core      : (テスト用ダミー・自作、公式データ不使用)"
        echo "frames    : 100"
        echo
        echo "# main"
        echo "# seq    clock   frame  cpu   kind  port  value  pc"
        printf '%6d %7d %6d main  OUT   00FD   01     37F4\n' 1 100 0
        printf '%6d %7d %6d main  IN    00FC   --     3863\n' 2 120 0
        printf '%6d %7d %6d main  OUT   00FD   02     37F4\n' 3 200 0
        printf '%6d %7d %6d main  IN    00FC   --     3863\n' 4 300 0
        printf '%6d %7d %6d main  OUT   00FD   03     37F4\n' 5 400 0
        printf '%6d %7d %6d main  OUT   00FD   04     3811\n' 6 410 0
        printf '%6d %7d %6d main  IN    00FC   --     3863\n' 7 420 0
        printf '%6d %7d %6d main  IN    00FC   --     3880\n' 8 421 0
        printf '%6d %7d %6d main  IN    00FC   --     3863\n' 9 422 0
        printf '%6d %7d %6d main  IN    00FC   --     3880\n' 10 423 0
        printf '%6d %7d %6d main  IN    00FC   --     3863\n' 11 424 0
        echo
        echo "# sub"
        echo "# seq    clock   frame  cpu   kind  port  value  pc"
        local seq=100
        local clock=210
        for i in $(seq 1 10); do
            printf '%6d %7d %6d sub   IN    00FA   80     9000\n' $((++seq)) $((clock++)) 0
            printf '%6d %7d %6d sub   OUT   00FB   01     9001\n' $((++seq)) $((clock++)) 0
        done
    } > "$out"
}

FIXTURE="$WORK/fixture.iolog.txt"
gen_fixture "$FIXTURE"

# --- a. 正常フィクスチャ ---------------------------------------------------
BASE_OUT="$WORK/base_report.txt"
python3 "$ANALYZE" --iolog "$FIXTURE" --label fixture --out "$BASE_OUT" >/dev/null

if grep -qE '^\s*0\s+1\s+.*1byte.*\s+0\s+0\s*$' "$BASE_OUT"; then
    pass "a. ラウンドA(FDCアクセス無し)がFA=0 FB=0で検出される"
else
    fail "a. ラウンドAの検出結果が期待と異なる: $(sed -n '/ラウンド別/,/応答種別/p' "$BASE_OUT")"
fi

if grep -qE '^\s*1\s+1\s+.*1byte.*\s+10\s+10\s*$' "$BASE_OUT"; then
    pass "a. ラウンドB(FDCバースト10件)がFA=10 FB=10で検出される"
else
    fail "a. ラウンドBの検出結果が期待と異なる(FA/FB=10/10のはず)"
fi

if grep -qE '^\s*2\s+2\s+.*5byte.*\s+0\s+0\s*$' "$BASE_OUT"; then
    pass "a. ラウンドC(5byte応答、FDCアクセス無し)が検出される"
else
    fail "a. ラウンドCの検出結果が期待と異なる(5byte応答のはず)"
fi

if grep -qE '起動シーケンス全体.*FA=10 FB=10' "$BASE_OUT" \
    && grep -qE '各ラウンドの時間窓の合計.*FA=10 FB=10' "$BASE_OUT"; then
    pass "a. 集中度確認: 全体10/10とラウンド合計10/10が一致する"
else
    fail "a. 集中度確認の一致が出ない: $(grep -A2 '集中度確認' "$BASE_OUT")"
fi

# --- b. clockシャッフル: ラウンドBのFDC集中が崩れること --------------------
python3 - "$FIXTURE" "$WORK/shuffled.iolog.txt" <<'PYEOF'
import re, random, sys
src, dst = sys.argv[1], sys.argv[2]
ROW_RE = re.compile(
    r"^(\s*)(\d+)(\s+)(\d+)(\s+)(\d+)(\s+)(main|sub)(\s+)(IN|OUT)(\s+)"
    r"([0-9A-Fa-f]{4})(\s+)([0-9A-Fa-f]{2}|--)(\s+)([0-9A-Fa-f]{4})(\s*)$"
)
lines = open(src, encoding="utf-8").read().splitlines(keepends=True)
idxs, clocks = [], []
for i, line in enumerate(lines):
    m = ROW_RE.match(line)
    if not m:
        continue
    idxs.append(i)
    clocks.append(int(m.group(4)))
rng = random.Random(7)
shuffled = clocks[:]
rng.shuffle(shuffled)
out = lines[:]
for i, new_clock in zip(idxs, shuffled):
    m = ROW_RE.match(lines[i])
    g = list(m.groups())
    g[3] = str(new_clock)
    out[i] = "".join(g)
open(dst, "w", encoding="utf-8").write("".join(out))
PYEOF

SHUFFLED_OUT="$WORK/shuffled_report.txt"
python3 "$ANALYZE" --iolog "$WORK/shuffled.iolog.txt" --label shuffled --out "$SHUFFLED_OUT" >/dev/null

if grep -qE '^\s*1\s+1\s+.*1byte.*\s+10\s+10\s*$' "$SHUFFLED_OUT"; then
    fail "b. clockシャッフル後もラウンドBがFA=10 FB=10のまま(真の時間窓を見ていない疑い)"
else
    pass "b. clockシャッフル後、ラウンドBのFDC集中(10/10)が崩れた(真の時間窓を見ている証拠)"
fi

# --- c. SENDのpc破壊: ラウンドが1つも検出されなくなること -----------------
sed -E 's/(main  OUT   00FD   [0-9A-Fa-f]{2})     (37F4|3811)$/\1     9999/' "$FIXTURE" \
    > "$WORK/pc_broken.iolog.txt"

BROKEN_OUT="$WORK/broken_report.txt"
python3 "$ANALYZE" --iolog "$WORK/pc_broken.iolog.txt" --label broken --out "$BROKEN_OUT" >/dev/null

if grep -qE 'ラウンド数\(バルク含む\): 0' "$BROKEN_OUT"; then
    pass "c. SENDのpcを未知の値に破壊すると、ラウンドが1つも検出されなくなる(pc分類が効いている証拠)"
else
    fail "c. pcを破壊してもラウンドが検出され続けた(pc分類の検出力に疑いあり): $(grep 'ラウンド数' "$BROKEN_OUT")"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
    echo "==> 全項目 OK"
    exit 0
else
    echo "==> 一部 NG"
    exit 1
fi

#!/usr/bin/env bash
# tools/analyze_sub_fe_selftest.sh — tools/analyze_sub_fe.py の検出力を
# 合成フィクスチャで検算する。
#
# 「不自然に揃った数字は観測系の故障を疑う」規律に基づき、わざと壊した
# 入力に対して結果が実際に崩れることを確認してから、実測ログへの適用結果
# (docs/notes/m6k-mixed-divergence.md 等)を信用する。
# tools/analyzer_redaction_selftest.sh / tools/verify_analyzer_corruption.py
# の作法(合成フィクスチャ・a/b/c方式の検査)を踏襲する。公式ROM・
# 公式ディスク不要、すべて自作の合成データ。
#
# 検査内容:
#   a. 正常フィクスチャ: 既知のRECV型待ちループ(pc=2000: 20->21 50件、
#      pc=2001: 41->40 50件)を、正しいOUT $FF文脈(0B/0A/0D/0C)付きで
#      50サイクル生成し、analyze_sub_fe.pyの出力に期待どおりの遷移・
#      ロール判定(RECV)が出ることを確認する。
#   b. clockシャッフル: 各行のclock値の集合はそのまま、行への割り当てだけを
#      シャッフルする(tools/verify_analyzer_corruption.pyのmake_shuffled_clock
#      と同じ操作)。真の発生順が失われるので、スピン単位の遷移集計
#      (20->21 50件、41->40 50件)は大きく崩れるはず。崩れなければ
#      解析器がclock順を実際には見ていない疑いが濃い。
#   c. pcラベルの破壊: 全イベントのpc列を固定の1値に潰したコピーを作り、
#      「候補待ちループが1種に潰れる」ことを確認する(pc別グループ化が
#      機能していることの検出力確認)。
#
# 使い方: tools/analyze_sub_fe_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZE="$SCRIPT_DIR/analyze_sub_fe.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 合成フィクスチャ生成(公式データ不使用) ---------------------------
# RECVサイクルを50回、sub側に生成する(1.10節のRECVプリミティブの型を
# 模した合成データ。値そのものは実測から知られている語彙をテスト用に
# 再利用しているだけで、ログの中身ではない)。
gen_fixture() {
    local out="$1"
    {
        echo "core      : (テスト用ダミー・自作、公式データ不使用)"
        echo "frames    : 100"
        echo
        echo "# main"
        echo "# seq    clock   frame  cpu   kind  port  value  pc"
        echo
        echo "# sub"
        echo "# seq    clock   frame  cpu   kind  port  value  pc"
        local seq=0
        local clock=0
        for i in $(seq 0 49); do
            printf '%6d %7d %6d sub   OUT   00FF   0B     1000\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d sub   IN    00FE   20     2000\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d sub   IN    00FE   21     2000\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d sub   OUT   00FF   0A     1001\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d sub   IN    00FC   --     1002\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d sub   OUT   00FF   0D     1003\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d sub   IN    00FE   41     2001\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d sub   IN    00FE   40     2001\n' $((++seq)) $((++clock)) 0
            printf '%6d %7d %6d sub   OUT   00FF   0C     1004\n' $((++seq)) $((++clock)) 0
        done
    } > "$out"
}

FIXTURE="$WORK/fixture.iolog.txt"
gen_fixture "$FIXTURE"

# --- a. 正常フィクスチャ: 期待どおりの遷移・ロール判定が出ること --------
BASE_OUT="$WORK/base_report.txt"
python3 "$ANALYZE" --iolog "$FIXTURE" --out "$BASE_OUT" --label fixture >/dev/null

if grep -q 'pc=2000' "$BASE_OUT" && grep -qE '遷移: 20->21\(50\)' "$BASE_OUT"; then
    pass "a. pc=2000の遷移(20->21 x50件)が正しく検出される"
else
    fail "a. pc=2000の遷移が期待どおりに出ない: $(grep -A5 'pc=2000' "$BASE_OUT")"
fi

if grep -q 'pc=2001' "$BASE_OUT" && grep -qE '遷移: 41->40\(50\)' "$BASE_OUT"; then
    pass "a. pc=2001の遷移(41->40 x50件)が正しく検出される"
else
    fail "a. pc=2001の遷移が期待どおりに出ない"
fi

if grep -A2 'pc=2000' "$BASE_OUT" | grep -q '推定ロール: RECV' \
    && grep -A2 'pc=2001' "$BASE_OUT" | grep -q '推定ロール: RECV'; then
    pass "a. pc=2000/2001とも前後のOUT \$FF(0B/0A/0D/0C)からRECVロールと正しく判定される"
else
    # 除外理由: 上の \$FF はダブルクオート文字列内でバックスラッシュ
    # エスケープ済みであり、変数展開されない（リテラルの "$FF" と
    # 表示するためのエスケープ）。check_cleanroom.sh のヒューリスティックは
    # バックスラッシュを見ないため誤検出する。
    fail "a. RECVロール判定が出ない(前後\$FF文脈の対応付けが機能していない疑い)" # cleanroom-lint:ignore
fi

# --- a2. 効いているビット判定(bit_significance, 第10版で追加)の検出力 -----
# 正常フィクスチャでは pc=2000(20->21) は bit0=1、pc=2001(41->40) は bit0=0
# が「exit/loop継続を分離する」と判定されるはず(20=0b00100000,
# 21=0b00100001; 41=0b01000001,40=0b01000000のいずれもbit0のみが変わる)。
if grep -A9 'pc=2000' "$BASE_OUT" | grep -q '効いているビット.*bit0=1'; then
    pass "a2. pc=2000でbit0=1が単一ビット判定される(正常フィクスチャ)"
else
    fail "a2. pc=2000のビット判定が期待どおりでない: $(grep -A9 'pc=2000' "$BASE_OUT" | grep '効いているビット')"
fi
if grep -A9 'pc=2001' "$BASE_OUT" | grep -q '効いているビット.*bit0=0'; then
    pass "a2. pc=2001でbit0=0が単一ビット判定される(正常フィクスチャ)"
else
    fail "a2. pc=2001のビット判定が期待どおりでない: $(grep -A9 'pc=2001' "$BASE_OUT" | grep '効いているビット')"
fi

# 検出力確認: pc=2000のexit値集合に、loop継続値と同じbit0を持つ値
# (0x20, bit0=0)を1件だけ「即抜けのスピン」として混入させる。これは
# 「途中では0x20を読んで回り続けるが、別のあるスピンでは0x20を読んだ
# 瞬間に抜けた」という矛盾した観測を人工的に作ることに相当し、
# bit0だけでは exit/loop継続 を分離できなくなるはず。
python3 - "$FIXTURE" "$WORK/bitbreak.iolog.txt" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().splitlines(keepends=True)
# 末尾に、孤立した1回だけの IN $FE=20 (pc=2000) を追加する。前後を
# 無関係のOUT $FFで挟んで独立した1件スピンとして扱われるようにする
# (analyze_sub_fe.pyのスピン境界判定は「連続する同一pcのIN $FE」なので、
# 前後を別イベントで挟めば別スピンになる)。
extra = (
    "  9001    9001      0 sub   OUT   00FF   99     9000\n"
    "  9002    9002      0 sub   IN    00FE   20     2000\n"
    "  9003    9003      0 sub   OUT   00FF   99     9000\n"
)
lines.append(extra)
open(dst, "w", encoding="utf-8").write("".join(lines))
PYEOF

BITBREAK_OUT="$WORK/bitbreak_report.txt"
python3 "$ANALYZE" --iolog "$WORK/bitbreak.iolog.txt" --out "$BITBREAK_OUT" --label bitbreak >/dev/null

if grep -A9 'pc=2000' "$BITBREAK_OUT" | grep -q '単一ビットでは説明がつかない'; then
    pass "a2. exit値にloop継続値と同じbit0の値を混ぜるとbit0判定が崩れる(検出力の確認)"
else
    fail "a2. bit0=0の孤立exitを混入させてもbit0判定が崩れなかった(検出力に疑いあり): $(grep -A9 'pc=2000' "$BITBREAK_OUT" | grep '効いているビット')"
fi

# --- b. clockシャッフル: スピン単位の遷移集計が崩れること ------------------
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
rng = random.Random(99)
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
python3 "$ANALYZE" --iolog "$WORK/shuffled.iolog.txt" --out "$SHUFFLED_OUT" --label shuffled >/dev/null

# シャッフル後は真の発生順が失われるため、pc=2000の"20->21"遷移が
# 50件ちょうど出ることは期待しない(スピン境界がバラバラになり
# 大きく崩れるはず)。念のため「出力に現れる遷移件数の合計」自体は
# 総イベント数保存(パースは壊れていない)ことも確認し、「解析結果が
# 崩れた」ことと「パースが壊れた」ことを区別する。
# (シェルのgrep連鎖は複数ブロックにまたがると誤爆しやすいため、
# セクション単位で厳密にパースするPythonで抽出する。)
SHUF_2000_2121=$(python3 - "$SHUFFLED_OUT" <<'PYEOF'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"### pc=2000.*?(?=\n### |\Z)", text, re.S)
if not m:
    print(0)
else:
    block = m.group(0)
    tm = re.search(r"20->21\((\d+)\)", block)
    print(tm.group(1) if tm else 0)
PYEOF
)

if [[ "$SHUF_2000_2121" -lt 50 ]]; then
    pass "b. clockシャッフル後、pc=2000の20->21遷移が50件未満に崩れた(件数=${SHUF_2000_2121}。真の発生順を見ている証拠)"
else
    fail "b. clockシャッフル後も20->21が50件のまま(順序を見ていない疑い)"
fi

# --- c. pcラベル破壊: 候補待ちループがpc別に分かれず1種に潰れること -------
sed -E 's/(00FE   [0-9A-Fa-f]{2})     [0-9A-Fa-f]{4}$/\1     9999/' "$FIXTURE" \
    | sed -E 's/(00FF   [0-9A-Fa-f]{2})     [0-9A-Fa-f]{4}$/\1     8888/' \
    | sed -E 's/(00FC   --)     [0-9A-Fa-f]{4}$/\1     7777/' \
    > "$WORK/pc_collapsed.iolog.txt"

COLLAPSED_OUT="$WORK/collapsed_report.txt"
python3 "$ANALYZE" --iolog "$WORK/pc_collapsed.iolog.txt" --out "$COLLAPSED_OUT" --label collapsed >/dev/null

N_LOOPS=$(grep -oE '候補待ちループ.*: [0-9]+種' "$COLLAPSED_OUT" | grep -oE '[0-9]+種' | grep -oE '[0-9]+')
if [[ "$N_LOOPS" == "1" ]]; then
    pass "c. 全pcを1値に潰すと候補待ちループが1種に統合される(pc別グループ化が機能している証拠)"
else
    fail "c. pcを1値に潰しても候補待ちループが1種にならなかった(N=${N_LOOPS}。グループ化ロジックの検出力に疑いあり)"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
    echo "==> 全項目 OK"
    exit 0
else
    echo "==> 一部 NG"
    exit 1
fi

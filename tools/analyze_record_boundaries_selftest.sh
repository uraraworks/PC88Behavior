#!/usr/bin/env bash
# tools/analyze_record_boundaries_selftest.sh — tools/analyze_record_boundaries.py
# の検出力を合成フィクスチャで検算する（m7bi）。公式ROM・公式ディスク不要。
#
# 「陽性対照は成果物が実際に変わることまで確認する」規律
# （過去に空振り2回。tools/analyze_write_path_selftest.sh の作法を踏襲）。
#
# 検査内容:
#   a. 正常フィクスチャ: バルク後に2つのrun(長さ3, 長さ2)を合成し、
#      窓(a)(b)どちらも同じrun長ヒストグラムを報告し、「一致」と出ること。
#   b. 陽性対照その1: run2の長さを2→4に変えると、報告されるバルク後run長が
#      実際に変わること（[3, 2] → [3, 4]）。決め打ちで固定値を返して
#      いないことの確認。
#   c. 陽性対照その2: データポート($FC)の値が伏せ字されていない壊れた
#      入力を与えると、「解析不可」として拒否すること（黙って解析しない）。
#   d. 陽性対照その3: 窓(a)(b)が食い違う合成ログ(finish後に再アームでも
#      FB/FDでもない別イベントを挟み、窓(a)は連続runとみなし、窓(b)は
#      別runとみなす)を作ると、「不一致」と報告されること。
#
# 使い方: tools/analyze_record_boundaries_selftest.sh
# 全項目OKなら終了コード0、1つでも落ちたら1。

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
ANALYZE="$REPO/tools/analyze_record_boundaries.py"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }
overall_rc=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 合成フィクスチャ生成(公式データ不使用、値はすべてダミー) --------------
# 1バイト受信サイクル: OUT $FF 0B(再アーム,runの2バイト目以降のみ) ->
#                       OUT $FF 0A -> IN $FC(伏せ字) -> OUT $FF 0D ->
#                       OUT $FF 0C(完了)
# run境界の作り方:
#   "fb"    完了直後に sub OUT $FB を1件挟んでからrunを終える
#           (窓(a)(b)どちらも同じ場所でrunを切る=一致するケース)
#   "other" 完了直後に sub IN $FE(再アームでもFB/FDでもない)を挟んで
#           そのまま次バイトのサイクルへ入る
#           (窓(a)はFB/FDが無いので連続runとみなす。窓(b)は次が再アーム
#            でないのでそこでrunを切る=食い違うケース)
#   "eof"   何も挟まずログを終える(両窓ともEOFで打ち切り=一致)
gen() {  # $1=出力 $2=run長カンマ区切り(例"3,2") $3=各run境界の種類カンマ区切り
         # (要素数はrun数と同じ。最後の要素は"eof"を想定するが指定可)
         # $4=(省略可)値伏せ字を壊すか(1で壊す)
  python3 - "$1" "$2" "$3" "${4:-0}" <<'PYEOF'
import sys
path, runlens_s, styles_s, corrupt = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1"
runlens = [int(x) for x in runlens_s.split(",")]
styles = styles_s.split(",")
assert len(runlens) == len(styles)

rows = []
seq = [0]
clock = [0]

def ev(cpu, kind, port, value):
    seq[0] += 1
    clock[0] += 1
    v = value if value is not None else "--"
    rows.append(f"{seq[0]:>6} {clock[0]:>7} {clock[0]:>6}  {cpu:<4}  {kind:<4}  {port}   {v}   0100")

# バルク本体(sub OUT $FC を3件。これがバルク終端を決める)
for _ in range(3):
    ev("sub", "OUT", "00FC", None)

def byte_cycle(rearm_before):
    if rearm_before:
        ev("sub", "OUT", "00FF", "0B")
    ev("sub", "OUT", "00FF", "0A")
    ev("sub", "IN", "00FC", "AA" if corrupt else None)
    ev("sub", "OUT", "00FF", "0D")
    ev("sub", "OUT", "00FF", "0C")

for ridx, (n, style) in enumerate(zip(runlens, styles)):
    for b in range(n):
        byte_cycle(rearm_before=(b > 0))
    if style == "fb":
        ev("sub", "OUT", "00FB", None)
    elif style == "other":
        ev("sub", "IN", "00FE", "01")
        # 次のrunの先頭バイトへ、再アームを経ずに直結する
        # (窓(b)からは「再アームなしで終わった」に見える)
    elif style == "eof":
        pass
    else:
        raise ValueError(f"unknown style: {style}")

with open(path, "w") as f:
    f.write("# analyze_record_boundaries_selftest の合成フィクスチャ(公式データ不使用)\n")
    f.write("core      : (テスト用ダミー)\nframes    : 1\n\n")
    f.write("# main\n# seq    clock   frame  cpu   kind  port  value  pc\n\n")
    f.write("# sub\n# seq    clock   frame  cpu   kind  port  value  pc\n")
    f.write("\n".join(rows) + "\n")
PYEOF
}

run_analyze() {  # $1=iolog $2=out
  python3 "$ANALYZE" --iolog "$1" --label selftest --out "$2"
}

# --- a. 正常フィクスチャ: run長[3,2]、両方"fb"境界 -------------------------
gen "$WORK/a.iolog.txt" "3,2" "fb,eof"
A_OUT="$WORK/a_report.txt"
run_analyze "$WORK/a.iolog.txt" "$A_OUT" >/dev/null
cat "$A_OUT" | sed 's/^/  /'

if grep -q "バルク後run長(出現順): 一致  \[3, 2\]" "$A_OUT"; then
  ok "a. 正常フィクスチャで窓(a)(b)が一致し、バルク後run長[3, 2]と報告される"
else
  ng "a. 期待した一致結果が出なかった"
  overall_rc=1
fi

# --- b. 陽性対照その1: run2の長さを2→4に変えると報告が変わること ----------
gen "$WORK/b.iolog.txt" "3,4" "fb,eof"
B_OUT="$WORK/b_report.txt"
run_analyze "$WORK/b.iolog.txt" "$B_OUT" >/dev/null
if grep -q "バルク後run長(出現順): 一致  \[3, 4\]" "$B_OUT"; then
  ok "b. 陽性対照: run長を2→4に変えると報告も[3, 2]→[3, 4]に変わる(検出力の確認)"
else
  ng "b. run長を変えても報告が追随しなかった(決め打ちの疑い)"
  echo "$(grep 'バルク後run長' "$B_OUT")"
  overall_rc=1
fi

# --- c. 陽性対照その2: 伏せ字されていない壊れた入力を拒否すること ----------
gen "$WORK/c.iolog.txt" "3,2" "fb,eof" 1
C_OUT="$WORK/c_report.txt"
if python3 "$ANALYZE" --iolog "$WORK/c.iolog.txt" --label corrupt --out "$C_OUT" >/tmp/c_stdout.$$ 2>&1; then
  rc=0
else
  rc=$?
fi
if [[ "$rc" -ne 0 ]] && grep -q "解析不可" "$C_OUT"; then
  ok "c. 陽性対照: 伏せ字されていないデータポートを検出し解析を拒否する(rc=$rc)"
else
  ng "c. 伏せ字漏れの入力を拒否しなかった(黙って解析してしまった)"
  cat "$C_OUT" | sed 's/^/  /'
  overall_rc=1
fi
rm -f /tmp/c_stdout.$$

# --- d. 陽性対照その3: 窓(a)(b)が食い違う合成ログでは「不一致」と出ること --
gen "$WORK/d.iolog.txt" "2,2" "other,eof"
D_OUT="$WORK/d_report.txt"
run_analyze "$WORK/d.iolog.txt" "$D_OUT" >/dev/null
cat "$D_OUT" | sed 's/^/  /'
if grep -q "全体run長ヒストグラム: 不一致" "$D_OUT"; then
  ok "d. 陽性対照: 窓(a)(b)が食い違う合成ログでは「不一致」と報告される(検出力の確認)"
else
  ng "d. 窓(a)(b)を食い違わせても「一致」のままだった(検出力に疑いあり)"
  overall_rc=1
fi

echo
if [[ "$overall_rc" -eq 0 ]]; then
  echo "analyze_record_boundaries_selftest: OK(全項目)"
else
  echo "analyze_record_boundaries_selftest: 失敗あり"
fi
exit "$overall_rc"

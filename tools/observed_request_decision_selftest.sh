#!/usr/bin/env bash
# tools/observed_request_decision_selftest.sh — 要求グループ→応答決定関数
# (`_observed_single_by_request`)の selftest（公式環境不要）。
#
# 背景（第52版・m7ap、docs/notes/m7ap-*.md）: この決定関数は
# tools/verify_l3.sh では**一度も踏まれない**。故障注入で確認済み——
# 表の応答値を1ビット変えても、表の並び順を逆にしても、verify_l3.sh の
# 出力は1文字も変わらなかった。第51版までの9段の即値比較チェーンを
# 第52版でテーブル駆動へ書き換えるにあたり、「verify_l3.sh が不変だった」
# ではこの書き換えの妥当性を何も担保できないため、独立の検出力を用意した。
#
# 検査すること:
#   1. 9つの要求グループそれぞれで、実装（ROMバイト列の実行）と定義
#      （OBSERVED_SINGLE_RESPONSE_BY_REQUEST を上から見る参照モデル）が
#      同じ応答値・同じ送信ルーチンを選ぶこと
#   2. 各グループの各バイトを1つずつ変えた全ケースでも両者が一致すること
#      （順序依存・部分一致の取り違えをここで捕まえる）
#   3. どのグループにも一致しない要求がフォールバックへ落ちること
#   4. 陽性対照: 表・解釈器をわざと壊すと 1〜3 が落ちること（検出力の確認）
#
# 値（応答バイトの中身）は表示しない。一致/不一致とケース数だけを扱う。

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }

overall_rc=0

run_probe() {   # $1 = 故障注入モード名（"none" で無傷）
  PC88_DECISION_FAULT="$1" python3 - <<'EOF'
import os, sys
sys.path.insert(0, "tools")
sys.path.insert(0, "src/l3_service")
import make_subrom as m
import observed_request_decision_probe as probe

fault = os.environ.get("PC88_DECISION_FAULT", "none")

a = m.build_subrom()
a.resolve()

if fault == "swap_response":
    # 表の中の応答値の位置を1つ壊す（エントリ2の応答値を1ビット反転）
    base = a.labels["_observed_request_table"]
    # エントリ0: run_len兼送信種別,期待値[n],応答値
    pos = base
    for i, (hdr, _resp) in enumerate(m.OBSERVED_SINGLE_RESPONSE_BY_REQUEST):
        if i == 2:
            a.code[pos + 1 + len(hdr)] ^= 0x01   # 応答値
            break
        pos += 1 + len(hdr) + 1
elif fault == "swap_send_kind":
    # 送信ルーチンの種別を全エントリで反転する
    pos = a.labels["_observed_request_table"]
    for hdr, _resp in m.OBSERVED_SINGLE_RESPONSE_BY_REQUEST:
        a.code[pos] ^= 0x80
        pos += 1 + len(hdr) + 1
elif fault == "short_compare":
    # 極小Z80側で各エントリの最終1バイト比較を省略する。
    # 圧縮後の表はrun_lenと比較長が同じフィールドなので、表を書き換えると
    # エントリ境界まで壊れて例外になる。それでは陽性対照にならない。
    pass
elif fault != "none":
    print(f"未知の故障注入モード: {fault}")
    sys.exit(2)

bad = 0
total = 0
first_mismatch = None

def check(run_len, hdr_bytes):
    global bad, total, first_mismatch
    total += 1
    reason = probe.compare(a, run_len, hdr_bytes,
                           short_compare=(fault == "short_compare"))
    if reason:
        bad += 1
        if first_mismatch is None:
            first_mismatch = reason

# 1. 9グループそのもの
for hdr, _resp in m.OBSERVED_SINGLE_RESPONSE_BY_REQUEST:
    check(len(hdr), list(hdr) + [0xAA] * 8)
# 2. 各バイトを1つずつ変えた全ケース
for hdr, _resp in m.OBSERVED_SINGLE_RESPONSE_BY_REQUEST:
    for k in range(len(hdr)):
        for delta in (0x01, 0x80, 0xFF):
            mutated = list(hdr)
            mutated[k] = (mutated[k] ^ delta) & 0xFF
            check(len(hdr), mutated + [0xAA] * 8)
    # run_len だけ違うケース
    for rl in (0, 1, 2, 3, 8, 9, 255):
        if rl == len(hdr):
            continue
        check(rl, list(hdr) + [0xAA] * 8)
# 3. どのグループにも一致しない要求
for rl in range(0, 10):
    check(rl, [0x5A] * 16)

print(f"cases={total} mismatch={bad}")
if first_mismatch is not None:
    print(f"first_mismatch={first_mismatch}")
# 比較不一致は専用rcにする。Pythonの未捕捉例外はrc=1なので区別できる。
sys.exit(10 if bad else 0)
EOF
}

say "無傷の実装が定義（参照モデル）と全ケースで一致すること"
out="$(run_probe none)"; rc=$?
echo "  $out"
if [ "$rc" -eq 0 ]; then
  ok "実装（ROMバイト列の実行）と定義が全ケースで一致した"
else
  ng "実装と定義が食い違うケースがある"
  overall_rc=1
fi

for fault in swap_response swap_send_kind short_compare; do
  say "陽性対照: 故障注入 '$fault' で不一致が検出されること"
  out="$(run_probe "$fault")"; rc=$?
  echo "  $out"
  if [ "$rc" -eq 10 ]; then
    ok "陽性対照 '$fault': 期待どおり不一致として検出された"
  else
    ng "陽性対照 '$fault': 比較不一致で検出できなかった（rc=${rc}、例外なら陽性対照の空振り）"
    overall_rc=1
  fi
done

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "observed_request_decision_selftest: OK（全項目）"
else
  echo "observed_request_decision_selftest: 失敗あり"
fi
exit "$overall_rc"

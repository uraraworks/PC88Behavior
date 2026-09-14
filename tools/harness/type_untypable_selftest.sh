#!/usr/bin/env bash
# q88measure --type の「打てない文字」検出の自己検査（公式ROM不要）。
#
# main.c の ascii_to_retrok は英字・SHIFT対応表・ASCII 0x20-0x3F 以外の
# 文字に対して0を返す。以前はそれを stderr に警告するだけで走行を続けて
# おり、警告を読み落とすと欠けた打鍵列のまま「正常終了」して測定が
# 黙って壊れた（docs/notes/l4-s1a-text-vram-preregistration-addendum.md
# 4.）。この検査は次の3点を確認する:
#   1. 打てない文字(例 '@')を含む --type は、走行を始める前にrc!=0で
#      止まり、stderrに何文字目のどのコードかが出ること
#   2. 打てる文字だけの --type は（--coreが無い等の別理由を除き）この
#      検出には引っかからないこと
#   3. 検出そのものを無効化する故障注入
#      （Q88MEASURE_FAULT_SKIP_UNTYPABLE_CHECK）をすると、1.が素通り
#      して「打てない文字を無視」の警告だけになり、NGとして検出できる
#      こと（＝この検査自身の検出力の確認）
#
# --core を渡していないが問題ない。--type の文字チェックは argv 走査中
# （dlopenより前）に行われるため、コア無しでも検査できる。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-typeuntypable.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

make -s -C "$FRONTEND_DIR"

# --- 1. 打てない文字は走行前にrc!=0で止まる -------------------------------
set +e
"$FRONTEND" --type 'A@B' >"$WORK/bad.stdout" 2>"$WORK/bad.stderr"
bad_rc=$?
set -e
[ "$bad_rc" -ne 0 ] || ng "打てない文字'@'を含む--typeを弾けない"
grep -q -- '--type に打てない文字がある(2文字目): 0x40' "$WORK/bad.stderr" \
  || ng "打てない文字の分類メッセージ(何文字目・コード)が無い"
# --coreが無いための使い方エラー(rc=2)とは別の終了コードであること
# （main.cのusage()はrc=2で終わる。schedule_typing失敗はrc=1で
#   区別しているので、rc=2ではないことも確認する）
[ "$bad_rc" -ne 2 ] || ng "打てない文字の検出が--core不足のusageエラーと区別できていない(rc=2)"
ok "打てない文字を含む--typeは走行前にrc=${bad_rc}で止まる"

# --- 2. 打てる文字だけなら、この検出には引っかからない ---------------------
set +e
"$FRONTEND" --type 'AB' >"$WORK/good.stdout" 2>"$WORK/good.stderr"
good_rc=$?
set -e
# --coreを渡していないのでusageで終わる(rc=2)のが正しい。打てない文字の
# 分類メッセージ(usage文面の一般論ではなく、実際に検出したときのメッセージ)
# が出ていないことだけを確認する。
if grep -q -- '--type に打てない文字がある' "$WORK/good.stderr" \
   || grep -q -- '打てない文字を無視' "$WORK/good.stderr"; then
  ng "打てる文字だけなのに打てない文字の警告/エラーが出た"
fi
[ "$good_rc" -eq 2 ] || ng "打てる文字だけの--typeで想定外のrc=${good_rc}(usageエラーrc=2以外)"
ok "打てる文字だけの--typeは従来どおり(この検出には引っかからない)"

# --- 3. 故障注入: 検出そのものを無効化すると1.が素通りする ----------------
set +e
Q88MEASURE_FAULT_SKIP_UNTYPABLE_CHECK=1 \
  "$FRONTEND" --type 'A@B' >"$WORK/fault.stdout" 2>"$WORK/fault.stderr"
fault_rc=$?
set -e
grep -q -- '打てない文字を無視(2文字目): 0x40' "$WORK/fault.stderr" \
  || ng "故障注入版の実行が失敗した(従来どおりの警告読み飛ばしになっていない)"
if grep -q -- '--type に打てない文字がある' "$WORK/fault.stderr"; then
  ng "故障注入(Q88MEASURE_FAULT_SKIP_UNTYPABLE_CHECK)をしたのに1.のエラーが出た(検出が無効化されていない)"
fi
[ "$fault_rc" -ne "$bad_rc" ] || ng "故障注入してもrcが1.と同じ(${bad_rc})のまま変化していない"
ok "故障注入(Q88MEASURE_FAULT_SKIP_UNTYPABLE_CHECK)で1.の検出が素通りすることを確認(rc=${fault_rc})"

# --allow-untypable も同じ「警告のみで素通り」を提供することの確認
set +e
"$FRONTEND" --allow-untypable --type 'A@B' >"$WORK/allow.stdout" 2>"$WORK/allow.stderr"
allow_rc=$?
set -e
grep -q -- '打てない文字を無視(2文字目): 0x40' "$WORK/allow.stderr" \
  || ng "--allow-untypableでも従来どおりの警告読み飛ばしにならない"
ok "--allow-untypable指定時は警告読み飛ばしになる(rc=${allow_rc})"

ok "全項目合格"

#!/usr/bin/env bash
# tools/m6fd_rewrap_add1.py の自己検査。合成のresult.jsonだけで完結する。
#   1. IV-R-*走・I-*走がそれぞれQZ7A/QZ7Bキーに包み直され、値(pos・bytes9_15)は
#      一切変わらないこと。
#   2. 対象外(II/III/IV-fill/V)の走はentry_fields=nullのまま変わらないこと。
#   3. 元のファイルが変更されないこと(別ファイルへ書く)。
#   4. 冪等性: 既に名前キーの走を渡しても変わらないこと。
#   5. 陰性対照: 出力先が入力と同じパスだとエラーになる。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

python3 - "$WORK/result.json" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
runs = [
    {"arm": "IV-R-14", "repetition": 1,
     "entry_fields": {"pos": {"c": 18, "h": 0, "r": 5, "offset": 0},
                       "bytes9_15": [0x20, 20, 0xEE, 0xEE, 0xEE, 0xEE, 0xEE]}},
    {"arm": "I-1", "repetition": 2,
     "entry_fields": {"pos": {"c": 18, "h": 1, "r": 3, "offset": 4},
                       "bytes9_15": [0x20, 5, 1, 2, 3, 4, 5]}},
    {"arm": "II-d", "phase": 2, "repetition": 1, "entry_fields": None},
    {"arm": "IV-fill-free", "repetition": 1, "entry_fields": None},
]
json.dump({"schema": 1, "runs": runs}, out.open("w", encoding="utf-8"), sort_keys=True, separators=(",", ":"))
PY

python3 "$REPO/tools/m6fd_rewrap_add1.py" "$WORK/result.json" "$WORK/rewrapped.json"
rewrap_rc=$?

VERIFY="$WORK/verify.py"
cat > "$VERIFY" <<'PYEOF'
import json, sys
from pathlib import Path
orig = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
new = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
fails = []
by_arm = {(r["arm"], r["repetition"]): r for r in new["runs"]}

ivr = by_arm[("IV-R-14", 1)]
if list(ivr["entry_fields"].keys()) != ["QZ7A"]:
    fails.append(f"IV-Rの走がQZ7Aキーで包まれていない: {ivr['entry_fields']!r}")
elif ivr["entry_fields"]["QZ7A"] != orig["runs"][0]["entry_fields"]:
    fails.append("IV-Rの走の値が変わった")

i1 = by_arm[("I-1", 2)]
if list(i1["entry_fields"].keys()) != ["QZ7B"]:
    fails.append(f"I-1の走がQZ7Bキーで包まれていない: {i1['entry_fields']!r}")
elif i1["entry_fields"]["QZ7B"] != orig["runs"][1]["entry_fields"]:
    fails.append("I-1の走の値が変わった")

iid = by_arm[("II-d", 1)]
if iid["entry_fields"] is not None:
    fails.append(f"対象外の走(II-d)のentry_fieldsが変わった: {iid['entry_fields']!r}")

fillfree = by_arm[("IV-fill-free", 1)]
if fillfree["entry_fields"] is not None:
    fails.append(f"対象外の走(IV-fill-free)のentry_fieldsが変わった: {fillfree['entry_fields']!r}")

if fails:
    for m in fails:
        print("NG: " + m)
    sys.exit(1)
print("OK: 包み直し後の値・キーを確認した")
sys.exit(0)
PYEOF

if [ "$rewrap_rc" -eq 0 ] && python3 "$VERIFY" "$WORK/result.json" "$WORK/rewrapped.json"; then
  ok "1〜3: IV-R/Iが名前キーに包まれ、値は不変、対象外はnullのまま"
else
  ng "包み直しの検査が失敗した(rc=$rewrap_rc)"
fi

if diff -q "$WORK/result.json" "$WORK/result.json.orig" >/dev/null 2>&1; then :; fi
cp "$WORK/result.json" "$WORK/result.json.orig"
python3 "$REPO/tools/m6fd_rewrap_add1.py" "$WORK/result.json" "$WORK/rewrapped2.json" >/dev/null 2>&1
if diff -q "$WORK/result.json" "$WORK/result.json.orig" >/dev/null 2>&1; then
  ok "3: 元のファイルは変更されない"
else
  ng "3: 元のファイルが変更された"
fi

# --- 4. 冪等性: 既に名前キーの走を渡しても変わらない -------------------------
if python3 "$REPO/tools/m6fd_rewrap_add1.py" "$WORK/rewrapped.json" "$WORK/rewrapped_twice.json" \
    >/dev/null 2>&1 && diff -q "$WORK/rewrapped.json" "$WORK/rewrapped_twice.json" >/dev/null 2>&1; then
  ok "4: 冪等性(既に名前キーの走はそのまま)"
else
  ng "4: 冪等性が成り立たない"
fi

# --- 5. 陰性対照: 出力先が入力と同じパス -------------------------------------
if python3 "$REPO/tools/m6fd_rewrap_add1.py" "$WORK/result.json" "$WORK/result.json" \
    >"$WORK/neg.out" 2>&1; then
  ng "5: 出力先=入力先でもエラーにならなかった"
else
  ok "5: 陰性対照(出力先=入力先): エラーで検出した"
fi

echo
if [ "$rc" -eq 0 ]; then echo "全項目 OK"; else echo "NG あり"; fi
exit "$rc"

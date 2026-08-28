#!/usr/bin/env bash
# m7daの44セクタ交互配置を、合成座標だけで検査する。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
overall=0; detected=0; faults=4
ok() { echo "  OK   $1"; }
ng() { echo "  NG   $1"; overall=1; }

python3 - "$WORK" <<'PY'
import json
import pathlib
import sys

w = pathlib.Path(sys.argv[1])
payload = 44 * 256
base = {
    "read_lengths": [1, 14, 16, 16, 2],
    "preamble_per_port": {"FC": 3, "FD": 3},
    "regular": [
        {"port": "FC" if i % 2 == 0 else "FD",
         "coord": i + 1 if i < payload - 1 else payload - 1}
        for i in range(payload)
    ],
}

def write(name, obj):
    (w / name).write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")

write("normal.json", base)

missing = json.loads(json.dumps(base))
del missing["regular"][100]
write("missing-one.json", missing)

swapped = json.loads(json.dumps(base))
for event in swapped["regular"]:
    event["port"] = "FD" if event["port"] == "FC" else "FC"
write("ports-swapped.json", swapped)

tail = json.loads(json.dumps(base))
tail["regular"][-1]["coord"] = payload
write("tail-duplicate-missing.json", tail)

read_length = json.loads(json.dumps(base))
read_length["read_lengths"][-1] += 1
write("read-length-plus-one-sector.json", read_length)
PY

normal="$(python3 tools/check_5635_origin_structure.py "$WORK/normal.json" 2>&1)"
if grep -q 'FC=5632+3=5635 FD=5632+3=5635 末尾重複=1件' <<<"$normal"; then
  ok "3+5632の正常形を陽性対照として受理した"
else
  ng "正常形を受理しなかった"; printf '%s\n' "$normal"
fi

for fixture in missing-one ports-swapped tail-duplicate-missing read-length-plus-one-sector; do
  if python3 tools/check_5635_origin_structure.py "$WORK/$fixture.json" >/dev/null 2>&1; then
    ng "故障 $fixture を受理した"
  else
    detected=$((detected+1)); ok "故障 $fixture を検出した"
  fi
done

if [ "$detected" -ne "$faults" ]; then
  ng "故障注入の空振り $((faults-detected))件"
fi
echo "check_5635_origin_structure_selftest: 検出 ${detected}/${faults}、空振り $((faults-detected))"
exit "$overall"

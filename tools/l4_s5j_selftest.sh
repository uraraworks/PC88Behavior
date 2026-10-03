#!/usr/bin/env bash
# l4-s5jの合成対照と自作ROMの陰性対照。公式ROMは使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO/tests/conformance/expected_l4_s5j.tsv" <<'PY'
import pathlib
import re
import sys

lines = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines()
rows = [line.split('\t') for line in lines if line and not line.startswith('#')]
ids = {row[0] for row in rows}
assert len(rows) == len(ids) == 113
assert ids == ({f'b{i:02d}' for i in range(1, 37)}
               | {f'a{i:02d}' for i in range(1, 79) if i != 71})
assert '# excluded a71 打鍵器具が @ を打てない' in lines
assert all(len(row) == 2 and re.fullmatch(r'[0-9a-f]{16}|no_line', row[1])
           for row in rows)
print('OK 期待値の形・B群36腕/A群77腕・a71除外・署名形式')
PY
python3 "$REPO/tools/l4_s5j_measure.py" selftest "$@"

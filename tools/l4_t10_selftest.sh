#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
root=$(pwd)
# 初回器具はEDIT実行後にも打鍵行が残る前提。MOTORの回帰だけを
# 従来の入口で測り、EDIT自体は追補1で現行ROMを測る。
fixture="$root/tmp/impl4-work/t10-motor-fixture"
mkdir -p "$fixture/project" "$root/tmp/t10-work/selftest"
cp -R src tools "$fixture/project/"
ln -sfn "$root/../vendor" "$fixture/vendor"
python3 - "$fixture/project" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
needle = '    CALL N_EDIT_STMT\n    OR A\n    RET NZ\n'
for name in ('interp.asm', 'run.asm'):
    path = root / 'src/l4_basic' / name
    data = path.read_text()
    if data.count(needle) != 1:
        raise SystemExit('EDIT入口の検査用置換が一意でない')
    path.write_text(data.replace(needle, '    NOP\n' * 5))
PY
work="$fixture/project/tmp/t10-work/selftest"
python3 "$fixture/project/tools/l4_t10_editmotor_measure.py" selftest
cp "$work/actual.json" "$root/tmp/t10-work/selftest/actual.json"
python3 tools/l4_t10_editmotor_measure.py expected --measured "$work/actual.json" --out "$work/expected-cli.json"
python3 tools/l4_t10_editmotor_measure.py check --measured "$work/actual.json" --expected "$work/expected-cli.json"
python3 - "$work/expected-cli.json" "$work/broken.json" <<'PY'
import json, sys
from pathlib import Path
source,target=map(Path,sys.argv[1:]); data=json.loads(source.read_text())
for run in data['records']['ref-none']['runs']: run['screen']['operationa']['6'][0]^=1
target.write_text(json.dumps(data,ensure_ascii=False))
PY
if python3 tools/l4_t10_editmotor_measure.py check --measured "$work/actual.json" --expected "$work/broken.json"; then
    echo 'CLI陰性対照失敗' >&2; exit 1
fi
printf '%s\n' 'CLI陰性対照: 壊した期待値を拒否'

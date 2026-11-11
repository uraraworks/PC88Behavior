#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
mkdir -p tmp/t11-work
${CC:-cc} -std=c99 -D_POSIX_C_SOURCE=200809L -I../vendor/quasi88-libretro/src/LIBRETRO/libretro-common/include -Itools/harness/core tools/harness/sound_board_selftest.c -ldl -o tmp/t11-work/sound-board-selftest
tmp/t11-work/sound-board-selftest
for round in first addendum1 addendum2; do
work=tmp/t11-work/selftest
[ "$round" = first ] || work=tmp/t11-work/selftest-$round
python3 tools/l4_t11_soundplay_measure.py selftest --round "$round"
python3 tools/l4_t11_soundplay_measure.py expected --round "$round" --measured "$work/actual.json" --out "$work/expected-cli.json"
python3 tools/l4_t11_soundplay_measure.py check --round "$round" --measured "$work/actual.json" --expected "$work/expected-cli.json"
python3 - "$work/expected-cli.json" "$work/broken.json" <<'PY'
import json, sys
from pathlib import Path
source,target=map(Path,sys.argv[1:]); data=json.loads(source.read_text())
for run in data['records']['A/ref-none' if data['round']=='addendum2' else 'ref-none']['runs']: run['screen']['operationa']['6'][0]^=1
target.write_text(json.dumps(data,ensure_ascii=False))
PY
if python3 tools/l4_t11_soundplay_measure.py check --round "$round" --measured "$work/actual.json" --expected "$work/broken.json"; then
    echo 'CLI陰性対照失敗' >&2; exit 1
fi
printf '%s\n' 'CLI陰性対照: 壊した期待値を拒否'
done
for round in addendum1 addendum2; do
if env -u PC88_REF_DISK_DIR python3 tools/l4_t11_soundplay_measure.py measure --round "$round" --official --rom-dir tmp/t11-work/absent-rom --work-dir tmp/t11-work/negative --out tmp/t11-work/negative.json > tmp/t11-work/missing-env.txt; then
    echo '環境変数の陰性対照失敗' >&2; exit 1
fi
if ! rg -q '^PC88_REF_DISK_DIR_missing$' tmp/t11-work/missing-env.txt; then
    echo '環境変数の拒否理由が不一致' >&2; exit 1
fi
printf '%s\n' '環境変数なしを拒否'
done
if python3 tools/l4_t11_soundplay_measure.py expected --round addendum1 --measured tmp/t11-work/selftest/actual.json --out tmp/t11-work/wrong-round.json; then
    echo 'ラウンド不一致の陰性対照失敗' >&2; exit 1
fi
printf '%s\n' 'ラウンド不一致を拒否'

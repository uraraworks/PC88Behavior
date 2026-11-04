#!/usr/bin/env bash
# 合成 ROM だけで画面ハッシュの決定性・変化・非漏洩を検査する。
# 故障注入: 検査直前に最初のログを空にすると行数検査が失敗する（実施済み）。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)}"
WORK="${TMPDIR:-/tmp}/pc88-frame-hash.$$"
trap 'rm -rf "$WORK"' EXIT
[ -n "$CORE" ] || { echo 'コアがない' >&2; exit 1; }
mkdir -p "$WORK/a" "$WORK/b" "$WORK/font"
make -s -C "$REPO/tools/harness/frontend"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/font" --enable-font > /dev/null
python3 "$REPO/src/l1_ipl/make_ipl_rom.py" "$WORK/a" --font-sample > /dev/null
python3 "$REPO/src/l1_ipl/make_ipl_rom.py" "$WORK/b" > /dev/null
cp "$WORK/font/FONT.ROM" "$WORK/a/FONT.ROM"
cp "$WORK/font/FONT.ROM" "$WORK/b/FONT.ROM"
front="$REPO/tools/harness/frontend/q88measure"
for run in 1 2 3; do
  rom=a; [ "$run" != 3 ] || rom=b
  "$front" --core "$CORE" --rom-dir "$WORK/$rom" --frames 60 --type 'SECRETTEST' \
    --frame-hash-every 10 --frame-hash-log "$WORK/$run.fh" --screenshot "$WORK/$run.ppm" --out "$WORK/$run.out" \
    >"$WORK/$run.stdout" 2>"$WORK/$run.stderr"
done
[ "${FRAME_HASH_TEST_BREAK:-0}" != 1 ] || : > "$WORK/1.fh"
python3 - "$WORK" <<'PY'
import hashlib, pathlib, re, sys
w = pathlib.Path(sys.argv[1])
logs = [(w / f'{i}.fh').read_text() for i in (1, 2, 3)]
for log in logs:
    lines = log.splitlines()
    assert len(lines) == 60 // 10
    assert all(re.fullmatch(r'[0-9]+ [0-9a-f]{64}', line) for line in lines)
    assert [int(line.split()[0]) for line in lines] == list(range(10, 61, 10))
for i, log in enumerate(logs, 1):
    ppm = (w / f'{i}.ppm').read_bytes()
    header = b'P6\n640 400\n255\n'
    assert ppm.startswith(header)
    assert hashlib.sha256(ppm[len(header):]).hexdigest() == log.splitlines()[-1].split()[1]
assert logs[0] == logs[1]
assert logs[0] != logs[2]
for i in (1, 2, 3):
    for suffix in ('fh', 'stdout', 'stderr'):
        text = (w / f'{i}.{suffix}').read_text()
        assert 'SECRETTEST' not in text
        assert not re.search(r'(?<![0-9a-fA-F])[0-9a-fA-F]{65,}(?![0-9a-fA-F])', text)
PY
for args in '--frame-hash-every 10' "--frame-hash-log $WORK/missing" "--frame-hash-every 0 --frame-hash-log $WORK/zero"; do
  rc=0
  # 引数はこのスクリプト内の固定値のみ。
  # shellcheck disable=SC2086
  "$front" --core "$CORE" --rom-dir "$WORK/a" $args > /dev/null 2>&1 || rc=$?
  [ "$rc" -eq 2 ] || { echo "引数検査が失敗: rc=$rc" >&2; exit 1; }
done
echo '画面ハッシュ自己検査: 合格'

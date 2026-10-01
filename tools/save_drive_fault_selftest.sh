#!/usr/bin/env bash
# hybrid(自作main＋公式sub)の J-1(ドライブ2宛て)/J-D1(ドライブ1宛て)が
# 「書き込み先ドライブ D の誤り」を検出できるかの故障注入。
# s2_write_stream 先頭の `AND 1`(E6 01)を、ビルド後の N88_2.ROM 上で
#   AND 0 (D常に0=ドライブ1) / OR 1 (D常に1=ドライブ2) に書き換える。src は不変。
# 狙いの段で落ちたことを conform_save.sh が残す stage.txt で確かめる:
#   frontend_rc=0（タイムアウト等の手前で落ちていない）・compare=ng（宛先に読み戻せない）、
#   および可能な腕では other_drive=changed（誤ったドライブへ書かれた）。
# 公式環境(PC88_REF_ROM_DIR/PC88_REF_DISK_DIR)が無ければ SKIP で rc=0。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "${PC88_REF_ROM_DIR:-}" ] || [ -z "${PC88_REF_DISK_DIR:-}" ] ||
   [ ! -f "${PC88_REF_ROM_DIR}/DISK.ROM" ] || [ ! -f "${PC88_REF_DISK_DIR}/N88_FE.D88" ]; then
  echo "SKIP 公式環境なし"; exit 0
fi
WORK="$(mktemp -d "${TMPDIR:-/tmp}/save-drive-fault.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
ng() { printf 'NG %s\n' "$1" >&2; exit 1; }
python3 "$REPO/src/build_main_rom.py" "$WORK/good" >"$WORK/build.out" 2>"$WORK/build.err" || ng ビルド
stage() { # run_dir key
  sed -n "s/^$2=//p" "$1/stage.txt"
}
run_arm() { # tag romdir
  local rc=0
  SAVE_CONFORM_TEST_ROM_DIR="$2" PC88_SAVE_CONFORM_WORK="$WORK/$1.work" \
    bash "$REPO/tools/conform_save.sh" hybrid >"$WORK/$1.out" 2>"$WORK/$1.err" || rc=$?
  printf '%s' "$rc"
}
# 陽性対照: 壊さないビルドは両腕 OK
[ "$(run_arm good "$WORK/good")" -eq 0 ] || ng 陽性対照
for arm in J-1 J-D1; do
  grep -qx "$arm"$'\tOK' "$WORK/good.out" || ng "陽性対照 $arm"
  [ "$(stage "$WORK/good.work/runs/$arm" compare)" = ok ] || ng "陽性対照段 $arm"
done
inject() { # tag replacement-hex
  cp -R "$WORK/good" "$WORK/$1"
  python3 - "$REPO" "$WORK/$1/N88_2.ROM" "$2" <<'PY'
from pathlib import Path
import sys
repo, path, repl = Path(sys.argv[1]), Path(sys.argv[2]), bytes.fromhex(sys.argv[3])
sys.path.insert(0, str(repo / 'tools' / 'asm'))
import z80text
asm = z80text.Assembler()
asm.assemble(repo / 'src' / 'ext_bank' / 'bank2.asm')
offset = asm.labels['s2_write_stream'] - 0x6000
rom = bytearray(path.read_bytes())
if rom[offset:offset + 2] != b'\xe6\x01':
    raise SystemExit('NG: 故障注入位置')
rom[offset:offset + 2] = repl
path.write_bytes(rom)
PY
}
expect_ng() { # tag badarm goodarm other_drive_must_change(0/1)
  local rc
  rc="$(run_arm "$1" "$WORK/$1")"
  [ "$rc" -eq 1 ] || ng "$1 rc=$rc"
  grep -qx "$2"$'\tNG' "$WORK/$1.out" || ng "$1 $2 がNGでない"
  grep -qx "$3"$'\tOK' "$WORK/$1.out" || ng "$1 $3 がOKでない（腕の弁別なし）"
  local d="$WORK/$1.work/runs/$2"
  [ "$(stage "$d" frontend_rc)" = 0 ] || ng "$1 手前で落ちた(frontend)"
  if [ "$4" = 1 ]; then
    [ "$(stage "$d" other_drive)" = changed ] || ng "$1 もう一方のドライブ不変の段で落ちていない"
  fi
  [ "$(stage "$d" compare)" = ng ] || ng "$1 読み戻し照合の段で落ちていない"
  printf '%s\t%s NG（frontend_rc=0, other_drive=%s, compare=ng）、%s OK\n' "$1" "$2" "$(stage "$d" other_drive)" "$3"
}
inject d_always_drive1 e600   # AND 0: D=0 → ドライブ1固定
inject d_always_drive2 f601   # OR 1 : D=1 → ドライブ2固定
# 公式 N88_FE のドライブ1は D=0 で書かせても書き換わらない（other_drive=ok）ため、
# この故障は読み戻し照合(compare)の段だけが検出する。ドライブ2側は両段が検出する。
expect_ng d_always_drive1 J-1 J-D1 0
expect_ng d_always_drive2 J-D1 J-1 1
echo OK

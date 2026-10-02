#!/usr/bin/env bash
# 自作mainのKILL/NAMEを、m6f-kの全10腕・各2走で公式の判定に照合する。
# hybridだけ公式DISK.ROMをコピーする。測定は親が明示して実行する。
# PC88_KILLNAME_CONFORM_WORK はリポジトリ外の未使用パスを指定する。
# 成功後の通常の入力待ちOkはG5で検査する。凍結測定器を迂回・改変しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-local}"
case "$MODE" in local|hybrid) ;; *) printf 'NG モード\n' >&2; exit 2;; esac
CHECK="$REPO/tools/killname_conform_check.py"
EXPECTED="$REPO/tools/killname_conform_expected.tsv"
python3 "$CHECK" validate "$EXPECTED" >/dev/null
if [ "$MODE" = hybrid ] && [ ! -f "${PC88_REF_ROM_DIR:-}/DISK.ROM" ]; then
  printf 'hybrid\t未実施\t公式環境なし\n'; exit 3
fi
if [ -n "${PC88_KILLNAME_CONFORM_WORK:-}" ]; then
  WORK="$PC88_KILLNAME_CONFORM_WORK"
  KEEP=1
else
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/killname-conform.XXXXXX")"
  rmdir "$WORK"
  KEEP=0
fi
# パス検査はmkdir・ビルド・公式ファイルのコピーより先に行う。
python3 - "$REPO" "$WORK" <<'PY'
from pathlib import Path
import sys
repo,work=map(lambda x:Path(x).resolve(),sys.argv[1:])
if work == repo or repo in work.parents or work.exists():
    raise SystemExit('NG 作業先はリポジトリ外の未使用パスが必要')
PY
mkdir -p "$WORK/rom" "$WORK/media"
trap '[ "$KEEP" -eq 1 ] || rm -rf "$WORK"' EXIT
python3 "$REPO/src/build_main_rom.py" "$WORK/rom" >"$WORK/build.out" 2>"$WORK/build.err" || {
  rg -i 'error|エラー' "$WORK/build.err" >&2 || true
  exit 2
}
if [ "$MODE" = hybrid ]; then
  cp "$PC88_REF_ROM_DIR/DISK.ROM" "$WORK/rom/DISK.ROM"
fi
# ドライブ1も合成媒体。自作mainは公式起動媒体を必要としない。
python3 - "$REPO/tools" "$WORK/media/N88_FE.D88" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1])
from make_m6fk_disk import build
Path(sys.argv[2]).write_bytes(build('KM'))
PY
source "$REPO/tools/lib_l3_measure.sh"
ensure_l3_frontend
PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/media" \
  bash "$REPO/tools/measure_m6fk.sh" --work "$WORK/measure" --result "$WORK/result.json" \
  --arms K-1,K-2,K-3,K-4,N-1,N-2,N-3,N-4,N-5,N-6 \
  >"$WORK/measure.out" 2>"$WORK/measure.err" || {
    printf '%s\tNG\t測定ゲート\n' "$MODE"
    exit 1
  }
python3 "$CHECK" compare "$EXPECTED" "$WORK/result.json"

#!/usr/bin/env bash
# no_disk / unreadable_diskを公式・混成各1走し、値なし交換構造まで一括解析する。
# 生iologを保存するため、出力先は必ずリポジトリ外を指定する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"

usage() {
  cat <<'EOF'
使い方:
  PC88_ERROR_SHAPE_OPT_IN=1 \
  PC88_REF_ROM_DIR=/path/to/rom PC88_REF_DISK_DIR=/path/to/disk \
    tools/measure_error_exchange_shape.sh --out-dir /path/to/output

公式環境を使う実測なので PC88_ERROR_SHAPE_OPT_IN=1 が必須。
出力先には conform_l3.sh と同名規則の生iolog 4個と、値なし解析報告2個を置く。
EOF
}

OUT_DIR=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --out-dir)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      OUT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "エラー: 未知の引数: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "${PC88_ERROR_SHAPE_OPT_IN:-}" != "1" ]; then
  echo "SKIP: 公式環境の実測は未実行（PC88_ERROR_SHAPE_OPT_IN=1 が必要）"
  echo "SKIPは合格ではないため終了コード3を返す。"
  exit 3
fi
if [ -z "${PC88_REF_ROM_DIR:-}" ] || [ -z "${PC88_REF_DISK_DIR:-}" ]; then
  echo "SKIP: PC88_REF_ROM_DIR / PC88_REF_DISK_DIR が未設定。実測は未実行。" >&2
  echo "SKIPは合格ではないため終了コード3を返す。" >&2
  exit 3
fi
if [ -z "$OUT_DIR" ]; then
  echo "エラー: --out-dir が必要" >&2
  usage >&2
  exit 2
fi

mkdir -p "$OUT_DIR" || exit 1
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
case "$OUT_DIR/" in
  "$REPO/"*)
    echo "エラー: 生iologを含むため --out-dir はリポジトリ外を指定すること" >&2
    exit 2
    ;;
esac

DISK="$PC88_REF_DISK_DIR/N88_FE.D88"
if [ ! -f "$DISK" ]; then
  echo "エラー: 参照ディスクが無い（PC88_REF_DISK_DIR/N88_FE.D88）" >&2
  exit 1
fi
CORE="$(find_l3_core)"
if [ -z "$CORE" ]; then
  echo "エラー: コアが無い。先に tools/setup_harness.sh を実行すること" >&2
  exit 1
fi
ensure_l3_frontend || exit 1
FRONTEND="$REPO/tools/harness/frontend/q88measure"
ENTRY_TIMEOUT=300
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

targets=(
  path.no_disk.official.run1.iolog.txt
  path.no_disk.mixed.run1.iolog.txt
  path.unreadable_disk.official.run1.iolog.txt
  path.unreadable_disk.mixed.run1.iolog.txt
  error-exchange-shape.no_disk.txt
  error-exchange-shape.unreadable_disk.txt
)
for target in "${targets[@]}"; do
  if [ -e "$OUT_DIR/$target" ]; then
    echo "エラー: 既存出力を上書きしない: $OUT_DIR/$target" >&2
    exit 1
  fi
done

copy_roms() {
  local mode="$1" destination="$2" file copied=0
  mkdir -p "$destination"
  if [ "$mode" = official ]; then
    for file in "$PC88_REF_ROM_DIR"/*.ROM; do
      [ -f "$file" ] || continue
      cp -p "$file" "$destination"/ || return 1
      copied=1
    done
    [ "$copied" -eq 1 ] || return 1
  else
    build_mixed_rom "$PC88_REF_ROM_DIR" "$destination" || return 1
  fi
}

measure_one() {
  local scenario="$1" mode="$2"
  local base="$WORK/path.${scenario}.${mode}.run1"
  local rom="$base.rom" disk_a="$base.a.d88" disk_b="$base.b.d88"
  local media frames iolog="$base.iolog.txt" rc
  copy_roms "$mode" "$rom" || return 1
  cp "$DISK" "$disk_a" || return 1
  case "$scenario" in
    no_disk)
      media="$disk_a"
      frames=800
      ;;
    unreadable_disk)
      python3 "$REPO/tools/make_l3_testdisk.py" "$disk_b" >/dev/null || return 1
      printf '%s\n' "$disk_a" "$disk_b" > "$base.m3u"
      media="$base.m3u"
      frames=3000
      ;;
    *) return 2 ;;
  esac
  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$ENTRY_TIMEOUT" \
    "$FRONTEND" --core "$CORE" --rom-dir "$rom" --disk "$media" \
    --frames "$frames" --io-log "$iolog" --out "$base.report.txt" \
    --type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n' \
    >"$base.stdout.txt" 2>"$base.stderr.txt"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "エラー: $scenario/$mode の実測失敗または${ENTRY_TIMEOUT}秒上限（rc=$rc）" >&2
    return "$rc"
  fi
  if grep -Eq '^# 取りこぼし: [1-9][0-9]*件' "$iolog"; then
    echo "エラー: $scenario/$mode のI/Oログに取りこぼしがある" >&2
    return 3
  fi
  echo "OK: $scenario/$mode（I/Oログ取りこぼし0件）"
}

for scenario in no_disk unreadable_disk; do
  for mode in official mixed; do
    measure_one "$scenario" "$mode" || exit 1
  done
  python3 "$REPO/tools/analyze_error_exchange_shape.py" \
    --official "$WORK/path.${scenario}.official.run1.iolog.txt" \
    --mixed "$WORK/path.${scenario}.mixed.run1.iolog.txt" \
    --label "$scenario" --out "$WORK/error-exchange-shape.${scenario}.txt" || exit 1
  echo "OK: $scenario の値なし交換構造を解析"
done

for target in "${targets[@]}"; do
  mv "$WORK/$target" "$OUT_DIR/$target" || exit 1
done
echo "完了: 生iolog 4個と値なし解析報告2個を指定出力先へ保存した。"

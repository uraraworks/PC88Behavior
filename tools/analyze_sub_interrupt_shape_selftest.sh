#!/usr/bin/env bash
# 無傷ログ（陰性対照）は合格し、main直前イベント注入（陽性対照）は落ちる。
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

make_io() {
  local injected="$1"
  {
    echo '# seq clock frame cpu kind port value pc'
    echo '1 10 1 sub OUT 00FB -- 0100'
    if [ "$injected" = yes ]; then
      echo '1 11 1 main OUT 0040 00 0200'
    fi
    echo '2 13 1 sub IN 00FA 00 0101'
    echo '3 14 1 sub OUT 00FB -- 0102'
    echo '4 15 1 sub IN 00FA 00 0103'
    echo '5 16 1 sub IN 00FB -- 0104'
    echo '6 17 1 sub IN 00FA 00 0105'
    echo '7 18 1 sub IN 00FB -- 0106'
  } >"$TMP/$injected.io"
}

make_io no
make_io yes
{
  echo '# seq clock frame cpu im level ret_pc handler_pc'
  echo '1 12 1 sub 0 0 0101 0101'
  echo '# 取りこぼし: 0件 / 総イベント数: 1件'
} >"$TMP/int"

if ! python3 "$REPO/tools/analyze_sub_interrupt_shape.py" \
    --iolog "$TMP/no.io" --intlog "$TMP/int" --check >/dev/null 2>&1; then
  echo 'NG: 無傷の合成ログ（陰性対照）が不合格'
  exit 1
fi

set +e
python3 "$REPO/tools/analyze_sub_interrupt_shape.py" \
  --iolog "$TMP/yes.io" --intlog "$TMP/int" --check >/dev/null 2>&1
fault_rc=$?
set -e
if [ "$fault_rc" -ne 1 ]; then
  echo "NG: main直前イベント注入（陽性対照）がrc=1にならない（rc=${fault_rc}）"
  exit 1
fi

echo 'OK: 無傷の合成ログ（陰性対照） rc=0'
echo 'OK: main直前イベント注入（陽性対照） rc=1（故障を検出）'

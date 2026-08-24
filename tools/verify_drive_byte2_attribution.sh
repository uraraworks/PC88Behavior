#!/usr/bin/env bash
# 要求byte2 bit0の恒久伝播に対する回帰検査。既定ROMでB:のFDC
# unit/head差が公式に対して0件となり、故障注入版では差が出ることを確認する。
#
# 公式ROM・ディスクの内容は読まず、使い捨て複製と測定フックにだけ
# 渡す。生ログ、媒体複製、M3U、標準出力はmktemp配下にだけ置く。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
COMPARE="$REPO/tools/compare_l3_entry_fdc.py"
RUN_TIMEOUT=300
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; }

# 既定ROMは差なし、故障注入版は差あり、の両方を必須にする。
judge_counts() {
  local default="$1" broken="$2"
  [ "$default" -eq 0 ] 2>/dev/null && [ "$broken" -gt 0 ] 2>/dev/null
}

extract_diff_count() {
  awk '/^入口区間のunit\/head差件数: [0-9]+件$/ {
         sub(/.*: /, ""); sub(/件$/, ""); print
       }' "$1"
}

compare_count() {
  local official="$1" mixed="$2" out="$3" count rc
  python3 "$COMPARE" --official "$official" --mixed "$mixed" \
    --after-frame 700 >"$out" 2>"${out}.err"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    return 2
  fi
  count="$(extract_diff_count "$out")"
  if ! [[ "$count" =~ ^[0-9]+$ ]]; then
    return 2
  fi
  printf '%s\n' "$count"
}

make_synthetic_log() {
  local path="$1" unit="$2"
  python3 - "$path" "$unit" <<'PYEOF'
import sys

path, unit = sys.argv[1], int(sys.argv[2])
# 公開μPD765形式のSENSE DRIVE STATUS。公式データは不使用。
events = (("OUT", 0x04), ("OUT", unit), ("IN", 0x20 | unit))
with open(path, "w", encoding="utf-8") as fp:
    fp.write("# 合成FDCログ、公式データ不使用\n# sub\n")
    for seq, (kind, value) in enumerate(events, 1):
        fp.write(f"{seq:6d} {seq:6d} 700 sub {kind:<4} 00FB {value:02X} 0100\n")
PYEOF
}

run_selftest() {
  local base="$WORK/selftest.official.txt"
  local default="$WORK/selftest.default.txt"
  local broken="$WORK/selftest.broken.txt"
  local injected_default="$WORK/selftest.injected-default.txt"
  local injected_broken="$WORK/selftest.injected-broken.txt"
  local c_default c_broken c_injected_default c_injected_broken rc=0

  make_synthetic_log "$base" 1
  make_synthetic_log "$default" 1
  make_synthetic_log "$broken" 0
  # 故障注入1: 既定ROM側にunit差を入れる。
  make_synthetic_log "$injected_default" 0
  # 故障注入2: 故障注入版側のunit差を消す。
  make_synthetic_log "$injected_broken" 1

  c_default="$(compare_count "$base" "$default" "$WORK/selftest.default.out")" || c_default=""
  c_broken="$(compare_count "$base" "$broken" "$WORK/selftest.broken.out")" || c_broken=""
  c_injected_default="$(compare_count "$base" "$injected_default" "$WORK/selftest.injected-default.out")" || c_injected_default=""
  c_injected_broken="$(compare_count "$base" "$injected_broken" "$WORK/selftest.injected-broken.out")" || c_injected_broken=""

  if [ -z "$c_default" ] || [ -z "$c_broken" ] \
     || [ -z "$c_injected_default" ] || [ -z "$c_injected_broken" ]; then
    ng "selftest: 合成ログのunit/head差件数を抽出できない"
    return 1
  fi
  if [ "$c_default" = "$c_injected_default" ]; then
    ng "selftest: 既定ROM側への故障注入で結果が変わらない（検査ではなく注入を疑うこと）"
    rc=1
  fi
  if [ "$c_broken" = "$c_injected_broken" ]; then
    ng "selftest: 故障注入版側への反対向き注入で結果が変わらない（検査ではなく注入を疑うこと）"
    rc=1
  fi
  if judge_counts "$c_default" "$c_broken"; then
    ok "selftest: 既定差0件・故障注入版差ありの組を合格と判定"
  else
    ng "selftest: 正常な合成入力を合格と判定できない"
    rc=1
  fi
  if judge_counts "$c_injected_default" "$c_broken"; then
    ng "selftest: 既定ROM側に差を入れる故障注入を見逃した"
    rc=1
  else
    ok "selftest: 既定ROM側に差を入れる故障注入を不合格として検出"
  fi
  if judge_counts "$c_default" "$c_injected_broken"; then
    ng "selftest: 故障注入版側の差を消す注入を見逃した"
    rc=1
  else
    ok "selftest: 故障注入版側の差を消す注入を不合格として検出"
  fi
  return "$rc"
}

copy_roms_for_mode() {
  local mode="$1" dst="$2" f copied=0
  case "$mode" in
    official)
      mkdir -p "$dst"
      for f in "$PC88_REF_ROM_DIR"/*.ROM; do
        [ -f "$f" ] || continue
        cp -p "$f" "$dst"/ || return 1
        copied=1
      done
      [ "$copied" -eq 1 ]
      ;;
    default)
      build_mixed_rom "$PC88_REF_ROM_DIR" "$dst"
      ;;
    broken)
      build_mixed_rom "$PC88_REF_ROM_DIR" "$dst" --break-drive-selector
      ;;
    *) return 2 ;;
  esac
}

run_measurement() {
  local mode="$1" run="$2" base="$WORK/${mode}.run${run}"
  local rom="${base}.rom" disk_a="${base}.a.d88" disk_b="${base}.b.d88"
  local media="${base}.m3u" iolog="${base}.iolog.txt" rc

  copy_roms_for_mode "$mode" "$rom" || return 1
  cp "$PC88_REF_DISK_DIR/N88_FE.D88" "$disk_a" || return 1
  cp "$PC88_REF_DISK_DIR/N88_FE.D88" "$disk_b" || return 1
  printf '%s\n' "$disk_a" "$disk_b" > "$media"
  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$RUN_TIMEOUT" \
    "$FRONTEND" --core "$CORE" --rom-dir "$rom" --disk "$media" \
    --frames 3000 --io-log "$iolog" \
    --type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n' \
    >"${base}.stdout.txt" 2>"${base}.stderr.txt"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    ng "${mode}-run${run}: q88measure失敗または${RUN_TIMEOUT}秒上限（rc=${rc}）"
    return "$rc"
  fi
  if grep -Eq '^# 取りこぼし: [1-9][0-9]*件' "$iolog"; then
    ng "${mode}-run${run}: I/Oログに取りこぼしがある"
    return 3
  fi
  ok "${mode}-run${run}: 測定完了・取りこぼし0件"
}

check_determinism() {
  local mode="$1" normalized1="$WORK/${mode}.normalized1" normalized2="$WORK/${mode}.normalized2"
  awk 'seen || /^# main$/ {seen=1; print}' "$WORK/${mode}.run1.iolog.txt" > "$normalized1"
  awk 'seen || /^# main$/ {seen=1; print}' "$WORK/${mode}.run2.iolog.txt" > "$normalized2"
  if cmp -s "$normalized1" "$normalized2"; then
    ok "${mode}: パスを含むヘッダを除き2回のイベント列が一致"
  else
    ng "${mode}: パスを含むヘッダを除いて2回が不一致"
    return 1
  fi
}

echo "==> 帰属判定ロジックのselftest（公式データ不使用）"
if ! run_selftest; then
  exit 1
fi

echo "==> drive-byte2恒久伝播の回帰検査本体"
if [ -z "${PC88_REF_ROM_DIR:-}" ] || [ -z "${PC88_REF_DISK_DIR:-}" ]; then
  echo "SKIP: 公式ROM・公式ディスクの環境変数が未設定（本体未実行、selftestのみrc=0）"
  echo "      PC88_REF_ROM_DIR と PC88_REF_DISK_DIR を設定して再実行すること。"
  exit 0
fi
if [ ! -f "$PC88_REF_DISK_DIR/N88_FE.D88" ]; then
  echo "エラー: 参照ディスクが無い: $PC88_REF_DISK_DIR/N88_FE.D88" >&2
  exit 1
fi
CORE="$(find_l3_core)"
if [ -z "$CORE" ]; then
  echo "エラー: コアが無い。先に tools/setup_harness.sh を実行すること" >&2
  exit 1
fi
ensure_l3_frontend || exit 1
FRONTEND="$REPO/tools/harness/frontend/q88measure"

overall=0
for mode in official default broken; do
  for run in 1 2; do
    run_measurement "$mode" "$run" || overall=1
  done
done
[ "$overall" -eq 0 ] || exit 1
for mode in official default broken; do
  check_determinism "$mode" || overall=1
done
[ "$overall" -eq 0 ] || exit 1

default_counts=()
broken_counts=()
for run in 1 2; do
  default_counts+=("$(compare_count \
    "$WORK/official.run${run}.iolog.txt" "$WORK/default.run${run}.iolog.txt" \
    "$WORK/compare.default.run${run}.txt")") || overall=1
  broken_counts+=("$(compare_count \
    "$WORK/official.run${run}.iolog.txt" "$WORK/broken.run${run}.iolog.txt" \
    "$WORK/compare.broken.run${run}.txt")") || overall=1
done
[ "$overall" -eq 0 ] || { ng "FDCコマンド列の比較または差件数抽出に失敗"; exit 1; }

printf '公式に対するunit/head差件数: 既定ROM run1=%s件 run2=%s件\n' \
  "${default_counts[0]}" "${default_counts[1]}"
printf '公式に対するunit/head差件数: 故障注入版 run1=%s件 run2=%s件\n' \
  "${broken_counts[0]}" "${broken_counts[1]}"
for run in 0 1; do
  if ! judge_counts "${default_counts[$run]}" "${broken_counts[$run]}"; then
    overall=1
  fi
done
if [ "$overall" -eq 0 ]; then
  ok "回帰検査: 2回とも既定ROMは差0件、故障注入版は差あり"
else
  ng "回帰検査: 既定ROM差0件・故障注入版非0件の両条件を満たさない"
fi
exit "$overall"

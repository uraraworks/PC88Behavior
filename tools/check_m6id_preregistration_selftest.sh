#!/usr/bin/env bash
# m6i-d G3/G7照合器の陽性対照、凍結値の陰性対照、起動前停止。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6id_preregistration.py"
CONFIG="$REPO/tools/m6id_frozen.tsv"
ADDENDUM="$REPO/docs/notes/m6i-d-addendum1-unverified-arms.md"

python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err" || exit 1

expect_fail() {
  local label="$1"
  shift
  if "$@" >"$WORK/$label.out" 2>"$WORK/$label.err"; then
    echo "NG: $label を通した" >&2
    exit 1
  fi
  grep -q gate_failed "$WORK/$label.err" || exit 1
}

mutate() {
  local key="$1"
  local value="$2"
  local output="$3"
  awk -F '\t' -v key="$key" -v value="$value" 'BEGIN {OFS="\t"} $1==key {$2=value} {print}' \
    "$CONFIG" >"$output"
}

mutate arm_frames 599 "$WORK/frame.tsv"
expect_fail frame python3 "$CHECK" --config "$WORK/frame.tsv"
mutate repetitions 3 "$WORK/repetitions.tsv"
expect_fail repetitions python3 "$CHECK" --config "$WORK/repetitions.tsv"
mutate gate_run_min_length 33 "$WORK/gate-min.tsv"
expect_fail gate_min python3 "$CHECK" --config "$WORK/gate-min.tsv"
mutate normal_media_sha256 "$(printf '0%.0s' {1..64})" "$WORK/media.tsv"
expect_fail media python3 "$CHECK" --config "$WORK/media.tsv"
awk -F '\t' '$1!="arm" || $2!="D-B3"' "$CONFIG" >"$WORK/arm.tsv"
expect_fail arm python3 "$CHECK" --config "$WORK/arm.tsv"
awk -F '\t' 'BEGIN {OFS="\t"} $1=="judgment" && $2=="arm_gate_released" \
  {$2="arm_gate_changed"} {print}' "$CONFIG" >"$WORK/judgment.tsv"
expect_fail judgment python3 "$CHECK" --config "$WORK/judgment.tsv"
sed 's/m6i_d_only_b5_unverified/m6i_d_only_b5_changed/g' \
  "$ADDENDUM" >"$WORK/addendum.md"
expect_fail addendum python3 "$CHECK" --addendum "$WORK/addendum.md"

cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6ID_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6ID_FROZEN_CONFIG="$WORK/frame.tsv" M6ID_FRONTEND="$WORK/fake_frontend" \
M6ID_FRONTEND_SENTINEL="$WORK/started" \
  "$REPO/tools/measure_m6id.sh" --arm D-B0 --result "$WORK/result.json" \
  >"$WORK/measure.out" 2>"$WORK/measure.err"
measure_rc=$?
set -e
if [ "$measure_rc" -eq 0 ] || [ -e "$WORK/started" ] \
   || ! grep -q preregistration_mismatch "$WORK/measure.out"; then
  echo "NG: 測定入口をfrontend前に停止できない" >&2
  exit 1
fi

echo "check_m6id_preregistration_selftest: 項目数=8、陰性対照7件・起動前停止 OK"

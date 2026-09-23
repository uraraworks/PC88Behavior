#!/usr/bin/env bash
# m6i-g G3/G9照合器の陽性対照、凍結値の陰性対照、frontend前停止。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6ig_preregistration.py"
CONFIG="$REPO/tools/m6ig_frozen.tsv"
python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err" || exit 1
expect_fail() {
  local name="$1"; shift
  if "$@" >"$WORK/$name.out" 2>"$WORK/$name.err"; then echo "NG: $name" >&2; exit 1; fi
  grep -q gate_failed "$WORK/$name.err" || exit 1
}
mutate() {
  local key="$1" old="$2" new="$3" out="$4"
  awk -F '\t' -v key="$key" -v old="$old" -v new="$new" 'BEGIN{OFS="\t"} $1==key && $2==old{$2=new}{print}' "$CONFIG" >"$out"
}
mutate arm_frames 600 599 "$WORK/value.tsv"
expect_fail frozen_value python3 "$CHECK" --config "$WORK/value.tsv"
awk -F '\t' '$1!="arm" || $2!="G-L1"' "$CONFIG" >"$WORK/arm.tsv"
expect_fail arm_name python3 "$CHECK" --config "$WORK/arm.tsv"
mutate issue_frame G-N:6 G-N:7 "$WORK/frame.tsv"
expect_fail issue_frame python3 "$CHECK" --config "$WORK/frame.tsv"
mutate expected_state G-L1:1,1,0 G-L1:1,0,0 "$WORK/state.tsv"
expect_fail expected_state python3 "$CHECK" --config "$WORK/state.tsv"
mutate plain_subrom_sha256 d8b2e64bc27465f955fd308719228f21b06aa07fd780081a88124a52e6d76070 08b2e64bc27465f955fd308719228f21b06aa07fd780081a88124a52e6d76070d "$WORK/subsha.tsv"
expect_fail sub_sha python3 "$CHECK" --config "$WORK/subsha.tsv"
mutate judgment g_l1_success g_l1_changed "$WORK/judgment.tsv"
expect_fail judgment python3 "$CHECK" --config "$WORK/judgment.tsv"
sed 's/| G-N | m6i-b B0 の main（前置きなし・即発行） | 6 |/| G-N | m6i-b B0 の main（前置きなし・即発行） | 7 |/' \
  "$REPO/docs/notes/m6i-g-clean-preamble-boundary-preregistration.md" >"$WORK/prereg.md"
expect_fail prereg_frame python3 "$CHECK" --prereg "$WORK/prereg.md"

cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6IG_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6IG_FROZEN_CONFIG="$WORK/value.tsv" M6IG_FRONTEND="$WORK/fake_frontend" \
M6IG_FRONTEND_SENTINEL="$WORK/started" "$REPO/tools/measure_m6ig.sh" \
  --arm G-N --result "$WORK/result.json" >"$WORK/measure.out" 2>"$WORK/measure.err"
rc=$?
set -e
if [ "$rc" -eq 0 ] || [ -e "$WORK/started" ] || ! grep -q preregistration_mismatch "$WORK/measure.out"; then
  echo "NG: frontend前停止" >&2; exit 1
fi
echo "check_m6ig_preregistration_selftest: 項目数=9、陰性対照8件（凍結値7・起動前停止1）OK"

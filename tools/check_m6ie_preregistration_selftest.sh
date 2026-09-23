#!/usr/bin/env bash
# m6i-e G3/G9照合器の陽性対照、陰性対照、frontend起動前停止。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6ie_preregistration.py"
CONFIG="$REPO/tools/m6ie_frozen.tsv"
python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err" || exit 1
expect_fail() {
  local name="$1"; shift
  if "$@" >"$WORK/$name.out" 2>"$WORK/$name.err"; then echo "NG: $name" >&2; exit 1; fi
  grep -q gate_failed "$WORK/$name.err" || exit 1
}
awk -F '\t' 'BEGIN{OFS="\t"} $1=="arm_frames"{$2="599"}{print}' "$CONFIG" >"$WORK/value.tsv"
expect_fail frozen_value python3 "$CHECK" --config "$WORK/value.tsv"
awk -F '\t' '$1!="arm" || $2!="E2"' "$CONFIG" >"$WORK/arm.tsv"
expect_fail arm_name python3 "$CHECK" --config "$WORK/arm.tsv"
awk -F '\t' 'BEGIN{OFS="\t"} $1=="judgment" && $2=="e2_success"{$2="e2_changed"}{print}' "$CONFIG" >"$WORK/judgment.tsv"
expect_fail judgment_name python3 "$CHECK" --config "$WORK/judgment.tsv"
awk -F '\t' 'BEGIN{OFS="\t"} $1=="insertion_e2"{$2="db-fe-00-00-00-01"}{print}' "$CONFIG" >"$WORK/insertion.tsv"
expect_fail insertion python3 "$CHECK" --config "$WORK/insertion.tsv"
sed 's/発行フレームが60/発行フレームが61/' "$REPO/docs/notes/m6i-e-gate-harm-mechanism-preregistration.md" >"$WORK/prereg.md"
expect_fail prereg_frame python3 "$CHECK" --prereg "$WORK/prereg.md"
cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6IE_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6IE_FROZEN_CONFIG="$WORK/value.tsv" M6IE_FRONTEND="$WORK/fake_frontend" \
M6IE_FRONTEND_SENTINEL="$WORK/started" "$REPO/tools/measure_m6ie.sh" \
  --arm E0 --result "$WORK/result.json" >"$WORK/measure.out" 2>"$WORK/measure.err"
rc=$?
set -e
if [ "$rc" -eq 0 ] || [ -e "$WORK/started" ] || ! grep -q preregistration_mismatch "$WORK/measure.out"; then
  echo "NG: frontend前停止" >&2; exit 1
fi
echo "check_m6ie_preregistration_selftest: 項目数=7、陰性対照6件・起動前停止 OK"

#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
cat >"$WORK/frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6IK_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/frontend"
printf 'rc=1\ntools/run_all_selftests.sh\n' >"$WORK/g1-bad.txt"
if M6IK_FRONTEND="$WORK/frontend" M6IK_FRONTEND_SENTINEL="$WORK/started" \
  "$REPO/tools/measure_m6ik.sh" --work "$WORK/run" --g1-result "$WORK/g1-bad.txt" \
  --dry-run-sub-rom "$WORK/unused.rom" >"$WORK/out" 2>"$WORK/err"; then exit 1; fi
grep -q -E '"reason":"G1"' "$WORK/out"
[ ! -e "$WORK/started" ]
mkdir "$WORK/existing"
if "$REPO/tools/measure_m6ik.sh" --work "$WORK/existing" \
  --g1-result "$WORK/g1-bad.txt" >"$WORK/out" 2>"$WORK/err"; then exit 1; fi
printf '%s\n' 'measure_m6ik_selftest: G1陰性・既存作業先拒否・起動前停止 OK'

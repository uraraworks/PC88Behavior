#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cc -std=c99 -Wall -Wextra -Werror -I"$REPO/tools/harness/core" \
  "$REPO/tools/harness/sub_interrupt_intervention_selftest.c" \
  "$REPO/tools/harness/core/q88h_exchange_intervention.c" \
  "$REPO/tools/harness/core/q88h_sub_interrupt_intervention.c" \
  -o "$WORK/selftest"
"$WORK/selftest"

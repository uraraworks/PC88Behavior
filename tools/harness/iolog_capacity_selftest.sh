#!/usr/bin/env bash
# バッファ容量を変えても、容量内のI/O記録内容が変わらないことを検査する。
set -eu

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/probe.c" <<'EOF'
#include <stdio.h>
#include "q88h_iolog.h"

int main(void)
{
    unsigned i;
    q88h_iolog_t *log;
    retro_q88h_iolog_reset();
    retro_q88h_iolog_set_enabled(1);
    log = retro_q88h_iolog();
    for (i = 0; i < 4; i++) {
        retro_q88h_iolog_set_frame(700 + i);
        q88h_iolog_record(log, i & 1, 0xFA + i, 0x80 + i, 0x100 + i);
    }
    printf("events=%u dropped=%u\n", log->n_events, log->n_dropped);
    for (i = 0; i < log->n_events; i++)
        printf("%u %u %u %u %u %u %u\n", log->ev[i].seq,
               log->ev[i].clock, log->ev[i].frame, log->ev[i].pc,
               log->ev[i].kind, log->ev[i].port, log->ev[i].value);
    return 0;
}
EOF

for capacity in 4 8; do
  cc -std=c99 -Wall -Wextra -Werror -DQ88H_IOLOG_MAX_EVENTS="$capacity" \
    -I"$REPO/tools/harness/core" "$WORK/probe.c" \
    "$REPO/tools/harness/core/q88h_iolog.c" \
    "$REPO/tools/harness/core/q88h_clock.c" -o "$WORK/probe-$capacity"
  "$WORK/probe-$capacity" > "$WORK/out-$capacity"
done

cmp "$WORK/out-4" "$WORK/out-8"
echo "OK: I/Oログ容量を変えても容量内4イベントの測定結果は不変"

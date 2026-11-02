#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="${PC88_VENDOR_DIR:-$REPO/../vendor}/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
[[ -f "$CORE" ]] || { echo 'コアがありません' >&2; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/b58-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
inc=(-I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core")
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L "${inc[@]}" "$REPO/tools/harness/frontend/main.c" -ldl -o "$WORK/front"
cat > "$WORK/check.c" <<EOF_C
#define main frontend_main
#include "$REPO/tools/harness/frontend/main.c"
#undef main
int main(void) {
    char *args[] = {"front", "--key-at", "2", "--key", "RETROK_UP", "--core", "/missing"};
    uint16_t k;
    if (!named_key("RETROK_F1", &k) || k != RETROK_F1 ||
        !named_key("RETROK_KP5", &k) || k != RETROK_KP5 ||
        named_key("RETROK_NOT_A_KEY", &k)) return 1;
    (void)frontend_main(7, args);
    for (g_frame = 0; g_frame < 8; g_frame++)
        if (input_state_cb(0, RETRO_DEVICE_KEYBOARD, 0, RETROK_UP) != (g_frame >= 2 && g_frame < 6)) return 2;
    return 0;
}
EOF_C
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L "${inc[@]}" "$WORK/check.c" -ldl -o "$WORK/check"
"$WORK/check" > /dev/null 2>&1
mkdir "$WORK/rom"
python3 - "$WORK/rom" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
(p / 'N88.ROM').write_bytes(bytes.fromhex('18 fe') + bytes(0x7ffe))
(p / 'DISK.ROM').write_bytes(bytes(0x800))
PY
"$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 12 --key-at 2 --key RETROK_UP --out "$WORK/out" > /dev/null 2>&1
if "$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 12 --key-at 2 --key RETROK_NOT_A_KEY > /dev/null 2>&1; then
  echo '不明なキー名を受理しました' >&2; exit 1
fi

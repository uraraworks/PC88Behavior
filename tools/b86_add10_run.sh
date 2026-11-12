#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
[ "$#" -eq 1 ] || { echo '使い方: b86_add10_run.sh 出力ディレクトリ' >&2; exit 2; }
out="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1")"
case "$out/" in "$repo/"*) echo '出力先はリポジトリ外にしてください' >&2; exit 2;; esac
[ ! -e "$out" ] || { echo '出力先が既に存在します' >&2; exit 2; }
umask 077; mkdir -p "$out/raw"
core="${PC88_CORE:-$(find "$repo/../vendor/quasi88-libretro" -maxdepth 1 -name 'quasi88_libretro.*' -type f | head -1)}"
front="${PC88_FRONTEND:-$repo/tools/harness/frontend/q88measure}"
[ -f "$core" ] && [ -x "$front" ] || { echo 'コアまたは frontend がありません' >&2; exit 1; }
cleanup() { find "$out/raw" \( -name io -o -name mem -o -name trace -o -name stdout -o -name stderr -o -name probe.d88 -o -name probe.bin -o -name values.tmp \) -type f -delete; find "$out/raw" -name rom -type d -prune -exec rm -rf {} +; }
trap cleanup EXIT
while IFS= read -r name; do
 if [ -n "${B86_ADD10_FILTER:-}" ] && ! [[ "$name" =~ $B86_ADD10_FILTER ]]; then continue; fi
 dir="$out/raw/$name"; mkdir -p "$dir/rom"
 python3 "$repo/tools/b86_add10.py" generate "$dir" "$name"
 if [ -n "${PC88_REF_ROM_DIR:-}" ]; then cp "$PC88_REF_ROM_DIR"/*.ROM "$dir/rom/"; frames="${B86_FRAMES:-2010}"
 elif [ -n "${B86_ADD10_OWN_ROM_DIR:-}" ]; then cp "$B86_ADD10_OWN_ROM_DIR"/*.ROM "$dir/rom/"; frames="${B86_FRAMES:-60}"
 else
  frames="${B86_FRAMES:-60}"
  python3 - "$dir/probe.bin" "$dir/rom" <<'PY'
import pathlib,sys
sector=pathlib.Path(sys.argv[1]).read_bytes(); d=pathlib.Path(sys.argv[2]); rom=bytearray(0x8000)
rom[:3]=bytes.fromhex('c3 00 01'); boot=bytes.fromhex('f3 31 00 f0 21 00 03 11 00 c0 01 00 01 ed b0 c3 00 c0')
rom[0x100:0x100+len(boot)]=boot; rom[0x300:0x400]=sector
# 自作対照入口は RET。6F6B は HL の自作受け口を呼ぶ。
for addr in (0x6f96,0x42f6,0x43e1,0x43e9,0x4353,0x7071,0x11df,0x3e0d,0x3080): rom[addr]=0xc9
rom[0x6f6b:0x6f6f]=bytes.fromhex('cd 91 33 c9'); rom[0x3391]=0xe9
rom[0x3080:0x3088]=bytes.fromhex('f5 db 00 32 d0 e6 f1 c9')
(d/'N88.ROM').write_bytes(rom); (d/'DISK.ROM').write_bytes(bytes.fromhex('18 fe')+bytes(0x7fe))
PY
 fi
 args=(); case "$name" in *-r00b0-*) args=(--key-matrix "0:0:0:$frames");; *-r03b2-*) args=(--key-matrix "3:2:0:$frames");; *-r07b4-*) args=(--key-matrix "7:4:0:$frames");; *-r0bb7-*) args=(--key-matrix "11:7:0:$frames");; esac
 if ! /usr/bin/perl -e 'alarm shift; exec @ARGV' "${B86_TIMEOUT:-180}" "$front" --core "$core" --rom-dir "$dir/rom" --disk "$dir/probe.d88" --frames "$frames" --out "$dir/trace" --io-log "$dir/io" --mem-write-log "$dir/mem" --mem-write-range C000-FFFF ${args[@]+"${args[@]}"} >"$dir/stdout" 2>"$dir/stderr"; then rm -f "$dir/io" "$dir/mem"; fi
 if [[ "$name" == 3080-* && "$name" != 3080-none-* ]] && ! grep -q "キーマトリクス押下:" "$dir/stderr"; then rm -f "$dir/io" "$dir/mem"; fi
 if [ -f "$dir/io" ] && [ -f "$dir/mem" ]; then python3 "$repo/tools/b86_add10.py" extract "$dir" "$name" || true; fi
 rm -f "$dir/io" "$dir/mem"
 rm -rf "$dir/rom" "$dir/trace" "$dir/probe.d88" "$dir/probe.bin" "$dir/stdout" "$dir/stderr"
done < <(python3 "$repo/tools/b86_add10.py" list)
python3 "$repo/tools/b86_add10.py" report "$out"

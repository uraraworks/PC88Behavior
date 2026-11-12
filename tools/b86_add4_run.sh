#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
[ "$#" -eq 1 ] || { echo '使い方: b86_add4_run.sh 出力ディレクトリ' >&2; exit 2; }
out="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1")"
case "$out/" in "$repo/"*) echo '出力先はリポジトリ外にしてください' >&2; exit 2;; esac
[ ! -e "$out" ] || { echo '出力先が既に存在します' >&2; exit 2; }
umask 077
mkdir -p "$out/raw" "$out/summary"
core="${PC88_CORE:-$(find "$repo/../vendor/quasi88-libretro" -maxdepth 1 -name 'quasi88_libretro.*' -type f | head -1)}"
front="${PC88_FRONTEND:-$repo/tools/harness/frontend/q88measure}"
[ -f "$core" ] && [ -x "$front" ] || { echo 'コアまたは frontend がありません' >&2; exit 1; }
while IFS= read -r name; do
 dir="$out/raw/$name"; mkdir -p "$dir/rom"
 python3 "$repo/tools/b86_add4.py" generate "$dir" "$name"
 if [ -n "${PC88_REF_ROM_DIR:-}" ]; then
  cp "$PC88_REF_ROM_DIR"/*.ROM "$dir/rom/"; frames="${B86_FRAMES:-2010}"
 else
  frames="${B86_FRAMES:-60}"
  python3 - "$dir/probe.bin" "$dir/rom" <<'PY'
import pathlib,sys
sector=pathlib.Path(sys.argv[1]).read_bytes(); d=pathlib.Path(sys.argv[2]); rom=bytearray(0x8000)
rom[:3]=bytes.fromhex('c3 00 01'); boot=bytes.fromhex('f3 31 00 f0 21 00 03 11 00 c0 01 00 01 ed b0 c3 00 c0')
rom[0x100:0x100+len(boot)]=boot; rom[0x300:0x400]=sector
for addr in (0x37c9,0x37d2,0x3847): rom[addr]=0xc9
(d/'N88.ROM').write_bytes(rom); (d/'DISK.ROM').write_bytes(bytes.fromhex('18 fe')+bytes(0x7fe))
PY
 fi
 /usr/bin/perl -e 'alarm shift; exec @ARGV' "${B86_TIMEOUT:-180}" "$front" --core "$core" --rom-dir "$dir/rom" --disk "$dir/probe.d88" --frames "$frames" --out "$dir/trace" --io-log "$dir/io" >"$dir/stdout" 2>"$dir/stderr" || { echo "実行失敗: $name" >&2; exit 1; }
 python3 "$repo/tools/b86_add4.py" summarize "$dir" "$name" "$out/summary/$name.json"
 gzip -f "$dir/io"
 # ROM 複製と大きな一時出力を残さない。
 rm -rf "$dir/rom" "$dir/trace" "$dir/probe.d88"
done < <(python3 "$repo/tools/b86_add4.py" list)

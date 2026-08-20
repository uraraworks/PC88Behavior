#!/usr/bin/env bash
# ROM/RAM 判定器（q88h_addr_is_rom, tools/harness/core/q88h_trace.h まわり /
# tools/patches/0002-bus-trace.patch）の疎通試験 兼 故障注入による検出力確認。
#
# 背景（docs/notes/m3b-alphados-demand.md「残す宿題」2）: この判定器は
# コミット 56c19d4 でコードを読んで正しさを確認しただけで、**実測で RAM 側の
# 枝を一度も踏んでいなかった**。「全部 ROM と判定する壊れた判定器」でも
# これまでの測定結果と見分けが付かなかった、ということ。
#
# ここでやること:
#   1. 自作 ROM（make_test_rom.py --enable-ram-exec）で、RAM(0x9000, window/
#      main_ram 固定帯) に自前のコードを書き込んで JP させ、RAM 実行を
#      故意に発生させる。port $31 等のバンク切替は使わない
#      （公開仕様に触れる余地を最初から作らないほうが単純なため）。
#   2. 実際にビルド済みのコアに対して走らせ、(fetch, ROM) と (fetch, RAM)
#      の両方に非ゼロの件数が出ることを確認する（陽性対照そのもの）。
#   3. 判定ロジック（q88h_addr_is_rom）を意図的に壊した3種の故障注入版を
#      その場でビルドし、それぞれ「期待どおりに結果が変わる」ことを確認する:
#        - always_rom: 常に ROM と判定   → RAM 側の件数が 0 になるはず
#        - always_ram: 常に RAM と判定   → ROM 側の件数が 0 になるはず
#        - shifted   : window/main_ram 固定帯の判定を意図的にずらす
#                      → 内訳が正常版と変わるはず
#      3種のいずれかが正常版と同じ結果になったら、判定器か観測系が死んでいる
#      ということなので、その場で NG にする（合否条件を緩めない）。
#
# 故障注入版はコピーしたコア一式（$VENDOR を丸ごと cp -a）の上で
# ビルドする。共有の $VENDOR 本体（他セッションも使う可能性がある）は
# 一切書き換えない。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="${TMPDIR:-/tmp}/pc88h-romram-selftest.$$"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
trap 'rm -rf "$WORK"' EXIT

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi

PLATFORM_ARG=""
case "$(uname -s)" in
  Darwin) PLATFORM_ARG="platform=osx" ;;
esac

say "フロントエンドをビルド"
make -s -C "$REPO/tools/harness/frontend"

say "合成 ROM を生成（自作のバイト列。公式 ROM は使わない。--enable-ram-exec）"
mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_test_rom.py" "$WORK/rom" --enable-ram-exec >"$WORK/make_test_rom.log"
cat "$WORK/make_test_rom.log"

# --------------------------------------------------------------------------
# main CPU の [実行された番地 (fetch, ROM)] / [実行された番地 (fetch, RAM)]
# セクションに載っている番地レンジの行数を数える（0件なら "(なし)" の1行）。
# --------------------------------------------------------------------------
count_main_rom() {
  sed -n '/\[メインCPU 実行された番地 (fetch, ROM)\]/,/\[メインCPU 実行された番地 (fetch, RAM)\]/p' "$1" \
    | grep -c '^  [0-9A-F][0-9A-F][0-9A-F][0-9A-F]-' || true
}
count_main_ram() {
  sed -n '/\[メインCPU 実行された番地 (fetch, RAM)\]/,/\[メインCPU データとして読まれた番地\]/p' "$1" \
    | grep -c '^  [0-9A-F][0-9A-F][0-9A-F][0-9A-F]-' || true
}

say "陽性対照: 実際のコアで RAM(0x9000) 実行が観測されるか"
run_trace() {
  # $1 = core, $2 = out
  "$REPO/tools/harness/frontend/q88measure" \
    --core "$1" \
    --rom-dir "$WORK/rom" \
    --frames 8 \
    --out "$2" \
    --expect-exec 0x0000 --expect-exec 0x1234 >"$2.log" 2>&1
}

run_trace "$CORE" "$WORK/trace-normal.txt"
base_rom="$(count_main_rom "$WORK/trace-normal.txt")"
base_ram="$(count_main_ram "$WORK/trace-normal.txt")"
echo "正常版: main ROM側=${base_rom}件 RAM側=${base_ram}件"

fail=0
if [ "$base_rom" -le 0 ]; then
  echo "NG: 正常版で ROM 側の実行番地が 0 件。陽性対照として成立していない" >&2
  fail=1
fi
if [ "$base_ram" -le 0 ]; then
  echo "NG: 正常版で RAM 側の実行番地が 0 件。" \
       "m3b の宿題（RAM側の枝が実測で一度も踏まれていない）が未解消" >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "NG: 陽性対照が成立していないため、故障注入の検出力確認に進めない" >&2
  exit 1
fi

# --------------------------------------------------------------------------
# 故障注入。$VENDOR を丸ごとコピーし、q88h_addr_is_rom() だけをその場で
# 壊してリビルドする。共有の $VENDOR 本体は一切変更しない。
# --------------------------------------------------------------------------
build_variant() {
  # $1 = variant名, $2 = 差し込むPythonの置換スクリプト(stdinで pc88main.c を渡す)
  local variant="$1"
  local dst="$WORK/vendor-$variant"
  cp -a "$VENDOR" "$dst"
  python3 - "$dst/src/pc88main.c" <<PYEOF
import sys
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
$2
open(p, 'w', encoding='utf-8').write(s)
PYEOF
  # ヘッダ依存漏れでの再ビルド漏れ事故(4982ad8)と、直前の別selftestが
  # 残した異なるビルド条件の.o混在を避ける。コピー先だけをcleanし、
  # 全オブジェクトを同じ条件で確実に再コンパイルする。
  local build_jobs
  build_jobs="$(sysctl -n hw.ncpu 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)"
  ( cd "$dst" && make $PLATFORM_ARG clean >"$WORK/clean-$variant.log" 2>&1 ) \
    || { echo "NG: $variant のcleanに失敗。ログ: $WORK/clean-$variant.log" >&2; exit 1; }
  ( cd "$dst" && make $PLATFORM_ARG -j"$build_jobs" \
      >"$WORK/build-$variant.log" 2>&1 ) \
    || { echo "NG: $variant のビルドに失敗。ログ: $WORK/build-$variant.log" >&2; \
         grep -i error "$WORK/build-$variant.log" >&2 || true; exit 1; }
  local lib
  lib="$(ls "$dst"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
  if [ -z "$lib" ]; then
    echo "NG: $variant のビルド成果物が見つからない" >&2; exit 1
  fi
  echo "$lib"
}

check_variant() {
  # $1 = variant名, $2 = core path, $3 = 期待するROM側条件("zero"/"nonzero"),
  # $4 = 期待するRAM側条件("zero"/"nonzero")
  local variant="$1" core="$2" want_rom="$3" want_ram="$4"
  run_trace "$core" "$WORK/trace-$variant.txt"
  local rom ram
  rom="$(count_main_rom "$WORK/trace-$variant.txt")"
  ram="$(count_main_ram "$WORK/trace-$variant.txt")"
  echo "  $variant: main ROM側=${rom}件 RAM側=${ram}件"

  local ok=1
  if [ "$want_rom" = "zero" ] && [ "$rom" -ne 0 ]; then ok=0; fi
  if [ "$want_rom" = "nonzero" ] && [ "$rom" -eq 0 ]; then ok=0; fi
  if [ "$want_ram" = "zero" ] && [ "$ram" -ne 0 ]; then ok=0; fi
  if [ "$want_ram" = "nonzero" ] && [ "$ram" -eq 0 ]; then ok=0; fi

  if [ "$rom" = "$base_rom" ] && [ "$ram" = "$base_ram" ]; then
    echo "NG: $variant の結果が正常版(ROM=${base_rom} RAM=${base_ram})と同一。" \
         "判定器か観測系が死んでいる（故障注入で検出できなかった）" >&2
    return 1
  fi

  if [ "$ok" -ne 1 ]; then
    echo "NG: $variant が期待どおりの結果にならなかった" \
         "(期待: ROM=$want_rom RAM=$want_ram / 実際: ROM=$rom RAM=$ram)" >&2
    return 1
  fi

  echo "  OK: $variant は期待どおり検出された"
  return 0
}

say "故障注入 1/3: always_rom（常に ROM と判定させる）"
lib_always_rom="$(build_variant always_rom "
old = 'static int q88h_addr_is_rom( word addr )\n{\n'
assert old in s, '対象関数が見つからない(always_rom)'
s = s.replace(old, old + '  return 1;   /* 故障注入 selftest: 常にROM (always_rom) */\n', 1)
")"
check_variant always_rom "$lib_always_rom" nonzero zero || fail=1

say "故障注入 2/3: always_ram（常に RAM と判定させる）"
lib_always_ram="$(build_variant always_ram "
old = 'static int q88h_addr_is_rom( word addr )\n{\n'
assert old in s, '対象関数が見つからない(always_ram)'
s = s.replace(old, old + '  return 0;   /* 故障注入 selftest: 常にRAM (always_ram) */\n', 1)
")"
check_variant always_ram "$lib_always_ram" zero nonzero || fail=1

say "故障注入 3/3: shifted（window/main_ram固定帯の判定境界をずらす）"
lib_shifted="$(build_variant shifted "
old = '  else if( addr < 0xc000 ) return 0;   /* main_ram 固定 */\n'
assert old in s, '対象行が見つからない(shifted)'
new = '  else if( addr < 0xc000 ) return 1;   /* 故障注入 selftest: 境界を意図的にずらしROM扱いにする (shifted) */\n'
s = s.replace(old, new, 1)
")"
# shifted はROM/RAMどちらが0になるかを固定で期待しない
# （境界のずらし方次第で結果が変わりうる）。「正常版と食い違うこと」だけを
# check_variant内の同一判定で見る。want指定は現状値をそのまま渡し
# nonzero/zeroどちらでも通す代わりに、同一判定の分岐で確実に拾わせる。
run_trace "$lib_shifted" "$WORK/trace-shifted.txt"
shifted_rom="$(count_main_rom "$WORK/trace-shifted.txt")"
shifted_ram="$(count_main_ram "$WORK/trace-shifted.txt")"
echo "  shifted: main ROM側=${shifted_rom}件 RAM側=${shifted_ram}件"
if [ "$shifted_rom" = "$base_rom" ] && [ "$shifted_ram" = "$base_ram" ]; then
  echo "NG: shifted の結果が正常版(ROM=${base_rom} RAM=${base_ram})と同一。" \
       "判定器か観測系が死んでいる（故障注入で検出できなかった）" >&2
  fail=1
else
  echo "  OK: shifted は期待どおり正常版と異なる結果になった"
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "NG: 上記のいずれかが不合格。" >&2
  exit 1
fi

say "合格"
echo "正常版で ROM側=${base_rom}件・RAM側=${base_ram}件の実行番地を観測（陽性対照）。"
echo "故障注入3種（always_rom / always_ram / shifted）すべてで、期待どおり" \
     "結果が変化することを確認した。ROM/RAM判定器は検出力を持っている。"

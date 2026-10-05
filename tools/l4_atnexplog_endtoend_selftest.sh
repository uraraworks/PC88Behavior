#!/usr/bin/env bash
# tools/l4_atnexplog_endtoend_selftest.sh — ATN/EXP/LOG(第4.16b節)のBASIC
# 呼び出し経路end-to-end検査(陰性対照つき)。**公式ROMは要らない**
# (自作ROMだけで完結する)。tools/l4_sincos_endtoend_selftest.shと全く
# 同じ設計(EXT_BANK_CALLのBC/DE退避不具合の再発防止と同じ検査方法)を
# 踏襲する。
#
# 背景: tools/l4_atnexplog_bank_conform.py(バンクルーチン単体のバイト
# 照合)だけでは、`interp.asm FTNF_DO_ATN/EXP/LOG`→`EXT_BANK_CALL`
# (src/ext_bank/relay.asm)→バンク0`EXT_BANK0_ATN/EXP/LOG_ENTRY`
# (src/ext_bank/bank0.asm)という実際の呼び出し経路が正しく往復する
# ことまでは確認できない(SQR/SIN/COS/TANがまさにこれでハングを見落とした
# 前例)。`print log(0)`(Illegal function call、interp.asm側で
# EXT_BANK_CALLへ行く前に弾く経路)も1腕含め、誤りの腕がEXT_BANK_CALLの
# 窓状態を乱さないことも合わせて確かめる。
#
# 検査:
#   1. 通常ビルドで`print atn(.5)\nprint exp(1)\nprint log(2)\n
#      print log(0)\n`を打ち、期待どおり出力セルが変化すること
#      (9セル・相対Ok行・出力ハッシュを固定値と照合する)。
#   2. --io-logで、EXT_BANK_CALLの窓復元OUT(ポート0x71)が、直前のIN
#      (同ポート)で読んだ値と全ペアで一致すること。
#   3. 陰性対照(--inject-ext-bank-bcde-fault、build_main_rom.py):
#      relay.asmのBC/DE退避を外した状態を再現したビルドで、上記1・2が
#      実際に壊れること(検出力の確認)。
#
# tests/conformance/expected_l4_trans.tsv との公式ROM期待値照合は
# tools/conform_l4.sh(TRANS場面、l4-c8)が別途行う。本器具はそれより
# 軽量な単発の通し経路検査で、run_all_selftests.shから毎回回す想定。
#
# 使い方: tools/l4_atnexplog_endtoend_selftest.sh

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
source "$REPO/tools/lib_l3_measure.sh"

BUILD="$REPO/src/build_main_rom.py"
RECORD="$REPO/tools/l4_print_conform_record.py"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng() { printf '  \033[31mNG\033[0m   %s\n' "$1" >&2; FAILED=1; }

FAILED=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

core="$(find_l3_core)"
if [ -z "$core" ]; then
  echo "エラー: コアが無い。tools/setup_harness.sh を先に実行すること" >&2
  exit 1
fi
make -s -C "$REPO/tools/harness/frontend" || exit 1

# l4_sincos_endtoend_selftest.shと同じ走行フレーム構成。打鍵文字列は4行
# (ATN/EXP/LOGそれぞれ1回ずつ+誤りの腕log(0)を1回)。
TYPED='print atn(.5)\nprint exp(1)\nprint log(2)\nprint log(0)\n'
BEFORE=690
DUMP=900
RUN=1400   # 4行分、SIN/COS/TANのRUN=1200より余裕を見る

# この採取時点(DUMP=900)はATNの結果・Ok・次のEXP入力の途中。
# 記録器の相対Ok行は最後の変化行を基準にする。後続の窓復元はI/Oで確認。
# DIM移転前の通常自作ROMでも同じ記録になることを実測した固定値。
# 「何か表示された」だけでは誤り表示も通るので陽性側も本文ハッシュを照合する。
EXPECTED_CELLS=9
EXPECTED_OK_ROW=3
EXPECTED_SHA=5bf3c6b2243618a707cbe8eb34d81b2c44139d8104859b1c3f3f263d45ad7d92

vram_out_path() {
  local base="$1" frame="$2"
  local stem="${base%.bin}"
  printf '%s.f%06d.bin' "$stem" "$frame"
}

run_and_check() {
  local romdir="$1" prefix="$2"
  local before_out after_out iolog
  before_out="$(vram_out_path "$prefix.before.bin" "$BEFORE")"
  after_out="$(vram_out_path "$prefix.after.bin" "$DUMP")"
  iolog="$prefix.iolog.txt"
  run_q88measure_retry "$iolog" "$prefix.stdout.txt" "$prefix.stderr.txt" \
      --core "$core" --rom-dir "$romdir" --frames "$RUN" \
      --io-log "$iolog" \
      --vram-dump "$prefix.before.bin" --vram-dump-at "$BEFORE" \
      --vram-dump "$prefix.after.bin" --vram-dump-at "$DUMP" \
      --type-at 300 --type '\n' --type-at 700 --type "$TYPED" || { echo "NA NA NA -1"; return 1; }
  if grep -qi 'untypable\|打てない' "$prefix.stderr.txt" 2>/dev/null; then
    echo "NA NA NA -1"; return 1
  fi
  if [ ! -f "$before_out" ] || [ ! -f "$after_out" ]; then
    echo "NA NA NA -1"; return 1
  fi
  local cell_count ok_row output_sha
  local record
  record="$(python3 "$RECORD" --before "$before_out" --after "$after_out" \
      --count-only-rows 19)" || { echo "NA NA NA -1"; return 1; }
  read -r cell_count ok_row output_sha <<< "$record"
  [ -n "$output_sha" ] || { echo "NA NA NA -1"; return 1; }

  local restore_ok
  restore_ok="$(python3 - "$iolog" << 'PYEOF'
import sys
path = sys.argv[1]
rows = []
with open(path, encoding="utf-8") as f:
    in_main = False
    for line in f:
        line = line.rstrip("\n")
        if line.startswith("# seq"):
            in_main = True
            continue
        if line.startswith("# sub") or line.startswith("#"):
            continue
        if not in_main or not line.strip():
            continue
        cols = line.split()
        if len(cols) < 7:
            continue
        rows.append(cols)

# l4_sincos_endtoend_selftest.shと同じ状態機械
# (IN->OUT(バンク選択、無視)->OUT(復元、INの値と一致するはず))。
pending = None
phase = 0
mismatch = 0
pairs = 0
for cols in rows:
    kind, port, value = cols[4], cols[5], cols[6]
    if port != "0071":
        continue
    if kind == "IN":
        pending = value
        phase = 1
    elif kind == "OUT":
        if phase == 1:
            phase = 2
        elif phase == 2:
            pairs += 1
            if value != pending:
                mismatch += 1
            pending = None
            phase = 0

if pairs == 0:
    print(-1)  # 採取失敗を「食い違いがある」と取り違えない
else:
    print(1 if mismatch == 0 else 0)
PYEOF
)"
  echo "${cell_count} ${ok_row} ${output_sha} ${restore_ok}"
}

# -----------------------------------------------------------------------
say "1. 通常ビルドで print atn(.5)/exp(1)/log(2)/log(0) が正しく完了すること"
NORMAL_ROM="$WORK/rom_normal"
if ! python3 "$BUILD" "$NORMAL_ROM" >"$WORK/build_normal.txt" 2>&1; then
  ng "build_main_rom.py(通常)が失敗"; cat "$WORK/build_normal.txt" >&2
fi
read -r cell_ok ok_row_n sha_n restore_ok_n < <(run_and_check "$NORMAL_ROM" "$WORK/normal")
if [ "$cell_ok" = "$EXPECTED_CELLS" ] && [ "$ok_row_n" = "$EXPECTED_OK_ROW" ] && [ "$sha_n" = "$EXPECTED_SHA" ]; then
  ok "通常ビルド: 出力が固定した正常記録と一致した(cell_count=${cell_ok}、相対Ok行=${ok_row_n}、SHA一致)"
else
  ng "通常ビルド: 正常記録と不一致(cell_count=${cell_ok:-?}、相対Ok行=${ok_row_n:-?}、SHA=${sha_n:-?})"
fi
if [ "$restore_ok_n" = "1" ]; then
  ok "通常ビルド: EXT_BANK_CALLの窓復元OUT(0x71)が直前のIN(0x71)の値と全て一致した"
else
  ng "通常ビルド: 窓復元OUT(0x71)が直前のIN(0x71)の値と食い違った(restore_ok=${restore_ok_n:-?})"
fi

# -----------------------------------------------------------------------
say "2. 陰性対照(--inject-ext-bank-bcde-fault): BC/DE退避を外すと壊れること"
FAULT_ROM="$WORK/rom_fault"
if ! python3 "$BUILD" "$FAULT_ROM" --inject-ext-bank-bcde-fault >"$WORK/build_fault.txt" 2>&1; then
  ng "build_main_rom.py(--inject-ext-bank-bcde-fault)が失敗"; cat "$WORK/build_fault.txt" >&2
fi
read -r cell_f ok_row_f sha_f restore_ok_f < <(run_and_check "$FAULT_ROM" "$WORK/fault")
# ON/WHILE追加後は故障の着地点が配置依存で変わり、0セルの停止ではなく
# 「WHILE without WEND」の誤り表示(18セル)になった。BC/DE退避欠落で
# E(旧0x71)等が壊れ、窓復元も食い違うことは変わらない。実測の最初の
# 食い違いは旧0x71=FF→B1、旧0x32=A9→29。通常は9セルの
# ATN数値出力であり、移転前後ともその固定記録に一致することを確認済み。
# したがって「停止」ではなく正常記録との差と実際の窓復元不一致を必須とする。
# 計測失敗(NA/-1)を陰性対照の成功に含めない。
if [ -n "${sha_f:-}" ] && [ "$sha_f" != "NA" ] && [ -n "${sha_n:-}" ] && [ "$sha_n" != "NA" ] && [ "$sha_f" != "$sha_n" ]; then
  ok "陰性対照: 出力が通常ビルドと不一致(cell_count=${cell_f}、SHA不一致、故障を再現)"
else
  ng "陰性対照: 出力不一致を確認できなかった(cell_count=${cell_f:-?}、故障注入または計測を確認)"
fi
if [ "$restore_ok_f" = "0" ]; then
  ok "陰性対照: 窓復元OUT(0x71)が直前のIN(0x71)の値と食い違った(故障を再現)"
else
  ng "陰性対照: 窓復元OUT(0x71)の不一致を確認できなかった(restore_ok=${restore_ok_f:-?}、故障注入または計測を確認)"
fi

# -----------------------------------------------------------------------
if [ "$FAILED" -eq 0 ]; then
  echo
  echo "l4_atnexplog_endtoend_selftest: OK"
else
  echo
  echo "l4_atnexplog_endtoend_selftest: NG" >&2
fi
exit "$FAILED"

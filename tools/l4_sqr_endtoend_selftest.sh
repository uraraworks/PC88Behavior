#!/usr/bin/env bash
# tools/l4_sqr_endtoend_selftest.sh — SQR(第4.16b節)のBASIC呼び出し経路
# end-to-end検査(陰性対照つき)。**公式ROMは要らない**(自作ROMだけで
# 完結する)。
#
# 背景: docs/notes/l4-c8-transcendental-conformance-scene-results.mdで、
# `interp.asm FTNF_DO_SQR`→`EXT_BANK_CALL`(src/ext_bank/relay.asm)→
# バンク0`EXT_BANK0_SQR_ENTRY`(src/ext_bank/bank0.asm)という実際の
# 呼び出し経路を直接モードPRINTから通すとハングすることが分かった。
# tools/l4_sqr_bank_conform.py(バンクルーチン単体のバイト照合)は
# ハング発生後もOKのままだった——単体照合ではこの不具合を検出できない。
#
# 原因(--io-log・--int-logで特定、docs/notes/同上): EXT_BANK_CALLが
# 「C(旧0x32)・E(旧0x71)はCALL EXT_BANK_JUMP_HL(バンク側ルーチンの
# 呼び出し)をまたいでも保たれる」という前提に頼っていたが、
# EXT_BANK0_SQR_ENTRYはニュートン法のLDIRでBC/DEを作業用に使うため、
# この前提が破れて復元される0x71/0x32の値が化け、窓(0x6000-0x7FFF)が
# メインROM側へ戻らないままメインROM側のコードを実行してしまい暴走
# した(以後I/O・割り込みが一切発生しなくなる=ハングと同型)。
# 修正(2026-09-20、src/ext_bank/relay.asm): C・EをCALL EXT_BANK_JUMP_HL
# の前後でスタックへ退避するよう変更(PUSH BC/PUSH DE〜POP DE/POP BC)。
#
# 検査:
#   1. 通常ビルドで`print sqr(4)\n`を打ち、期待どおり出力セルが変化する
#      こと(cell_count>0)——ハングしていれば0のまま(以前の不具合の
#      症状そのもの)。
#   2. --io-logで、EXT_BANK_CALLの窓復元OUT(ポート0x71)の値が、直前の
#      IN(同ポート)で読んだ値と一致すること(=窓が正しく復元されたこと
#      の直接証拠。画面本文は一切見ない)。
#   3. 陰性対照(--inject-ext-bank-bcde-fault、build_main_rom.py):
#      修正前の状態(C/Eをスタック退避しない)を再現したビルドで、
#      上記1・2がいずれも実際に壊れること(検出力の確認)。
#
# tests/conformance/expected_l4_trans.tsv(SQR1〜4)との公式ROM期待値
# 照合はtools/conform_l4.sh(TRANS場面)が既に行っている。本器具は
# それより軽量な単発の通し経路検査で、run_all_selftests.shから毎回
# 回す想定。
#
# 使い方: tools/l4_sqr_endtoend_selftest.sh

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

# tools/conform_l4.sh のSQR1('print sqr(2)')と同じ走行フレーム
# (dump=824, run=1024, before=690)。打鍵文字列の長さも揃える
# ('print sqr(4)\n'、SQR1の'print sqr(2)\n'と同じ13キー)。
TYPED='print sqr(4)\n'
BEFORE=690
DUMP=824
RUN=1024

# ---------------------------------------------------------------------
# 1腕分の走行(--io-log付き)と、出力セル数・窓復元OUTの妥当性を返す。
# 標準出力: "<cell_count> <restore_ok>" (restore_ok は 1=一致/0=不一致)
# ---------------------------------------------------------------------
vram_out_path() {
  local base="$1" frame="$2"
  local stem="${base%.bin}"
  printf '%s.f%06d.bin' "$stem" "$frame"
}

run_and_check() {
  local romdir="$1" prefix="$2"
  local before_out after_out iolog
  # q88measureは--vram-dumpが2件以上あるとファイル名へフレーム番号を
  # 差し込む(tools/harness/frontend/main.c vram_dump_path_for)。
  # tools/conform_l4.sh のvram_out_pathと同じ規則。
  before_out="$(vram_out_path "$prefix.before.bin" "$BEFORE")"
  after_out="$(vram_out_path "$prefix.after.bin" "$DUMP")"
  iolog="$prefix.iolog.txt"
  run_q88measure_retry "$iolog" "$prefix.stdout.txt" "$prefix.stderr.txt" \
      --core "$core" --rom-dir "$romdir" --frames "$RUN" \
      --io-log "$iolog" \
      --vram-dump "$prefix.before.bin" --vram-dump-at "$BEFORE" \
      --vram-dump "$prefix.after.bin" --vram-dump-at "$DUMP" \
      --type-at 300 --type '\n' --type-at 700 --type "$TYPED" || { echo "0 0"; return 1; }
  if grep -qi 'untypable\|打てない' "$prefix.stderr.txt" 2>/dev/null; then
    echo "0 0"; return 1
  fi
  if [ ! -f "$before_out" ] || [ ! -f "$after_out" ]; then
    echo "0 0"; return 1
  fi
  local cell_count
  cell_count="$(python3 "$RECORD" --before "$before_out" --after "$after_out" \
      --count-only-rows 19 | cut -f1)"
  [ -n "$cell_count" ] || cell_count=0

  # EXT_BANK_CALLの窓復元OUT(0x71)が、直前のIN(0x71)で読んだ値と
  # 一致するかを--io-logだけから機械的に確認する(値そのものは
  # ハードウェア設定値=ポートの生値であって画面本文ではないので、
  # 不一致件数の判定にだけ使い、個々の値は出力しない)。
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

# EXT_BANK_CALL 1回につき、ポート0x71への操作は
#   IN(旧値を読む) -> OUT(バンク選択、窓を切り替える。旧値と違って当然)
#   -> OUT(窓を復元、旧値と一致するはず)
# の3手なので、IN直後の1回目のOUTは無視し、2回目のOUTだけをINの値と
# 突き合わせる(状態機械。単純に「INの次のOUT」を見ると、1回目の
# バンク選択OUTを誤って「復元」として比較してしまい、常に不一致に
# なる)。
pending = None   # IN(0x71)で読んだ値。Noneなら待機中でない
phase = 0        # 0=IN待ち, 1=1回目のOUT(バンク選択)待ち, 2=2回目のOUT(復元)待ち
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
    print(0)
else:
    print(1 if mismatch == 0 else 0)
PYEOF
)"
  echo "${cell_count} ${restore_ok}"
}

# -----------------------------------------------------------------------
say "1. 通常ビルド(修正後)で print sqr(4) が正しく完了すること"
NORMAL_ROM="$WORK/rom_normal"
if ! python3 "$BUILD" "$NORMAL_ROM" >"$WORK/build_normal.txt" 2>&1; then
  ng "build_main_rom.py(通常)が失敗"; cat "$WORK/build_normal.txt" >&2
fi
read -r cell_ok restore_ok_n < <(run_and_check "$NORMAL_ROM" "$WORK/normal")
if [ "${cell_ok:-0}" -gt 0 ] 2>/dev/null; then
  ok "通常ビルド: 出力セルが変化した(cell_count=${cell_ok}、ハングしていない)"
else
  ng "通常ビルド: 出力セルが変化しなかった(cell_count=${cell_ok:-0}、ハングの疑い)"
fi
if [ "$restore_ok_n" = "1" ]; then
  ok "通常ビルド: EXT_BANK_CALLの窓復元OUT(0x71)が直前のIN(0x71)の値と一致した"
else
  ng "通常ビルド: 窓復元OUT(0x71)が直前のIN(0x71)の値と食い違った(restore_ok=${restore_ok_n:-?})"
fi

# -----------------------------------------------------------------------
say "2. 陰性対照(--inject-ext-bank-bcde-fault): 修正前の状態を再現すると壊れること"
FAULT_ROM="$WORK/rom_fault"
if ! python3 "$BUILD" "$FAULT_ROM" --inject-ext-bank-bcde-fault >"$WORK/build_fault.txt" 2>&1; then
  ng "build_main_rom.py(--inject-ext-bank-bcde-fault)が失敗"; cat "$WORK/build_fault.txt" >&2
fi
read -r cell_f restore_ok_f < <(run_and_check "$FAULT_ROM" "$WORK/fault")
if [ "${cell_f:-0}" -eq 0 ] 2>/dev/null; then
  ok "陰性対照: 出力セルが変化しなかった(cell_count=${cell_f:-0}、修正前のハングを再現)"
else
  ng "陰性対照: 出力セルが変化してしまった(cell_count=${cell_f}、故障注入が効いていない可能性)"
fi
if [ "$restore_ok_f" = "0" ]; then
  ok "陰性対照: 窓復元OUT(0x71)が直前のIN(0x71)の値と食い違った(修正前の不具合を再現)"
else
  ng "陰性対照: 窓復元OUT(0x71)が一致してしまった(restore_ok=${restore_ok_f:-?}、故障注入が効いていない可能性)"
fi

# -----------------------------------------------------------------------
if [ "$FAILED" -eq 0 ]; then
  echo
  echo "l4_sqr_endtoend_selftest: OK"
else
  echo
  echo "l4_sqr_endtoend_selftest: NG" >&2
fi
exit "$FAILED"

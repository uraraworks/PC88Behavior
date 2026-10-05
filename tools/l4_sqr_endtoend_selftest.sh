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
# 検査: 直接モードとRUN経路の通常出力を固定記録で照合し、窓復元も確認する。
# RAM再配置後は直接モードの故障版も同じ数値を表示するため、RUN経路を
# 陰性対照の場面に加える（正常版のSQR結果を確認してから記録を固定）。
# RUNの戻り先は窓内にあるので、BC/DE退避欠落による復元不一致が出力にも現れる。
# 計測失敗・復元ペア未採取は陰性対照の成功に含めない。
# 詳細: docs/notes/tool-maintenance-2026-10-05-ram-relayout.md

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

# 既存の単発直接モードと同じ採取時点。正しい結果2とOkを確認した固定記録。
TYPED='print sqr(4)\n'
BEFORE=690
DUMP=824
RUN=1024
DIRECT_CELLS=1
DIRECT_OK_ROW=2
DIRECT_SHA=b7c6c0f9e88a41c3161497b494cd6f2f7f77eadc7c8e3b276afe06ffda6e9c95
# RUN場面では、記録器が番号行を原点にするためrun入力3セルも含まれる。
PROGRAM_CELLS=4
PROGRAM_OK_ROW=3
PROGRAM_SHA=5061a67904837027818fe593b751295b4baacd7b68e34af0f180ab5d7cdbd633

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
      --type-at 300 --type '\n' --type-at 700 --type "$TYPED" || { echo "NA NA NA -1"; return 1; }
  if grep -qi 'untypable\|打てない' "$prefix.stderr.txt" 2>/dev/null; then
    echo "NA NA NA -1"; return 1
  fi
  if [ ! -f "$before_out" ] || [ ! -f "$after_out" ]; then
    echo "NA NA NA -1"; return 1
  fi
  local cell_count ok_row output_sha record
  record="$(python3 "$RECORD" --before "$before_out" --after "$after_out" \
      --count-only-rows 19)" || { echo "NA NA NA -1"; return 1; }
  read -r cell_count ok_row output_sha <<< "$record"
  [ -n "$output_sha" ] || { echo "NA NA NA -1"; return 1; }

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
    print(-1)  # 復元ペア未採取を故障検出にしない
else:
    print(1 if mismatch == 0 else 0)
PYEOF
)" || { echo "NA NA NA -1"; return 1; }
  echo "${cell_count} ${ok_row} ${output_sha} ${restore_ok}"
}

# -----------------------------------------------------------------------
say "1. 通常ビルド: 直接モードとRUN経路のSQR結果を固定記録で照合"
NORMAL_ROM="$WORK/rom_normal"
if ! python3 "$BUILD" "$NORMAL_ROM" >"$WORK/build_normal.txt" 2>&1; then
  cat "$WORK/build_normal.txt" >&2; exit 1
fi
normal="$(run_and_check "$NORMAL_ROM" "$WORK/direct")" || { ng "直接モードの計測失敗"; exit 1; }
read -r cells ok_row sha restore <<< "$normal"
if [ "$cells" = "$DIRECT_CELLS" ] && [ "$ok_row" = "$DIRECT_OK_ROW" ] && [ "$sha" = "$DIRECT_SHA" ] && [ "$restore" = "1" ]; then
  ok "直接モード: 固定記録一致(1セル、相対Ok行2、SHA一致)、窓復元一致"
else
  ng "直接モード: 正常記録または窓復元が不一致"; exit 1
fi

TYPED='10 print sqr(4)\nrun\n'
DUMP=1000
RUN=1300
normal="$(run_and_check "$NORMAL_ROM" "$WORK/normal")" || { ng "RUN経路の計測失敗"; exit 1; }
read -r cells ok_row sha restore <<< "$normal"
if [ "$cells" = "$PROGRAM_CELLS" ] && [ "$ok_row" = "$PROGRAM_OK_ROW" ] && [ "$sha" = "$PROGRAM_SHA" ] && [ "$restore" = "1" ]; then
  ok "RUN経路: 固定記録一致(4セル、相対Ok行3、SHA一致)、窓復元一致"
else
  ng "RUN経路: 正常記録または窓復元が不一致"; exit 1
fi

say "2. 陰性対照: RUN経路でBC/DE退避欠落の影響を検出"
FAULT_ROM="$WORK/rom_fault"
if ! python3 "$BUILD" "$FAULT_ROM" --inject-ext-bank-bcde-fault >"$WORK/build_fault.txt" 2>&1; then
  cat "$WORK/build_fault.txt" >&2; exit 1
fi
fault="$(run_and_check "$FAULT_ROM" "$WORK/fault")" || { ng "陰性対照の計測失敗"; exit 1; }
read -r cells ok_row sha restore <<< "$fault"
if [ -n "$sha" ] && [ "$sha" != "NA" ] && { [ "$cells" != "$PROGRAM_CELLS" ] || [ "$ok_row" != "$PROGRAM_OK_ROW" ] || [ "$sha" != "$PROGRAM_SHA" ]; }; then
  ok "陰性対照: 固定した正常記録と不一致(cell_count=${cells}、相対Ok行=${ok_row}、SHA不一致)"
else
  ng "陰性対照: 正常記録との不一致を確認できなかった"
fi
if [ "$restore" = "0" ]; then
  ok "陰性対照: 採取した窓復元ペアに食い違いあり"
else
  ng "陰性対照: 窓復元不一致を確認できなかった(restore_ok=${restore:-?})"
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

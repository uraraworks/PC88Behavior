#!/usr/bin/env bash
# tools/recv_run_field_leak_selftest.sh
#
# tools/compare_recv_run_fields.py が受信runの値を一切標準出力・標準
# エラーへ出さないことを検査する。tools/screen_content_leak_selftest.sh
# と同型: 検査器を信用してよいのは「わざと壊して検出できる」ことを
# 確かめた後だけ（陰性対照）。
#
# フィクスチャは全て自作の合成データ。公式ROM・公式ディスクは不要かつ
# 未使用。合成データの各バイト値には、実データと混同しようがない
# 16進の合成カナリア（アルファベットを含む2桁16進、10進出力とは絶対に
# 衝突しない）を埋め込み、それが出力に現れないことを確認する。
#
# 検査項目:
#   a. compare_recv_run_fields.py が stage1/stage2 のどちらの出力にも
#      合成カナリア値を出さない
#   b. 判定そのものが正しく働く(合成データはC1になる設計)
#   c. comparatorの故障注入: 同一runどうしでeqが全位置True、1バイトだけ
#      差し替えたrunでその位置だけFalseになる
#   d. 陰性対照: わざと値を出す壊れた版では検査(a.相当)が正しく落ちる
#   e. 壊れた版は一時コピーのみで本体は無傷
#   f. 応答run抽出器(stage3)が出力に合成カナリア値を1文字も出さない
#   g. stage3の故障注入: 同一応答run列どうしはall_positions_equal=True、
#      1バイト差し替えるとその位置(run番号・位置番号)だけ食い違う
#   h. 陰性対照: 応答run値をわざと出す壊れたstage3では検査(f.相当)が落ちる
#
# 使い方: tools/recv_run_field_leak_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPARATOR="$SCRIPT_DIR/compare_recv_run_fields.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# 実データと混同しようがない合成カナリア(アルファベットを含む16進2桁)。
# 本検査器の出力は件数・真偽値・位置番号(10進の数字のみ)しか出さない
# 設計なので、アルファベットを含む16進文字列が出力に現れたら即座に
# 「値が漏れた」と判定できる。
CANARIES=("CE" "D1" "D2" "B7" "E1" "E2")

# --- フィクスチャ生成(合成データのみ。公式ROM・公式ディスク不使用) --------
#
# 2つの連続READ段(群R相当、直前受信runのpos0を共通のカナリアCEに揃え、
# pos1は段ごとに変える)と2つの単発段(群S相当、pos0を共通のカナリアB7に
# 揃える)を作る。pos0は「群R内で一致し、群Sと異なり、符号がR>Sで一貫する」
# ようCE(206) > B7(183)にしてあり、判定はC1になる設計。
SYNTH="$WORK/synth.iolog.txt"
python3 - > "$SYNTH" <<'PYEOF'
CANARY_R0 = 0xCE
CANARY_R1_A = 0xD1
CANARY_R1_B = 0xD2
CANARY_S0 = 0xB7
CANARY_S1_A = 0xE1
CANARY_S1_B = 0xE2

lines = []
seq = 1
clock = 10


def emit(cpu, kind, port, value, pc="0000"):
    global seq, clock
    val = f"{value:02X}" if isinstance(value, int) else value
    lines.append(f"{seq} {clock} 100 {cpu} {kind} {port} {val} {pc}")
    seq += 1
    clock += 1


def emit_recv_run(values):
    for v in values:
        emit("sub", "IN", "00FC", v)


def emit_command(opcode, params, results):
    emit("sub", "OUT", "00FB", opcode)
    for p in params:
        emit("sub", "OUT", "00FB", p)
    for r in results:
        emit("sub", "IN", "00FB", r)


def emit_continuous_stage(n_reads):
    emit_command(0x0F, [0, 0], [])
    emit_command(0x08, [], [0, 0])
    emit_command(0x04, [0], [0])
    for _ in range(n_reads):
        emit_command(0x06, [0] * 8, [0] * 7)


def emit_single_stage():
    emit_continuous_stage(1)


emit_recv_run([CANARY_R0, CANARY_R1_A])
emit_continuous_stage(2)

emit_recv_run([CANARY_S0, CANARY_S1_A])
emit_single_stage()

emit_recv_run([CANARY_R0, CANARY_R1_B])
emit_continuous_stage(2)

emit_recv_run([CANARY_S0, CANARY_S1_B])
emit_single_stage()

import sys
sys.stdout.write("\n".join(lines) + "\n")
PYEOF

# --- a. stage1/stage2 のどちらの出力にもカナリアが出ないこと -------------
python3 "$COMPARATOR" stage1 --iolog "$SYNTH" > "$WORK/s1.out" 2> "$WORK/s1.err"
RC_S1=$?
python3 "$COMPARATOR" stage2 --iolog "$SYNTH" > "$WORK/s2.out" 2> "$WORK/s2.err"
RC_S2=$?

LEAKED=0
for c in "${CANARIES[@]}"; do
  if grep -qF "$c" "$WORK/s1.out" "$WORK/s1.err" "$WORK/s2.out" "$WORK/s2.err"; then
    LEAKED=1
  fi
done

if [[ "$LEAKED" -eq 1 ]]; then
  fail "a. compare_recv_run_fields.py の出力へ受信runの値(カナリア)が漏れた"
else
  pass "a. compare_recv_run_fields.py はstage1/stage2のどちらでも値を出さない"
fi

# --- b. 合成データの設計どおりC1と判定されること --------------------------
if [[ "$RC_S1" -eq 0 && "$RC_S2" -eq 0 ]] && grep -q '^verdict=C1$' "$WORK/s2.out"; then
  pass "b. 合成データ(設計どおりR>Sで一貫)がC1と判定される"
else
  fail "b. 合成データがC1と判定されなかった(rc_s1=$RC_S1 rc_s2=$RC_S2)"
fi

# --- c. comparatorの故障注入(合成データ、内部関数を直接検査) --------------
FAULT_OUT="$(python3 - "$COMPARATOR" <<'PYEOF'
import importlib.util
import sys

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("cmp_mod", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

run_a = [0x10, 0x20, 0x30, 0x40]
run_b = list(run_a)  # 同一run

# 同一runどうし: 全位置でTrueのはず
same_eq = [mod._eq(a, b) for a, b in zip(run_a, run_b)]

# 1バイトだけ差し替え(位置2)
run_c = list(run_a)
run_c[2] = 0x31
diff_eq = [mod._eq(a, b) for a, b in zip(run_a, run_c)]

ok = True
ok &= all(same_eq)
ok &= diff_eq == [True, True, False, True]
print("OK" if ok else "NG")
PYEOF
)"

if [[ "$FAULT_OUT" == "OK" ]]; then
  pass "c. comparatorの故障注入: 同一runは全位置eq=True、1バイト差し替えはその位置だけFalse"
else
  fail "c. comparatorの故障注入が期待どおりに働かなかった"
fi

# --- d. 陰性対照: わざと値を出す壊れた版では検査(a.相当)が落ちること ------
# compare_recv_run_fields.py は同ディレクトリの兄弟モジュール(analyze_*.py
# 等)をsys.path経由でimportするため、壊れた版も同じディレクトリ
# (tools/)に一時ファイルとして置く。trapで確実に削除する。
BROKEN="$SCRIPT_DIR/.broken_compare_recv_run_fields_selftest_tmp.py"
rm -f "$BROKEN"
trap 'rm -rf "$WORK" "$BROKEN"' EXIT
cp "$COMPARATOR" "$BROKEN"
python3 - "$BROKEN" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
needle = "def _print_stage1(rep: dict, out) -> None:"
assert needle in text, "注入対象の関数定義が見つからない"
injected = (
    "def _debug_leak(rep):\n"
    "    import sys as _sys\n"
    "    runs = rep.get('_runs')\n"
    "    sub_rows = rep.get('_sub_rows')\n"
    "    if runs and sub_rows:\n"
    "        for idx in runs[0]:\n"
    "            print(f'DEBUG byte={sub_rows[idx].value:02X}', file=_sys.stderr)\n\n\n"
    + needle
)
text = text.replace(needle, injected, 1)
text = text.replace(
    "            rep = stage1_report(args.iolog)\n"
    "            _print_stage1(rep, sys.stdout)\n",
    "            rep = stage1_report(args.iolog)\n"
    "            _debug_leak(rep)\n"
    "            _print_stage1(rep, sys.stdout)\n",
    1,
)
open(path, "w", encoding="utf-8").write(text)
PYEOF

python3 "$BROKEN" stage1 --iolog "$SYNTH" > "$WORK/broken.out" 2> "$WORK/broken.err"

BROKEN_LEAKED=0
for c in "${CANARIES[@]}"; do
  if grep -qF "$c" "$WORK/broken.out" "$WORK/broken.err"; then
    BROKEN_LEAKED=1
  fi
done

if [[ "$BROKEN_LEAKED" -eq 1 ]]; then
  pass "d. 陰性対照: 値を出す壊れた版では検査(a.相当)が正しく落ちる（検出力あり）"
else
  fail "d. 陰性対照: 壊れた版でもカナリアが検出されなかった（検査に検出力が無い）"
fi

# 壊れた版は $WORK 配下の一時コピーのみで、tools/ の実体は変更していない。
if [[ -f "$COMPARATOR" ]] && ! diff -q "$COMPARATOR" "$BROKEN" > /dev/null 2>&1; then
  pass "e. 壊れた版は一時コピーのみで、tools/compare_recv_run_fields.py 本体は無傷"
else
  fail "e. tools/compare_recv_run_fields.py 本体が変更されているか、比較に失敗した"
fi

# --- stage3(応答run抽出器)向けフィクスチャ(合成データのみ) ---------------
#
# main視点のOUT $FD(SEND_PCS)とIN $FC(RECV_HANDSHAKE_PCS/RECV_BULK_PCS)を
# 交互に並べ、応答run(sub→main)を2本作る。A/B2本のログで、応答run 0の
# pos0を共通カナリアF0に揃え、pos1をF1(A)/F2(B)で分ける(1バイト差し替え
# 相当)。応答run 1はA/Bで完全一致させる(対照)。
CANARY_F0="F0"
CANARY_F1="F1"
CANARY_F2="F2"
CANARY_F3="F3"

gen_stage3_fixture() {
  # $1: 出力パス, $2: run0 pos1のカナリア(F1 or F2)
  python3 - "$1" "$2" <<'PYEOF'
import sys

out_path, run0_pos1 = sys.argv[1], sys.argv[2]
lines = []
seq = 1
clock = 10


def emit(cpu, kind, port, value_hex, pc):
    global seq, clock
    lines.append(f"{seq} {clock} 100 {cpu} {kind} {port} {value_hex} {pc}")
    seq += 1
    clock += 1


# 要求run(main→sub)
emit("main", "OUT", "00FD", "01", "37F4")
emit("main", "OUT", "00FD", "02", "3811")
# 応答run0(sub→main、ハンドシェイク経由): pos0共通、pos1だけ差し替え
emit("main", "IN", "00FC", "F0", "3863")
emit("main", "IN", "00FC", run0_pos1, "3880")
# 次の要求run
emit("main", "OUT", "00FD", "03", "37F4")
# 応答run1(sub→main、バルク経由): A/Bで完全一致(対照)
emit("main", "IN", "00FC", "F3", "C269")
emit("main", "IN", "00FC", "F3", "C269")

with open(out_path, "w", encoding="utf-8") as fp:
    fp.write("\n".join(lines) + "\n")
PYEOF
}

SYNTH3_A="$WORK/synth3_a.iolog.txt"
SYNTH3_B="$WORK/synth3_b.iolog.txt"
gen_stage3_fixture "$SYNTH3_A" "$CANARY_F1"
gen_stage3_fixture "$SYNTH3_B" "$CANARY_F2"
# 窓の終端は全イベントを含む十分大きな値に固定する。
UNTIL_CLOCK=9999

# --- f. stage3の出力にカナリアが出ないこと --------------------------------
python3 "$COMPARATOR" stage3 --iolog-a "$SYNTH3_A" --iolog-b "$SYNTH3_B" \
  --until-clock "$UNTIL_CLOCK" > "$WORK/s3.out" 2> "$WORK/s3.err"
RC_S3=$?

STAGE3_CANARIES=("$CANARY_F0" "$CANARY_F1" "$CANARY_F2" "$CANARY_F3")
LEAKED3=0
for c in "${STAGE3_CANARIES[@]}"; do
  if grep -qF "$c" "$WORK/s3.out" "$WORK/s3.err"; then
    LEAKED3=1
  fi
done

if [[ "$LEAKED3" -eq 1 ]]; then
  fail "f. compare_recv_run_fields.py stage3 の出力へ応答runの値(カナリア)が漏れた"
else
  pass "f. compare_recv_run_fields.py stage3 は値を出さない"
fi

# --- g. stage3の故障注入: 同一応答run列は一致、1バイト差し替えは局所化 ----
if [[ "$RC_S3" -eq 0 ]] \
  && grep -q '^run_count_equal=True$' "$WORK/s3.out" \
  && grep -q '^run_lengths_equal=True$' "$WORK/s3.out" \
  && grep -q '^all_positions_equal=False$' "$WORK/s3.out" \
  && grep -q '^mismatch_count=1$' "$WORK/s3.out" \
  && grep -q '^first_mismatch_run=0$' "$WORK/s3.out" \
  && grep -q '^first_mismatch_pos=1$' "$WORK/s3.out"; then
  pass "g.(前半) A≠B(応答run0 pos1のみ差し替え)は正しくその位置だけFalseになる"
else
  fail "g.(前半) A≠Bの故障注入結果が期待どおりでなかった(rc_s3=$RC_S3)"
fi

python3 "$COMPARATOR" stage3 --iolog-a "$SYNTH3_A" --iolog-b "$SYNTH3_A" \
  --until-clock "$UNTIL_CLOCK" > "$WORK/s3_same.out" 2> "$WORK/s3_same.err"
RC_S3_SAME=$?
if [[ "$RC_S3_SAME" -eq 0 ]] && grep -q '^all_positions_equal=True$' "$WORK/s3_same.out" \
  && grep -q '^mismatch_count=0$' "$WORK/s3_same.out"; then
  pass "g.(後半) 同一ログどうしの応答runは全位置eq=True"
else
  fail "g.(後半) 同一ログどうしの応答runが一致と判定されなかった"
fi

# --- h. 陰性対照: 応答run値をわざと出す壊れたstage3では検査(f.相当)が落ちる
BROKEN3="$SCRIPT_DIR/.broken_compare_recv_run_fields_stage3_selftest_tmp.py"
rm -f "$BROKEN3"
trap 'rm -rf "$WORK" "$BROKEN" "$BROKEN3"' EXIT
cp "$COMPARATOR" "$BROKEN3"
python3 - "$BROKEN3" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
needle = "def _print_stage3(rep: dict, out) -> None:"
assert needle in text, "注入対象の関数定義が見つからない"
injected = (
    "def _debug_leak_stage3(runs_a):\n"
    "    import sys as _sys\n"
    "    for run in runs_a:\n"
    "        for ev in run:\n"
    "            print(f'DEBUG byte={ev.value:02X}', file=_sys.stderr)\n\n\n"
    + needle
)
text = text.replace(needle, injected, 1)
text = text.replace(
    "            rep = stage3_report(args.iolog_a, args.iolog_b, args.until_clock)\n"
    "            _print_stage3(rep, sys.stdout)\n",
    "            rep = stage3_report(args.iolog_a, args.iolog_b, args.until_clock)\n"
    "            _debug_leak_stage3(_response_runs(m2s.parse_iolog(args.iolog_a)[0], args.until_clock))\n"
    "            _print_stage3(rep, sys.stdout)\n",
    1,
)
open(path, "w", encoding="utf-8").write(text)
PYEOF

python3 "$BROKEN3" stage3 --iolog-a "$SYNTH3_A" --iolog-b "$SYNTH3_B" \
  --until-clock "$UNTIL_CLOCK" > "$WORK/broken3.out" 2> "$WORK/broken3.err"

BROKEN3_LEAKED=0
for c in "${STAGE3_CANARIES[@]}"; do
  if grep -qF "$c" "$WORK/broken3.out" "$WORK/broken3.err"; then
    BROKEN3_LEAKED=1
  fi
done

if [[ "$BROKEN3_LEAKED" -eq 1 ]]; then
  pass "h. 陰性対照: 応答run値を出す壊れたstage3では検査(f.相当)が正しく落ちる（検出力あり）"
else
  fail "h. 陰性対照: 壊れたstage3でもカナリアが検出されなかった（検査に検出力が無い）"
fi

if [[ -f "$COMPARATOR" ]] && ! diff -q "$COMPARATOR" "$BROKEN3" > /dev/null 2>&1; then
  pass "h.(補足) 壊れたstage3版は一時コピーのみで、tools/compare_recv_run_fields.py 本体は無傷"
else
  fail "h.(補足) tools/compare_recv_run_fields.py 本体が変更されているか、比較に失敗した"
fi

exit "$FAIL"

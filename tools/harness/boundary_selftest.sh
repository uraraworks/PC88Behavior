#!/usr/bin/env bash
# ROM 境界の横断記録(--boundary-log、ゴールB の器具)の自己検査。
# 公式 ROM・公式ディスク・ゲームは一切使わない。make_boundary_rom.py が作る
# 自作の試験 ROM(起動コードが小さなルーチンを RAM の 9000h へ写して飛ぶ)で、
# 方針ノート docs/notes/goal-b-policy-2026-10-24.md 第7節2 の自己検査を行う。
#
#   陽性対照: ROM の X を CALL で2回(戻り2回)、Y を JP で1回(飛び込み型)、
#             RST 28h を1回、ROM の Z をデータとして読む、RAM の W を
#             ROM 側ルーチンと共有する。
#   陰性対照: ROM 内部どうしの CALL、RAM 内部どうしの CALL、ROM が ROM を読む、
#             RAM 側だけが触る W2 は、記録に出ない。
#   値が出ない検査: レジスタ・RAM・ROM データに目印の値(A5C3 / 5AE1 / A5)を
#             仕込み、出力にその表記が1つも出ないこと。
#   割り込み: IM1 の割り込みが RAM のループから ROM のハンドラへ入る横断が
#             「割り込み受理直後」として数えられ、戻りも対応づくこと。
#   故障注入: 器具をわざと壊した走(①分類を常に RAM ②戻りの対応づけを切る
#             ③レジスタ値を出力に混ぜる)で、判定が「狙った判定だけ」NG になること。
#             壊した走の NG の集合が期待と一致するまで合格にしない
#             (手前の別の判定で落ちているだけのものを検出力の証拠にしない)。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-boundary.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"
make -s -C "$FRONTEND_DIR"

mkdir -p "$WORK/rom-main" "$WORK/rom-int"
python3 "$REPO/tools/harness/make_boundary_rom.py" "$WORK/rom-main" >/dev/null
python3 "$REPO/tools/harness/make_boundary_rom.py" "$WORK/rom-int" --variant int >/dev/null

run() {  # run <romdir> <out> [frames] ; 環境変数はそのまま引き継ぐ
  "$FRONTEND" --core "$CORE" --rom-dir "$1" --frames "${3:-20}" \
    --out "$WORK/trace-$$.txt" --boundary-log "$2" \
    >"$2.stdout" 2>"$2.stderr" || { cat "$2.stderr" >&2; ng "走りが失敗した: $2"; }
}

# ---- 判定器 -------------------------------------------------------------
# 出力ファイルを読み、判定ごとに "PASS 名前" / "FAIL 名前" を1行ずつ出す。
# 期待値は make_boundary_rom.py の命令列から手で決めたもの(コアの出力から
# 写したものではない)。
cat > "$WORK/judge.py" <<'PYEOF'
import re, sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
lines = text.splitlines()

A, B, C = {}, {}, {}
for ln in lines:
    f = ln.split()
    if not f or ln.startswith("#"):
        continue
    if f[0] == "A" and len(f) == 7:
        A[int(f[1], 16)] = tuple(int(x) for x in f[2:])      # total call jump int ret
    elif f[0] == "B" and len(f) == 3:
        B[int(f[1], 16)] = int(f[2])
    elif f[0] == "C" and len(f) == 6:
        C[int(f[1], 16)] = tuple(int(x) for x in f[2:])      # rom_r rom_w ram_r ram_w

m = re.search(r"^instr\s*: ram=(\d+) rom=(\d+) none=(\d+)", text, re.M)
n_ram, n_rom = (int(m.group(1)), int(m.group(2))) if m else (0, 0)

X, Y, RST, Z, W, W2 = 0x1000, 0x2000, 0x0028, 0x3000, 0xA800, 0xA900
results = []
def j(name, cond): results.append((name, bool(cond)))

j("J0_wellformed", all(("# (%s 終わり)" % s) in text for s in "ABC") and m is not None)
j("J_CLASS_SEEN", n_ram > 0 and n_rom > 0)

# a. 横断(陽性)。total call jump int ret
j("A_X_call2_ret2",  A.get(X)   == (2, 2, 0, 0, 2))
j("A_Y_jump1",       A.get(Y)   == (1, 0, 1, 0, 0))
j("A_RST_call1_ret1", A.get(RST) == (1, 1, 0, 0, 1))
# a. 横断(陰性): ROM 内部の CALL(0200,1100)・RAM 内部の CALL(9040)・
#    ROM→RAM の JP/RET(9020 等)・起動の 0100 は出ない。出るのは3つだけ。
j("A_ONLY_3_TARGETS", set(A) == {X, Y, RST})

# b. ROM のデータ読み。LD A,(Z) で Z、LD HL,(Z) で Z と Z+1
j("B_Z",     B.get(Z) == 2 and B.get(Z + 1) == 1)
# b の陰性: ROM が ROM を読む(1200)・起動 LDIR が像を読む(0300〜)は出ない
j("B_ONLY_Z", set(B) == {Z, Z + 1})

# c. 共有 RAM 番地。W は ROM(X)が2回読み2回書き、RAM が1回読み1回書く
j("C_W",   C.get(W) == (2, 2, 1, 1))
j("C_W2_absent", W2 not in C)
# c の中身は、W・RAM コード領域(起動の LDIR が書き RAM が読む 9000-9040)・
# スタック(RAM の CALL が積み ROM の RET が取る AFFE-AFFF)に限られる
j("C_ONLY_EXPLAINED", all(a == W or 0x9000 <= a <= 0x9040 or a in (0xAFFE, 0xAFFF) for a in C))

# c の陰性: 起動の LDIR が RAM へ写した試験ルーチンの領域(W を除く)は、
# RAM 側命令のオペランド読みを数えない限り c に出ない(出るならコード領域全体が「共有」になる)
j("C_CODE_AREA_ABSENT", not any(0x9000 <= a <= 0x9040 for a in C))

# 値が出ない: 目印の語が1つも出ない(出力先のパスを含む見出し行は除く)
body = "\n".join(l for l in lines if not re.match(r"(core|rom-dir|disk|disk2)\s*:", l))
j("V_NO_VALUES", not re.search(r"(?<![0-9A-Za-z])(A5C3|5AE1|A5|5A|E1|C3)(?![0-9A-Za-z])", body))

for name, ok in results:
    print(("PASS " if ok else "FAIL ") + name)
PYEOF

cat > "$WORK/judge_int.py" <<'PYEOF'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
A = {}
for ln in text.splitlines():
    f = ln.split()
    if f and f[0] == "A" and len(f) == 7:
        A[int(f[1], 16)] = tuple(int(x) for x in f[2:])
res = []
def j(n, c): res.append((n, bool(c)))
t = A.get(0x38)
# total call jump int ret。全部が割り込み受理直後の呼び出し型で、戻りも対応づく
# (走りの終わりで戻りが間に合わない最後の1回だけは許す)
j("I_0038_all_int_call", t is not None and t[0] >= 5 and t[1] == t[0] and t[2] == 0 and t[3] == t[0])
j("I_0038_returns", t is not None and t[4] >= t[0] - 1)
j("I_ONLY_0038", set(A) == {0x38})
for n, c in res:
    print(("PASS " if c else "FAIL ") + n)
PYEOF

judge() { python3 -I "$WORK/judge.py" "$1"; }
fails() { judge "$1" | sed -n 's/^FAIL //p' | sort | tr '\n' ' '; }

# ---- 1. 通常走: 全判定 PASS ---------------------------------------------
run "$WORK/rom-main" "$WORK/base.txt"
JUDGED="$(judge "$WORK/base.txt")"
N_JUDGE="$(printf '%s\n' "$JUDGED" | wc -l | tr -d ' ')"
BASE_FAILS="$(fails "$WORK/base.txt")"
[ -z "$BASE_FAILS" ] || { printf '%s\n' "$JUDGED" >&2; ng "通常走で NG の判定がある: $BASE_FAILS"; }
printf '%s\n' "$JUDGED" | sed 's/^/  /'
ok "通常走: 全${N_JUDGE}判定 PASS"

# ---- 2. 割り込み受理直後の横断 -------------------------------------------
run "$WORK/rom-int" "$WORK/int.txt" 30
JI="$(python3 -I "$WORK/judge_int.py" "$WORK/int.txt")"
printf '%s\n' "$JI" | sed 's/^/  /'
printf '%s\n' "$JI" | grep -q '^FAIL' && ng "割り込み受理直後の横断の判定が NG"
N_INT="$(printf '%s\n' "$JI" | wc -l | tr -d ' ')"
ok "割り込み: ${N_INT}判定 PASS"

# ---- 3. オフのとき既存の測定出力を変えない --------------------------------
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom-main" --frames 20 \
  --out "$WORK/trace-off.txt" >"$WORK/off.stdout" 2>"$WORK/off.stderr" \
  || ng "--boundary-log なしの走りが失敗した"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom-main" --frames 20 \
  --out "$WORK/trace-on.txt" --boundary-log "$WORK/on.txt" \
  >"$WORK/on.stdout" 2>"$WORK/on.stderr" || ng "--boundary-log ありの走りが失敗した"
cmp -s "$WORK/trace-off.txt" "$WORK/trace-on.txt" \
  || ng "--boundary-log の有無で既存の trace 出力が変わった"
ok "--boundary-log の有無で既存の trace 出力(--out)は1バイトも変わらない"
[ ! -e "$WORK/off.txt" ] || ng "オフの走りで記録ファイルが作られた"
ok "--boundary-log を付けなければ記録ファイルは作られない"

# ---- 4. 故障注入: 壊した走が「狙った判定だけ」NG になる ---------------------
# 期待する NG の集合(判定名はアルファベット順)。壊した走では J0_wellformed が
# PASS のまま(走りも出力の形も壊れていない)であることも、集合の一致で確かめている。
inject() {  # inject <名前> <環境変数の値> <期待するNG集合>
  local name="$1" kind="$2" expect="$3" got
  Q88MEASURE_FAULT_BOUNDARY="$kind" run "$WORK/rom-main" "$WORK/fault-$name.txt"
  got="$(fails "$WORK/fault-$name.txt")"
  if [ "$got" != "$expect" ]; then
    judge "$WORK/fault-$name.txt" >&2
    ng "故障注入 $name: NG の集合が期待と違う (期待: $expect / 実際: $got)"
  fi
  printf '故障注入 %s: 狙いの判定で NG (%s)\n' "$name" "$got"
}

# ①分類を常に RAM → 横断も ROM データ読みも共有も消える。値は出ない(V は PASS)
EXP1="A_ONLY_3_TARGETS A_RST_call1_ret1 A_X_call2_ret2 A_Y_jump1 B_ONLY_Z B_Z C_W J_CLASS_SEEN "
# ②戻りの対応づけを切る → ret が 0 になる判定だけが落ちる(Y は元々 ret=0 なので PASS のまま)
EXP2="A_RST_call1_ret1 A_X_call2_ret2 "
# ③レジスタ値を1つ出力に混ぜる → 値が出ない判定だけが落ちる(他は全て PASS のまま)
EXP3="V_NO_VALUES "

FAULT_LINES="$(
  inject class_ram class_ram "$EXP1"
  inject no_return no_return "$EXP2"
  inject leak_reg  leak_reg  "$EXP3"
)" || exit 1
printf '%s\n' "$FAULT_LINES"
# ③は混ぜた値が実際に出力へ載っていることも見る(判定器の見落としではないこと)
grep -q '故障注入(leak_reg)で混ぜたレジスタ値: A5C3' "$WORK/fault-leak_reg.txt" \
  || ng "故障注入 leak_reg: 混ぜたはずの値が出力に無い(注入が効いていない)"
ok "故障注入 leak_reg: 目印 A5C3 が実際に出力へ載り、値が出ない検査だけがそれを検出した"

echo "全判定 PASS (通常走 ${N_JUDGE}判定 + 割り込み ${N_INT}判定 + オフ時不変 2項目)"
echo "故障注入3種(class_ram / no_return / leak_reg)がそれぞれ狙いの判定で NG"

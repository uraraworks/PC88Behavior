#!/usr/bin/env bash
# tools/l4_mbf_z80_selftest.sh — M7段階4a-1。src/l4_basic/mbf_single.asm
# （単精度MBF四則演算・符号反転・比較・整数変換）を実際にZ80として実行し、
# tools/l4_mbf_oracle_v2.py（GW-BASIC由来の予測器）とバイト単位で突き合わせる
# tools/l4_mbf_conform.py のラッパ。詳細・実行手段の説明は
# tools/l4_mbf_conform.py のモジュールdocstring参照。
#
# run_all_selftests.sh から毎回回す想定のため、件数は数千件規模の探索的な
# 照合（開発時にターミナルで直接 l4_mbf_conform.py を叩いて行った）より
# 少なめに抑えている（境界値・機械構成した丸め境界は件数によらず常に
# 含まれるので、検出力そのものは大きく落ちない）。
#
# 公式ROM・私物は一切不要（自作の空ROMをq88measureで走らせるだけ）。
# tools/harness/frontend/q88measure と vendor/quasi88-libretro のコアが
# 要る（tools/setup_harness.sh 済みであること。無ければ即NGで知らせる）。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFORM="$REPO/tools/l4_mbf_conform.py"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"

ok() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng() { printf '  \033[31mNG\033[0m   %s\n' "$1" >&2; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "NG: コア成果物が無い。先に tools/setup_harness.sh を実行すること" >&2
  exit 1
fi

make -s -C "$REPO/tools/harness/frontend" || { echo "NG: q88measureのビルドに失敗" >&2; exit 1; }
[ -x "$FRONTEND" ] || { echo "NG: $FRONTEND が無い" >&2; exit 1; }

overall=0

run_case() {
  local desc="$1"; shift
  if python3 "$CONFORM" "$@" >/tmp/l4mbf_z80_selftest.$$ 2>&1; then
    ok "$desc"
  else
    ng "$desc"
    cat /tmp/l4mbf_z80_selftest.$$ >&2
    overall=1
  fi
  rm -f /tmp/l4mbf_z80_selftest.$$
}

echo "==> 正常系（境界値＋乱数、演算ごと）"
run_case "add  N=400"  add  -n 400 --frames 90
run_case "sub  N=400"  sub  -n 400 --frames 90
run_case "neg  N=300"  neg  -n 300 --frames 60
run_case "cmp  N=300"  cmp  -n 300 --frames 60
run_case "itos N=400"  itos -n 400 --frames 60
run_case "mul  N=400"  mul  -n 400 --frames 200
run_case "div  N=400"  div  -n 400 --frames 900
# fin: docs/spec/l4-basic.md 第3.6版5.1.1節の推定REP01(1手ごとに
# 単精度へ丸め直す、$FINE/MDPTENの倍精度56bit経由・$CSD1回丸めではない)
# に作り直し済み(2026-09-15、M7)。予測器もfin_algo="rep01"に合わせて
# あり(tools/l4_mbf_conform.py expected_fin)、乱数複数シード計5000件超・
# 境界値(指数上下限近く・7桁定数・`!`・e+/e-の大小・小数点以下の桁数・
# 先頭0の小数)の照合で不一致0件を確認済みなので--max-mismatchは0のまま
# 使う(REP01自体がl4-s4i・l4-s4j実測57件中55件しか再現しない推定である
# ことは仕様書5.1.1節に記録済みで、この0件はZ80実装と予測器の一致を
# 指すもの)。
run_case "fin  N=1300 seed1" fin -n 1300 --seed 1 --frames 3000 --max-mismatch 0
run_case "fin  N=1300 seed2" fin -n 1300 --seed 2 --frames 3000 --max-mismatch 0
run_case "fin  N=1300 seed3" fin -n 1300 --seed 3 --frames 3000 --max-mismatch 0
run_case "fin  N=1300 seed4" fin -n 1300 --seed 4 --frames 3000 --max-mismatch 0
# fout: 本件(M7段階4-2)でGW手順($FOTNV相当の倍精度DBL_TABLEスケール＋
# 「0.5を足して切り捨て」)へ作り直した。乱数照合は複数シード合計
# 5000件超・境界値(MAX_POS/MAX_NEG/MIN_POS/MIN_NEG含む)・仕様書第5節の
# 観測例つきで不一致0件を確認済みなので--max-mismatchは0にする
# (frames=20000: 倍精度演算が単精度より1ステップあたり重く、旧来の
# frames=2000では大きいバッチの途中でフレーム予算が尽き出力が書かれない
# 〔missing〕まま不一致扱いになったため引き上げた)。
run_case "fout N=1700 seed1" fout -n 1700 --seed 1 --frames 20000 --max-mismatch 0
run_case "fout N=1700 seed2" fout -n 1700 --seed 2 --frames 20000 --max-mismatch 0
run_case "fout N=1700 seed3" fout -n 1700 --seed 3 --frames 20000 --max-mismatch 0

echo "==> 故障注入（陰性対照。不一致が出ることを正常系として扱う）"
# 2026-09-20追記(l4-c7実装後の見直し): 単精度add/sub/mul/divがaway丸め
# (docs/spec/l4-basic.md 5.3a節、759de46)へ変わったのに合わせ、故障注入
# 点を実際に踏まれる箇所へ付け直した(tools/l4_mbf_conform.py FAULTS参照)。
# - add --fault sticky: 同符号加算(WK_BORROW=0)はaway化により
#   guard=0x80でのWK_STICKYの値が丸め方向に影響しなくなった(away規則の
#   数学的帰結、guard bit7=1なら常に切り上げ)ため、この故障は検出不能に
#   なった。away化そのものを検出するadd --fault tie_evenに差し替える。
run_case "add  --fault tie_even"       add -n 800 --frames 90  --fault tie_even       --expect-ng
run_case "sub  --fault sticky"         sub -n 800 --frames 90  --fault sticky         --expect-ng
run_case "sub  --fault tie_even"       sub -n 800 --frames 90  --fault tie_even       --expect-ng
run_case "add  --fault round_truncate" add -n 400 --frames 90  --fault round_truncate --expect-ng
run_case "sub  --fault round_truncate" sub -n 400 --frames 90  --fault round_truncate --expect-ng
# mul --fault mul_coarse: 2026-09-20以前はWK_MUL_ROUNDMODE=0の粗いROUNS
# 再現が既定だったが、away化(MBF_MUL_HALFUPと同じ経路が既定)によりその
# 分岐はどこからも到達しなくなった。旧mul_coarse(guardバイトのマスクを
# 緩める版)はこの到達不能な分岐を書き換えるだけで効果が無くなったため、
# MBF_MULの入口自体を旧既定(ROUNDMODE=0)へ戻す内容に作り直した
# (tools/l4_mbf_conform.py FAULT_MUL_COARSE参照)。
run_case "mul  --fault mul_coarse"     mul -n 400 --frames 200 --fault mul_coarse     --expect-ng
# div --fault ???: MBF_DIVは_add_roundを共有するが、単精度の正規化された
# 24bit仮数どうしの除算は、除数の仮数が2進数として持てる末尾ゼロが
# 高々23bit(先頭の明示1ビットを除く)であるため、「guard=0x80ちょうど・
# 真の剰余=0(WK_STICKY=0)」という真のタイに到達することが数学的に
# ありえない(2026-09-20、親から指摘を受けて検証。除数の奇数部分が
# 2^(24-t)で商を割り切るには商も2で割り切れる必要があるが、商の最下位
# ビットはguard=1(タイ条件)の定義上つねに1で矛盾する——l4-s7bの
# 「除算はtieを作れない」という記述の数学的な理由が本タスクで確定した)。
# よってdiv --fault tie_even/div_stickyはどちらも検出不能(旧div_sticky
# は削除、tie_evenはaddで既に検証済み——_add_roundは共有コードなので
# タイ分岐自体の正しさはadd/subの故障注入で担保される)。DIVの陰性対照は
# 代わりに、guard>=0x81/guard<0x80という「タイ以外(=DIVが実際に到達する
# 全域)」の丸め判定が機能していることをround_truncateで確認する。
run_case "div  --fault round_truncate" div -n 400 --frames 900 --fault round_truncate --expect-ng
run_case "fin  --fault fin_bang"       fin -n 30  --frames 400 --fault fin_bang       --expect-ng
# l4-s7c(2026-09-20)で通常経路をEXACTへ入れ替えた
# (docs/spec/l4-basic.md 5.1.1節第3.8版、mbf_single.asm
# `_fin_scale_nonzero_exact`)。fin_exactは「EXACTを注入する陽性対照」
# だったが通常経路が既にEXACTになったため意味を失い、代わりに
# 「REP01(旧実装、現在は不使用)を注入する陰性対照」fin_rep01に置き換えた。
# fin_rep10(REP01ループ内部を狙った故障注入)は、その対象(REP01ループ)
# 自体が通常経路から呼ばれなくなり故障を注入しても出力に影響しなくなった
# ため退役させた(空振りしてexpect-ngが常に偽になるだけの無意味な検査に
# なるため。tools/l4_mbf_conform.py FAULT_FIN_REP10_OLD/NEWはコードごと
# 残置——REP01のコード自体は削除していない、規律「行き止まりを消さない」)。
run_case "fin  --fault fin_rep01"      fin -n 100 --frames 1500 --fault fin_rep01      --expect-ng
run_case "fout --fault fout_trunc"       fout -n 200 --frames 20000 --fault fout_trunc       --expect-ng
run_case "fout --fault fout_round_even"  fout -n 200 --frames 20000 --fault fout_round_even  --expect-ng
run_case "fout --fault fout_len7"        fout -n 200 --frames 20000 --fault fout_len7        --expect-ng
run_case "fout --fault fout_6dig"        fout -n 200 --frames 20000 --fault fout_6dig        --expect-ng

# M7段階4b-1: 倍精度MBF(8B)の四則・変換（src/l4_basic/mbf_double.asm）。
# インタプリタへの組み込み・定数の読み取り(DFIN)・出力(FOUT倍精度経路)は
# 4b-2/4b-3で別に行うため、ここでは演算・変換ルーチン単体の照合のみ。
echo "==> 倍精度（境界値＋乱数、演算・変換ごと、複数シード）"
run_case "dadd N=1200 seed1" dadd -n 1200 --seed 1 --frames 90
run_case "dadd N=1200 seed2" dadd -n 1200 --seed 2 --frames 90
run_case "dsub N=1200 seed1" dsub -n 1200 --seed 1 --frames 90
run_case "dsub N=1200 seed2" dsub -n 1200 --seed 2 --frames 90
run_case "dneg N=1000 seed1" dneg -n 1000 --seed 1 --frames 60
run_case "dneg N=1000 seed2" dneg -n 1000 --seed 2 --frames 60
run_case "dcmp N=1000 seed1" dcmp -n 1000 --seed 1 --frames 60
run_case "dcmp N=1000 seed2" dcmp -n 1000 --seed 2 --frames 60
run_case "itod N=1000 seed1" itod -n 1000 --seed 1 --frames 60
run_case "itod N=1000 seed2" itod -n 1000 --seed 2 --frames 60
run_case "stod N=1000 seed1" stod -n 1000 --seed 1 --frames 60
run_case "stod N=1000 seed2" stod -n 1000 --seed 2 --frames 60
run_case "dtos N=1000 seed1" dtos -n 1000 --seed 1 --frames 300
run_case "dtos N=1000 seed2" dtos -n 1000 --seed 2 --frames 300
run_case "dmul N=1200 seed1" dmul -n 1200 --seed 1 --frames 3000
run_case "dmul N=1200 seed2" dmul -n 1200 --seed 2 --frames 3000
run_case "ddiv N=1200 seed1" ddiv -n 1200 --seed 1 --frames 5000
run_case "ddiv N=1200 seed2" ddiv -n 1200 --seed 2 --frames 5000
# M7段階4b-2: 倍精度FIN(DREP10A)。境界値+乱数2000件×2シード
# (frames=30000: 長い桁の積み上げ・|net_exp|回の×10/÷10反復を含むため
# 単精度FINより重い)。
run_case "dfin N=2000 seed1" dfin -n 2000 --seed 1 --frames 30000
run_case "dfin N=2000 seed2" dfin -n 2000 --seed 2 --frames 30000
# M7段階4b-2: 倍精度FOUT。
run_case "dfout N=2000 seed1" dfout -n 2000 --seed 1 --frames 30000
run_case "dfout N=2000 seed2" dfout -n 2000 --seed 2 --frames 30000

echo "==> 倍精度 故障注入（陰性対照。不一致が出ることを正常系として扱う）"
run_case "dadd --fault dsticky"          dadd -n 800 --frames 90   --fault dsticky          --expect-ng
run_case "dsub --fault dsticky"          dsub -n 800 --frames 90   --fault dsticky          --expect-ng
run_case "dadd --fault dround_truncate"  dadd -n 400 --frames 90   --fault dround_truncate  --expect-ng
run_case "dsub --fault dround_truncate"  dsub -n 400 --frames 90   --fault dround_truncate  --expect-ng
run_case "dmul --fault dmul_sticky"      dmul -n 400 --frames 3000 --fault dmul_sticky       --expect-ng
run_case "ddiv --fault ddiv_sticky"      ddiv -n 400 --frames 5000 --fault ddiv_sticky       --expect-ng
run_case "dfin --fault dfin_round_even"  dfin -n 200 --frames 30000 --fault dfin_round_even  --expect-ng
run_case "dfin --fault dfin_div_as_mul"  dfin -n 200 --frames 30000 --fault dfin_div_as_mul  --expect-ng
run_case "dfout --fault dfout_round_even" dfout -n 300 --frames 30000 --fault dfout_round_even --expect-ng
run_case "dfout --fault dfout_k14"        dfout -n 300 --frames 30000 --fault dfout_k14        --expect-ng

if [ "$overall" -eq 0 ]; then
  echo "l4_mbf_z80_selftest: OK"
else
  echo "l4_mbf_z80_selftest: NG" >&2
fi
exit "$overall"

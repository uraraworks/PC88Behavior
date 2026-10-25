#!/usr/bin/env bash
# b3_analyze_boot_decision.py を合成 iolog で検査する（候補1件・K1/分類・前で切る・漏洩検査と陰性対照）。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$REPO/tools/b3_analyze_boot_decision.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "b3_analyze_boot_decision_selftest: FAIL: $*" >&2; exit 1; }

# mk FILE TMP KIND V1 V2 P41 : 合成ログ。印: pc=BEEF、データポート値=A5
mk() {
  local f="$1" tmp="$2" kind="$3" v1="$4" v2="$5" p41="$6"
  {
    echo "# PC88Behavior 合成 I/O 記録"; echo "frames    : 60"; echo; echo "# main"
    echo "# seq  clock  frame  cpu   kind  port  value  pc"
    echo "     1  1      0  main  IN    0040   $v1   BEEF"
    if [ "$kind" != rom ]; then echo "     2  2      0  main  IN    00FC   A5   BEEF"; fi
    echo "     3  3      1  main  IN    0040   $v2   BEEF"
    echo "     4  4      1  main  IN    0042   07   BEEF"
    case "$kind" in
      rom|mixc1) echo "     5  5      2  main  OUT   00C1   01   BEEF" ;;
      disk) echo "     5  5      2  main  OUT   00FF   01   BEEF"; echo "     6  6      2  main  OUT   00FD   A5   BEEF" ;;
    esac
    echo "     9  9      3  main  IN    0041   $p41   BEEF"
    echo "    10  10      3  main  IN    0040   00   BEEF"
    echo "# sub"
    if [ "$kind" = disk ] || [ "$kind" = mixc1 ]; then
      echo "     1  1      2  sub   IN    00FD   A5   BEEF"
      echo "     2  2      2  sub   OUT   00FC   A5   BEEF"
    fi
  } > "$tmp"
  mv "$tmp" "$f"
}
# N側: 40 = 08/28（bit3=1固定、bit5は揺れる）。D側: 40 = 00/20（bit3=0、bit5揺れる）。
# 41 は分岐点より後でだけ N=00 / D=01（候補に出てはいけない）。
mk "$WORK/n1.txt" "$WORK/t" rom  08 28 00
mk "$WORK/n2.txt" "$WORK/t" rom  28 08 00
mk "$WORK/d1.txt" "$WORK/t" disk 00 20 01
mk "$WORK/d2.txt" "$WORK/t" disk 20 00 01
mk "$WORK/m1.txt" "$WORK/t" mixc1 08 28 00
gzip -k "$WORK/d2.txt" && mv "$WORK/d2.txt.gz" "$WORK/d2gz.txt.gz"

OUT="$WORK/out.txt"
args=(--run n1:N:"$WORK/n1.txt" --run n2:N:"$WORK/n2.txt" --run d1:D1:"$WORK/d1.txt"
      --run d2:D1:"$WORK/d2gz.txt.gz" --run m1:C1:"$WORK/m1.txt" --track 40:3 --track 41:0)
python3 -I "$TOOL" "${args[@]}" > "$OUT" 2>&1 || fail "解析器が異常終了"

# 陽性: 候補はちょうど (40,3,1,0) の1件
[ "$(grep -c $'^R1\tcandidate\t' "$OUT")" = 1 ] || fail "候補が1件でない"
grep -q $'^R1\tcandidate\tport=40\tbit=3\ta=1\tb=0\t' "$OUT" || fail "候補が (40,3,1,0) でない"
# 揺れるビット (bit5) と後だけ違う 41 は候補外
grep -q $'^R1\tnon_candidates\t.*varies_within_arm=[1-9]' "$OUT" || fail "揺れの件数が出ない"
grep -q 'port=41' <(grep candidate "$OUT") && fail "分岐点より後だけ違う41が候補に出た"
# K1・分類
grep -q $'run=n1\tarm=N\tK1_port=C1\tbranch_frame=2\tK2=0\tK3=0\tclass=ROM' "$OUT" || fail "ROM形"
grep -q $'run=d1\tarm=D1\tK1_port=FF.*class=DISK' "$OUT" || fail "ディスク形"
grep -q $'run=m1\tarm=C1\tK1_port=C1.*K3=2.*class=MIXED' "$OUT" || fail "混在"
# R4: 41 bit0 は 分岐前に読み無し、走全体では D=1
grep -q $'run=d1\tarm=D1\tport=41\tbit=0\tbefore=-\tbefore_reads=0\twhole=1' "$OUT" || fail "R4 前/全体"

# 漏洩検査: 印 (BEEF, A5) が出力に一切現れない
grep -qiE 'BEEF|A5' "$OUT" && fail "印が出力に漏れた"
# 陰性対照: 故障注入版では検査が FAIL になること
B3_ANALYZER_FAULT_LEAK=1 python3 -I "$TOOL" "${args[@]}" > "$WORK/leak.txt" 2>&1
grep -qiE 'BEEF|A5' "$WORK/leak.txt" || fail "陰性対照: 故障注入でも印が出ない（検査が効いていない）"
# エラー経路も本文を出さない
echo "     1  1      0  main  IN    00ZZ   A5   BEEF" > "$WORK/bad.txt"
python3 -I "$TOOL" --run x:N:"$WORK/bad.txt" > "$WORK/bad.out" 2>&1
grep -qiE 'BEEF|A5|ZZ' "$WORK/bad.out" && fail "エラー出力に本文が出た"
# 欄の数が違う（clock 欄の無い7欄）ログは黙って0件にせず止まる
echo "     1      0  main  IN    0040   08   BEEF" > "$WORK/old7.txt"
python3 -I "$TOOL" --run x:N:"$WORK/old7.txt" > "$WORK/old7.out" 2>&1 && fail "形式違いのログを黙って読んだ"
grep -qiE 'BEEF|08' "$WORK/old7.out" && fail "形式違いのエラー出力に本文が出た"

echo "b3_analyze_boot_decision_selftest: 陽性1・前切り1・K1/分類3・R4 1・漏洩1・陰性対照1・エラー1・形式違い1 OK"

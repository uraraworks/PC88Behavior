#!/usr/bin/env bash
# 需要プロファイルの測定一式。
#
# 条件を1つずつ手で叩いていると、何をどの設定で測ったのかが残らない。
# 一式をここに書いておけば、第三者が同じプロファイルを再導出できる。
# 条件を足すときはここに足す。measurements/ の中身はこの出力である。
#
# 打鍵のタイミングについて:
#   起動時に "How many files(0-15)?" が出るので、まず RETURN で抜ける。
#   ディスクを入れると起動が遅くなるので、抜けるフレームを後ろにずらす。
#   1 文字あたり 8 フレーム（押し 4 + 離し 4）かかるので、
#   --frames は「打ち終わり + 実行に十分な余裕」を見て決める。
#
# 使い方: tools/measure_suite.sh [条件名の前方一致]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILTER="${1:-}"
M="$REPO/tools/measure.sh"

run() {
  local name="$1"; shift
  case "$name" in "$FILTER"*) ;; *) return 0;; esac
  printf '%-16s' "$name"
  if "$M" "$name" "$@" >/dev/null 2>&1; then echo "ok"; else echo "NG"; fi
}

# 起動直後（ディスク無し）に打つ場合の前置き
NB="--type-at 120 --type \n --type-at 400"
# ディスク起動の場合はプロンプトが出るまで時間がかかる
DB="--type-at 300 --type \n --type-at 700"

# ---- ディスク無し：BASIC の言語機能 --------------------------------------
run idle-noinput  --frames 600
run b0-prompt     --frames  900 --type-at 120 --type '\n'
run b1-print      --frames 1200 --type-at 120 --type '\n' --type-at 400 --type 'PRINT 12345\n'
run b2-for        --frames 1800 --type-at 120 --type '\n' --type-at 400 --type 'FOR I=1 TO 5:PRINT I:NEXT\n'
run b3-string     --frames 1800 --type-at 120 --type '\n' --type-at 400 --type 'A$="XY":PRINT A$+A$,LEN(A$)\n'
run b4-math       --frames 1800 --type-at 120 --type '\n' --type-at 400 --type 'PRINT SIN(1)+SQR(2)*3/7-4\n'
run b5-screen     --frames 1800 --type-at 120 --type '\n' --type-at 400 --type 'SCREEN 1:CLS:LINE(0,0)-(100,100)\n'
run b6-error      --frames 1200 --type-at 120 --type '\n' --type-at 400 --type 'FOOBAR 999\n'
run b7-program    --frames 3000 --type-at 120 --type '\n' --type-at 400 --type '10 FOR J=1 TO 3\n20 PRINT J*J;"!"\n30 NEXT\nLIST\nRUN\n'
run b8-dataread   --frames 3000 --type-at 120 --type '\n' --type-at 400 --type '10 DATA 11,22,33\n20 READ A,B,C\n30 PRINT A+B+C\n40 RESTORE\nRUN\n'
run b9-deffn      --frames 2400 --type-at 120 --type '\n' --type-at 400 --type '10 DEF FNS(X)=X*X+1\n20 PRINT FNS(4)\nRUN\n'
run b10-gosub     --frames 3000 --type-at 120 --type '\n' --type-at 400 --type '10 FOR K=1 TO 2\n20 ON K GOSUB 100,200\n30 NEXT\n40 END\n100 PRINT "A":RETURN\n200 PRINT "B":RETURN\nRUN\n'
run b11-onerror   --frames 3000 --type-at 120 --type '\n' --type-at 400 --type '10 ON ERROR GOTO 100\n20 ERROR 5\n30 END\n100 PRINT ERR;ERL:RESUME 30\nRUN\n'
run b12-graphics  --frames 2400 --type-at 120 --type '\n' --type-at 400 --type 'SCREEN 1:CLS:CIRCLE(150,80),40:PAINT(150,80):PSET(10,10)\n'
run b13-arrays    --frames 3000 --type-at 120 --type '\n' --type-at 400 --type '10 DIM Z(4,4)\n20 FOR P=0 TO 4:Z(P,P)=P*2:NEXT\n30 PRINT Z(3,3)\nRUN\n'
run b14-strfunc   --frames 2400 --type-at 120 --type '\n' --type-at 400 --type 'B$="ABCDEF":PRINT MID$(B$,2,3);LEFT$(B$,2);RIGHT$(B$,1);ASC(B$)\n'
run b15-console   --frames 2400 --type-at 120 --type '\n' --type-at 400 --type 'WIDTH 40:COLOR 2:LOCATE 5,5:PRINT "X":CONSOLE 0,25\n'
run b16-numtype   --frames 2400 --type-at 120 --type '\n' --type-at 400 --type 'DEFDBL D:D=1/3:PRINT D;CDBL(1)/7;CINT(2.7);FIX(-2.7)\n'
run b17-input     --frames 3000 --type-at 120 --type '\n' --type-at 400 --type '10 INPUT "N";V\n20 PRINT V*2\nRUN\n' --type-at 2000 --type '21\n'
run b18-peek      --frames 2400 --type-at 120 --type '\n' --type-at 400 --type 'PRINT PEEK(0);PEEK(1):POKE 60000,1:PRINT PEEK(60000)\n'
run b19-beep      --frames 2400 --type-at 120 --type '\n' --type-at 400 --type 'BEEP:PRINT TIME$;DATE$\n'
run b20-printusing --frames 2400 --type-at 120 --type '\n' --type-at 400 --type 'PRINT USING "###.##";3.14159\n'

# ---- ディスクあり ---------------------------------------------------------
run d0-boot       --frames 1800 --disk-name N88_FE.D88
run d1-files      --frames 2400 --disk-name N88_FE.D88 --type-at 300 --type '\n' --type-at 700 --type 'FILES\n'
run d2-save       --frames 3600 --disk-name N88_FE.D88 --type-at 300 --type '\n' --type-at 700 --type '10 PRINT "T"\nSAVE"TMPQ88"\nFILES\n'
run d3-diskwrite  --frames 4200 --disk-name N88_FE.D88 --disk-writable --type-at 300 --type '\n' --type-at 700 --type '10 PRINT "T"\nSAVE"TMPQ88"\nFILES\nKILL"TMPQ88"\n'
run d4-saveload   --frames 4800 --disk-name N88_FE.D88 --disk-writable --type-at 300 --type '\n' --type-at 700 --type '10 PRINT "T"\nSAVE"TMPQ88"\nNEW\nLOAD"TMPQ88"\nLIST\n'
# この N88-BASIC は OPEN "O",#1,"名前" 形式を受け付けない（Syntax error）。
# OPEN "名前" FOR mode AS #n 形式なら通る。測って分かったこと。
run d5-seqfile    --frames 6000 --disk-name N88_FE.D88 --disk-writable --type-at 300 --type '\n' --type-at 700 --type 'OPEN "TMPD" FOR OUTPUT AS #1\nPRINT#1,"HI"\nCLOSE\nOPEN "TMPD" FOR INPUT AS #1\nINPUT#1,W$\nCLOSE\nPRINT W$\n'

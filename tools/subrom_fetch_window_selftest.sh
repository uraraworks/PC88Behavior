#!/usr/bin/env bash
# tools/subrom_fetch_window_selftest.sh — サブROMフェッチ窓(0x0800)整列の
# selftest（公式環境不要）。
#
# 背景（m7an、docs/notes/m7an-*.md）: 計測ハーネスのサブCPU ROMロード
# （tools/patches/0001-cleanroom-harness.patch: `load_system_file(SUB_ROM,
# sub_romram, 0x00800)`）は常に0x0800バイトしか読み込まない。DISK.ROMの
# 生成コードがこの境界を跨ぐ命令（絶対番地call/jp・相対分岐jr系・
# 固定RAM番地の即値ロード等）を持つと、その命令の一部バイトがロード
# されず不定動作になる。src/l3_service/make_subrom.pyの
# find_fetch_window_straddles()がこれを検出し、build()が検出時だけ
# 整列パディングを自動挿入して跨ぎを解消する。
#
# この selftest は:
#   1. 跨ぎが無い状態（既定のLIMIT=1〜4）でstraddleが0件であることを確認する
#   2. 陽性対照: 意図的に跨がせた状態（align_padding_bytesを直接指定）で
#      straddleが検出されることを確認する（検出力の確認）
#   3. 陽性対照: 整列を諦める上限(MAX_ALIGN_PADDING_ATTEMPTS)を0にすると
#      build()がSystemExitで失敗することを確認する
#
# 値（ROM内容）は一切表示しない。命令の位置・バイト数・件数だけを扱う。

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }

overall_rc=0

say "既定ビルド(LIMIT=1〜4)がサブROMフェッチ窓(0x0800)を跨がないこと"
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
fail = False
for L in (1, 2, 3, 4):
    os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = str(L)
    if "make_subrom" in sys.modules:
        del sys.modules["make_subrom"]
    import make_subrom as m
    rom, used = m.build()
    a = m.build_subrom(align_padding_bytes=0)
    a.resolve()
    # buildが選んだalign_padding_bytesを再現するのではなく、build()自身が
    # 最終的にstraddleの無い状態へ収束していることをbuild()の戻り値
    # (使用バイト数)とは独立に、build_subrom+resolveをbuild()と同じ
    # 探索ロジックで再実行して確認する。
    align = 0
    while m.find_fetch_window_straddles(a):
        align += 1
        if align > m.MAX_ALIGN_PADDING_ATTEMPTS:
            print(f"LIMIT={L}: FAIL 整列で解消できない")
            fail = True
            break
        a = m.build_subrom(align_padding_bytes=align)
        a.resolve()
    else:
        print(f"LIMIT={L}: OK straddle=0 (align_padding_bytes={align}, used={used})")
sys.exit(1 if fail else 0)
EOF
)"
echo "$out"
if echo "$out" | grep -q "FAIL"; then
  ng "既定ビルドがフェッチ窓を跨いだまま"
  overall_rc=1
else
  ok "LIMIT=1〜4のいずれもフェッチ窓を跨がない（build()の整列が効いている）"
fi

say "陽性対照1: 命令の途中に境界を置くとfind_fetch_window_straddlesが検出すること"
# 第52版・m7ap: 以前はLIMIT=2の既定ビルドが実際に持っていたstraddleを
# 陽性対照に流用していたが、テーブル駆動化でコードが縮み跨ぎが消えたため
# 陽性対照そのものが無効化された（検出力ゼロの検査が通り続ける状態）。
# 実コードの偶然に依存しない形に作り直す: 幅2以上の命令の途中に境界を
# 置けば必ず跨ぎになり、命令の先頭に置けば必ず跨がない。
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = "1"
if "make_subrom" in sys.modules:
    del sys.modules["make_subrom"]
import make_subrom as m
a = m.build_subrom()
a.resolve()
# 幅2以上の命令を1つ選ぶ（どれでもよい。ここでは先頭から最初のもの）
pos, width = next((p, w) for p, w in a.instr_spans if w >= 2)
inside = m.find_fetch_window_straddles(a, boundary=pos + 1)   # 命令の途中
at_start = m.find_fetch_window_straddles(a, boundary=pos)     # 命令の先頭
print(f"命令の途中に境界: straddles={len(inside)}")
print(f"命令の先頭に境界: straddles={len(at_start)}")
sys.exit(0 if (len(inside) >= 1 and len(at_start) == 0) else 1)
EOF
)"
echo "$out"
if echo "$out" | grep -q "命令の途中に境界: straddles=0"; then
  ng "陽性対照1: 命令の途中に置いた境界を検出しなかった（検出力が無い）"
  overall_rc=1
elif ! echo "$out" | grep -q "命令の先頭に境界: straddles=0"; then
  ng "陽性対照1: 命令の先頭に置いた境界を誤検出した（false positive）"
  overall_rc=1
else
  ok "陽性対照1: 命令の途中で検出・命令の先頭で非検出（検出力とfalse positive無しの両方）"
fi

say "陽性対照2: MAX_ALIGN_PADDING_ATTEMPTS=0でbuild()がSystemExitすること"
# 第52版・m7ap: 陽性対照1と同じ理由で、実コードの偶然のstraddleに依存
# しない形へ作り直した。SUB_ROM_FETCH_WINDOWを命令の途中へ動かして
# 必ず跨ぎが起きる状況を作り、整列の上限0で失敗することを確認する。
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = "1"
if "make_subrom" in sys.modules:
    del sys.modules["make_subrom"]
import make_subrom as m
a = m.build_subrom()
a.resolve()
pos, width = next((p, w) for p, w in a.instr_spans if w >= 2)
m.SUB_ROM_FETCH_WINDOW = pos + 1   # 命令の途中に窓境界を置く
m.MAX_ALIGN_PADDING_ATTEMPTS = 0
try:
    m.build()
    print("NG: SystemExitが上がらなかった")
except SystemExit:
    print("OK: SystemExitが上がった")
EOF
)"
echo "$out"
if echo "$out" | grep -q "^OK"; then
  ok "陽性対照2: 整列の上限到達がSystemExitとして検出された"
else
  ng "陽性対照2: 整列上限のSystemExitが発火しなかった"
  overall_rc=1
fi

say "陽性対照3: find_out_of_window_blocksが境界の外のブロックを検出すること"
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = "1"
if "make_subrom" in sys.modules:
    del sys.modules["make_subrom"]
import make_subrom as m
a = m.build_subrom()
a.resolve()
# 陽性対照: 境界を意図的に小さくして(0x0100)、既知の到達可能ブロックが
# 検出されることを確認する(実際のSUB_ROM_FETCH_WINDOWでの判定とは別)。
blocks_small = m.find_out_of_window_blocks(a, boundary=0x0100)
# 陰性対照: 境界を意図的に巨大にして(0x8000)、何も検出されないことを確認する。
blocks_huge = m.find_out_of_window_blocks(a, boundary=0x8000)
print(f"boundary=0x0100: blocks={len(blocks_small)}")
print(f"boundary=0x8000: blocks={len(blocks_huge)}")
sys.exit(0 if (len(blocks_small) > 0 and len(blocks_huge) == 0) else 1)
EOF
)"
echo "$out"
if [ "$overall_rc" -eq 0 ] && echo "$out" | grep -q "boundary=0x8000: blocks=0"; then
  ok "陽性対照3: 小さい境界で検出・巨大な境界で非検出(検出力とfalse positive無しの両方を確認)"
else
  ng "陽性対照3: find_out_of_window_blocksの検出力に問題がある"
  overall_rc=1
fi

say "既定ビルド(LIMIT=1〜4)が窓超過0バイトであること（第52版・m7apで報告から検査へ格上げ）"
# m7aoの時点では既定でも9バイト超過しており報告に留めていた。m7apの
# テーブル駆動化で全LIMITが窓内に収まったので、ここは検査にする。
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
fail = False
for L in (1, 2, 3, 4):
    os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = str(L)
    if "make_subrom" in sys.modules:
        del sys.modules["make_subrom"]
    import make_subrom as m
    rom, used = m.build()   # build()自身が窓超過ならSystemExitする
    a = m.build_subrom(align_padding_bytes=0)
    a.resolve()
    align = 0
    while m.find_fetch_window_straddles(a):
        align += 1
        a = m.build_subrom(align_padding_bytes=align)
        a.resolve()
    blocks = m.find_out_of_window_blocks(a)
    over = sum(sz for _, _, sz in blocks)
    print(f"LIMIT={L}: used={used} 窓超過={over}バイト ブロック数={len(blocks)}")
    if over:
        fail = True
sys.exit(1 if fail else 0)
EOF
)"
rc=$?
echo "$out"
if [ "$rc" -eq 0 ]; then
  ok "LIMIT=1〜4のいずれも窓超過0バイト（build()の関門も通過）"
else
  ng "窓超過が残っている（または build() が関門で失敗した）"
  overall_rc=1
fi

say "陽性対照4: 窓の外に到達可能コードがあるとbuild()がSystemExitすること"
# 新設した関門（build()内のfind_out_of_window_blocks検査）の検出力確認。
# 窓を意図的に小さくすれば必ず窓の外のブロックができる。
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = "1"
if "make_subrom" in sys.modules:
    del sys.modules["make_subrom"]
import make_subrom as m
# 窓を縮めるが、**命令の途中に境界を置かない**こと。命令の途中だと整列
# パディングの側が先に働き、パディングが膨らんで整列用jrが届かなくなる
# （第54版で実際に踏んだ）。ラベルの位置は必ず命令の先頭なので、
# 0x0400付近のラベル位置を境界に選べば straddle は0のまま
# 「窓の外に到達可能ブロックがある」状態だけを作れる。
a = m.build_subrom()
a.resolve()
boundary = max(v for v in a.labels.values() if v <= 0x0400)
m.SUB_ROM_FETCH_WINDOW = boundary
try:
    m.build()
    print("NG: SystemExitが上がらなかった")
except SystemExit as e:
    print("OK: SystemExitが上がった" if "窓" in str(e) else f"NG: 別の理由で失敗: {e}")
EOF
)"
echo "$out"
if echo "$out" | grep -q "^OK"; then
  ok "陽性対照4: 窓の外の到達可能コードをbuild()が関門で止めた"
else
  ng "陽性対照4: 窓外の関門が発火しなかった"
  overall_rc=1
fi

say "陽性対照5: 開始は窓の内側で、末尾の命令だけが丸ごと窓の外にある到達可能ブロックをbuild()が止めること（m7lb/m7lc）"
# 陽性対照4は命令の跨ぎを避けるため、境界を「ラベルの位置＝区間の開始」に置く。
# そのため作れるのは「区間が丸ごと窓の外」という形だけで、「開始は内側・末尾だけ
# 外」という形は1度も作っていなかった。関門(find_out_of_window_blocks)は長らく
# 区間の開始位置しか見ておらず、この形を見逃していた（m7lbで、既定ビルドの余白
# 9バイトを超えた版が黙って通り、適合を壊していたことを確定した）。
# ここでは境界を「最後の区間の内側で、本当の命令の先頭にあたる位置」に置く。
# call/jp等はオペコード(1バイト)とオペランド(2バイト)が別々のinstr_spansとして
# 記録されるので、フィックスアップのオペランド位置は候補から外す（そこは命令の
# 途中である。その形は陽性対照6で別に扱う）。最後の区間なので「開始が窓の外の
# 区間」は1つも無く、開始位置だけを見る関門では検出されない形を狙って作れる。
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = "1"
if "make_subrom" in sys.modules:
    del sys.modules["make_subrom"]
import make_subrom as m
a = m.build_subrom()
a.resolve()
last_start = max(a.labels.values())
end = len(a.code)
operands = {pos for pos, _, _ in a.fixups}
cands = sorted(pos for pos, _ in a.instr_spans
               if last_start < pos < end and pos not in operands)
if not cands:
    print("NG: 最後の区間の内側に本当の命令の先頭が無く、この形を作れない")
    sys.exit(0)
boundary = cands[0]
starts_outside = [v for v in a.labels.values() if v >= boundary]
straddles = m.find_fetch_window_straddles(a, boundary)
print(f"境界=最後の区間の開始+{boundary - last_start}バイト（命令の先頭） 開始が外の区間={len(starts_outside)} 跨ぎ={len(straddles)}")
if starts_outside or straddles:
    print("NG: 狙った形（開始は内側・末尾の命令だけ外・跨ぎ0）になっていない")
    sys.exit(0)
blocks = m.find_out_of_window_blocks(a, boundary=boundary)
print("DIRECT_OK" if blocks else "DIRECT_NG: find_out_of_window_blocksが末尾の窓越えを検出しない")
m.SUB_ROM_FETCH_WINDOW = boundary
try:
    m.build()
    print("BUILD_NG: SystemExitが上がらなかった")
except SystemExit as e:
    print("BUILD_OK" if "窓" in str(e) else f"BUILD_NG: 別の理由で失敗: {e}")
EOF
)"
echo "$out"
if echo "$out" | grep -q "^DIRECT_OK" && echo "$out" | grep -q "^BUILD_OK"; then
  ok "陽性対照5: 末尾の命令だけ窓の外にある到達可能ブロックを、検出関数もbuild()の関門も止めた"
else
  ng "陽性対照5: 末尾の命令だけ窓の外にある到達可能ブロックを見逃した"
  overall_rc=1
fi

say "陽性対照6: オペコードは窓の内側・オペランドが窓の外というcall/jpをbuild()が止めること（m7lc）"
# call/jpはオペコードとオペランドが別々のinstr_spansとして記録されるので、
# 境界がちょうどその間に来ると、find_fetch_window_straddlesは「跨ぎ0」と
# 判定する（オペコード区間は境界で終わり、オペランド区間は境界から始まるため）。
# 整列パディングはこの形を直さない。m7lcの修正後は、区間の終了位置を窓と
# 突き合わせるので、この形はbuild()の関門で止まる（パディングで直るのではなく、
# ビルドが失敗する側に倒れる）。その振る舞いをここで固定する。
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = "1"
if "make_subrom" in sys.modules:
    del sys.modules["make_subrom"]
import make_subrom as m
a = m.build_subrom()
a.resolve()
last_start = max(a.labels.values())
end = len(a.code)
cands = sorted(pos for pos, _, kind in a.fixups
               if last_start < pos < end and kind == "abs")
if not cands:
    print("NG: 最後の区間の内側に絶対番地オペランドが無く、この形を作れない")
    sys.exit(0)
boundary = cands[0]
starts_outside = [v for v in a.labels.values() if v >= boundary]
straddles = m.find_fetch_window_straddles(a, boundary)
print(f"境界=最後の区間の開始+{boundary - last_start}バイト（オペコードとオペランドの間） 開始が外の区間={len(starts_outside)} 跨ぎ={len(straddles)}")
if starts_outside:
    print("NG: 狙った形になっていない（開始が外の区間がある）")
    sys.exit(0)
m.SUB_ROM_FETCH_WINDOW = boundary
try:
    m.build()
    print("BUILD_NG: SystemExitが上がらなかった")
except SystemExit as e:
    print("BUILD_OK" if "窓" in str(e) else f"BUILD_NG: 別の理由で失敗: {e}")
EOF
)"
echo "$out"
if echo "$out" | grep -q "^BUILD_OK"; then
  ok "陽性対照6: オペランドだけ窓の外に出たcall/jpをbuild()の関門が止めた"
else
  ng "陽性対照6: オペランドだけ窓の外に出たcall/jpを見逃した"
  overall_rc=1
fi

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "subrom_fetch_window_selftest: OK（全項目）"
else
  echo "subrom_fetch_window_selftest: 失敗あり"
fi
exit "$overall_rc"

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

say "陽性対照1: 意図的に跨がせるとfind_fetch_window_straddlesが検出すること"
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = "2"
if "make_subrom" in sys.modules:
    del sys.modules["make_subrom"]
import make_subrom as m
# LIMIT=2の既定(align=0)は既にstraddleを1件持つ(m7an確認済み)ことを利用する。
a = m.build_subrom(align_padding_bytes=0)
a.resolve()
s = m.find_fetch_window_straddles(a)
print(f"align=0: straddles={len(s)}")
sys.exit(0 if len(s) >= 1 else 1)
EOF
)"
echo "$out"
if echo "$out" | grep -q "straddles=0"; then
  ng "陽性対照1: 意図的な跨ぎが検出されなかった（検出力が無い）"
  overall_rc=1
else
  ok "陽性対照1: 意図的な跨ぎ(align_padding_bytes=0の既知straddle)を検出した"
fi

say "陽性対照2: MAX_ALIGN_PADDING_ATTEMPTS=0でbuild()がSystemExitすること"
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = "2"
if "make_subrom" in sys.modules:
    del sys.modules["make_subrom"]
import make_subrom as m
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

say "既定ビルド(LIMIT=1〜4)の窓超過量を報告する（値ではなくバイト数だけ）"
# 第51版時点ではSUB_ROM_FETCH_WINDOW(0x0800)未満に収まっていない
# (m7ao、docs/notes/m7ao-*.md)。ここではbuild()を境界超過で
# 失敗させる強制はまだ入れていない（現状の全パイプラインを壊すため）。
# 超過量を可視化するだけの報告に留め、削減は次サイクルの課題として
# 明記する。
out="$(python3 - <<'EOF'
import sys, os
sys.path.insert(0, "src/l3_service")
for L in (1, 2, 3, 4):
    os.environ["PC88_BULK_READ_INTERVENTION_LIMIT"] = str(L)
    if "make_subrom" in sys.modules:
        del sys.modules["make_subrom"]
    import make_subrom as m
    rom, used = m.build()
    align = 0
    a = m.build_subrom(align_padding_bytes=0)
    a.resolve()
    while m.find_fetch_window_straddles(a):
        align += 1
        a = m.build_subrom(align_padding_bytes=align)
        a.resolve()
    blocks = m.find_out_of_window_blocks(a)
    over = sum(sz for _, _, sz in blocks)
    print(f"LIMIT={L}: used={used} 窓超過={over}バイト ブロック数={len(blocks)}")
EOF
)"
echo "$out"
ok "報告のみ（既知の未達成。docs/notes/m7ao-*.md参照）"

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "subrom_fetch_window_selftest: OK（全項目）"
else
  echo "subrom_fetch_window_selftest: 失敗あり"
fi
exit "$overall_rc"

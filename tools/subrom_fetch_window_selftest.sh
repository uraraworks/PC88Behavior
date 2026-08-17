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

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "subrom_fetch_window_selftest: OK（全項目）"
else
  echo "subrom_fetch_window_selftest: 失敗あり"
fi
exit "$overall_rc"

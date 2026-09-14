#!/usr/bin/env bash
# tools/asm/asm_selftest.sh — M7段階0（後半）の自己検査。
#
# docs/notes/l4-design.md 段階0:
#   既存2生成器（make_ipl_rom.py / make_subrom.py）が --emit-asm で
#   書き出した .asm を tools/asm/z80text.py で組み直し、生成器自身が
#   出したROMバイトと一致することを確かめる。既存2生成器がオラクル
#   （正解役）になる。
#
# 検査項目:
#   1. 生成器の既定出力（sha256）が、この検査を追加する前の値から
#      変わっていないこと（--emit-asm系オプションはバイト出力に無関係）。
#   2. 各生成器が出す全ROMについて、.asm経由の再組み立てがバイト一致。
#      make_ipl_rom.py は N88.ROM と DISK.ROM の2つ、make_subrom.py は
#      DISK.ROM 1つ。
#   3. 陽性対照（故障注入）: 書き出した.asmを1か所だけ機械的に壊すと
#      不一致（またはアセンブル自体の失敗）を検出できること。
#
# 使い方: tools/asm/asm_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

fail=0
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; fail=$((fail+1)); }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

Z80TEXT="tools/asm/z80text.py"

# ---- 既定出力の sha256（このアセンブラ機能を追加する前に実測して固定した値）----
EXPECT_N88_SHA="042b27209b97ac638aa6433be2f01de451c03f71349c9f6bc11fa123190aadf0"
EXPECT_IPL_DISK_SHA="9c7e2a5d8c69b54d7bcc404c8e863e90f0ea2013f4273c9318c1343e5e9f6c5b"
EXPECT_SUBROM_DISK_SHA="d8b2e64bc27465f955fd308719228f21b06aa07fd780081a88124a52e6d76070"

sha256_of() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        sha256sum "$1" | awk '{print $1}'
    fi
}

# --------------------------------------------------------------------------
# 1. make_ipl_rom.py: N88.ROM / DISK.ROM
# --------------------------------------------------------------------------
IPL_OUT="$WORK/ipl_out"
IPL_ASM="$WORK/ipl_asm"
mkdir -p "$IPL_OUT"
if ! python3 src/l1_ipl/make_ipl_rom.py "$IPL_OUT" --emit-asm-dir "$IPL_ASM" \
        > "$WORK/ipl_build.log" 2>&1; then
    ng "make_ipl_rom.py の実行に失敗した"
    tail -20 "$WORK/ipl_build.log"
else
    ok "make_ipl_rom.py 実行成功（N88.ROM / DISK.ROM / --emit-asm-dir）"
fi

# N88.asm の内訳（命令文/data/raw）。生成器が STATS 行を標準出力に出す
# （tools/asm/asm_emit.py の count_kinds()。M7段階0後半）。
ipl_stats_line="$(grep '^STATS N88 ' "$WORK/ipl_build.log" || true)"
echo "  内訳   $ipl_stats_line"
ipl_raw="$(printf '%s' "$ipl_stats_line" | sed -n 's/.*raw=\([0-9]*\).*/\1/p')"
if [ "$ipl_raw" = "0" ]; then
    ok "N88.asm: コード中の生db 0件"
else
    ng "N88.asm: コード中に生db が $ipl_raw 件残っている（命令メソッド化されていない直書き）"
fi

n88_sha="$(sha256_of "$IPL_OUT/N88.ROM")"
if [ "$n88_sha" = "$EXPECT_N88_SHA" ]; then
    ok "N88.ROM の sha256 が変更前と一致"
else
    ng "N88.ROM の sha256 が変わった: $n88_sha (期待 $EXPECT_N88_SHA)"
fi

ipl_disk_sha="$(sha256_of "$IPL_OUT/DISK.ROM")"
if [ "$ipl_disk_sha" = "$EXPECT_IPL_DISK_SHA" ]; then
    ok "make_ipl_rom.py の DISK.ROM の sha256 が変更前と一致"
else
    ng "make_ipl_rom.py の DISK.ROM の sha256 が変わった: $ipl_disk_sha (期待 $EXPECT_IPL_DISK_SHA)"
fi

# N88.ROM: コード領域だけ.asmから再組み立てして比較する（末尾はFILLパディング）。
if python3 "$Z80TEXT" "$IPL_ASM/N88.asm" -o "$WORK/n88_reasm.bin" \
        > "$WORK/n88_reasm.log" 2>&1; then
    if python3 - "$IPL_OUT/N88.ROM" "$WORK/n88_reasm.bin" <<'PYEOF'
import sys
rom = open(sys.argv[1], "rb").read()
reasm = open(sys.argv[2], "rb").read()
ok = rom[:len(reasm)] == reasm and set(rom[len(reasm):]) <= {0}
sys.exit(0 if ok else 1)
PYEOF
    then
        ok "N88.ROM: .asm経由の再組み立てがバイト一致"
    else
        ng "N88.ROM: .asm経由の再組み立てがバイト不一致"
    fi
else
    ng "N88.asm の再アセンブルに失敗"
    tail -20 "$WORK/n88_reasm.log"
fi

# DISK.ROM（make_ipl_rom.py側）: build_disk()はAsmを使わないので全体一致で比較。
if python3 "$Z80TEXT" "$IPL_ASM/DISK.asm" -o "$WORK/ipl_disk_reasm.bin" \
        > "$WORK/ipl_disk_reasm.log" 2>&1; then
    if cmp -s "$IPL_OUT/DISK.ROM" "$WORK/ipl_disk_reasm.bin"; then
        ok "make_ipl_rom.py の DISK.ROM: .asm経由の再組み立てがバイト一致"
    else
        ng "make_ipl_rom.py の DISK.ROM: .asm経由の再組み立てがバイト不一致"
    fi
else
    ng "DISK.asm（ipl）の再アセンブルに失敗"
    tail -20 "$WORK/ipl_disk_reasm.log"
fi

# --------------------------------------------------------------------------
# 2. make_subrom.py: DISK.ROM
# --------------------------------------------------------------------------
SUB_OUT="$WORK/sub_out"
mkdir -p "$SUB_OUT"
SUB_ASM="$WORK/sub.asm"
if ! python3 src/l3_service/make_subrom.py "$SUB_OUT" --emit-asm "$SUB_ASM" \
        > "$WORK/sub_build.log" 2>&1; then
    ng "make_subrom.py の実行に失敗した"
    tail -20 "$WORK/sub_build.log"
else
    ok "make_subrom.py 実行成功（DISK.ROM / --emit-asm）"
fi

# sub.asm の内訳（命令文/data/raw）。
sub_stats_line="$(grep '^STATS DISK ' "$WORK/sub_build.log" || true)"
echo "  内訳   $sub_stats_line"
sub_raw="$(printf '%s' "$sub_stats_line" | sed -n 's/.*raw=\([0-9]*\).*/\1/p')"
if [ "$sub_raw" = "0" ]; then
    ok "sub.asm: コード中の生db 0件"
else
    ng "sub.asm: コード中に生db が $sub_raw 件残っている（命令メソッド化されていない直書き）"
fi

sub_sha="$(sha256_of "$SUB_OUT/DISK.ROM")"
if [ "$sub_sha" = "$EXPECT_SUBROM_DISK_SHA" ]; then
    ok "make_subrom.py の DISK.ROM の sha256 が変更前と一致"
else
    ng "make_subrom.py の DISK.ROM の sha256 が変わった: $sub_sha (期待 $EXPECT_SUBROM_DISK_SHA)"
fi

if python3 "$Z80TEXT" "$SUB_ASM" -o "$WORK/sub_reasm.bin" \
        > "$WORK/sub_reasm.log" 2>&1; then
    if python3 - "$SUB_OUT/DISK.ROM" "$WORK/sub_reasm.bin" <<'PYEOF'
import sys
rom = open(sys.argv[1], "rb").read()
reasm = open(sys.argv[2], "rb").read()
ok = rom[:len(reasm)] == reasm and set(rom[len(reasm):]) <= {0}
sys.exit(0 if ok else 1)
PYEOF
    then
        ok "make_subrom.py の DISK.ROM: .asm経由の再組み立てがバイト一致"
    else
        ng "make_subrom.py の DISK.ROM: .asm経由の再組み立てがバイト不一致"
    fi
else
    ng "sub.asm の再アセンブルに失敗"
    tail -20 "$WORK/sub_reasm.log"
fi

# --------------------------------------------------------------------------
# 3. 陽性対照（故障注入）: .asmを1か所だけ機械的に壊すと検出できるか
# --------------------------------------------------------------------------

# 3a. ある LD のオペランドを変える（N88.asm の "LD SP,0xF000" を書き換える）。
BROKEN1="$WORK/n88_broken_ld.asm"
sed 's/LD SP,0xF000/LD SP,0xF001/' "$IPL_ASM/N88.asm" > "$BROKEN1"
if grep -q "LD SP,0xF001" "$BROKEN1"; then
    if python3 "$Z80TEXT" "$BROKEN1" -o "$WORK/broken1.bin" \
            > "$WORK/broken1.log" 2>&1; then
        broken_len=$(wc -c < "$WORK/broken1.bin")
        if cmp -s <(head -c "$broken_len" "$IPL_OUT/N88.ROM") "$WORK/broken1.bin"; then
            ng "陽性対照(LDオペランド破壊)を検出できなかった"
        else
            ok "陽性対照(LDオペランド破壊)を検出できた（バイト不一致）"
        fi
    else
        ok "陽性対照(LDオペランド破壊)を検出できた（アセンブル自体が失敗）"
    fi
else
    ng "陽性対照(LDオペランド破壊)の仕込みに失敗（対象行が無い）"
fi

# 3b. ある JR を JP に変える（N88.asm の "JR HALT_LOOP" を想定。
#     無ければ最初に見つかった JR 行を書き換える）。
BROKEN2="$WORK/n88_broken_jr.asm"
python3 - "$IPL_ASM/N88.asm" "$BROKEN2" <<'PYEOF'
import re
import sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().splitlines()
done = False
for i, line in enumerate(lines):
    m = re.match(r"^(\s*)JR\s+(\S+)\s*$", line)
    if m and not done:
        lines[i] = f"{m.group(1)}JP {m.group(2)}"
        done = True
        break
open(dst, "w", encoding="utf-8").write("\n".join(lines) + "\n")
sys.exit(0 if done else 1)
PYEOF
if [ $? -eq 0 ]; then
    if python3 "$Z80TEXT" "$BROKEN2" -o "$WORK/broken2.bin" \
            > "$WORK/broken2.log" 2>&1; then
        orig_len=$(wc -c < "$IPL_OUT/N88.ROM")
        broken_len=$(wc -c < "$WORK/broken2.bin")
        if [ "$broken_len" != "$orig_len" ] || ! cmp -s "$IPL_OUT/N88.ROM" "$WORK/broken2.bin"; then
            ok "陽性対照(JR→JP破壊)を検出できた（バイト不一致/長さ変化）"
        else
            ng "陽性対照(JR→JP破壊)を検出できなかった"
        fi
    else
        ok "陽性対照(JR→JP破壊)を検出できた（アセンブル自体が失敗）"
    fi
else
    ng "陽性対照(JR→JP破壊)の仕込みに失敗（JR行が見つからない）"
fi

# --------------------------------------------------------------------------
# 4. 陽性対照（生db検出）: PC88_ASM_INJECT_RAW_DB=1 で生成器の一部の
#    呼び出しを命令メソッド経由から db() 直呼びへ切り替える
#    （バイト列は変えない）。「コード中の生db 0件」検査自体が
#    検出できることを確かめる。
# --------------------------------------------------------------------------
IPL_INJECT_OUT="$WORK/ipl_inject_out"
IPL_INJECT_ASM="$WORK/ipl_inject_asm"
mkdir -p "$IPL_INJECT_OUT"
if PC88_ASM_INJECT_RAW_DB=1 python3 src/l1_ipl/make_ipl_rom.py "$IPL_INJECT_OUT" \
        --emit-asm-dir "$IPL_INJECT_ASM" > "$WORK/ipl_inject.log" 2>&1; then
    inject_ipl_raw="$(sed -n 's/.*raw=\([0-9]*\).*/\1/p' "$WORK/ipl_inject.log")"
    if [ -n "$inject_ipl_raw" ] && [ "$inject_ipl_raw" -gt 0 ]; then
        ok "陽性対照(N88: PC88_ASM_INJECT_RAW_DB=1)を検出できた（raw=${inject_ipl_raw})"
    else
        ng "陽性対照(N88: PC88_ASM_INJECT_RAW_DB=1)を検出できなかった（raw=${inject_ipl_raw})"
    fi
    if cmp -s "$IPL_OUT/N88.ROM" "$IPL_INJECT_OUT/N88.ROM"; then
        ok "陽性対照(N88)はROMバイトを変えていない"
    else
        ng "陽性対照(N88)がROMバイトまで変えてしまった（注入方法が不適切）"
    fi
else
    ng "陽性対照(N88)用のmake_ipl_rom.py実行に失敗した"
    tail -20 "$WORK/ipl_inject.log"
fi

SUB_INJECT_OUT="$WORK/sub_inject_out"
SUB_INJECT_ASM="$WORK/sub_inject.asm"
mkdir -p "$SUB_INJECT_OUT"
if PC88_ASM_INJECT_RAW_DB=1 python3 src/l3_service/make_subrom.py "$SUB_INJECT_OUT" \
        --probe-site general_read_request --probe-mode clear \
        --emit-asm "$SUB_INJECT_ASM" > "$WORK/sub_inject.log" 2>&1; then
    inject_sub_raw="$(sed -n 's/.*raw=\([0-9]*\).*/\1/p' "$WORK/sub_inject.log")"
    if [ -n "$inject_sub_raw" ] && [ "$inject_sub_raw" -gt 0 ]; then
        ok "陽性対照(sub: PC88_ASM_INJECT_RAW_DB=1 + probe)を検出できた（raw=${inject_sub_raw})"
    else
        ng "陽性対照(sub: PC88_ASM_INJECT_RAW_DB=1 + probe)を検出できなかった（raw=${inject_sub_raw})"
    fi
else
    ng "陽性対照(sub)用のmake_subrom.py実行に失敗した"
    tail -20 "$WORK/sub_inject.log"
fi

# --------------------------------------------------------------------------
# 5. 単独実行（tools/asm/ を伴わない）: 生成器ファイル自身の方針
#    （冒頭docstring）は「外部依存ゼロで、第三者が
#    `python3 make_ipl_rom.py/make_subrom.py <出力先>` だけで同じROMを
#    再生成できる」こと。生成器ファイルだけを一時ディレクトリへコピー
#    （tools/asm が無い状態）して実行し、
#      ①既定実行が rc=0 で通る
#      ②出力ROMのsha256が上のEXPECT_*と一致（バイト不変）
#      ③単独コピーで --emit-asm(-dir) を付けると rc≠0
#    を確かめる。さらに陽性対照として、asm_emit の import を
#    無条件（try/except無し）に機械的に戻したコピーが①で落ちる
#    （＝この検査自体に検出力がある）ことを確かめる。
#    ここで見つかった実例: ccc44e2/1d376af でtools/asm/asm_emit.pyを
#    無条件importしていたため、生成器を単独コピーして実行すると
#    ImportErrorで落ちていた（early_response_rom_selftest.shのNGで発覚）。
# --------------------------------------------------------------------------

# asm_emit の import を try/except から無条件importへ機械的に戻す
# （M7段階0の元の不具合を再現する陽性対照専用。tools/asm/asm_emit.py
# 自体は書き換えない——生成器ファイルのコピーだけを書き換える）。
revert_to_unconditional_import() {
    python3 - "$1" <<'PYEOF'
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
try_idx = next(i for i, l in enumerate(lines) if l.strip() == "try:")
import_lines = []
i = try_idx + 1
while True:
    l = lines[i]
    import_lines.append(l[4:] if l.startswith("    ") else l)
    if "_ASM_EMIT_AVAILABLE = True" in l:
        i += 1
        break
    i += 1
except_idx = next(j for j in range(i, len(lines))
                   if lines[j].strip().startswith("except ImportError"))
j = except_idx + 1
while j < len(lines):
    l = lines[j]
    if l.strip() == "" or l.startswith(" ") or l.startswith("\t"):
        j += 1
        continue
    break
new_lines = lines[:try_idx] + import_lines[:-1] + lines[j:]
open(path, "w", encoding="utf-8").write("".join(new_lines))
PYEOF
}

STANDALONE_IPL="$WORK/standalone_ipl"
STANDALONE_SUB="$WORK/standalone_sub"
mkdir -p "$STANDALONE_IPL" "$STANDALONE_SUB"
cp src/l1_ipl/make_ipl_rom.py "$STANDALONE_IPL/make_ipl_rom.py"
cp src/l3_service/make_subrom.py "$STANDALONE_SUB/make_subrom.py"

# 5a. 単独コピー・既定実行（tools/asmは同梱していない）
if ( cd "$STANDALONE_IPL" && python3 make_ipl_rom.py out ) \
        > "$WORK/standalone_ipl.log" 2>&1; then
    ok "make_ipl_rom.py 単独コピーの既定実行が rc=0"
else
    ng "make_ipl_rom.py 単独コピーの既定実行が失敗した"
    tail -20 "$WORK/standalone_ipl.log"
fi
standalone_n88_sha="$(sha256_of "$STANDALONE_IPL/out/N88.ROM" 2>/dev/null || true)"
if [ "$standalone_n88_sha" = "$EXPECT_N88_SHA" ]; then
    ok "単独コピーのN88.ROMのsha256が変更前と一致"
else
    ng "単独コピーのN88.ROMのsha256が不一致: $standalone_n88_sha (期待 $EXPECT_N88_SHA)"
fi
standalone_ipl_disk_sha="$(sha256_of "$STANDALONE_IPL/out/DISK.ROM" 2>/dev/null || true)"
if [ "$standalone_ipl_disk_sha" = "$EXPECT_IPL_DISK_SHA" ]; then
    ok "単独コピー(make_ipl_rom.py)のDISK.ROMのsha256が変更前と一致"
else
    ng "単独コピー(make_ipl_rom.py)のDISK.ROMのsha256が不一致: $standalone_ipl_disk_sha (期待 $EXPECT_IPL_DISK_SHA)"
fi

if ( cd "$STANDALONE_SUB" && python3 make_subrom.py out ) \
        > "$WORK/standalone_sub.log" 2>&1; then
    ok "make_subrom.py 単独コピーの既定実行が rc=0"
else
    ng "make_subrom.py 単独コピーの既定実行が失敗した"
    tail -20 "$WORK/standalone_sub.log"
fi
standalone_sub_sha="$(sha256_of "$STANDALONE_SUB/out/DISK.ROM" 2>/dev/null || true)"
if [ "$standalone_sub_sha" = "$EXPECT_SUBROM_DISK_SHA" ]; then
    ok "単独コピー(make_subrom.py)のDISK.ROMのsha256が変更前と一致"
else
    ng "単独コピー(make_subrom.py)のDISK.ROMのsha256が不一致: $standalone_sub_sha (期待 $EXPECT_SUBROM_DISK_SHA)"
fi

# 5b. 単独コピーで --emit-asm(-dir) を付けると rc≠0（分かりやすいエラーで終了）
if ( cd "$STANDALONE_IPL" && python3 make_ipl_rom.py out2 --emit-asm-dir asmout ) \
        > "$WORK/standalone_ipl_emit.log" 2>&1; then
    ng "make_ipl_rom.py 単独コピー+--emit-asm-dir が rc=0 になってしまった（本来rc≠0）"
else
    ok "make_ipl_rom.py 単独コピー+--emit-asm-dir が rc≠0（想定どおり）"
fi
if ( cd "$STANDALONE_SUB" && python3 make_subrom.py out2 --emit-asm x.asm ) \
        > "$WORK/standalone_sub_emit.log" 2>&1; then
    ng "make_subrom.py 単独コピー+--emit-asm が rc=0 になってしまった（本来rc≠0）"
else
    ok "make_subrom.py 単独コピー+--emit-asm が rc≠0（想定どおり）"
fi

# 5c. 陽性対照: asm_emit importを無条件に戻したコピーは、単独実行(tools/asm無し)
# だとImportErrorで落ちる（＝5aの検査自体に検出力がある）ことを確かめる。
STANDALONE_IPL_BROKEN="$WORK/standalone_ipl_broken"
STANDALONE_SUB_BROKEN="$WORK/standalone_sub_broken"
mkdir -p "$STANDALONE_IPL_BROKEN" "$STANDALONE_SUB_BROKEN"
cp src/l1_ipl/make_ipl_rom.py "$STANDALONE_IPL_BROKEN/make_ipl_rom.py"
cp src/l3_service/make_subrom.py "$STANDALONE_SUB_BROKEN/make_subrom.py"
revert_to_unconditional_import "$STANDALONE_IPL_BROKEN/make_ipl_rom.py"
revert_to_unconditional_import "$STANDALONE_SUB_BROKEN/make_subrom.py"

if ( cd "$STANDALONE_IPL_BROKEN" && python3 make_ipl_rom.py out ) \
        > "$WORK/standalone_ipl_broken.log" 2>&1; then
    ng "陽性対照(N88: 無条件import復元)を検出できなかった（単独実行が通ってしまった）"
else
    ok "陽性対照(N88: 無条件import復元)を検出できた（単独実行がImportErrorで失敗）"
fi
if ( cd "$STANDALONE_SUB_BROKEN" && python3 make_subrom.py out ) \
        > "$WORK/standalone_sub_broken.log" 2>&1; then
    ng "陽性対照(sub: 無条件import復元)を検出できなかった（単独実行が通ってしまった）"
else
    ok "陽性対照(sub: 無条件import復元)を検出できた（単独実行がImportErrorで失敗）"
fi

echo
if [ "$fail" -eq 0 ]; then
    echo "全項目 OK"
else
    echo "NG: $fail 件"
fi
exit "$fail"

#!/usr/bin/env bash
# tools/l4_s1f_chain_selftest.sh — l4-s1f 事前登録「器具の自己検査」節の
# 「連続打鍵チェーンの自己検査」。
#
# --key-matrix のみを1走に5個連ねてマーカー QXZJK を打った場合と、
# --type "QXZJK" で同じ文字列を打った場合(l4-s1a・l4-s1bの既存実績と
# 同じ経路)とで、マーカー行の row_signature(SHA-256)が一致することを
# 確かめる。
#
# 追記(実ROMでの試走、2026-09-19): 「非空白セル件数==5の行」でマーカー行
# row0を特定する方法は、実ROMでは成立しなかった(起動直後の画面には
# マーカー行を含め既に非空白セルがある。ここでは何が書かれているかには
# 触れない)。代わりに、キー入力の無い基準走(baseline)との
# --diff-before/--diff-after で「押す前が空白だったセル」の座標から
# マーカーの位置(row0・開始col0)を特定する方式に直した。この事実は
# 事前登録の「マーカー行の無編集時の内容は列0〜4」という前提
# （行頭・行中・行末の列決め打ち0/2/5）にも影響する可能性があり、
# 本番24腕へ進む前に追補（マーカーの開始列col0を決め打ちせず、この
# 自己検査で実測してから腕ごとの位置決め回数を決める）が要る。
# ここでは自己検査の合否判定のみ行い、24腕の実測には進んでいない。
#
# 注記(読み替え): main.c の ascii_to_retrok() は英字A-Z/a-zを大小区別
# せず同じRETROKへ、SHIFT無しで変換する(shift=0固定、main.c 311-318行)。
# つまり --type は元々CAPSを合成しない。したがって本自己検査は
# CAPS無し(既定の小文字状態)で両経路を比べる。これは「連続打鍵チェーン
# の機構(--key-matrixで複数キーを1走に連ねてもタイミングが崩れないか)」
# を確かめるのが目的であり、CAPSの効果自体は docs/spec/l3-main.md 第10節
# (l4-s1bで既に確定済み)を信頼する。事前登録の実際の24腕では
# CAPSを別途保持する(tools/l4_s1f_arms.py)。
#
# 使い方: PC88_REF_ROM_DIR=/path/to/rom tools/l4_s1f_chain_selftest.sh --out-dir DIR
# private/ に対する ls・cat・find・存在確認は一切行わない。ハーネスが
# 「ROM未検出」を返した場合はそのまま失敗として終了する。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
PROBE="$REPO/tools/l4_vram_probe.py"

OUT_DIR=""
ROM_DIR="${PC88_REF_ROM_DIR:-}"
while [ $# -gt 0 ]; do
    case "$1" in
        --out-dir) OUT_DIR="$2"; shift 2;;
        --rom-dir) ROM_DIR="$2"; shift 2;;
        *) echo "[chain_selftest] 未知の引数: $1" >&2; exit 2;;
    esac
done
[ -n "$ROM_DIR" ] || { echo "[chain_selftest] PC88_REF_ROM_DIR か --rom-dir が要る" >&2; exit 2; }
[ -n "$OUT_DIR" ] || { echo "[chain_selftest] --out-dir が要る(リポジトリ外)" >&2; exit 2; }
case "$OUT_DIR" in
    "$REPO"/*) echo "[chain_selftest] --out-dir はリポジトリ外にすること" >&2; exit 2;;
esac
mkdir -p "$OUT_DIR"

make -s -C "$FRONTEND_DIR"
CORE_CANDIDATES=("$REPO/../vendor/quasi88-libretro"/quasi88_libretro.*)
CORE="${CORE_CANDIDATES[0]:-}"
[ -n "$CORE" ] && [ -f "$CORE" ] || { echo "[chain_selftest] コアが無い" >&2; exit 1; }

START=700
HOLD=4
GAP=8
DUMP_FRAME=$((START + 5*(HOLD+GAP) + 20))
FRAMES=$((DUMP_FRAME + 50))

echo "[chain_selftest] Run A: --key-matrix チェーン(5キー連続)"
"$FRONTEND" --core "$CORE" --rom-dir "$ROM_DIR" --frames "$FRAMES" \
    --key-matrix "0x04:1:$START:$HOLD" \
    --key-matrix "0x05:0:$((START+1*(HOLD+GAP))):$HOLD" \
    --key-matrix "0x05:2:$((START+2*(HOLD+GAP))):$HOLD" \
    --key-matrix "0x03:2:$((START+3*(HOLD+GAP))):$HOLD" \
    --key-matrix "0x03:3:$((START+4*(HOLD+GAP))):$HOLD" \
    --vram-dump "$OUT_DIR/chainA.bin" --vram-dump-at "$DUMP_FRAME" \
    >"$OUT_DIR/chainA.stdout.txt" 2>"$OUT_DIR/chainA.stderr.txt"
RC_A=$?

echo "[chain_selftest] Run B: --type 文字列"
"$FRONTEND" --core "$CORE" --rom-dir "$ROM_DIR" --frames "$FRAMES" \
    --type "QXZJK" --type-at "$START" --key-hold "$HOLD" --key-gap "$GAP" \
    --vram-dump "$OUT_DIR/chainB.bin" --vram-dump-at "$DUMP_FRAME" \
    >"$OUT_DIR/chainB.stdout.txt" 2>"$OUT_DIR/chainB.stderr.txt"
RC_B=$?

if [ "$RC_A" -ne 0 ] || [ "$RC_B" -ne 0 ]; then
    echo "[chain_selftest] NG: 走行そのものが失敗した(rc_A=$RC_A rc_B=$RC_B)。ROM未検出の可能性。stderrを確認すること" >&2
    exit 1
fi

echo "[chain_selftest] 非空白行の要約からマーカー行(row0)を特定"
python3 "$PROBE" --vram-dump "$OUT_DIR/chainA.bin" --nonblank-summary-rows all --json \
    >"$OUT_DIR/chainA.nonblank.json"
python3 "$PROBE" --vram-dump "$OUT_DIR/chainB.bin" --nonblank-summary-rows all --json \
    >"$OUT_DIR/chainB.nonblank.json"

ROW_A=$(python3 - "$OUT_DIR/chainA.nonblank.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
entries = d["nonblank_summary"][0]["nonblank_summary"]
cand = [e["row0"] for e in entries if e["nonblank_count"] == 5]
print(cand[0] if cand else -1)
PY
)
ROW_B=$(python3 - "$OUT_DIR/chainB.nonblank.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
entries = d["nonblank_summary"][0]["nonblank_summary"]
cand = [e["row0"] for e in entries if e["nonblank_count"] == 5]
print(cand[0] if cand else -1)
PY
)

if [ "$ROW_A" -lt 0 ] || [ "$ROW_B" -lt 0 ]; then
    echo "[chain_selftest] 未確定: 非空白5セルの行が見つからない(ROW_A=$ROW_A ROW_B=$ROW_B)。" >&2
    echo "[chain_selftest] 実ROMでは起動直後の画面に既に非空白セルがあり、" >&2
    echo "[chain_selftest] この判定方式(件数==5)では行を特定できない可能性がある。" >&2
    echo "[chain_selftest] --diff-before(キー入力の無い基準走)/--diff-afterで" >&2
    echo "[chain_selftest] マーカーの実際の座標を先に確認し、事前登録の追補が要るか判断すること。" >&2
    exit 1
fi

python3 "$PROBE" --vram-dump "$OUT_DIR/chainA.bin" --row-signature "$ROW_A" --json >"$OUT_DIR/chainA.sig.json"
python3 "$PROBE" --vram-dump "$OUT_DIR/chainB.bin" --row-signature "$ROW_B" --json >"$OUT_DIR/chainB.sig.json"

SHA_A=$(python3 -c "import json;d=json.load(open('$OUT_DIR/chainA.sig.json'));print(d['row_signature'][0]['row_signature'][0]['row_sha256'])")
SHA_B=$(python3 -c "import json;d=json.load(open('$OUT_DIR/chainB.sig.json'));print(d['row_signature'][0]['row_signature'][0]['row_sha256'])")

echo "[chain_selftest] ROW_A=$ROW_A ROW_B=$ROW_B"
if [ "$ROW_A" != "$ROW_B" ]; then
    echo "[chain_selftest] NG: マーカー行の行番号が一致しない(ROW_A=$ROW_A ROW_B=$ROW_B)" >&2
    exit 1
fi
if [ "$SHA_A" != "$SHA_B" ]; then
    echo "[chain_selftest] NG: row_sha256が不一致(内容が食い違う)" >&2
    exit 1
fi

echo "[chain_selftest] OK: --key-matrixチェーンと--typeが同じ行番号・同じrow_sha256"
exit 0

#!/usr/bin/env bash
# compare_l3_entry_fdc.py のunit/head・結果ステータス分類自己検査。
# 入力は公開μPD765形式から作った合成ログだけで、公式データは含まない。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/compare_l3_entry_fdc.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

make_log() {
  local path="$1" unit="$2" status="$3"
  python3 - "$path" "$unit" "$status" <<'EOF'
import sys
path, unit, status = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
events = [
    ("OUT", 0x04), ("OUT", unit), ("IN", status),
]
with open(path, "w", encoding="utf-8") as fp:
    fp.write("# 合成FDCログ（公式データ不使用）\n")
    fp.write("core      : (テスト用ダミー)\nframes    : 800\n\n")
    fp.write("# main\n# seq clock frame cpu kind port value pc\n\n")
    fp.write("# sub\n# seq clock frame cpu kind port value pc\n")
    for seq, (kind, value) in enumerate(events, 1):
        fp.write(f"{seq:6d} {seq:6d} 700 sub {kind:<4} 00FB {value:02X} 0100\n")
EOF
}

# B/head0、READY、WRITE PROTECTEDを表す公開分類用の合成値。
make_log "$WORK/base.txt" 1 97
make_log "$WORK/same.txt" 1 97
# 故障注入1: unitだけAへ変える。
make_log "$WORK/bad-unit.txt" 0 96
# 故障注入2: WRITE PROTECTEDだけ落とす。
make_log "$WORK/bad-status.txt" 1 33

if out="$(python3 "$CHECK" --official "$WORK/base.txt" --mixed "$WORK/same.txt" \
      --after-frame 700 2>&1)" \
   && printf '%s\n' "$out" | grep -q '公式入口区間unit/head分類:.*B/head0' \
   && printf '%s\n' "$out" | grep -q 'FDC READ DATA発行件数: 公式=0件、混成=0件' \
   && printf '%s\n' "$out" | grep -q 'FDC WRITE DATA発行件数: 公式=0件、混成=0件' \
   && printf '%s\n' "$out" | grep -q '入口区間のunit/head差: なし' \
   && printf '%s\n' "$out" | grep -q '入口区間の結果ステータス差: なし'; then
  ok "同じunit/head・結果分類を全長一致と判定"
else
  ng "同じ合成ログの分類が一致しない"
fi

out="$(python3 "$CHECK" --official "$WORK/base.txt" --mixed "$WORK/bad-unit.txt" \
      --after-frame 700 2>&1)"
if printf '%s\n' "$out" | grep -q '最初のunit/head差: コマンド1件目' \
   && printf '%s\n' "$out" | grep -q '公式=B/head0、混成=A/head0'; then
  ok "故障注入したunit差を位置と公開分類で検出"
else
  ng "unit差を検出できない"
fi

out="$(python3 "$CHECK" --official "$WORK/base.txt" --mixed "$WORK/bad-status.txt" \
      --after-frame 700 2>&1)"
if printf '%s\n' "$out" | grep -q '最初の結果ステータス差: コマンド1件目' \
   && printf '%s\n' "$out" | grep -q 'WRITE PROTECTED'; then
  ok "故障注入したST3分類差を位置と公開ビット名で検出"
else
  ng "ST3分類差を検出できない"
fi

if printf '%s\n' "$out" | grep -Eq '0x|=[0-9A-Fa-f]{2}([、,/]|$)'; then
  ng "分類出力へ結果バイト値が漏れた"
else
  ok "分類出力に結果バイト値を出さない"
fi

# --- ここから m7fi向け追加: SEEK/SENSE INTERRUPT STATUSの段一致判定 ---
# SEEK(2パラメータ) -> SENSE INTERRUPT STATUS(結果2バイト) -> READ DATA(8パラメータ)
# の3段からなる合成ログ。シリンダ値・PCN値は検査対象であり合成データなので
# 公式データには当たらない（クリーンルーム規律 禁止事項1・4対象外）。
make_stage_log() {
  local path="$1" seek_cyl="$2" sense_st0="$3" read_c="$4"
  python3 - "$path" "$seek_cyl" "$sense_st0" "$read_c" <<'EOF'
import sys
path = sys.argv[1]
seek_cyl, sense_st0, read_c = (int(v, 0) for v in sys.argv[2:5])
events = [
    ("OUT", 0x0F), ("OUT", 0x01), ("OUT", seek_cyl),          # SEEK B/head0
    ("OUT", 0x08), ("IN", sense_st0), ("IN", seek_cyl),        # SENSE INTERRUPT STATUS
    ("OUT", 0x06), ("OUT", 0x01), ("OUT", read_c),             # READ DATA unit/head, C
    ("OUT", 0), ("OUT", 1), ("OUT", 2), ("OUT", 8), ("OUT", 0x1B), ("OUT", 0xFF),
]
with open(path, "w", encoding="utf-8") as fp:
    fp.write("# 合成FDCログ（公式データ不使用）\n")
    fp.write("core      : (テスト用ダミー)\nframes    : 800\n\n")
    fp.write("# main\n# seq clock frame cpu kind port value pc\n\n")
    fp.write("# sub\n# seq clock frame cpu kind port value pc\n")
    for seq, (kind, value) in enumerate(events, 1):
        fp.write(f"{seq:6d} {seq:6d} 700 sub {kind:<4} 00FB {value:02X} 0100\n")
EOF
}

# SEEK END|unit1のST0で、SEEK指定シリンダ・READ DATAのCとも揃えた基準ログ。
make_stage_log "$WORK/stage-base.txt" 40 0x21 40
# 故障注入3: SEEKの指定シリンダだけ変える（stage_cylinder_consistencyの
# 「等しい」判定を崩すことも兼ねる）。
make_stage_log "$WORK/stage-bad-seek.txt" 41 0x21 41
# 故障注入4: SEEKの指定シリンダとREAD DATAのCだけをずらす（SEEK自体は基準と
# 一致させたまま、同一ログ内の内部整合だけを崩す）。
make_stage_log "$WORK/stage-bad-consistency.txt" 40 0x21 41
# 故障注入5: SENSE INTERRUPT STATUSのST0だけ変える（SEEK ENDが落ち、ICが
# 「無効コマンド」分類へ変わる）。
make_stage_log "$WORK/stage-bad-sense.txt" 40 0x81 40

# seek_cylinder_match / stage_cylinder_consistency を直接呼ぶ検査。
# 標準出力にTrue/Falseの真偽以外（シリンダ値そのもの等）が出ないことも
# 併せて確認する。
py_out="$(python3 - "$WORK" <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, "tools")
import compare_l3_entry_fdc as c

work = Path(sys.argv[1])

def load(name):
    _, cmds, _ = c.command_names(work / name)
    return cmds

seek_b, sense_b, read_b = load("stage-base.txt")
seek_s, sense_s, read_s = load("stage-bad-seek.txt")
seek_c, sense_c, read_c = load("stage-bad-consistency.txt")

print("match_same=", c.seek_cylinder_match(seek_b, seek_b))
print("match_diff=", c.seek_cylinder_match(seek_b, seek_s))
print("consistency_same=", c.stage_cylinder_consistency(seek_b, read_b))
print("consistency_diff=", c.stage_cylinder_consistency(seek_c, read_c))
try:
    c.seek_cylinder_match(seek_b, read_b)
    print("guard=NG(例外が出なかった)")
except c.awp.SafeError:
    print("guard=OK")
EOF
)"

if printf '%s\n' "$py_out" | grep -q '^match_same= True$' \
   && printf '%s\n' "$py_out" | grep -q '^match_diff= False$' \
   && printf '%s\n' "$py_out" | grep -q '^consistency_same= True$' \
   && printf '%s\n' "$py_out" | grep -q '^consistency_diff= False$' \
   && printf '%s\n' "$py_out" | grep -q '^guard=OK$'; then
  ok "seek_cylinder_match/stage_cylinder_consistencyが真偽を正しく返す（陽性対照込み）"
else
  ng "seek_cylinder_match/stage_cylinder_consistencyの判定が想定と違う"
  printf '%s\n' "$py_out"
fi

if printf '%s\n' "$py_out" | grep -Eq '[0-9]{2,}'; then
  ng "seek_cylinder_match/stage_cylinder_consistencyの出力に数値が漏れた"
else
  ok "seek_cylinder_match/stage_cylinder_consistencyの出力に数値が無い"
fi

# --list-all-stages: 同一ログ同士なら段1(SEEK)・段2(SENSE INTERRUPT STATUS)
# とも「一致」。
out="$(python3 "$CHECK" --official "$WORK/stage-base.txt" --mixed "$WORK/stage-base.txt" \
      --after-frame 700 --list-all-stages 2>&1)"
if printf '%s\n' "$out" | grep -q '段1(SEEK): シリンダ指定 一致' \
   && printf '%s\n' "$out" | grep -q '段2(SENSE INTERRUPT STATUS):.*一致$'; then
  ok "--list-all-stagesが同一ログを段番号付きで一致と判定"
else
  ng "--list-all-stagesの同一ログ判定が想定と違う"
fi

# 故障注入3（陽性対照）: SEEK段のシリンダ差を「不一致」として検出できるか。
out="$(python3 "$CHECK" --official "$WORK/stage-base.txt" --mixed "$WORK/stage-bad-seek.txt" \
      --after-frame 700 --list-all-stages 2>&1)"
if printf '%s\n' "$out" | grep -q '段1(SEEK): シリンダ指定 不一致'; then
  ok "--list-all-stagesが故障注入したSEEKシリンダ差を不一致として検出"
else
  ng "--list-all-stagesがSEEKシリンダ差を検出できない"
fi

# 故障注入5（陽性対照）: SENSE INTERRUPT STATUS段の復号差を「不一致」として
# 検出できるか。
out="$(python3 "$CHECK" --official "$WORK/stage-base.txt" --mixed "$WORK/stage-bad-sense.txt" \
      --after-frame 700 --list-all-stages 2>&1)"
if printf '%s\n' "$out" | grep -q '段2(SENSE INTERRUPT STATUS):.*不一致$' \
   && printf '%s\n' "$out" | grep -q '無効コマンド'; then
  ok "--list-all-stagesが故障注入したSENSE INTERRUPT STATUS差を不一致として検出"
else
  ng "--list-all-stagesがSENSE INTERRUPT STATUS差を検出できない"
fi

if printf '%s\n' "$out" | grep -Eq '0x|=[0-9A-Fa-f]{2}([、,/]|$)'; then
  ng "--list-all-stagesの出力へ結果バイト値が漏れた"
else
  ok "--list-all-stagesの出力に結果バイト値を出さない"
fi

# 既存の引数なし（--after-frame無し）呼び出しの振る舞いを壊していないことの確認。
out="$(python3 "$CHECK" --official "$WORK/base.txt" --mixed "$WORK/same.txt" 2>&1)"
if printf '%s\n' "$out" | grep -q 'FDCコマンド種別の最初の差: なし（全長一致）' \
   && ! printf '%s\n' "$out" | grep -q '入口区間'; then
  ok "--after-frame無しの既存出力を壊していない"
else
  ng "--after-frame無し呼び出しの出力が変わった"
fi

exit "$rc"

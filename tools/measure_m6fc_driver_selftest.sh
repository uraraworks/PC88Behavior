#!/usr/bin/env bash
# tools/measure_m6fc_driver_selftest.sh — tools/measure_m6fc.sh (m6f-c測定
# ドライバ)自体の自己検査。公式ROM・本物のq88measureは一切使わない。
#
# 背景: mfc_segments (measure_m6fc.sh 内、check_m6fc_preregistration.SEGMENTS
# を frontend への --type 引数へ変換する関数) が、本物の改行を含んだ
# 文字列をそのまま `frame<TAB>text` の1行として出していたため、bash の
# `while IFS=$'\t' read` が本物の改行のところで行を打ち切り、Enter の打鍵
# (末尾の"\n"=バックスラッシュ+nの2文字)が失われていた。この不具合は
# GB (起動確認腕)で顕在化し、2回目の本測定まで気付かれなかった。修正は
# 「\nの2文字へ戻してから出す」(凍結表 tools/m6fc_frozen.tsv と同じ書き方)。
# 単体の自己検査 (tools/check_m6fc_preregistration_selftest.sh 等) は
# 凍結表とSEGMENTSの内容が一致するかしか見ておらず、この「ドライバが
# その内容をどう1行に直列化するか」という結線までは見ていなかったため
# 検出できなかった。この自己検査はその結線を、偽フロントエンドに渡る
# 実際のargvを記録して検査する。
#
# やること:
#   1. M6FC_FRONTEND に偽フロントエンド(一時python、$WORKに生成)を差し込み、
#      PC88_REF_ROM_DIR は空の一時ディレクトリ、find_l3_core が見つからない
#      環境に備えて measure_m6fc.sh に足した試験用の口 M6FC_TEST_CORE で
#      コアの実在チェックだけ迂回する(既定は無効。本番の挙動は変えない)。
#   2. 全512走(256腕×2)を回すと重いので、同じく試験用の口
#      M6FC_TEST_SW_MAX (SW腕の掃引上限。既定255=無効)と
#      M6FC_TEST_STOP_AFTER_ARM (指定した腕を2走終えたら打ち切る。既定は無効)
#      で GB→SW-00→(A1,A1b,)A2 までに絞って回す。
#   3. 偽フロントエンドに渡ったargvを記録し、GB-FFの"bt"打鍵・SWの打鍵・
#      A2の3区間の打鍵が凍結表 tools/m6fc_frozen.tsv の segment 行と完全に
#      一致すること、かつどの引数にも本物の改行文字が含まれないことを検査する。
#   4. 陰性対照: mfc_segments を修正前の形(text.replace未適用)に戻した
#      一時コピーで同じ検査を回すと、最初の腕(GB-FF)で
#      segments_count 関門に引っかかり rc!=0 になることを確認する
#      (bashのreadが本物の改行で行を打ち切るため、渡した区間数と
#      凍結表の区間数が食い違う)。
#
# 画面本文・公式ROM・vendor/・禁止された生成器/自己検査は一切触れない。
#
# 使い方: tools/measure_m6fc_driver_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
BROKEN="$REPO/tools/.measure_m6fc_broken_selftest_tmp.sh"
trap 'rm -rf "$WORK"; rm -f "$BROKEN"' EXIT
rc=0

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

# --- 偽フロントエンドを用意する ---------------------------------------------
FAKE="$WORK/fake_frontend.py"
cat > "$FAKE" <<'PYEOF'
#!/usr/bin/env python3
"""m6f-cドライバ自己検査用の偽フロントエンド。本物のq88measureの代わりに
受け取ったargvを記録し、合成のio-log/レポートを書くだけ。実エミュレーション
は一切行わない。argvの記録は1呼び出し=1行のJSON({"argv":[...]})とし、
各引数はJSON文字列として書く(本物の改行はJSONの\nへ、打鍵文字列自身が
持つ「バックスラッシュ+n」2文字はJSONの\\nへ、それぞれ別の形で符号化
されるので、呼び出し元は両者を区別して検査できる)。
"""
import json
import os
import sys


def _find(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
    return None


def main() -> int:
    argv = sys.argv[1:]
    out_path = _find(argv, "--out")
    iolog_path = _find(argv, "--io-log")
    disk1_path = _find(argv, "--disk")
    typed = [argv[i + 1] for i, a in enumerate(argv) if a == "--type" and i + 1 < len(argv)]

    log_path = os.environ.get("M6FC_SELFTEST_ARGV_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv}, ensure_ascii=False) + "\n")

    # G8陰性対照専用: 指定時だけ、コアがドライブ1(書き込み保護のはずの
    # 参照複製)を書き換えてしまった場合を模す。既定は無効(本番の挙動は
    # 変えない)。
    if os.environ.get("M6FC_SELFTEST_CORRUPT_DISK1") and disk1_path:
        with open(disk1_path, "r+b") as f:
            f.seek(0)
            f.write(b"\xff")

    if iolog_path:
        with open(iolog_path, "w", encoding="utf-8") as f:
            f.write("# fake iolog (measure_m6fc_driver_selftest)\n")

    if out_path:
        bt = 'print chr$(90);chr$(81);"bt"\\n'
        tag = None
        if bt in typed:
            tag = "bt"
        if tag is None:
            for t in typed:
                if t.startswith('10 on error goto 90:f$="2:"+chr$(81)+chr$(90)+chr$(55)+chr$(65)'):
                    tag = "ok"
                    break
        if tag is None:
            for t in typed:
                if t.startswith('10 print chr$(90);chr$(81);"ld"'):
                    tag = "ld"
                    break
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("[測定終了時のテキスト画面]\n")
            if tag is not None:
                f.write("0| ZQ" + tag + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
chmod +x "$FAKE"

mkdir -p "$WORK/rom" "$WORK/raw" "$WORK/refdisk"
ARGVLOG="$WORK/argv.jsonl"
: > "$ARGVLOG"

# 追補2(ドライブ2で測る): 参照ディスク(ドライブ1)は凍結表の reference_disk
# (N88_FE.D88)という名前の合成ファイルを使い捨てで用意する。中身は公式
# ディスクではなく、この自己検査だけが読み書きする合成バイト列。
printf 'FAKE-REFERENCE-DISK-FOR-SELFTEST' > "$WORK/refdisk/N88_FE.D88"

# --- 1. 陽性側: 修正済みドライバを偽フロントエンドで、GB→SW-00→A2まで回す ----
env \
  M6FC_FRONTEND="$FAKE" \
  PC88_REF_ROM_DIR="$WORK/rom" \
  PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FC_TEST_CORE="selftest-core" \
  M6FC_TEST_SW_MAX=0 \
  M6FC_TEST_STOP_AFTER_ARM=A2 \
  M6FC_SELFTEST_ARGV_LOG="$ARGVLOG" \
  "$REPO/tools/measure_m6fc.sh" --raw-dir "$WORK/raw" --result "$WORK/result.json" \
  >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt"
run_rc=$?

if [ "$run_rc" -eq 0 ] && grep -q 'stopped after arm=A2' "$WORK/run.stdout.txt"; then
  ok "陽性側: ドライバがGB→SW-00→A2までrc=0で完走した"
else
  ng "陽性側: ドライバがrc=0で完走しなかった(rc=$run_rc)。末尾: $(tail -c 300 "$WORK/run.stderr.txt")"
fi

# --- 2. argvの検査(GB-FF/SW-00/A2が凍結表と完全一致・本物の改行が無い) ------
VERIFY="$WORK/verify_positive.py"
cat > "$VERIFY" <<'PYEOF'
import json
import re
import sys
from pathlib import Path

argv_log = Path(sys.argv[1])
frozen_path = Path(sys.argv[2])


def load_frozen_segments(path):
    segs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2 or parts[0] != "segment":
            continue
        arm, frame, text = parts[1].split(":", 2)
        segs.setdefault(arm, []).append((int(frame), text))
    return segs


frozen = load_frozen_segments(frozen_path)

calls = []
if argv_log.exists():
    for line in argv_log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            calls.append(json.loads(line)["argv"])

DISK_RE = re.compile(r"^(?P<arm>.+)-r(?P<rep>\d+)\.d88$")


def arm_of(argv):
    # 追補2(ドライブ2で測る): --disk はドライブ1の参照ディスク複製
    # (ファイル名は ARM-rN.drive1.d88)、--disk2 が生成器の媒体
    # (ファイル名は ARM-rN.d88)。腕名は --disk2 から取る。
    for i, a in enumerate(argv):
        if a == "--disk2" and i + 1 < len(argv):
            m = DISK_RE.match(Path(argv[i + 1]).name)
            if m:
                return m.group("arm")
    return None


by_arm = {}
for argv in calls:
    by_arm.setdefault(arm_of(argv), []).append(argv)


def type_at(argv, frame):
    target = str(frame)
    for i in range(len(argv) - 3):
        if argv[i] == "--type-at" and argv[i + 1] == target and argv[i + 2] == "--type":
            return argv[i + 3]
    return None


fails = []

# --- GB-FF: --type-at 700 直後の --type が凍結表のBTと完全一致し \n で終わる
gbff = by_arm.get("GB-FF", [])
if len(gbff) != 2:
    fails.append(f"GB-FFの呼び出しが2件でない: {len(gbff)}")
else:
    expected = next((t for f, t in frozen.get("GB-FF", []) if f == 700), None)
    if expected is None:
        fails.append("凍結表にGB-FFの700区間が無い")
    for argv in gbff:
        got = type_at(argv, 700)
        if got != expected:
            fails.append(f"GB-FFの--type-at 700直後の--typeが凍結表と不一致: got={got!r}")
        elif not got.endswith("\\n"):
            fails.append("GB-FFの打鍵が\\n(バックスラッシュ+n)で終わっていない")

# --- SW-00: --type-at 700 直後の --type が凍結表のSWと完全一致
sw = by_arm.get("SW-00", [])
if len(sw) != 2:
    fails.append(f"SW-00の呼び出しが2件でない: {len(sw)}")
else:
    expected = next((t for f, t in frozen.get("SW", []) if f == 700), None)
    if expected is None:
        fails.append("凍結表にSWの700区間が無い")
    for argv in sw:
        got = type_at(argv, 700)
        if got != expected:
            fails.append("SW-00の--type-at 700直後の--typeが凍結表と不一致")

# --- A2: 700/2500/4000 の3区間が凍結表と完全一致
a2 = by_arm.get("A2", [])
if len(a2) != 2:
    fails.append(f"A2の呼び出しが2件でない: {len(a2)}")
else:
    expected_frames = [700, 2500, 4000]
    frozen_a2 = frozen.get("A2", [])
    if sorted(f for f, _ in frozen_a2) != expected_frames:
        fails.append("凍結表のA2区間がframes仕様(700,2500,4000)と不一致")
    for argv in a2:
        for frame, text in frozen_a2:
            got = type_at(argv, frame)
            if got != text:
                fails.append(f"A2の--type-at {frame}直後の--typeが凍結表と不一致")

# --- 2b. 全呼び出しが --disk(ドライブ1) と --disk2(ドライブ2) の両方を
#         受け取っていること(追補2: ドライブ1に参照ディスク・ドライブ2に
#         自作媒体)。
def has_both_disks(argv):
    return "--disk" in argv and "--disk2" in argv


missing_disk_args = [argv for argv in calls if not has_both_disks(argv)]
if missing_disk_args:
    fails.append(f"--diskまたは--disk2を欠いた呼び出しが{len(missing_disk_args)}件ある")

# --- 3. どの引数にも本物の改行文字が含まれないこと ---------------------------
leaked = False
for argv in calls:
    for a in argv:
        if "\n" in a:
            leaked = True
if leaked:
    fails.append("argvに本物の改行文字を含む引数がある")

if not calls:
    fails.append("argvログが空(偽フロントエンドが一度も呼ばれていない)")

if fails:
    for m in fails:
        print("NG: " + m)
    sys.exit(1)
print("OK: GB-FF/SW-00/A2のargvが凍結表と完全一致し、本物の改行を含む引数も無い"
      f"(呼び出し{len(calls)}件)")
sys.exit(0)
PYEOF

verify_out="$(python3 "$VERIFY" "$ARGVLOG" "$REPO/tools/m6fc_frozen.tsv" 2>&1)"
verify_rc=$?
printf '%s\n' "$verify_out"
if [ "$verify_rc" -eq 0 ]; then
  ok "argv検査: 凍結表と完全一致・本物の改行なし"
else
  ng "argv検査が失敗した"
fi

# --- 4. 陰性対照: mfc_segments を修正前の形に戻すとNGになること ------------
python3 - "$REPO/tools/measure_m6fc.sh" "$BROKEN" <<'PYEOF' >"$WORK/revert.out" 2>&1
import sys
from pathlib import Path

src_path, dst_path = Path(sys.argv[1]), Path(sys.argv[2])
lines = src_path.read_text(encoding="utf-8").splitlines(keepends=True)
target_idx = [i for i, l in enumerate(lines) if l.strip().startswith('print(f"{frame}')]
if len(target_idx) != 1:
    print(f"ANCHOR_COUNT={len(target_idx)}")
    sys.exit(1)
i = target_idx[0]
indent = lines[i][: len(lines[i]) - len(lines[i].lstrip(" "))]
lines[i] = indent + 'print(f"{frame}\\t{text}")\n'
dst_path.write_text("".join(lines), encoding="utf-8")
print("REVERTED")
PYEOF
revert_rc=$?
if [ "$revert_rc" -eq 0 ] && grep -q REVERTED "$WORK/revert.out"; then
  ok "陰性対照用コピー: mfc_segmentsを修正前の形に戻した"
else
  ng "陰性対照用コピーの作成に失敗した: $(cat "$WORK/revert.out")"
fi
chmod +x "$BROKEN"

: > "$ARGVLOG"
env \
  M6FC_FRONTEND="$FAKE" \
  PC88_REF_ROM_DIR="$WORK/rom" \
  PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FC_TEST_CORE="selftest-core" \
  M6FC_TEST_SW_MAX=0 \
  M6FC_TEST_STOP_AFTER_ARM=A2 \
  M6FC_SELFTEST_ARGV_LOG="$ARGVLOG" \
  "$BROKEN" --raw-dir "$WORK/raw2" --result "$WORK/result2.json" \
  >"$WORK/broken.stdout.txt" 2>"$WORK/broken.stderr.txt"
broken_rc=$?

calls_after_broken="$(wc -l < "$ARGVLOG" | tr -d ' ')"
if [ "$broken_rc" -ne 0 ]; then
  ok "陰性対照: 修正前の形に戻すとドライバがNG(rc=$broken_rc)になった"
else
  ng "陰性対照: 修正前の形に戻してもrc=0で完走してしまった(検出力なし)"
fi
if [ "$calls_after_broken" -eq 0 ]; then
  ok "陰性対照: 偽フロントエンドが一度も呼ばれずGB-FFの区間数チェックで止まった"
else
  ng "陰性対照: 偽フロントエンドが${calls_after_broken}回呼ばれてしまった(想定は0回)"
fi

# --- 5. G8陰性対照: 偽フロントエンドがドライブ1(参照複製)を書き換えたら
#        ドライバがgate_failed G8で止まること -----------------------------
env \
  M6FC_FRONTEND="$FAKE" \
  PC88_REF_ROM_DIR="$WORK/rom" \
  PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FC_TEST_CORE="selftest-core" \
  M6FC_TEST_SW_MAX=0 \
  M6FC_TEST_STOP_AFTER_ARM=A2 \
  M6FC_SELFTEST_CORRUPT_DISK1=1 \
  "$REPO/tools/measure_m6fc.sh" --raw-dir "$WORK/raw_g8" --result "$WORK/result_g8.json" \
  >"$WORK/g8.stdout.txt" 2>"$WORK/g8.stderr.txt"
g8_rc=$?

if [ "$g8_rc" -ne 0 ] && grep -q '"reason":"G8"' "$WORK/g8.stdout.txt"; then
  ok "G8陰性対照: ドライブ1の書き換えをgate_failed G8として検出した"
else
  ng "G8陰性対照: ドライブ1の書き換えを検出できなかった(rc=$g8_rc, stdout=$(cat "$WORK/g8.stdout.txt"))"
fi

# 参照ディスク本体が、この検査のせいで壊れていないことも確かめる
# (書き換えたのは複製 --disk のパスであり、参照ディスクそのものではない)。
if [ "$(cat "$WORK/refdisk/N88_FE.D88")" = "FAKE-REFERENCE-DISK-FOR-SELFTEST" ]; then
  ok "G8陰性対照: 参照ディスク本体は書き換わっていない(複製だけが壊れた)"
else
  ng "G8陰性対照: 参照ディスク本体まで書き換わってしまった"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"

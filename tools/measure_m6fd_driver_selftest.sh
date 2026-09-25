#!/usr/bin/env bash
# tools/measure_m6fd.sh (m6f-d測定ドライバ)自体の自己検査。公式ROM・本物の
# q88measureは一切使わない。derive_m6fd.py / tools/m6fd_entry.py は
# まだ無い(別担当)ため、試験用の口 M6FD_TEST_R_STAR /
# M6FD_TEST_SKIP_ENTRY_FIELDS で迂回する。
#
# 検査項目:
#   (a) I-1・II-d・III-00-07・IV-R-00・V-crc の打鍵が凍結表と完全一致して
#       届く(本物の改行なし)
#   (b) II-dの2段目の --disk2 像が付け替え済み(偽フロントエンドが1段目では
#       H1〜H3に従う合成ファイルQZ7Bを--disk2に書き込み、2段目でQZ7Rが
#       (18,1,1)にあることを独立に確認)
#   (c) V-*で --disk が媒体・--disk2 なし
#   (d) G8陰性対照(ドライブ1書き換えの検出)
#   (e) rc=134の回し直し
#   (f) 取りこぼしがIV-fillでは続行・I-1ではgate_failed
#
# 画面本文・公式ROM・vendor/・禁止された生成器/自己検査は一切触れない。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

# --- 偽フロントエンドを用意する ---------------------------------------------
FAKE="$WORK/fake_frontend.py"
cat > "$FAKE" <<'PYEOF'
#!/usr/bin/env python3
"""m6f-dドライバ自己検査用の偽フロントエンド。実エミュレーションはせず、
argvを記録し、合成のio-log/レポート/disk2像を書くだけ。

m6f-dのH1〜H3(仮説)を単純化してBASICのファイル書き込みを模す: 1段目で
"QZ7B"を書く打鍵(rec_tpl系)を検知したら --disk2 のイメージへ
名前QZ7Bのエントリを(18,1,1)に置く(実物のROMがやるであろう配置の代用)。
2段目でQZ7Rを読む打鍵を検知したら、その名前が--disk2像の(18,1,1)に
あるかどうかで"rb 0"(見つかった)/"er"(見つからない)を出し分ける。
"""
import json
import os
import struct
import sys

D88_HEADER_SIZE = 32
TRACK_COUNT = 164
TRACK_TABLE_SIZE = TRACK_COUNT * 4
SECTOR_HEADER_SIZE = 16
SECTOR_SIZE = 256
SECTORS_PER_TRACK = 16
TRACK_BYTES = SECTORS_PER_TRACK * (SECTOR_HEADER_SIZE + SECTOR_SIZE)


def _find(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
    return None


def _find_all(argv, name):
    return [argv[i + 1] for i, a in enumerate(argv) if a == name and i + 1 < len(argv)]


def _sector_offset(c, h, r):
    phys = c * 2 + h
    return (D88_HEADER_SIZE + TRACK_TABLE_SIZE + phys * TRACK_BYTES
            + (r - 1) * (SECTOR_HEADER_SIZE + SECTOR_SIZE) + SECTOR_HEADER_SIZE)


def _minimal_d88():
    header = bytearray(32)
    track_table = bytearray(TRACK_COUNT * 4)
    body = bytearray()
    offset = 32 + TRACK_COUNT * 4
    for c in range(40):
        for h in range(2):
            trk = bytearray()
            for r in range(1, 17):
                hdr = bytearray(16)
                hdr[0], hdr[1], hdr[2], hdr[3] = c, h, r, 1
                hdr[4] = 16
                hdr[14] = SECTOR_SIZE & 0xFF
                hdr[15] = (SECTOR_SIZE >> 8) & 0xFF
                trk += hdr
                trk += bytes([0xFF]) * SECTOR_SIZE
            phys = c * 2 + h
            struct.pack_into("<I", track_table, phys * 4, offset)
            body += trk
            offset += len(trk)
    struct.pack_into("<I", header, 28, offset)
    return bytearray(bytes(header) + bytes(track_table) + bytes(body))


FAT_COORD = (18, 1, 14)
CHAIN_START_UNIT = 50


def _write_chain_entry(img, name, coord, chain_len):
    """m6fd_relocate.py が読める最小限の構造(エントリ+FAT[18,1,14]の鎖)を
    合成する。本体セクタの中身は関係ない(relocateはバイトをそのまま写す
    だけ)。鎖はCHAIN_START_UNITから連番、終端値は160以上の適当な値。"""
    off = _sector_offset(*coord)
    entry = bytearray(16)
    padded = (name + " " * 9)[:9].encode("ascii")
    entry[0:9] = padded
    entry[10] = CHAIN_START_UNIT
    img[off:off + 16] = entry

    fat_off = _sector_offset(*FAT_COORD)
    fat = bytearray(img[fat_off:fat_off + SECTOR_SIZE])
    for i in range(chain_len):
        unit = CHAIN_START_UNIT + i
        fat[unit] = (CHAIN_START_UNIT + i + 1) if i + 1 < chain_len else 0xC9
    img[fat_off:fat_off + SECTOR_SIZE] = fat


def _entry_name_at(img, coord=(18, 1, 1)):
    off = _sector_offset(*coord)
    return bytes(img[off:off + 9]).rstrip(b" ").decode("ascii", "replace")


def main() -> int:
    argv = sys.argv[1:]
    out_path = _find(argv, "--out")
    iolog_path = _find(argv, "--io-log")
    disk1_path = _find(argv, "--disk")
    disk2_path = _find(argv, "--disk2")
    typed = _find_all(argv, "--type")

    log_path = os.environ.get("M6FD_SELFTEST_ARGV_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv}, ensure_ascii=False) + "\n")

    if os.environ.get("M6FD_SELFTEST_CORRUPT_DISK1") and disk1_path:
        with open(disk1_path, "r+b") as f:
            f.seek(0)
            f.write(b"\xff")

    # rc=134 (abort) を指定回数だけ返す。
    abort_n = int(os.environ.get("M6FD_SELFTEST_ABORT_N", "0"))
    counter_path = os.environ.get("M6FD_SELFTEST_ABORT_COUNTER")
    if abort_n > 0 and counter_path:
        n = 0
        if os.path.exists(counter_path):
            n = int(open(counter_path).read().strip() or "0")
        if n < abort_n:
            with open(counter_path, "w") as f:
                f.write(str(n + 1))
            return 134

    drop_arms = os.environ.get("M6FD_SELFTEST_DROP_ARMS", "").split()
    arm_hint = os.path.basename(out_path or "")

    tag = None
    if 'print chr$(90);chr$(81);"bt"\\n' in typed:
        tag = "bt"
    is_stage2_read = any('chr$(81)+chr$(90)+chr$(55)+chr$(82)' in t for t in typed)
    is_stage1_write = any('chr$(81)+chr$(90)+chr$(55)+chr$(66)' in t for t in typed)
    is_dir_read = any('chr$(81)+chr$(68)' in t for t in typed)
    is_save_q7l = any('save"2:q7l"' in t for t in typed)

    # 1段目: 生成器が既に作った媒体へ、m6fd_relocate.pyが読める最小限の
    # エントリ+鎖を書き込む(実際のBASICのファイル書き込みの代用)。
    # 鎖の長さは腕ごとの--dst-unitsの個数に合わせる(II-d/neg1/neg2は2、
    # III-FF/III-00・II-pは1)。
    if disk2_path and os.path.exists(disk2_path) and is_stage1_write:
        if arm_hint.startswith(("II-d-", "II-neg1-", "II-neg2-")):
            chain_len = 2
        else:
            chain_len = 1
        img = bytearray(open(disk2_path, "rb").read())
        _write_chain_entry(img, "QZ7B", (18, 1, 1), chain_len)
        with open(disk2_path, "r+b") as f:
            f.seek(0)
            f.write(bytes(img))
    elif disk2_path and os.path.exists(disk2_path) and is_save_q7l:
        img = bytearray(open(disk2_path, "rb").read())
        _write_chain_entry(img, "q7l", (18, 1, 1), 1)
        with open(disk2_path, "r+b") as f:
            f.seek(0)
            f.write(bytes(img))

    ok_tag = None
    if is_stage2_read:
        name_at_dir = None
        if disk2_path and os.path.exists(disk2_path):
            img = bytearray(open(disk2_path, "rb").read())
            name_at_dir = _entry_name_at(img)
        ok_tag = "rb 0" if name_at_dir == "QZ7R" else "er 53 0"
    elif is_dir_read:
        ok_tag = "ok"

    if iolog_path:
        with open(iolog_path, "w", encoding="utf-8") as f:
            f.write("# fake iolog (measure_m6fd_driver_selftest)\n")
            for a in drop_arms:
                if arm_hint.startswith(a + "-"):
                    f.write("# 取りこぼし: 3件 / 総イベント数: 9件\n")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("[測定終了時のテキスト画面]\n")
            row = 0
            if tag is not None:
                f.write(f"{row}| ZQ{tag}\n"); row += 1
            if ok_tag is not None:
                f.write(f"{row}| ZQ{ok_tag}\n"); row += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
chmod +x "$FAKE"

mkdir -p "$WORK/rom" "$WORK/raw" "$WORK/refdisk"
printf 'FAKE-REFERENCE-DISK-FOR-SELFTEST' > "$WORK/refdisk/N88_FE.D88"
ARGVLOG="$WORK/argv.jsonl"

# --- 1. 陽性側: I→II→III(r<=7)→IV-R(0..0)→IV-fill→Vまで完走させる ----------
: > "$ARGVLOG"
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_TEST_R_STAR="none" M6FD_TEST_SKIP_ENTRY_FIELDS=1 \
  M6FD_TEST_III_MAX=7 M6FD_TEST_IV_R_MAX=0 \
  M6FD_SELFTEST_ARGV_LOG="$ARGVLOG" \
  "$REPO/tools/measure_m6fd.sh" --raw-dir "$WORK/raw" --result "$WORK/result.json" \
  >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt"
run_rc=$?

if [ "$run_rc" -eq 0 ] && grep -q 'measurement complete' "$WORK/run.stdout.txt"; then
  ok "陽性側: ドライバがI→II→III(r<=7)→IV-R(0)→IV-fill→Vまでrc=0で完走した"
else
  ng "陽性側: ドライバがrc=0で完走しなかった(rc=$run_rc)。末尾: $(tail -c 400 "$WORK/run.stderr.txt")"
fi

# --- (a) I-1・II-d・III-00-07・IV-R-00・V-crc の打鍵が凍結表と完全一致 -------
VERIFY="$WORK/verify.py"
cat > "$VERIFY" <<'PYEOF'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
argv_log = Path(sys.argv[2])
sys.path.insert(0, str(repo / "tools"))
import check_m6fd_preregistration as c

calls = []
if argv_log.exists():
    for line in argv_log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            calls.append(json.loads(line)["argv"])


def type_at(argv, frame):
    target = str(frame)
    for i in range(len(argv) - 3):
        if argv[i] == "--type-at" and argv[i + 1] == target and argv[i + 2] == "--type":
            return argv[i + 3]
    return None


def out_name(argv):
    for i, a in enumerate(argv):
        if a == "--out" and i + 1 < len(argv):
            return Path(argv[i + 1]).name
    return ""


fails = []

# I-1: フレーム700の打鍵が凍結表と完全一致・\nで終わる
i1_calls = [a for a in calls if out_name(a).startswith("I-1-p-r")]
if len(i1_calls) != 2:
    fails.append(f"I-1の呼び出しが2件でない: {len(i1_calls)}")
else:
    expected = c.resolve_segments("I-1", None)[0][1].replace("\n", "\\n")
    for argv in i1_calls:
        got = type_at(argv, 700)
        if got != expected:
            fails.append(f"I-1の打鍵が凍結表と不一致: got={got!r}")
        if "\n" in (got or ""):
            fails.append("I-1の打鍵に本物の改行が混入")

# II-d: 1段目(I-17相当)・2段目(II_STAGE2)がそれぞれ一致
iid_p1 = [a for a in calls if out_name(a).startswith("II-d-p1-r")]
iid_p2 = [a for a in calls if out_name(a).startswith("II-d-p2-r")]
if len(iid_p1) != 2 or len(iid_p2) != 2:
    fails.append(f"II-dの呼び出し件数が想定外: p1={len(iid_p1)} p2={len(iid_p2)}")
else:
    exp1 = c.resolve_segments("II-d", "1")[0][1].replace("\n", "\\n")
    exp2 = c.resolve_segments("II-d", "2")[0][1].replace("\n", "\\n")
    for argv in iid_p1:
        if type_at(argv, 700) != exp1:
            fails.append("II-d 1段目の打鍵が凍結表と不一致")
    for argv in iid_p2:
        if type_at(argv, 700) != exp2:
            fails.append("II-d 2段目の打鍵が凍結表と不一致")

# III-00-07: 2段目の打鍵が凍結表と完全一致
iii_calls = [a for a in calls if out_name(a).startswith("III-00-07-p2-r")]
if len(iii_calls) != 2:
    fails.append(f"III-00-07の2段目呼び出しが2件でない: {len(iii_calls)}")
else:
    expected = c.resolve_segments("III-00-07", "2")[0][1].replace("\n", "\\n")
    for argv in iii_calls:
        if type_at(argv, 700) != expected:
            fails.append("III-00-07 2段目の打鍵が凍結表と不一致")

# IV-R-00: 打鍵が凍結表(=m6fc SW)と完全一致
ivr_calls = [a for a in calls if out_name(a).startswith("IV-R-00-p-r")]
if len(ivr_calls) != 2:
    fails.append(f"IV-R-00の呼び出しが2件でない: {len(ivr_calls)}")
else:
    expected = c.resolve_segments("IV-R-00", None)[0][1].replace("\n", "\\n")
    for argv in ivr_calls:
        if type_at(argv, 700) != expected:
            fails.append("IV-R-00の打鍵が凍結表と不一致")

# V-crc: 打鍵が凍結表と完全一致
vcrc_calls = [a for a in calls if out_name(a).startswith("V-crc-p-r")]
if len(vcrc_calls) != 2:
    fails.append(f"V-crcの呼び出しが2件でない: {len(vcrc_calls)}")
else:
    expected = c.resolve_segments("V-crc", None)[0][1].replace("\n", "\\n")
    for argv in vcrc_calls:
        if type_at(argv, 700) != expected:
            fails.append("V-crcの打鍵が凍結表と不一致")

# 改行漏れの全体チェック
for argv in calls:
    for a in argv:
        if "\n" in a:
            fails.append("argvに本物の改行文字を含む引数がある")
            break

# --- (b) II-dの2段目でQZ7Rが(18,1,1)にある(rb 0が出た)ことを確認 -------------
# 測定ドライバ自身の作業ディレクトリ(WORK)はドライバ終了時に削除されるため、
# レポートファイルを直接は読めない。永続する結果JSON(result.json)の
# markersで確認する(ドライバの正規の出口を経由した検査)。
result_path = Path(sys.argv[3])
result_doc = json.loads(result_path.read_text(encoding="utf-8"))
ii_d_p2 = [r for r in result_doc.get("runs", [])
           if r.get("arm") == "II-d" and r.get("phase") == 2]
if not ii_d_p2:
    fails.append("結果JSONにII-dのphase=2の走が無い")
elif not all(any(m.get("tag") == "rb" and m.get("numbers") == [0] for m in r.get("markers", []))
             for r in ii_d_p2):
    fails.append(f"II-dのphase=2にZQrb 0が無い(付け替えが効いていない): {ii_d_p2!r}")

# --- (c) V-* で --disk はあるが --disk2 が無い(全V呼び出しについて確認) ------
v_calls = [a for a in calls if out_name(a).startswith("V-")]
if not v_calls:
    fails.append("V群の呼び出しが記録されていない")
for argv in v_calls:
    if "--disk2" in argv:
        fails.append(f"V群の呼び出しに--disk2がある(想定外): {out_name(argv)}")
    if "--disk" not in argv:
        fails.append(f"V群の呼び出しに--diskが無い: {out_name(argv)}")

if fails:
    for m in fails:
        print("NG: " + m)
    sys.exit(1)
print(f"OK: 打鍵一致・改行なし・II-d付け替え確認・V群--disk2なし(呼び出し{len(calls)}件)")
sys.exit(0)
PYEOF

verify_out="$(python3 "$VERIFY" "$REPO" "$ARGVLOG" "$WORK/result.json" 2>&1)"
verify_rc=$?
printf '%s\n' "$verify_out"
if [ "$verify_rc" -eq 0 ]; then
  ok "(a)(b)(c): 打鍵一致・II-d付け替え確認・V群--disk2なしを検査した"
else
  ng "(a)(b)(c)の検査が失敗した"
fi

# --- (d) G8陰性対照: ドライブ1書き換えでgate_failed G8 -----------------------
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_TEST_R_STAR="none" M6FD_TEST_SKIP_ENTRY_FIELDS=1 \
  M6FD_TEST_STOP_AFTER_ARM=I-1 M6FD_SELFTEST_CORRUPT_DISK1=1 \
  "$REPO/tools/measure_m6fd.sh" --raw-dir "$WORK/raw_g8" --result "$WORK/result_g8.json" \
  >"$WORK/g8.stdout.txt" 2>"$WORK/g8.stderr.txt"
g8_rc=$?
if [ "$g8_rc" -ne 0 ] && grep -q '"reason":"G8"' "$WORK/g8.stdout.txt"; then
  ok "(d) G8陰性対照: ドライブ1の書き換えをgate_failed G8として検出した"
else
  ng "(d) G8陰性対照を検出できなかった(rc=$g8_rc, stdout=$(cat "$WORK/g8.stdout.txt"))"
fi

# --- (e) rc=134の回し直し ----------------------------------------------------
rm -f "$WORK/abort_counter.txt"
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_TEST_R_STAR="none" M6FD_TEST_SKIP_ENTRY_FIELDS=1 \
  M6FD_TEST_STOP_AFTER_ARM=I-1 \
  M6FD_SELFTEST_ABORT_N=2 M6FD_SELFTEST_ABORT_COUNTER="$WORK/abort_counter.txt" \
  "$REPO/tools/measure_m6fd.sh" --raw-dir "$WORK/raw_ab" --result "$WORK/result_ab.json" \
  >"$WORK/ab.stdout.txt" 2>"$WORK/ab.stderr.txt"
ab_rc=$?
if [ "$ab_rc" -eq 0 ] && [ "$(cat "$WORK/abort_counter.txt" 2>/dev/null)" = "2" ]; then
  ok "(e) rc=134を2回吸収し3回目で完走した"
else
  ng "(e) rc=134の回し直しが想定どおりでない(rc=$ab_rc)"
fi

# 3回とも abort なら abort として記録され、rc=0で継続すること。
rm -f "$WORK/abort_counter2.txt"
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_TEST_R_STAR="none" M6FD_TEST_SKIP_ENTRY_FIELDS=1 \
  M6FD_TEST_STOP_AFTER_ARM=I-1 \
  M6FD_SELFTEST_ABORT_N=99 M6FD_SELFTEST_ABORT_COUNTER="$WORK/abort_counter2.txt" \
  M6FD_TEST_RUNS_COPY="$WORK/runs_allabort.ndjson" \
  "$REPO/tools/measure_m6fd.sh" --raw-dir "$WORK/raw_ab3" --result "$WORK/result_ab3.json" \
  >"$WORK/ab3.stdout.txt" 2>"$WORK/ab3.stderr.txt"
ab3_rc=$?
if [ "$ab3_rc" -eq 0 ] && python3 -c "
import json
rows=[json.loads(l) for l in open('$WORK/runs_allabort.ndjson') if l.strip()]
assert any(r.get('abort') is True and r.get('abort_retries')==3 for r in rows), rows
" 2>"$WORK/ab3_check.err"; then
  ok "(e) 3回ともabortなら abort:true, abort_retries:3 として記録し継続した"
else
  ng "(e) 3回abort時の記録が想定と違う(rc=$ab3_rc): $(cat "$WORK/ab3_check.err" 2>/dev/null)"
fi

# --- (f) 取りこぼし: IV-fillは続行、I-1はgate_failed -------------------------
: > "$ARGVLOG"
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_TEST_R_STAR="none" M6FD_TEST_SKIP_ENTRY_FIELDS=1 \
  M6FD_TEST_III_MAX=1 M6FD_TEST_IV_R_MAX=0 M6FD_TEST_STOP_AFTER_ARM=IV-fill \
  M6FD_SELFTEST_DROP_ARMS="IV-fill-free" \
  M6FD_TEST_RUNS_COPY="$WORK/runs_dropok.ndjson" \
  "$REPO/tools/measure_m6fd.sh" --raw-dir "$WORK/raw_dropok" --result "$WORK/result_dropok.json" \
  >"$WORK/dropok.stdout.txt" 2>"$WORK/dropok.stderr.txt"
dropok_rc=$?
if [ "$dropok_rc" -eq 0 ] && python3 -c "
import json
rows=[json.loads(l) for l in open('$WORK/runs_dropok.ndjson') if l.strip()]
fillfree=[r for r in rows if r['arm']=='IV-fill-free']
assert len(fillfree)==2 and all(r['iolog_dropped']==3 and r['reads'] is None for r in fillfree), fillfree
" 2>"$WORK/dropok_check.err"; then
  ok "(f) IV-fill-freeの取りこぼしで止まらず、件数を記録し座標はnullにした"
else
  ng "(f) IV-fillの取りこぼし継続が想定と違う(rc=$dropok_rc): $(cat "$WORK/dropok_check.err" 2>/dev/null)"
fi

env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_TEST_R_STAR="none" M6FD_TEST_SKIP_ENTRY_FIELDS=1 \
  M6FD_TEST_STOP_AFTER_ARM=I-1 \
  M6FD_SELFTEST_DROP_ARMS="I-1" \
  "$REPO/tools/measure_m6fd.sh" --raw-dir "$WORK/raw_dropng" --result "$WORK/result_dropng.json" \
  >"$WORK/dropng.stdout.txt" 2>"$WORK/dropng.stderr.txt"
dropng_rc=$?
if [ "$dropng_rc" -ne 0 ] && grep -q '"reason":"run_summary"' "$WORK/dropng.stdout.txt"; then
  ok "(f) I-1の取りこぼしはgate_failed(run_summary)で止まった"
else
  ng "(f) I-1の取りこぼしで止まらなかった(rc=$dropng_rc, stdout=$(cat "$WORK/dropng.stdout.txt"))"
fi

echo
if [ "$rc" -eq 0 ]; then echo "全項目 OK"; else echo "NG あり"; fi
exit "$rc"

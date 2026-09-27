#!/usr/bin/env bash
# tools/measure_m6ff.sh (m6f-f測定ドライバ)自体の自己検査。公式ROM・本物の
# q88measureは一切使わない。偽フロントエンドがdisk2像へエントリを合成し、
# ドライバが tools/m6fd_entry.entry_fields(実物)で読み戻して結果JSONへ
# 詰めるところまでを確認する。
#
# 検査項目:
#   (a) 陽性側: 6腕×2走が完走し、judge_m6ff.pyがtype_byte等の判定を出す
#   (b) F-Sの種別バイトが0x80でない → control_failed
#   (c) F-0のディレクトリに他腕の名前が残る → g6_ok=false (G6 NG)
#   (d) 2走で不一致 → inconclusive
#   (e) 凍結表(media_sha256)を壊す → gate_failed、起動回数0
#   (f) --bsave-addr 未指定 → gate_failed、起動回数0
#   (g) 漏えい目印: 本体セクタに埋めた秘密の値が、どの出力にも現れない
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
"""m6f-fドライバ自己検査用の偽フロントエンド。実エミュレーションはせず、
argvを記録し、合成のio-log/レポート/disk2像を書くだけ。

--out のファイル名(<arm>-r<rep>.report.txt)から腕と走を判定し、disk2像の
(18,1,1)に、対応する名前のエントリを合成する。9〜15バイト目(bytes9_15)は
腕ごとの既定値を使い、環境変数で上書き・欠落・不一致を注入できる。
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

DEFAULT_BYTES9_15 = {
    "F-S": [0x80, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
    "F-A": [0xA0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
    "F-P": [0xA1, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
    "F-B": [0xA2, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
    "F-D": [0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
}
NAME_OF = {"F-S": "qzs", "F-A": "qza", "F-P": "qzp", "F-B": "qzb", "F-D": "qzd"}


def _find(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
    return None


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


def _write_entry(img, name, bytes9_15, coord=(18, 1, 1)):
    off = _sector_offset(*coord)
    entry = bytearray(16)
    padded = (name + " " * 9)[:9].encode("ascii")
    entry[0:9] = padded
    for j, v in enumerate(bytes9_15):
        entry[9 + j] = v
    img[off:off + 16] = entry


def _write_body_marker(img, coord, value):
    off = _sector_offset(*coord)
    img[off:off + 16] = bytes([value]) * 16


def main() -> int:
    argv = sys.argv[1:]
    out_path = _find(argv, "--out")
    iolog_path = _find(argv, "--io-log")
    disk2_path = _find(argv, "--disk2")

    log_path = os.environ.get("M6FF_SELFTEST_ARGV_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv}, ensure_ascii=False) + "\n")

    arm_hint = os.path.basename(out_path or "")  # "<arm>-r<rep>.report.txt"
    arm = None
    rep = None
    for a in ("F-S", "F-A", "F-P", "F-B", "F-D", "F-0"):
        prefix = a + "-r"
        if arm_hint.startswith(prefix):
            arm = a
            rest = arm_hint[len(prefix):]
            rep = rest.split(".", 1)[0]
            break

    if disk2_path and os.path.exists(disk2_path) and arm and arm != "F-0":
        img = bytearray(open(disk2_path, "rb").read())
        name = NAME_OF[arm]
        bytes9_15 = list(DEFAULT_BYTES9_15[arm])

        override = os.environ.get("M6FF_SELFTEST_TYPE_BYTE_OVERRIDE", "")
        for item in override.split():
            k, _, v = item.partition("=")
            if k == arm:
                bytes9_15[0] = int(v, 0)

        skip_no_entry = os.environ.get("M6FF_SELFTEST_NO_ENTRY_ARM", "")
        write_it = not any(a2 == arm for a2 in skip_no_entry.split())

        mismatch_arm = os.environ.get("M6FF_SELFTEST_MISMATCH_ARM", "")
        if arm == mismatch_arm and rep == "2":
            bytes9_15[0] = (bytes9_15[0] + 1) & 0xFF

        if write_it:
            _write_entry(img, name, bytes9_15)

        marker = os.environ.get("M6FF_SELFTEST_BODY_MARKER")
        if marker:
            _write_body_marker(img, (1, 0, 1), int(marker, 0))

        with open(disk2_path, "r+b") as f:
            f.seek(0)
            f.write(bytes(img))
    elif disk2_path and os.path.exists(disk2_path) and arm == "F-0":
        if os.environ.get("M6FF_SELFTEST_F0_LEAK"):
            img = bytearray(open(disk2_path, "rb").read())
            _write_entry(img, "qzs", DEFAULT_BYTES9_15["F-S"])
            with open(disk2_path, "r+b") as f:
                f.seek(0)
                f.write(bytes(img))

    if iolog_path:
        with open(iolog_path, "w", encoding="utf-8") as f:
            f.write("# fake iolog (measure_m6ff_driver_selftest)\n")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("[測定終了時のテキスト画面]\n0| ok\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
chmod +x "$FAKE"

mkdir -p "$WORK/rom" "$WORK/raw" "$WORK/refdisk"
printf 'FAKE-REFERENCE-DISK-FOR-SELFTEST' > "$WORK/refdisk/N88_FE.D88"
ARGVLOG="$WORK/argv.jsonl"

# --- (a) 陽性側: 6腕×2走が完走し、judge_m6ff.pyが判定を出す -----------------
: > "$ARGVLOG"
env M6FF_SELFTEST_ARGV_LOG="$ARGVLOG" \
  M6FF_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FF_TEST_CORE="selftest-core" \
  "$REPO/tools/measure_m6ff.sh" --raw-dir "$WORK/raw_pos" --result "$WORK/result_pos.json" \
  --bsave-addr '&HD000' \
  >"$WORK/pos.stdout.txt" 2>"$WORK/pos.stderr.txt"
pos_rc=$?
if [ "$pos_rc" -eq 0 ] && grep -q 'measurement complete' "$WORK/pos.stdout.txt"; then
  ok "陽性側: 6腕×2走がrc=0で完走した"
else
  ng "陽性側の完走に失敗した(rc=$pos_rc): $(tail -c 400 "$WORK/pos.stderr.txt")"
fi

boot_count="$(grep -c '"--core"' "$ARGVLOG" 2>/dev/null || true)"
[ -n "$boot_count" ] || boot_count=0
if [ "$boot_count" -eq 12 ]; then
  ok "陽性側: 起動回数が6腕×2走=12件"
else
  ng "陽性側の起動回数が想定外: $boot_count"
fi

judge_pos_out="$(python3 "$REPO/tools/judge_m6ff.py" --result "$WORK/result_pos.json" 2>&1)"
judge_pos_rc=$?
if [ "$judge_pos_rc" -eq 0 ] && python3 -c "
import json,sys
doc=json.loads('''$judge_pos_out''')
assert doc['arms']['F-S']['status']=='type_byte' and doc['arms']['F-S']['value']=='0x80', doc
assert doc['arms']['F-D']['status']=='type_byte' and doc['arms']['F-D']['value']=='0x00', doc
assert doc['g5_ok'] is True and doc['g6_ok'] is True and doc['control_failed'] is False, doc
assert doc['bytes11_15']['status']=='bytes11_15_unchanged', doc
"; then
  ok "(a) judge_m6ff.pyがtype_byte/g5_ok/g6_ok/bytes11_15_unchangedを正しく出した"
else
  ng "(a) judge_m6ff.pyの出力が想定外: $judge_pos_out"
fi

# --- (b) F-Sの種別バイトが0x80でない → control_failed -----------------------
env M6FF_SELFTEST_TYPE_BYTE_OVERRIDE="F-S=0x99" \
  M6FF_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FF_TEST_CORE="selftest-core" \
  "$REPO/tools/measure_m6ff.sh" --raw-dir "$WORK/raw_b" --result "$WORK/result_b.json" \
  --bsave-addr '&HD000' \
  >"$WORK/b.stdout.txt" 2>"$WORK/b.stderr.txt"
b_rc=$?
if [ "$b_rc" -eq 0 ] && python3 -c "
import json,subprocess,sys
out=subprocess.run(['python3','$REPO/tools/judge_m6ff.py','--result','$WORK/result_b.json'],capture_output=True,text=True)
doc=json.loads(out.stdout)
assert doc['arms']['F-S']['value']=='0x99', doc
assert doc['control_failed'] is True and doc['g5_ok'] is False, doc
"; then
  ok "(b) F-Sの種別バイト異常をcontrol_failedとして検出した"
else
  ng "(b) F-S異常のcontrol_failed検出に失敗した(rc=$b_rc)"
fi

# --- (c) F-0のディレクトリに他腕の名前が残る → g6_ok=false ------------------
env M6FF_SELFTEST_F0_LEAK=1 \
  M6FF_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FF_TEST_CORE="selftest-core" \
  "$REPO/tools/measure_m6ff.sh" --raw-dir "$WORK/raw_c" --result "$WORK/result_c.json" \
  --bsave-addr '&HD000' \
  >"$WORK/c.stdout.txt" 2>"$WORK/c.stderr.txt"
c_rc=$?
if [ "$c_rc" -eq 0 ] && python3 -c "
import json,subprocess
out=subprocess.run(['python3','$REPO/tools/judge_m6ff.py','--result','$WORK/result_c.json'],capture_output=True,text=True)
doc=json.loads(out.stdout)
assert doc['g6_ok'] is False, doc
assert 'qzs' in doc['arms']['F-0']['found'], doc
"; then
  ok "(c) F-0のエントリ残留をg6_ok=falseとして検出した"
else
  ng "(c) F-0陰性対照の検出に失敗した(rc=$c_rc)"
fi

# --- (d) 2走で不一致 → inconclusive -----------------------------------------
env M6FF_SELFTEST_MISMATCH_ARM="F-A" \
  M6FF_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FF_TEST_CORE="selftest-core" \
  "$REPO/tools/measure_m6ff.sh" --raw-dir "$WORK/raw_d" --result "$WORK/result_d.json" \
  --bsave-addr '&HD000' \
  >"$WORK/d.stdout.txt" 2>"$WORK/d.stderr.txt"
d_rc=$?
if [ "$d_rc" -eq 0 ] && python3 -c "
import json,subprocess
out=subprocess.run(['python3','$REPO/tools/judge_m6ff.py','--result','$WORK/result_d.json'],capture_output=True,text=True)
doc=json.loads(out.stdout)
assert doc['arms']['F-A']['status']=='inconclusive', doc
"; then
  ok "(d) 2走不一致をinconclusiveとして検出した"
else
  ng "(d) 2走不一致の検出に失敗した(rc=$d_rc)"
fi

# --- (e) 凍結表(media_sha256)を壊す → gate_failed、起動回数0 ----------------
BROKEN_CFG="$WORK/broken_frozen.tsv"
sed 's/^media_sha256\t.*/media_sha256\tdeadbeef/' "$REPO/tools/m6ff_frozen.tsv" > "$BROKEN_CFG"
: > "$ARGVLOG"
env M6FF_SELFTEST_ARGV_LOG="$ARGVLOG" M6FF_FROZEN_CONFIG="$BROKEN_CFG" \
  M6FF_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FF_TEST_CORE="selftest-core" \
  "$REPO/tools/measure_m6ff.sh" --raw-dir "$WORK/raw_e" --result "$WORK/result_e.json" \
  --bsave-addr '&HD000' \
  >"$WORK/e.stdout.txt" 2>"$WORK/e.stderr.txt"
e_rc=$?
e_boot="$(grep -c '"--core"' "$ARGVLOG" 2>/dev/null || true)"; [ -n "$e_boot" ] || e_boot=0
if [ "$e_rc" -ne 0 ] && grep -q '"reason":"preregistration_mismatch"' "$WORK/e.stdout.txt" \
  && [ "$e_boot" -eq 0 ]; then
  ok "(e) 凍結表の破壊をgate_failedで検出し、起動回数0のまま止まった"
else
  ng "(e) 凍結表破壊の検出に失敗した(rc=$e_rc, boot=$e_boot, stdout=$(cat "$WORK/e.stdout.txt"))"
fi

# --- (f) --bsave-addr 未指定 → gate_failed、起動回数0 ------------------------
: > "$ARGVLOG"
env M6FF_SELFTEST_ARGV_LOG="$ARGVLOG" \
  M6FF_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FF_TEST_CORE="selftest-core" \
  "$REPO/tools/measure_m6ff.sh" --raw-dir "$WORK/raw_f" --result "$WORK/result_f.json" \
  >"$WORK/f.stdout.txt" 2>"$WORK/f.stderr.txt"
f_rc=$?
f_boot="$(grep -c '"--core"' "$ARGVLOG" 2>/dev/null || true)"; [ -n "$f_boot" ] || f_boot=0
if [ "$f_rc" -ne 0 ] && grep -q '"reason":"bsave_addr_missing"' "$WORK/f.stdout.txt" \
  && [ "$f_boot" -eq 0 ]; then
  ok "(f) --bsave-addr未指定をgate_failedで検出し、起動回数0のまま止まった"
else
  ng "(f) --bsave-addr未指定の検出に失敗した(rc=$f_rc, boot=$f_boot)"
fi

# --- (g) 漏えい目印: 本体セクタに埋めた秘密の値がどの出力にも現れない -------
SECRET=173  # 0xAD、ドライバは9〜15バイト目とmarkers以外読まないので出ないはず
env M6FF_SELFTEST_BODY_MARKER="$SECRET" \
  M6FF_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FF_TEST_CORE="selftest-core" \
  "$REPO/tools/measure_m6ff.sh" --raw-dir "$WORK/raw_g" --result "$WORK/result_g.json" \
  --bsave-addr '&HD000' \
  >"$WORK/g.stdout.txt" 2>"$WORK/g.stderr.txt"
g_rc=$?
leak=0
if [ "$g_rc" -eq 0 ]; then
  if grep -q -e "173" -e "0xad" -e "0xAD" -e "173,173" \
      "$WORK/g.stdout.txt" "$WORK/result_g.json" 2>/dev/null; then
    leak=1
  fi
  judge_g_out="$(python3 "$REPO/tools/judge_m6ff.py" --result "$WORK/result_g.json" 2>&1)"
  case "$judge_g_out" in *173*|*0xad*|*0xAD*) leak=1 ;; esac
fi
if [ "$g_rc" -eq 0 ] && [ "$leak" -eq 0 ]; then
  ok "(g) 本体セクタの秘密の値がどの出力にも現れなかった"
else
  ng "(g) 漏えい目印検査が失敗した(rc=$g_rc, leak=$leak)"
fi

echo
if [ "$rc" -eq 0 ]; then echo "全項目 OK"; else echo "NG あり"; fi
exit "$rc"

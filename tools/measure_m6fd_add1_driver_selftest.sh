#!/usr/bin/env bash
# tools/measure_m6fd_add1.sh (m6f-d 追補1測定ドライバ)自体の自己検査。
# 公式ROM・本物のq88measureは一切使わない。偽フロントエンドが合成の
# iolog(実物のparse_iolog/parse_commands/split_by_driveが読める形)・
# disk2像(QZ7Bエントリ、10バイト目=20)を書く。
#
# 検査項目:
#   (a) 陽性側: E-*(6腕)→IV-fill-free→(--r-star noneならIV-fill-resなし)で
#       rc=0完走し、result.jsonのE腕にwrites・entry_fields(QZ7Bキー)が入る
#   (b) --r-star 0xB0 を渡すとIV-fill-resも走る
#   (c) 取りこぼし: E-*はgate_failed、IV-fill-freeは継続
#   (d) G8陰性対照
#   (e) rc=134の回し直し
#   (f) --r-star noneでIV-fill-resが走らない(陰性対照)
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

FAKE="$WORK/fake_frontend.py"
cat > "$FAKE" <<'PYEOF'
#!/usr/bin/env python3
"""m6f-d 追補1ドライバ自己検査用の偽フロントエンド。実エミュレーションは
せず、合成のio-log(実物のparse_iolog/parse_commands/split_by_driveが読める
形)・レポート・disk2像(QZ7Bエントリ)を書くだけ。"""
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


def _sector_offset(c, h, r):
    phys = c * 2 + h
    return (D88_HEADER_SIZE + TRACK_TABLE_SIZE + phys * TRACK_BYTES
            + (r - 1) * (SECTOR_HEADER_SIZE + SECTOR_SIZE) + SECTOR_HEADER_SIZE)


def _coord_of_linear(n):
    r = n % SECTORS_PER_TRACK + 1
    phys = n // SECTORS_PER_TRACK
    c, h = divmod(phys, 2)
    return c, h, r


def _write_entry(img, name, coord, unit20):
    off = _sector_offset(*coord)
    entry = bytearray(16)
    padded = (name + " " * 9)[:9].encode("ascii")
    entry[0:9] = padded
    entry[10] = unit20
    img[off:off + 16] = entry


def main() -> int:
    argv = sys.argv[1:]
    out_path = _find(argv, "--out")
    iolog_path = _find(argv, "--io-log")
    disk1_path = _find(argv, "--disk")
    disk2_path = _find(argv, "--disk2")

    if os.environ.get("M6FD_ADD1_SELFTEST_CORRUPT_DISK1") and disk1_path:
        with open(disk1_path, "r+b") as f:
            f.seek(0)
            f.write(b"\xff")

    abort_n = int(os.environ.get("M6FD_ADD1_SELFTEST_ABORT_N", "0"))
    counter_path = os.environ.get("M6FD_ADD1_SELFTEST_ABORT_COUNTER")
    if abort_n > 0 and counter_path:
        n = 0
        if os.path.exists(counter_path):
            n = int(open(counter_path).read().strip() or "0")
        if n < abort_n:
            with open(counter_path, "w") as f:
                f.write(str(n + 1))
            return 134

    arm_hint = os.path.basename(out_path or "")
    is_e_arm = arm_hint.startswith("E-")
    drop_arms = os.environ.get("M6FD_ADD1_SELFTEST_DROP_ARMS", "").split()
    u = int(os.environ.get("M6FD_ADD1_SELFTEST_U", "3"))
    k_m = int(os.environ.get("M6FD_ADD1_SELFTEST_KM", "5"))

    if is_e_arm and disk2_path and os.path.exists(disk2_path):
        img = bytearray(open(disk2_path, "rb").read())
        _write_entry(img, "QZ7B", (18, 1, 1), 20)
        with open(disk2_path, "r+b") as f:
            f.seek(0)
            f.write(bytes(img))

    lines = []
    seq = [0]

    def ev(kind, value, frame=800):
        seq[0] += 1
        lines.append(f"{seq[0]:>6} {seq[0]:>6} {frame:>6}  sub   {kind:<4}  00FB   {value & 0xFF:02X}   0100")

    dropped = any(arm_hint.startswith(a + "-") for a in drop_arms)
    if dropped:
        lines.append("# 取りこぼし: 3件 / 総イベント数: 9件")
    elif is_e_arm:
        for i in range(u):
            c, h, r = _coord_of_linear(8 * k_m + i)
            ev("OUT", 0x45)  # WRITE DATA opcode(0x05)+MT/MFビット
            ev("OUT", 1)     # 装置番号1
            ev("OUT", c)
            ev("OUT", h)
            ev("OUT", r)
            for _ in range(4):
                ev("OUT", 0)  # N,EOT,GPL,DTLの残り4パラメータ
            for _ in range(256):
                ev("OUT", 0)  # データ部256バイト
            for _ in range(7):
                ev("IN", 0)   # 結果7バイト

    if iolog_path:
        with open(iolog_path, "w", encoding="utf-8") as f:
            f.write("# fake iolog (measure_m6fd_add1_driver_selftest)\n")
            f.write("\n".join(lines) + ("\n" if lines else ""))

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("[測定終了時のテキスト画面]\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
chmod +x "$FAKE"

mkdir -p "$WORK/rom" "$WORK/raw" "$WORK/refdisk"
printf 'FAKE-REFERENCE-DISK-FOR-SELFTEST' > "$WORK/refdisk/N88_FE.D88"

# --- (a) 陽性側: E-*→IV-fill-free、--r-star none ------------------------------
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_ADD1_SELFTEST_U=3 M6FD_ADD1_SELFTEST_KM=5 \
  "$REPO/tools/measure_m6fd_add1.sh" --raw-dir "$WORK/raw_pos" --result "$WORK/result_pos.json" \
  --r-star none \
  >"$WORK/pos.stdout.txt" 2>"$WORK/pos.stderr.txt"
pos_rc=$?
if [ "$pos_rc" -eq 0 ] && grep -q 'measurement complete' "$WORK/pos.stdout.txt"; then
  ok "(a) 陽性側: rc=0で完走した"
else
  ng "(a) 陽性側が失敗した(rc=$pos_rc): $(tail -c 400 "$WORK/pos.stderr.txt")"
fi

VERIFY="$WORK/verify_pos.py"
cat > "$VERIFY" <<'PYEOF'
import json, sys
from pathlib import Path
doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fails = []
runs = doc.get("runs", [])
e_runs = [r for r in runs if r["arm"].startswith("E-")]
if len(e_runs) != 12:
    fails.append(f"E腕の走数が想定外: {len(e_runs)}")
for r in e_runs:
    ef = r.get("entry_fields")
    if not isinstance(ef, dict) or "QZ7B" not in ef:
        fails.append(f"entry_fieldsがQZ7Bキーでない: {r['arm']} {ef!r}")
    writes = r.get("writes")
    if not isinstance(writes, list) or len(writes) != 3:
        fails.append(f"writesが想定(3件)と違う: {r['arm']} {writes!r}")
fill = [r for r in runs if r["arm"] == "IV-fill-free"]
if len(fill) != 2:
    fails.append(f"IV-fill-freeの走数が想定外: {len(fill)}")
resarm = [r for r in runs if r["arm"] == "IV-fill-res"]
if resarm:
    fails.append(f"--r-star noneなのにIV-fill-resが走った: {len(resarm)}")
if doc.get("r_star_input") is not None:
    fails.append(f"r_star_inputがnullでない: {doc.get('r_star_input')!r}")
if fails:
    for m in fails:
        print("NG: " + m)
    sys.exit(1)
print("OK: E腕writes/entry_fields・IV-fill-free・r-star none確認")
sys.exit(0)
PYEOF
if python3 "$VERIFY" "$WORK/result_pos.json"; then
  ok "(a) result.jsonの内容(writes・entry_fields・r-star none)を確認した"
else
  ng "(a) result.jsonの内容検査が失敗した"
fi

# --- (b) --r-star 0xB0 でIV-fill-resも走る ------------------------------------
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_ADD1_SELFTEST_U=2 M6FD_ADD1_SELFTEST_KM=1 \
  "$REPO/tools/measure_m6fd_add1.sh" --raw-dir "$WORK/raw_rstar" --result "$WORK/result_rstar.json" \
  --r-star 0xB0 \
  >"$WORK/rstar.stdout.txt" 2>"$WORK/rstar.stderr.txt"
rstar_rc=$?
if [ "$rstar_rc" -eq 0 ] && python3 -c "
import json
doc = json.load(open('$WORK/result_rstar.json'))
res = [r for r in doc['runs'] if r['arm'] == 'IV-fill-res']
assert len(res) == 2, res
assert doc['r_star_input'] == 0xB0, doc['r_star_input']
"; then
  ok "(b) --r-star 0xB0でIV-fill-resが2走走り、r_star_inputが記録された"
else
  ng "(b) --r-star指定時のIV-fill-resが想定と違う(rc=$rstar_rc)"
fi

# --- (c) 取りこぼし: E-*はgate_failed、IV-fill-freeは継続 --------------------
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_ADD1_SELFTEST_DROP_ARMS="E-2" \
  "$REPO/tools/measure_m6fd_add1.sh" --raw-dir "$WORK/raw_dropE" --result "$WORK/result_dropE.json" \
  --r-star none \
  >"$WORK/dropE.stdout.txt" 2>"$WORK/dropE.stderr.txt"
dropE_rc=$?
if [ "$dropE_rc" -ne 0 ] && grep -q '"reason":"run_summary_E-2_' "$WORK/dropE.stdout.txt"; then
  ok "(c) E-2の取りこぼしはgate_failedで止まった"
else
  ng "(c) E-2の取りこぼしで止まらなかった(rc=$dropE_rc): $(cat "$WORK/dropE.stdout.txt")"
fi

env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_ADD1_SELFTEST_DROP_ARMS="IV-fill-free" \
  "$REPO/tools/measure_m6fd_add1.sh" --raw-dir "$WORK/raw_dropF" --result "$WORK/result_dropF.json" \
  --r-star none \
  >"$WORK/dropF.stdout.txt" 2>"$WORK/dropF.stderr.txt"
dropF_rc=$?
if [ "$dropF_rc" -eq 0 ] && python3 -c "
import json
doc = json.load(open('$WORK/result_dropF.json'))
fill = [r for r in doc['runs'] if r['arm'] == 'IV-fill-free']
assert len(fill) == 2 and all(r['iolog_dropped'] == 3 for r in fill), fill
"; then
  ok "(c) IV-fill-freeの取りこぼしは継続し件数を記録した"
else
  ng "(c) IV-fill-freeの取りこぼし継続が想定と違う(rc=$dropF_rc)"
fi

# --- (d) G8陰性対照 ------------------------------------------------------------
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" M6FD_ADD1_SELFTEST_CORRUPT_DISK1=1 \
  "$REPO/tools/measure_m6fd_add1.sh" --raw-dir "$WORK/raw_g8" --result "$WORK/result_g8.json" \
  --r-star none \
  >"$WORK/g8.stdout.txt" 2>"$WORK/g8.stderr.txt"
g8_rc=$?
if [ "$g8_rc" -ne 0 ] && grep -q '"reason":"G8"' "$WORK/g8.stdout.txt"; then
  ok "(d) G8陰性対照: ドライブ1の書き換えをgate_failed G8として検出した"
else
  ng "(d) G8陰性対照を検出できなかった(rc=$g8_rc)"
fi

# --- (e) rc=134の回し直し -----------------------------------------------------
rm -f "$WORK/abort_counter.txt"
env \
  M6FD_FRONTEND="$FAKE" PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/refdisk" \
  M6FD_TEST_CORE="selftest-core" \
  M6FD_ADD1_SELFTEST_ABORT_N=2 M6FD_ADD1_SELFTEST_ABORT_COUNTER="$WORK/abort_counter.txt" \
  M6FD_ADD1_TEST_STOP_AFTER_ARM=E-2 \
  "$REPO/tools/measure_m6fd_add1.sh" --raw-dir "$WORK/raw_ab" --result "$WORK/result_ab.json" \
  --r-star none \
  >"$WORK/ab.stdout.txt" 2>"$WORK/ab.stderr.txt"
ab_rc=$?
if [ "$ab_rc" -eq 0 ] && [ "$(cat "$WORK/abort_counter.txt" 2>/dev/null)" = "2" ]; then
  ok "(e) rc=134を2回吸収し3回目で完走した"
else
  ng "(e) rc=134の回し直しが想定どおりでない(rc=$ab_rc)"
fi

# --- (f) --r-star none 陰性対照: IV-fill-resは走らない(既に(a)で確認済み。
#     ここでは result_pos.json の再確認としてまとめておく) ----------------------
if python3 -c "
import json
doc = json.load(open('$WORK/result_pos.json'))
assert not [r for r in doc['runs'] if r['arm'] == 'IV-fill-res']
"; then
  ok "(f) 陰性対照: --r-star noneでIV-fill-resが1件も走らない"
else
  ng "(f) 陰性対照が成立しなかった"
fi

echo
if [ "$rc" -eq 0 ]; then echo "全項目 OK"; else echo "NG あり"; fi
exit "$rc"

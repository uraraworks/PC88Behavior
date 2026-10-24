#!/usr/bin/env bash
# 起動用セクタのコード生成器 (tools/b2_make_boot_probe.py) と読み出しの白リスト
# (tools/b2_extract_boot_probe.py) の自己検査。公式 ROM・公式ディスクは一切使わない。
#
# 追補1 (docs/notes/goal-b-policy-addendum1-boot-sector-2026-10-24.md) 第6節の3:
# 「自作コードが自分の番地・レジスタを正しく書き残すことを、公式 ROM を使わず
#  自作 ROM の検査用の起動で確かめる。陰性対照つき」。
#
# 試験 ROM (make_b2_probe_test_rom.py) が生成器のセクタ像を RAM の既知の番地 X へ写し、
# 既知のレジスタ・既知の SP・既知の戻り先で CALL する。その書き込み記録を抽出器に通し、
# 期待値（試験 ROM を作る側の仕様から決めたもの。コアの出力から写さない）と照合する。
#
#   判定:
#     J_base      自分の番地が三者（発行元PCから逆算・控えの自己申告・控えの置き場）で X に一致
#     J_regs      AF BC DE HL IX IY・入口の SP・割り込みの許可状態・I レジスタが一致
#     J_ret       スタックの先頭2バイト（戻り先）が RETLAND に一致
#     J_markers   目印8個の一致ビット（一部わざと壊した・置かなかった）が期待どおり
#     J_romrange  ROM が書いた番地の範囲と件数が、試験 ROM の仕様から数えた期待に一致
#     J_whitelist 出力が白リストの書式だけで、ROM が上書きした値（デコイ）が出ない
#     J_ramother  自作コードのうち控え以外への書き込み（スタック積み込み）の件数が実行器の予測に一致
#     J_equiv     自作コードの全書き込み (番地,値) が、最小実行器の予測と一致
#     J_restore   RET の腕: 戻ったあとのレジスタ・SP が入口と同じ（ROM が書いた値で照合）
#     J_halted    止まる腕: 戻らない（完了印が無い）
#   腕: ret / halt / dihalt、X は 0xC000・0xB123（ページ境界またぎ・非整列）・0x9A00、
#       入口オフセットは 0・5・17、割り込みの許可状態は EI / DI の両方。
#   陰性対照: 別の番地へ置いた（CALL が外れる）→ 抽出器は no_record を返す。
#   故障注入（壊した走の FAIL の集合が、事前に決めた集合と一致するまで合格にしない）:
#     F1 自分の番地の計算を壊す(--fault-base-off)         期待 FAIL = {J_base}
#     F2 控えの順序を入れ替える(--fault-swap-order)        期待 FAIL = {J_regs}
#     F3 ROM の書き込みの値を抽出器に通す(B2X_FAULT_...)   期待 FAIL = {J_regs, J_whitelist}
#        (デコイは BC・DE の置き場を上書きするので J_regs も落ちる。J_whitelist が狙い)
#   生成器の検査: 範囲外の読み出し(--fault-oob-read)・戻り先の奥の読み出し
#     (--fault-stack-overread) を組み込んだコードは、組み立て時の検査が止める(rc=4)。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
GEN="$REPO/tools/b2_make_boot_probe.py"
EXTRACT="$REPO/tools/b2_extract_boot_probe.py"
MAKE_ROM="$REPO/tools/harness/make_b2_probe_test_rom.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-b2probe.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

# 私物のパスは受け取らない（この検査は公式 ROM・公式ディスクを使わない）
unset PC88_REF_ROM_DIR PC88_REF_DISK_DIR PC88_REF_DISKB PC88_GAME_DIR

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"
make -s -C "$FRONTEND_DIR"

# ---- 判定器 -------------------------------------------------------------
cat > "$WORK/judge.py" <<'PYEOF'
import json, pathlib, re, sys
REPO = pathlib.Path(sys.argv[1])
case = pathlib.Path(sys.argv[2])
mode = sys.argv[3]            # normal / norecord
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "harness"))
import b2_make_boot_probe as gen
import make_b2_probe_test_rom as mk

exp = json.loads((case / "e.json").read_text())
lay = json.loads((case / "l.json").read_text())
sector = (case / "s.bin").read_bytes()
out = (case / "ex.txt").read_text()
rc = int((case / "ex.rc").read_text())
X = exp["place_addr"]
res = {}

if mode == "norecord":
    res["J_norecord"] = (rc == 3 and "found=no" in out)
    # ROM が別の RAM 番地へ写して走らせたコードの書き込みの値は、出力に出てはならない
    res["J_noleak"] = not (exp["decoy_word"] is not None and exp["decoy_text"] in out)
    for k, v in res.items():
        print(("PASS " if v else "FAIL ") + k)
    sys.exit(0)

def f(pat, default=None):
    m = re.search(pat, out)
    return m.group(1) if m else default

# J_base
bt, br = f(r"base_true=(\w+)"), f(r"base_reported=(\w+)")
res["J_base"] = (bt == f"{X:04X}" and br == f"{X:04X}" and "consistent=yes" in out and rc == 0)

# J_regs
m = re.search(r"regs: AF=(\w+) BC=(\w+) DE=(\w+) HL=(\w+) IX=(\w+) IY=(\w+) SP=(\w+)", out)
R = exp["regs"]
want = [R["AF"], R["BC"], R["DE"], R["HL"], R["IX"], R["IY"], exp["sp_entry"]]
got = [int(g, 16) for g in m.groups()] if m and "-" not in "".join(m.groups()) else None
ok_regs = (got == want)
mi = re.search(r"intr: iff2=(\d) i=(\w+)", out)
ok_regs = ok_regs and bool(mi) and int(mi.group(1)) == exp["iff2"] and int(mi.group(2), 16) == exp["i_reg"]
res["J_regs"] = ok_regs

# J_ret
res["J_ret"] = (f(r"ret=(\w+)") == f"{exp['ret_addr']:04X}")

# J_markers
mm = re.search(r"markers: (.*)", out)
masks = [int(t.split("=")[1], 16) for t in mm.group(1).split()] if mm and "-" not in mm.group(1) else None
res["J_markers"] = (masks == exp["markers"])

# J_romrange
cnt = {}
for a in exp["rom_events"]:
    cnt[a] = cnt.get(a, 0) + 1
rng = []
for a in sorted(cnt):
    if rng and a == rng[-1][1] + 1:
        rng[-1][1] = a; rng[-1][2] += cnt[a]
    else:
        rng.append([a, a, cnt[a]])
want_lines = [f"  rom_range {lo:04X}-{hi:04X} rows={n}" for lo, hi, n in rng]
got_lines = [l for l in out.splitlines() if l.startswith("  rom_range")]
res["J_romrange"] = (got_lines == want_lines
                     and f(r"rom_pc_writes: rows=(\d+)") == str(len(exp["rom_events"])))

# J_whitelist
allowed = [r"^# b2_extract", r"^rows_total=\d+ unparsed_rows=\d+$", r"^rom_pc_writes: rows=\d+ ranges=\d+$",
           r"^  rom_range [0-9A-F]{4}-[0-9A-F]{4} rows=\d+$", r"^ram_pc_other_writes: rows=\d+$",
           r"^probe: found=", r"^base_true=", r"^regs: ", r"^intr: ", r"^ret=", r"^markers: "]
fmt_ok = all(any(re.match(p, l) for p in allowed) for l in out.splitlines())
leak = exp["decoy_word"] is not None and exp["decoy_text"] in out
res["J_whitelist"] = fmt_ok and not leak

# 生の記録（試験 ROM と自作コードの書き込み。この検査は自作だけなので値を読んでよい）
rows = []
for line in (case / "mwl.txt").read_text().splitlines():
    t = line.split()
    if len(t) == 5 and t[0].isdigit():
        rows.append((int(t[0]), int(t[2], 16), int(t[3], 16), int(t[4], 16)))
ram_rows = [(a, v, pc) for _, pc, a, v in rows if pc >= 0x8000]

# 実行器の予測（試験 ROM が作ったのと同じメモリ像・同じレジスタ・同じ戻り先）
mem = bytearray(65536)
mem[X:X + 256] = sector
for k in range(1, lay["k_markers"] + 1):
    mb = mk.marker_bytes(k, exp["marker_mode"])
    if mb is not None:
        mem[X + 256 * k: X + 256 * k + 4] = mb
regs = dict(exp["regs"])
sim, _ = gen.run_probe_sim(sector, lay, X, None, 0, regs, exp["iff2"], exp["i_reg"], exp["sp_entry"],
                           exp["ret_addr"], start_off=0, check=False, mem_init=mem)
store_pcs = {s["pc"] for s in lay["stores"]}
f2_addr = X + lay["rec_off"] + lay["fields"]["F2"][0]
sim_rows = [(a, v, pc) for a, v, pc in sim.writes]
other_pred = sum(1 for a, v, pc in sim_rows if (pc - X) not in store_pcs)
res["J_ramother"] = (f(r"ram_pc_other_writes: rows=(\d+)") == str(other_pred))
eq = len(ram_rows) == len(sim_rows)
if eq:
    for (a, v, pc), (sa, sv, spc) in zip(ram_rows, sim_rows):
        if a != sa or pc != spc:
            eq = False; break
        if a == f2_addr:
            if (v & 0x04) != (sv & 0x04): eq = False; break
        elif v != sv:
            eq = False; break
res["J_equiv"] = eq

# J_restore / J_halted
r2 = exp["r2"]
rom_w = {}
for _, pc, a, v in rows:
    if pc < 0x8000:
        rom_w[a] = v
def w16(a): return rom_w.get(a, -1) | (rom_w.get(a + 1, -1) << 8) if a in rom_w and a + 1 in rom_w else None
if exp["arm"] == "ret":
    want = [R["AF"], R["BC"], R["DE"], R["HL"], R["IX"], R["IY"], exp["sp_entry"] + 2]
    # 並び: AF BC DE HL IX IY SP。試験 ROM は HL@+0 DE@+2 BC@+4 IX@+6 IY@+8 AF@+10 SP@+12 に書く
    got = [w16(r2 + 10), w16(r2 + 4), w16(r2 + 2), w16(r2), w16(r2 + 6), w16(r2 + 8), w16(r2 + 12)]
    res["J_restore"] = (got == want and rom_w.get(r2 + 14) == 0xA5)
else:
    res["J_halted"] = (r2 + 14) not in rom_w

for k, v in res.items():
    print(("PASS " if v else "FAIL ") + k)
PYEOF

# ---- 1ケース: 生成 → 試験ROM → 実行 → 抽出 → 判定 ----------------------------
# run_case NAME ARM LOAD ENTRY IFF MARKERS DECOY PLACE MODE EXFAULT GENFAULT...
run_case() {
  local name="$1" arm="$2" load="$3" entry="$4" iff="$5" markers="$6" decoy="$7" place="$8" mode="$9" exfault="${10}"
  shift 10
  local d="$WORK/$name"
  mkdir -p "$d"
  python3 "$GEN" --arm "$arm" --load-addr "$load" --entry-offset "$entry" \
      --out-sector "$d/s.bin" --out-layout "$d/l.json" "$@" >"$d/gen.out" 2>"$d/gen.err" \
    || { cat "$d/gen.err" >&2; ng "$name: 生成器が失敗した"; }
  local extra=()
  [ "$decoy" = 1 ] && extra+=(--decoy)
  [ "$place" != "-" ] && extra+=(--place-addr "$place")
  [ -n "${MIMIC:-}" ] && extra+=(--mimic-base "$MIMIC")
  if [ "$mode" = norecord ]; then
    local trap
    trap="$(python3 -c "import json;l=json.load(open('$d/l.json'));print(l['load_addr']+l['here_sector_off'])")"
    extra+=(--trap-at "$trap")
  fi
  python3 "$MAKE_ROM" "$d/rom" --probe-sector "$d/s.bin" --layout "$d/l.json" --expected "$d/e.json" \
      --iff "$iff" --markers "$markers" ${extra[@]+"${extra[@]}"} >"$d/rom.out" \
    || ng "$name: 試験ROMの生成に失敗した"
  "$FRONTEND" --core "$CORE" --rom-dir "$d/rom" --frames 6 --out "$d/trace.txt" \
      --mem-write-log "$d/mwl.txt" --mem-write-range 8000-FFFF >"$d/run.out" 2>"$d/run.err" \
    || { cat "$d/run.err" >&2; ng "$name: 走りが失敗した"; }
  grep -q '取りこぼし: 0件' "$d/mwl.txt" || ng "$name: 取りこぼしが0件でない"
  local rc=0
  if [ -n "$exfault" ]; then
    B2X_FAULT_TRUST_ROM_WRITES=1 python3 "$EXTRACT" --log "$d/mwl.txt" --layout "$d/l.json" >"$d/ex.txt" 2>"$d/ex.err" || rc=$?
  else
    python3 "$EXTRACT" --log "$d/mwl.txt" --layout "$d/l.json" >"$d/ex.txt" 2>"$d/ex.err" || rc=$?
  fi
  echo "$rc" > "$d/ex.rc"
  python3 "$WORK/judge.py" "$REPO" "$d" "$mode" > "$d/judge.txt" || { cat "$d/judge.txt"; ng "$name: 判定器が失敗した"; }
}

# expect_fails NAME "J_a J_b"  ——  FAIL の集合が期待と完全に一致すること
expect_fails() {
  local name="$1" want="$2" got
  # grep は一致が無いと rc=1。pipefail + set -e で黙って死なないよう || true を付ける
  got="$( { grep '^FAIL ' "$WORK/$name/judge.txt" || true; } | awk '{print $2}' | sort | tr '\n' ' ' | sed 's/ $//')"
  want="$(printf '%s\n' $want | sort | tr '\n' ' ' | sed 's/ $//')"
  if [ "$got" != "$want" ]; then
    cat "$WORK/$name/judge.txt" >&2
    ng "$name: FAIL の集合が期待と違う（実際='$got' 期待='$want'）"
  fi
}
npass() { grep -c '^PASS ' "$WORK/$1/judge.txt" || true; }

# ===== 正常な走（FAIL は1つも無い）=====
run_case A ret    0xC000 0  1 std  1 -      normal ""
expect_fails A ""
ok "A: ret 腕 / X=C000 / 入口0 / EI / デコイあり → 判定$(npass A)項目すべて合格（番地・レジスタ・戻り先・目印・ROM範囲・白リスト・予測一致・復元）"

run_case B halt   0xB123 5  0  std  0 -      normal ""
expect_fails B ""
ok "B: halt 腕 / X=B123（非整列・ページまたぎ）/ 入口5 / DI → 判定$(npass B)項目すべて合格（IFF2=0 を控えた）"

run_case C dihalt 0x9A00 17 1  all 0 -      normal ""
expect_fails C ""
ok "C: dihalt 腕 / X=9A00 / 入口17 / EI / 目印全部あり → 判定$(npass C)項目すべて合格（IFF2=1 を DI より前に控えた）"

# 自分の番地の検出が X に追従することは、A/B/C の J_base（X=C000/B123/9A00）で確かめた。
# 目印が全部合う走で全マスクが F になること
grep -q '^markers: k1=F k2=F k3=F k4=F k5=F k6=F k7=F k8=F$' "$WORK/C/ex.txt" \
  || ng "C: 目印が全部ある走で全マスクが F にならない"
ok "目印: 壊した・置かなかった目印は一致ビットが減り（A/B の期待マスク）、全部ある走は F×8（C）"

# --near: 読み込み先の窓に重なる ROM 書き込みの範囲を上限なしで先に出す
python3 "$EXTRACT" --log "$WORK/A/mwl.txt" --layout "$WORK/A/l.json" --near C000-C0FF > "$WORK/A/near.txt" || true
grep -q '^  rom_range_near C000-C103 rows=264$' "$WORK/A/near.txt" || ng "A: --near で読み込み先の範囲が先に出ない"
ok "--near: 読み込み先の窓に重なる ROM 書き込みの範囲（C000-C103）を rom_range_near として出す"

# 陰性対照: 別の番地へ置く（CALL のオペランドは 0xC000 基準のまま）→ no_record
run_case N1 ret   0xC000 0  1  std 0 0xA000 norecord ""
expect_fails N1 ""
grep -q 'found=no' "$WORK/N1/ex.txt" || ng "N1: no_record にならない"
ok "N1(陰性対照): 組んだ番地と別の番地に置くと、抽出器は no_record(rc=3) を返し、控えを捏造しない"

# 陰性対照2: ROM が別の RAM 番地 (A400) へ控えを真似るコードを写して走らせる。プローブ本体は
# 外れた番地に置かれ実行されない。真似たコードの書き込みは発行元 PC が RAM 上なので、
# 「RAM 上の PC ならすべて自作コード」とする抽出器は値(7E7E)を控えとして出してしまう。
MIMIC=0xA400 run_case M1 ret   0xC000 0  1  std 0 0xA000 norecord ""
expect_fails M1 ""
grep -q 'found=no' "$WORK/M1/ex.txt" || ng "M1: ROM が置いた RAM 上のコードの書き込みから控えを作ってしまう"
ok "M1(陰性対照): ROM が別の RAM 番地へ写して走らせたコードが目印の値を書いても、抽出器は no_record で値を出さない"

# ===== 故障注入 =====
run_case F1 ret   0xC000 0  1  std 1 -      normal "" --fault-base-off
expect_fails F1 "J_base"
ok "F1(故障注入): 自分の番地の申告を +1 にすると J_base だけが FAIL（三者照合が食い違いを検出）"

run_case F2 halt  0xB123 5  1  std 0 -      normal "" --fault-swap-order
expect_fails F2 "J_regs"
ok "F2(故障注入): BC と DE を積む順を入れ替えると J_regs だけが FAIL"

run_case F3 ret   0xC000 0  1  std 1 -      normal "1"
expect_fails F3 "J_regs J_whitelist"
ok "F3(故障注入): ROM の書き込みを抽出器に通すと J_whitelist と J_regs が FAIL（白リストが ROM の値を締め出している証拠）"

# ===== 生成器の組み立て時検査 =====
for flt in oob-read stack-overread; do
  rc=0
  python3 "$GEN" --arm ret --load-addr 0xC000 --fault-"$flt" --out-sector "$WORK/v_$flt.bin" \
      >"$WORK/v_$flt.out" 2>"$WORK/v_$flt.err" || rc=$?
  [ "$rc" = 4 ] || ng "生成器: --fault-$flt を止めない(rc=$rc)"
  grep -q '許可範囲外の読み出し' "$WORK/v_$flt.err" || ng "生成器: --fault-$flt の止まった理由が読み出しの検査でない"
  [ ! -e "$WORK/v_$flt.bin" ] || ng "生成器: --fault-$flt でファイルを出した"
done
ok "生成器: 範囲外の読み出し・戻り先の奥の読み出しを含むコードは、組み立て時の検査が止めてファイルを出さない(rc=4)"

# 許可していない命令（LD A,(HL) など）は実行器が受け付けない（語彙の制限）
python3 - "$REPO" <<'PYEOF' || ng "語彙の制限の検査に失敗した"
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import b2_make_boot_probe as g
bad = {"LD A,(HL)": b"\x7e", "LDIR": b"\xed\xb0", "LD A,(nn)": b"\x3a\x00\xc0",
       "EX (SP),HL": b"\xe3", "LD A,(BC)": b"\x0a", "LD A,(DE)": b"\x1a"}
for name, code in bad.items():
    mem = bytearray(65536); mem[0x8000:0x8000 + len(code)] = code
    s = g.Z80Mini(mem); s.pc = 0x8000; s.sp = 0xF000
    try:
        s.step()
    except g.Unsupported:
        continue
    sys.exit(f"{name} が通ってしまった")
PYEOF
ok "生成器の語彙: LD A,(HL)・LD A,(BC)・LD A,(DE)・LD A,(nn)・LDIR・EX (SP),HL は実行器が受け付けない"

ok "全項目合格"

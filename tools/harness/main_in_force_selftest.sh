#!/usr/bin/env bash
# main CPU の IN の返り値の1ビット強制(--main-in-force、パッチ 0017)の自己検査。
# 公式 ROM・公式ディスクは一切使わない。make_main_in_force_rom.py の自作試験 ROM
# (IN A,(40h) を64回読み、値を OUT (99h) へ出す)で、--io-log の main IN 40 列と
# OUT 99 列を見る。OUT 列は「CPU が実際に受け取った値」の独立した写しなので、
# 記録だけが書き換わって CPU には届いていない故障を検出できる。
#
#   P1 陽性: 強制した方向で bit が常に 1/0、他ビットは介入なしの走と同じ。
#            changed は介入なし列から数えた期待値と一致。変動ビット(実走から選ぶ)でも同様。
#   N1 空の介入: 元と同じ値を強制 → matched>0, changed=0, main 節が介入なしと完全一致。
#   N2 別ポート: 0x31 を強制 → matched=0, changed=0, main 節が不変。
#   N3 未指定: 介入なしの走で、0017 版コアと vendor コアの iolog(main・sub)が一致。
#   故障注入: 期待値の反転 / 記録値の1件書き換え / N1 を反対値の走に当てる、で
#            狙った判定だけが FAIL すること(手前の別判定で落ちたものは数えない)。
#
# 環境変数 Q88_CORE: 0017 入りコアの dylib。既定は vendor のコア。
# 0017 が入っていなければ rc=77 (SKIP ではなく「0017 未適用」と明示)。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-mif.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

VCORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$VCORE" ] || ng "vendor のコア成果物が無い。先に tools/setup_harness.sh を実行すること"
CORE="${Q88_CORE:-$VCORE}"
[ -f "$CORE" ] || ng "Q88_CORE が無い: $CORE"
SYMS="$(nm -g "$CORE" 2>/dev/null || true)"
if ! grep -q retro_q88h_main_in_force_configure <<<"$SYMS"; then
  echo "0017 未適用: $CORE に retro_q88h_main_in_force_configure が無い。" \
       "Q88_CORE に 0017 入りコアを指定すること" >&2
  exit 77
fi
make -s -C "$FRONTEND_DIR"

mkdir -p "$WORK/rom"
python3 "$REPO/tools/harness/make_main_in_force_rom.py" "$WORK/rom"

FRAMES=90
run() {  # run <core> <tag> [opts...]
  local core="$1" tag="$2"; shift 2
  "$FRONTEND" --core "$core" --rom-dir "$WORK/rom" --frames "$FRAMES" \
    --out "$WORK/trace-$tag.txt" --io-log "$WORK/io-$tag.txt" "$@" \
    >"$WORK/$tag.stdout" 2>"$WORK/$tag.stderr" \
    || { cat "$WORK/$tag.stderr" >&2; ng "走りが失敗した: $tag"; }
}

cat > "$WORK/judge.py" <<'PYEOF'
import re, sys

W, MODE = sys.argv[1], sys.argv[2]

def section(path, name):
    out, on = [], False
    for ln in open(path, encoding="utf-8"):
        s = ln.rstrip("\n")
        if s.startswith("# ") and s[2:] in ("main", "sub"):
            on = (s[2:] == name); continue
        if on and s.strip() and not s.startswith("#"): out.append(s)
    return out

def col(lines, kind, port):
    r = []
    for s in lines:
        f = s.split()
        if len(f) >= 8 and f[4] == kind and int(f[5], 16) == port:
            r.append(int(f[6], 16))
    return r

def stat(tag):
    for ln in open(f"{W}/{tag}.stderr", encoding="utf-8"):
        m = re.search(r"main-in-force slot=0 port=(\w+) bit=(\d) value=(\d) matched=(\d+) changed=(\d+)", ln)
        if m: return int(m[4]), int(m[5])
    return None

base_main = section(f"{W}/io-base.txt", "main")
base_sub = section(f"{W}/io-base.txt", "sub")
B = col(base_main, "IN", 0x40)
assert len(B) == 64, len(B)
const_bits = [b for b in range(8) if len({(v >> b) & 1 for v in B}) == 1]
var_bits = [b for b in range(8) if len({(v >> b) & 1 for v in B}) == 2]

if MODE == "pick":
    if not const_bits or not var_bits:
        print("NONE"); sys.exit(0)
    cb = const_bits[0]
    print(cb, (B[0] >> cb) & 1, var_bits[0])
    sys.exit(0)

cb, cv, vb = (int(x) for x in sys.argv[3:6])

def apply(v, bit, val):
    return (v | (1 << bit)) if val else (v & ~(1 << bit) & 0xFF)

def runlog(tag):
    m = section(f"{W}/io-{tag}.txt", "main")
    return m, col(m, "IN", 0x40), col(m, "OUT", 0x99)

def p1(tag, bit, val, invert=False, tamper=False):
    m, i40, o99 = runlog(tag)
    if tamper: i40 = i40[:]; i40[10] ^= 1 << bit
    exp = [apply(v, bit, val ^ 1 if invert else val) for v in B]
    nchg = sum(1 for v in B if apply(v, bit, val) != v)
    st = stat(tag)
    return {"P1 IN列=期待(bit強制・他ビット不変)": i40 == exp,
            "P1 OUT列(CPU受取値)=IN列": o99 == i40,
            "P1 matched=64": st is not None and st[0] == 64,
            "P1 changed=期待": st is not None and st[1] == nchg,
            "P1 sub節が不変": section(f"{W}/io-{tag}.txt", "sub") == base_sub}, nchg

def n1(tag):
    m, i40, o99 = runlog(tag); st = stat(tag)
    return {"N1 matched>0": st is not None and st[0] > 0,
            "N1 changed=0": st is not None and st[1] == 0,
            "N1 main節が介入なしと完全一致": m == base_main}

def n2(tag):
    m, i40, o99 = runlog(tag); st = stat(tag)
    return {"N2 matched=0": st is not None and st[0] == 0,
            "N2 changed=0": st is not None and st[1] == 0,
            "N2 IN40列が不変": i40 == B,
            "N2 main節が介入なしと完全一致": m == base_main}

def n3():
    return {"N3 介入なし2走が一致(決定性)": section(f"{W}/io-base2.txt", "main") == base_main
                                          and section(f"{W}/io-base2.txt", "sub") == base_sub,
            "N3 0017版=vendor版 main": section(f"{W}/io-vbase.txt", "main") == base_main,
            "N3 0017版=vendor版 sub": section(f"{W}/io-vbase.txt", "sub") == base_sub}

def show(d):
    bad = []
    for k, v in d.items():
        print(("PASS " if v else "FAIL ") + k)
        if not v: bad.append(k)
    return bad

if MODE == "real":
    bad = []
    for tag, bit, val in (("f1", 3, 1), ("f0", 3, 0), ("v1", vb, 1), ("v0", vb, 0)):
        print(f"-- P1 {tag}: bit{bit}->{val}")
        d, n = p1(tag, bit, val); bad += show(d)
        print(f"   (changed期待={n})")
        if tag in ("v1", "v0"):
            bad += show({f"P1 {tag}: 変動ビットで 0<changed<64": 0 < n < 64})
    # bit3 の2方向のうち少なくとも一方は実際に値を変える
    n_f1 = p1("f1", 3, 1)[1]; n_f0 = p1("f0", 3, 0)[1]
    bad += show({"P1 bit3強制で changed>0 になる方向がある": n_f1 + n_f0 > 0})
    print(f"-- N1 定数ビット bit{cb}={cv} を同値で強制"); bad += show(n1("same"))
    print(f"-- P1 定数ビット bit{cb} を反対値({cv ^ 1})で強制")
    d, n = p1("opp", cb, cv ^ 1); bad += show(d)
    bad += show({"P1 反対値は全64件で changed": n == 64})
    print("-- N2 別ポート 0x31"); bad += show(n2("p31"))
    print("-- N3 未指定"); bad += show(n3())
    sys.exit(1 if bad else 0)

# ---- 故障注入: 狙った判定"だけ"が落ちること --------------------------------
FAULTS = {
  "invert":  (lambda: p1("f1", 3, 1, invert=True)[0], {"P1 IN列=期待(bit強制・他ビット不変)"}),
  "tamper":  (lambda: p1("v1", vb, 1, tamper=True)[0], {"P1 IN列=期待(bit強制・他ビット不変)", "P1 OUT列(CPU受取値)=IN列"}),
  "n1_opp":  (lambda: n1("opp"), {"N1 changed=0", "N1 main節が介入なしと完全一致"}),
  "n2_on40": (lambda: n2("v1"), {"N2 matched=0", "N2 changed=0", "N2 IN40列が不変", "N2 main節が介入なしと完全一致"}),
}
d, expect = FAULTS[MODE]
d = d()
bad = {k for k, v in d.items() if not v}
print(f"fault {MODE}: FAIL={sorted(bad)}")
sys.exit(0 if bad == expect else 1)
PYEOF

# ---- 実走 ----
run "$CORE" base
run "$CORE" base2
run "$VCORE" vbase
PICK="$(python3 "$WORK/judge.py" "$WORK" pick)"
[ "$PICK" != NONE ] || ng "介入なし列に定数ビットか変動ビットが無く、検査が成立しない"
read -r CB CV VB <<<"$PICK"
echo "選んだビット: 定数 bit$CB(値$CV) / 変動 bit$VB"
run "$CORE" f1   --main-in-force 0x40:3:1
run "$CORE" f0   --main-in-force 0x40:3:0
run "$CORE" v1   --main-in-force "0x40:$VB:1"
run "$CORE" v0   --main-in-force "0x40:$VB:0"
run "$CORE" same --main-in-force "0x40:$CB:$CV"
run "$CORE" opp  --main-in-force "0x40:$CB:$((CV ^ 1))"
run "$CORE" p31  --main-in-force 0x31:3:1

if python3 "$WORK/judge.py" "$WORK" real "$CB" "$CV" "$VB"; then
  ok "P1/N1/N2/N3 全判定 PASS"
else
  ng "実走の判定に FAIL がある"
fi

for f in invert tamper n1_opp n2_on40; do
  if python3 "$WORK/judge.py" "$WORK" "$f" "$CB" "$CV" "$VB"; then
    ok "故障注入 $f: 狙った判定だけが FAIL した"
  else
    ng "故障注入 $f: 期待した FAIL の集合と一致しない(検出力が無い)"
  fi
done

# ---- フロントエンドの引数検査(範囲外は rc=2) ----
for bad in 0x40:8:1 0x40:3:2 0x100:3:1 0x40:3 abc; do
  if "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 2 --out "$WORK/t.txt" \
       --main-in-force "$bad" >/dev/null 2>&1; then
    ng "不正な指定 $bad が受理された"
  fi
done
ok "不正な --main-in-force 指定は全て拒否された"

echo "main_in_force_selftest: 全て OK"

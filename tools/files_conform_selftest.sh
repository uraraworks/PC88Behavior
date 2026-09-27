#!/usr/bin/env bash
# FILES適合器の合成観測・偽フロントエンド自己検査（公式環境は使わない）。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/files-conform-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
EXPECTED="$REPO/tools/files_conform_expected.tsv"
CANARY="FILES_SCREEN_LEAK_91C7A5"

ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }
ok() { printf 'OK: %s\n' "$1"; }

mkdir "$WORK/rom"
printf 'selftest\n' >"$WORK/rom/N88.ROM"

# リポジトリの期待値から、観測JSONと同じ許可リスト構造だけを合成する。
# 画面本文は作らない。抽出結果が固定TSVと同一になること、および2走不一致を
# 拒否することを確かめる。
python3 - "$REPO" "$EXPECTED" "$WORK" <<'PY'
import copy, json, pathlib, sys
repo, expected, work = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
sys.path.insert(0, str(repo / "tools"))
import files_conform_check as check
import extract_files_conform_expected as extract
values = check.load_expected(expected)
groups = (
    ("m6fe-observations-v1", extract.BASE_ARMS, "base.json"),
    ("m6fe-add2-observations-v1", extract.ADD2_ARMS, "add2.json"),
    ("m6fe-add3-observations-v1", extract.ADD3_ARMS, "add3.json"),
)
for fmt, arms, name in groups:
    arm_values = {}
    for arm in arms:
        lines = [{"physical_row": row, "char_count": count, "sha256": digest}
                 for row, count, digest in values[arm]]
        arm_values[arm] = [{"entry_lines": copy.deepcopy(lines)},
                           {"entry_lines": copy.deepcopy(lines)}]
    (work / name).write_text(json.dumps({"format": fmt, "arms": arm_values},
                                        sort_keys=True, separators=(",", ":")), encoding="ascii")
broken = json.loads((work / "base.json").read_text(encoding="ascii"))
broken["arms"]["L1"][1]["entry_lines"][0]["sha256"] = "0" * 64
(work / "base-broken.json").write_text(json.dumps(broken, sort_keys=True,
                                                   separators=(",", ":")), encoding="ascii")
PY
python3 "$REPO/tools/extract_files_conform_expected.py" \
  "$WORK/base.json" "$WORK/add2.json" "$WORK/add3.json" "$WORK/extracted.tsv" \
  >"$WORK/extract.out" 2>"$WORK/extract.err" || ng "合成観測の抽出に失敗"
cmp -s "$EXPECTED" "$WORK/extracted.tsv" || ng "合成観測の抽出結果が固定値と不一致"
ok "2走一致の行署名だけを固定TSVへ抽出"
if python3 "$REPO/tools/extract_files_conform_expected.py" \
    "$WORK/base-broken.json" "$WORK/add2.json" "$WORK/add3.json" "$WORK/rejected.tsv" \
    >"$WORK/reject.out" 2>"$WORK/reject.err"; then
  ng "2走不一致を受理した"
fi
ok "陰性対照: 2走不一致を拒否"

# q88measureと同じ署名reportだけを書く偽フロントエンド。合成本文は漏えい
# 目印を含む入力待ち行だけだが、メモリ内で直ちにSHA-256化する。
cat >"$WORK/fake_frontend.py" <<'PY'
#!/usr/bin/env python3
import hashlib, os, pathlib, sys

args = sys.argv[1:]
def option(name):
    try: return args[args.index(name) + 1]
    except (ValueError, IndexError): raise SystemExit(2)

arm = os.environ["FILES_CONFORM_ARM"]
source = pathlib.Path(os.environ.get("FILES_FAKE_SOURCE_EXPECTED",
                                     os.environ["FILES_CONFORM_EXPECTED_FOR_FAKE"]))
out = pathlib.Path(option("--out"))
rows = []
active = None
for raw in source.read_text(encoding="ascii").splitlines()[2:]:
    f = raw.split("\t")
    if f[0] == "arm": active = f[1]
    elif f[0] == "row" and active == arm:
        rows.append((int(f[3]), int(f[4]), f[5]))
bad = set(os.environ.get("FILES_FAKE_BAD_ARMS", "").split())
if arm in bad:
    if rows:
        row, count, digest = rows[0]
        rows[0] = (row, count, ("0" if digest[0] != "0" else "1") + digest[1:])
    else:
        rows.append((0, 1, "0" * 64))
prompt_row = (max((row for row, _, _ in rows), default=-1) + 1)
canary = os.environ.get("FILES_FAKE_CANARY", "synthetic")
encoded = f"{prompt_row}\t{canary}\n".encode("utf-8")
final = rows + [(prompt_row, len(canary), hashlib.sha256(encoded).hexdigest()),
                (19, 1, "1" * 64)]

def snapshot(name, values):
    result = [f"snapshot_id\t{name}", "physical_row\tchar_count\tsha256"]
    result += [f"{row}\t{count}\t{digest}" for row, count, digest in sorted(values)]
    result += [f"line_count\t{len(values)}",
               f"char_count\t{sum(value[1] for value in values)}", f"sha256\t{'2' * 64}"]
    return result
baseline = [(0, 1, "3" * 64), (19, 1, "1" * 64)]
records = snapshot("baseline", baseline) + snapshot("final", final) + snapshot("late", final)
if "--screen-signature-at" in args and "preinsert:1100" in args:
    records += snapshot("preinsert", baseline)
out.write_text("\n".join(records) + "\n", encoding="ascii")
log = os.environ.get("FILES_FAKE_CALL_LOG")
if log:
    flags = [arm, pathlib.Path(option("--disk")).name,
             "insert" if "--insert-disk2" in args else "disk2",
             "swap" if "--swap-disk1" in args else "noswap"]
    with open(log, "a", encoding="ascii") as target: target.write("\t".join(flags) + "\n")
PY
chmod +x "$WORK/fake_frontend.py"

run_fake() {
  local name="$1" expected="$2" bad_arms="$3" rc=0
  FILES_CONFORM_FRONTEND="$WORK/fake_frontend.py" FILES_CONFORM_CORE=dummy \
    FILES_CONFORM_TEST_ROM_DIR="$WORK/rom" FILES_CONFORM_EXPECTED="$expected" \
    FILES_FAKE_SOURCE_EXPECTED="$EXPECTED" FILES_FAKE_BAD_ARMS="$bad_arms" \
    FILES_FAKE_CANARY="$CANARY" FILES_FAKE_CALL_LOG="$WORK/$name.calls" \
    PC88_FILES_CONFORM_WORK="$WORK/$name.work" \
    bash "$REPO/tools/conform_files.sh" >"$WORK/$name.out" 2>"$WORK/$name.err" || rc=$?
  printf '%s' "$rc"
}

rc="$(run_fake all-ok "$EXPECTED" "")"
[ "$rc" -eq 0 ] || ng "偽フロントエンド正例が失敗"
[ "$(awk -F '\t' '$2=="OK"{n++} END{print n+0}' "$WORK/all-ok.out")" -eq 24 ] \
  || ng "全腕OK集合が不正"
[ "$(wc -l <"$WORK/all-ok.calls" | tr -d ' ')" -eq 24 ] || ng "起動腕数が不正"
awk -F '\t' '$1 ~ /^D-|^E-/ && $4 != "noswap" {exit 1}
             $1 == "N-wait" && $3 != "insert" {exit 1}' "$WORK/all-ok.calls" \
  || ng "D/Eの最初からD1またはN-wait挿入手順が不正"
ok "偽フロントエンドで全24腕OK、媒体操作も所定どおり"

cp "$EXPECTED" "$WORK/one-broken.tsv"
python3 - "$WORK/one-broken.tsv" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); lines = p.read_text(encoding="ascii").splitlines()
for i, line in enumerate(lines):
    if line.startswith("row\tL1\t"):
        f=line.split("\t"); f[5] = ("0" if f[5][0] != "0" else "1") + f[5][1:]
        lines[i]="\t".join(f); break
p.write_text("\n".join(lines)+"\n", encoding="ascii")
PY
rc="$(run_fake broken-expected "$WORK/one-broken.tsv" "")"
[ "$rc" -eq 1 ] || ng "期待値1行破損が不一致終了にならない"
[ "$(awk -F '\t' '$2=="NG"{print $1}' "$WORK/broken-expected.out")" = L1 ] \
  || ng "期待値1行破損のNG腕がL1だけでない"
ok "陰性対照: 期待値1行破損で該当腕だけNG"

rc="$(run_fake selected-ng "$EXPECTED" "L0 D-expr L91")"
[ "$rc" -eq 1 ] || ng "選択故障が不一致終了にならない"
actual_ng="$(awk -F '\t' '$2=="NG"{print $1}' "$WORK/selected-ng.out" | tr '\n' ' ')"
[ "$actual_ng" = "L0 D-expr L91 " ] || ng "偽フロントエンドのOK/NG集合が不正"
ok "偽フロントエンドで意図したOK/NG集合を判別"

if grep -R -qF "$CANARY" "$WORK"/*.out "$WORK"/*.err "$WORK"/*.work 2>/dev/null; then
  ng "画面本文の漏えい目印を出力から検出"
fi
ok "漏えい目印はstdout/stderr/署名report/判定出力に無い"
# 陰性対照: 意図的な漏えいファイルなら同じ監査で検出できる。
printf '%s\n' "$CANARY" >"$WORK/leaking-output"
grep -qF "$CANARY" "$WORK/leaking-output" || ng "漏えい監査の陰性対照が不成立"
ok "陰性対照: 壊した出力の漏えい目印を検出"

ok "全項目合格"

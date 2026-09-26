#!/usr/bin/env bash
# m6f-e 器具Aの実走自己検査。公式ROM・公式ディスクは使わず、
# src/build_main_rom.py が作る自作main ROMを実際のq88measureで走らせる。
# 通常reportの画面本文は一時ディレクトリ内だけに置き、表示せず終了時に消す。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
BUILD="$REPO/src/build_main_rom.py"
CHECK="$REPO/tools/check_l3_screen_output.py"
COMPARE="$REPO/tools/compare_screen_signatures.py"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88-screen-signature-live.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR" || ng "q88measureのビルドに失敗"
mkdir -p "$WORK/rom"
python3 "$BUILD" "$WORK/rom" >"$WORK/build.stdout" 2>"$WORK/build.stderr" \
  || ng "自作main ROMの生成に失敗"

FRAMES=600
TYPE_AT=60
BASE_INPUT='PRINT1\n'
CHANGED_INPUT='PRINT2\n'
EARLY_FRAME=50

# 1走目: 通常report。stdout/stderrも一時領域へ閉じ込め、本文は表示しない。
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames "$FRAMES" \
  --type "$BASE_INPUT" --type-at "$TYPE_AT" --out "$WORK/normal.report" \
  >"$WORK/normal.stdout" 2>"$WORK/normal.stderr" \
  || ng "通常モードの実走に失敗"

# 既存規約で通常reportの各行を署名化する。本文はnormal.report以外へ書かない。
python3 - "$REPO" "$WORK/normal.report" "$WORK/normal-signature.tsv" <<'PYEOF' \
  || ng "通常reportの行別署名化に失敗"
import hashlib
import importlib.util
import pathlib
import sys

repo, report, output = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location(
    "check_l3_screen_output", repo / "tools/check_l3_screen_output.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
rows = module.read_screen(report)
whole = module.signature(rows)
with output.open("w", encoding="utf-8", newline="") as target:
    target.write("snapshot_id\tlive\nphysical_row\tchar_count\tsha256\n")
    for row, body in rows:
        canonical = f"{row}\t{body}\n".encode("utf-8")
        target.write(f"{row}\t{len(body)}\t{hashlib.sha256(canonical).hexdigest()}\n")
    target.write(f"line_count\t{whole.line_count}\n")
    target.write(f"char_count\t{whole.char_count}\n")
    target.write(f"sha256\t{whole.sha256}\n")
PYEOF

# 2走目: 同じフレーム数・同じ打鍵を署名専用モードで実走する。
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames "$FRAMES" \
  --type "$BASE_INPUT" --type-at "$TYPE_AT" --screen-signature-only \
  --screen-signature-at "live:$FRAMES" --out "$WORK/live-signature.tsv" \
  >"$WORK/live.stdout" 2>"$WORK/live.stderr" \
  || ng "署名専用モードの実走に失敗"

python3 "$COMPARE" --actual "$WORK/live-signature.tsv" \
  --expected "$WORK/normal-signature.tsv" --snapshot-id live \
  >"$WORK/live-compare.json" 2>"$WORK/live-compare.stderr" \
  || ng "通常report由来と署名専用モードの行別署名が一致しない"
ok "同条件2走の全行署名が一致"

# 画面全体の集約値は既存check_l3_screen_output.pyの結果とも照合する。
python3 "$CHECK" --report "$WORK/normal.report" \
  >"$WORK/legacy-signature.txt" 2>"$WORK/legacy-signature.stderr" \
  || ng "既存画面署名器の実行に失敗"
python3 - "$REPO" "$WORK/live-signature.tsv" "$WORK/legacy-signature.txt" <<'PYEOF' \
  || ng "画面全体署名が既存画面署名器と一致しない"
import importlib.util
import pathlib
import sys

repo, report, legacy_path = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location(
    "compare_screen_signatures", repo / "tools/compare_screen_signatures.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
actual = module.read_report(report, "live")
legacy = {}
for line in legacy_path.read_text(encoding="utf-8").splitlines():
    if "=" in line:
        key, value = line.split("=", 1)
        legacy[key] = value
if set(legacy) != {"line_count", "char_count", "sha256"}:
    raise SystemExit(1)
if (actual.line_count != int(legacy["line_count"])
        or actual.char_count != int(legacy["char_count"])
        or actual.sha256 != legacy["sha256"]):
    raise SystemExit(1)
PYEOF
ok "画面全体署名がcheck_l3_screen_output.pyと一致"

# 同条件の署名専用走のstdout/stderr/reportを監査する。画面節見出しに加え、
# 通常reportに実在する4文字以上の各本文行をgrep -Fの目印にする。
SIGNATURE_OUTPUTS=(
  "$WORK/live.stdout" "$WORK/live.stderr" "$WORK/live-signature.tsv"
)
if grep -Fq '[測定終了時のテキスト画面]' "${SIGNATURE_OUTPUTS[@]}"; then
  ng "署名専用出力に画面節見出しが現れた"
fi
python3 - "$REPO" "$WORK/normal.report" "${SIGNATURE_OUTPUTS[@]}" <<'PYEOF' \
  || ng "署名専用出力に通常reportの画面本文行が現れた"
import importlib.util
import pathlib
import subprocess
import sys
repo, report = map(pathlib.Path, sys.argv[1:3])
outputs = sys.argv[3:]
spec = importlib.util.spec_from_file_location("screen_reader", repo / "tools/check_l3_screen_output.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
for _, body in module.read_screen(report):
    if len(body) >= 4 and subprocess.run(
        ["grep", "-Fq", "--", body, *outputs], check=False
    ).returncode == 0:
        raise SystemExit(1)
PYEOF
ok "署名専用stdout/stderr/reportに画面節見出し・本文行なし"

expect_mismatch() {
  local actual="$1" label="$2" rc
  set +e
  python3 "$COMPARE" --actual "$actual" --expected "$WORK/normal-signature.tsv" \
    --snapshot-id live >"$WORK/${label}.compare.json" 2>"$WORK/${label}.compare.stderr"
  rc=$?
  set -e
  [ "$rc" -eq 1 ] || ng "陰性対照(${label})が不一致として検出されない"
}

# 陰性対照1: 打鍵を1文字だけ変え、同じ最終フレームで不一致になること。
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames "$FRAMES" \
  --type "$CHANGED_INPUT" --type-at "$TYPE_AT" --screen-signature-only \
  --screen-signature-at "live:$FRAMES" --out "$WORK/changed-key.tsv" \
  >"$WORK/changed-key.stdout" 2>"$WORK/changed-key.stderr" \
  || ng "打鍵変更の陰性対照実走に失敗"
expect_mismatch "$WORK/changed-key.tsv" changed-key
ok "陰性対照: 打鍵1文字変更を不一致として検出"

# 陰性対照2: 打鍵開始前のフレームを採り、最終画面と不一致になること。
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames "$FRAMES" \
  --type "$BASE_INPUT" --type-at "$TYPE_AT" --screen-signature-only \
  --screen-signature-at "live:$EARLY_FRAME" --out "$WORK/changed-frame.tsv" \
  >"$WORK/changed-frame.stdout" 2>"$WORK/changed-frame.stderr" \
  || ng "フレーム変更の陰性対照実走に失敗"
expect_mismatch "$WORK/changed-frame.tsv" changed-frame
ok "陰性対照: スナップショットのフレーム変更を不一致として検出"

# 漏えい監査そのものの陰性対照。通常reportには見出しと本文があるため、
# 同じgrep -Fが必ず検出できなければならない（本文は表示しない）。
grep -Fq '[測定終了時のテキスト画面]' "$WORK/normal.report" \
  || ng "漏えい監査の陰性対照が画面節見出しを検出できない"
python3 - "$REPO" "$WORK/normal.report" <<'PYEOF' \
  || ng "漏えい監査の陰性対照が本文行を検出できない"
import importlib.util
import pathlib
import subprocess
import sys
repo, report = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("screen_reader", repo / "tools/check_l3_screen_output.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
found = False
for _, body in module.read_screen(report):
    if len(body) >= 4 and subprocess.run(
        ["grep", "-Fq", "--", body, str(report)], check=False
    ).returncode == 0:
        found = True
        break
if not found:
    raise SystemExit(1)
PYEOF
ok "陰性対照: 本文を含む通常reportを漏えい監査が検出"

ok "全項目合格"

#!/usr/bin/env bash
# tools/refmeasure_selftest.sh — tools/refmeasure.py(公式環境での使い捨て
# 測定に関わる共通部品)単体の検査。
#
# 2026-08-11、この共通部品は tools/verify_analyzer_corruption.py から
# 切り出した(M6jでも同じ仕組みが要るため二重実装を避けた)。切り出し前は
# tools/analyzer_redaction_selftest.sh の e〜h がこの安全側プリミティブを
# (verify_analyzer_corruption.py 経由で)検査していたが、プリミティブ自体は
# refmeasure.py に移ったので、ここで直接検査する
# (analyzer_redaction_selftest.sh 側は、verify_analyzer_corruption.py が
# refmeasure を正しく使えているかの結合的な確認だけを残す。重複させない)。
#
# CLAUDE.md / docs/notes の方針どおり、検査器を信用してよいのはわざと壊して
# 検出できることを確かめた後だけ(tools/redact_iolog_selftest.sh の作法を
# 踏襲)。公式ROM・公式ディスク不要。フィクスチャは全て自作の合成データ。
#
# 使い方: tools/refmeasure_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REFMEASURE="$SCRIPT_DIR/refmeasure.py"

WORK="$(mktemp -d)"
BROKEN_NOREJECT="$SCRIPT_DIR/.refmeasure_broken_noreject_selftest.py"
BROKEN_NORMTREE="$SCRIPT_DIR/.refmeasure_broken_normtree_selftest.py"
trap 'rm -rf "$WORK" "$BROKEN_NOREJECT" "$BROKEN_NORMTREE"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

import_probe() {
    local module_path="$1"
    shift
    python3 - "$module_path" "$@"
}

# --- a. ref_env(): 両方未設定なら None、両方設定していればタプル ------------
A_OUT="$(env -u PC88_REF_ROM_DIR -u PC88_REF_DISK_DIR python3 - "$REFMEASURE" <<'PYEOF'
import importlib.util, sys
module_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("refmeasure_probe_a", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print("NONE" if m.ref_env() is None else "SOME")
PYEOF
)"
if [[ "$A_OUT" == "NONE" ]]; then
    pass "a-1. 環境変数が両方未設定なら ref_env() は None を返す"
else
    fail "a-1. 環境変数未設定でも ref_env() が None を返さなかった: $A_OUT"
fi

A2_OUT="$(PC88_REF_ROM_DIR="$WORK/rom" PC88_REF_DISK_DIR="$WORK/disk" python3 - "$REFMEASURE" <<'PYEOF'
import importlib.util, os, sys
module_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("refmeasure_probe_a2", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
r = m.ref_env()
expected = (os.environ["PC88_REF_ROM_DIR"], os.environ["PC88_REF_DISK_DIR"])
print("PAIR" if r == expected else f"OTHER:{r}")
PYEOF
)"
if [[ "$A2_OUT" == "PAIR" ]]; then
    pass "a-2. 両方設定していれば ref_env() が (rom_dir, disk_dir) を返す"
else
    fail "a-2. 両方設定していても ref_env() が期待した値を返さない: $A2_OUT"
fi

# --- b. reject_if_in_repo(): リポジトリ配下は拒否、外は通す ------------------
B_OUT="$(python3 - "$REFMEASURE" <<'PYEOF'
import importlib.util, sys
from pathlib import Path
module_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("refmeasure_probe_b", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

results = []
try:
    m.reject_if_in_repo(m.repo_root() / "measurements", "テスト用")
    results.append("INREPO_NOT_REJECTED")
except SystemExit:
    results.append("INREPO_REJECTED")

import tempfile
outside = Path(tempfile.mkdtemp(prefix="pc88h-refmeasure-selftest-outside-"))
try:
    m.reject_if_in_repo(outside, "テスト用")
    results.append("OUTSIDE_OK")
except SystemExit:
    results.append("OUTSIDE_REJECTED")
import shutil
shutil.rmtree(outside, ignore_errors=True)
print(",".join(results))
PYEOF
)"
if [[ "$B_OUT" == "INREPO_REJECTED,OUTSIDE_OK" ]]; then
    pass "b. reject_if_in_repo() はリポジトリ配下を拒否し、外は通す"
else
    fail "b. reject_if_in_repo() の判定が想定と異なる: $B_OUT"
fi

# --- c. DisposableRawDir: 正常終了・例外どちらでも削除される -----------------
run_disposable_probe() {
    local module_path="$1"
    python3 - "$module_path" <<'PYEOF'
import importlib.util
import sys

module_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("refmeasure_probe_c", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

holder = {}
try:
    with m.DisposableRawDir(prefix="pc88h-refmeasure-selftest-exc-") as d:
        holder["path"] = d
        if not d.is_dir():
            print("SETUP_FAILED")
            sys.exit(1)
        raise RuntimeError("わざと起こした例外(検査用)")
except RuntimeError:
    pass
p = holder.get("path")
print("GONE" if (p is not None and not p.exists()) else "EXISTS")
PYEOF
}

C_NORMAL_OUT="$(python3 - "$REFMEASURE" <<'PYEOF'
import importlib.util, sys
module_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("refmeasure_probe_c_normal", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

with m.DisposableRawDir(prefix="pc88h-refmeasure-selftest-normal-") as d:
    p = d
print("GONE" if not p.exists() else "EXISTS")
PYEOF
)"
if [[ "$C_NORMAL_OUT" == "GONE" ]]; then
    pass "c-1. DisposableRawDir: 正常終了時に生ログ用ディレクトリが削除される"
else
    fail "c-1. DisposableRawDir: 正常終了後もディレクトリが残った(結果: $C_NORMAL_OUT)"
fi

C_EXC_OUT="$(run_disposable_probe "$REFMEASURE")"
if [[ "$C_EXC_OUT" == "GONE" ]]; then
    pass "c-2. DisposableRawDir: with 内で例外が起きても生ログ用ディレクトリが削除される"
else
    fail "c-2. DisposableRawDir: 例外後も生ログ用ディレクトリが残った(結果: $C_EXC_OUT)"
fi

# --- d. discover_frontend_and_core() / measure_fresh_raw_log(): 未整備環境で
#        FullMeasurementError として失敗すること(実測定は経由しない) --------
D_OUT="$(env -u PC88_REF_ROM_DIR -u PC88_REF_DISK_DIR python3 - "$REFMEASURE" "$WORK" <<'PYEOF'
import importlib.util, sys
from pathlib import Path
module_path, workdir = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("refmeasure_probe_d", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
try:
    m.measure_fresh_raw_log(Path(workdir), 100)
    print("NOT_RAISED")
except m.FullMeasurementError:
    print("RAISED")
PYEOF
)"
if [[ "$D_OUT" == "RAISED" ]]; then
    pass "d. measure_fresh_raw_log() は環境変数未設定だと FullMeasurementError で失敗する(実測定は不要)"
else
    fail "d. measure_fresh_raw_log() が環境変数未設定でも例外を出さなかった: $D_OUT"
fi

# --- e. わざと壊すと落ちることの確認(検出力の裏付け) ------------------------
# tools/analyzer_redaction_selftest.sh の h-1/h-2 と同じ作法。保護コードを
# sedで無効化したコピーに対して同じ検査をかけ、上のb./c.が本当に検出力を
# 持っているか(常にpassするザル検査ではないか)を確認する。

# e-1: reject_if_in_repo の判定を無効化 → リポジトリ配下でも拒否されなくなる
sed -E 's/if p == repo or repo in p\.parents:/if False:/' "$REFMEASURE" > "$BROKEN_NOREJECT"
if diff -q "$REFMEASURE" "$BROKEN_NOREJECT" >/dev/null 2>&1; then
    fail "e-1. reject_if_in_repo を無効化したコピーの生成に失敗した(sedが対象行にマッチしなかった)"
else
    E1_OUT="$(python3 - "$BROKEN_NOREJECT" <<'PYEOF'
import importlib.util, sys
module_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("refmeasure_probe_e1", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
try:
    m.reject_if_in_repo(m.repo_root() / "measurements", "テスト用")
    print("NOT_REJECTED")
except SystemExit:
    print("REJECTED")
PYEOF
)"
    if [[ "$E1_OUT" == "NOT_REJECTED" ]]; then
        pass "e-1. reject_if_in_repo を無効化すると、リポジトリ配下の指定が素通りする退行を再現できた(=b.に検出力がある証拠)"
    else
        fail "e-1. 保護コードを無効化したのにリポジトリ配下が依然拒否された(sedが効いていない可能性)"
    fi
fi

# e-2: DisposableRawDir.__exit__ の rmtree を無効化 → 例外後もディレクトリが残る
sed -E 's/shutil\.rmtree\(self\.path, ignore_errors=True\)/pass  # broken-for-selftest/' \
    "$REFMEASURE" > "$BROKEN_NORMTREE"
if diff -q "$REFMEASURE" "$BROKEN_NORMTREE" >/dev/null 2>&1; then
    fail "e-2. rmtree を無効化したコピーの生成に失敗した(sedが対象行にマッチしなかった)"
else
    E2_OUT="$(run_disposable_probe "$BROKEN_NORMTREE")"
    if [[ "$E2_OUT" == "EXISTS" ]]; then
        pass "e-2. rmtree を無効化すると例外後も生ログ用ディレクトリが残る退行を再現できた(=c-2.に検出力がある証拠)"
        rm -rf "${TMPDIR:-/tmp}"/pc88h-refmeasure-selftest-exc-* 2>/dev/null || true
    else
        fail "e-2. 保護コードを無効化したのに生ログ用ディレクトリが削除された(結果: ${E2_OUT}。sedが効いていない可能性)"
    fi
fi

echo
echo "  (注記: 公式環境(PC88_REF_ROM_DIR/PC88_REF_DISK_DIR)がこの作業環境に無いため、"
echo "   discover_frontend_and_core()/measure_fresh_raw_log() が実際にq88measureを"
echo "   実行する経路そのものは未実行。上記は環境変数が未設定な場合の縮退動作と"
echo "   削除保証プリミティブ単体の検査。)"

echo
if [[ "$FAIL" -eq 0 ]]; then
    echo "==> 全項目 OK"
    exit 0
else
    echo "==> 一部 NG"
    exit 1
fi

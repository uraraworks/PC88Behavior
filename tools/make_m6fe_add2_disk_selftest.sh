#!/usr/bin/env bash
# m6f-e追補2の媒体・専用manifest・独立検査器を合成像だけで検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-add2-media.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/main" >/dev/null
python3 "$REPO/tools/make_m6fe_disk.py" --addendum2 "$WORK/add2a" >/dev/null
python3 "$REPO/tools/make_m6fe_disk.py" --addendum2 "$WORK/add2b" >/dev/null
python3 "$REPO/tools/check_m6fe_disk.py" --addendum2 "$WORK/add2a/manifest.json" \
  --image-dir "$WORK/add2a" --json >"$WORK/check.json"

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import hashlib, json, os, pathlib, subprocess, sys
repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
add2 = json.loads((work / "add2a/manifest.json").read_text(encoding="ascii"))
frozen = dict(line.split("\t") for line in
              (repo / "tools/m6fe_add2_frozen.tsv").read_text(encoding="ascii").splitlines())

def fail(label):
    print("NG " + label)
    raise SystemExit(1)

if json.loads((work / "check.json").read_text(encoding="ascii")) != {"failures": {}}:
    fail("positive")
if add2["format"] != "m6fe-add2-scenario-v1":
    fail("format")
if add2["media_order"] != ["L80", "L85", "L90", "L95", "L96'"]:
    fail("media_order")
if [len(add2["media"][arm]["entries"]) for arm in add2["media_order"]] != [80, 85, 90, 95, 96]:
    fail("counts")
if [arm["id"] for arm in add2["arms"]] != add2["media_order"]:
    fail("arms")
if any(arm["runs"] != 2 or arm["final_frame"] != 12000
       or arm["command"] != "CLS:FILES 2" or arm["events"] for arm in add2["arms"]):
    fail("plan")
raw = (work / "add2a/manifest.json").read_bytes()
if raw != (work / "add2b/manifest.json").read_bytes():
    fail("determinism")
if hashlib.sha256(raw).hexdigest() != frozen["manifest_sha256"]:
    fail("freeze")
if (work / "add2a/L96p.d88").read_bytes() != (work / "main/L96.d88").read_bytes():
    fail("l96_bytes")

# 独立検査器の陰性対照: 本体1バイト破壊のNG集合を完全一致で確認する。
broken = bytearray((work / "add2a/L80.d88").read_bytes())
broken[32 + 164 * 4 + 16] ^= 1
(work / "broken.d88").write_bytes(broken)
proc = subprocess.run([
    sys.executable, str(repo / "tools/check_m6fe_disk.py"), "--addendum2",
    str(work / "add2a/manifest.json"), "--media", "L80", "--image",
    str(work / "broken.d88"), "--json"], text=True, capture_output=True)
if proc.returncode != 1 or json.loads(proc.stdout) != {"failures": {"L80": ["body"]}}:
    fail("negative_body_set")

changed = work / "changed-manifest.json"
changed.write_bytes(raw + b" ")
proc = subprocess.run([
    sys.executable, str(repo / "tools/check_m6fe_disk.py"), "--addendum2",
    str(changed), "--image-dir", str(work / "add2a"), "--json"],
    text=True, capture_output=True)
if proc.returncode != 1 or json.loads(proc.stdout) != {"failures": {"manifest": ["manifest_sha256"]}}:
    fail("negative_manifest_set")
print("OK add2_media_manifest_l96_and_negative_controls")
PY

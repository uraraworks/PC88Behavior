#!/usr/bin/env bash
# m6f-e追補3の媒体・manifest・独立検査器を合成像だけで検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-add3-media.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

python3 "$REPO/tools/make_m6fe_disk.py" --addendum2 "$WORK/add2" >/dev/null
python3 "$REPO/tools/make_m6fe_disk.py" --addendum3 "$WORK/add3a" >/dev/null
python3 "$REPO/tools/make_m6fe_disk.py" --addendum3 "$WORK/add3b" >/dev/null
python3 "$REPO/tools/check_m6fe_disk.py" --addendum3 "$WORK/add3a/manifest.json" \
  --image-dir "$WORK/add3a" --json >"$WORK/check.json"

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import hashlib, json, os, pathlib, subprocess, sys
repo = pathlib.Path(os.environ["REPO"]); work = pathlib.Path(os.environ["WORK"])
doc = json.loads((work / "add3a/manifest.json").read_text(encoding="ascii"))
frozen = dict(line.split("\t") for line in
              (repo / "tools/m6fe_add3_frozen.tsv").read_text(encoding="ascii").splitlines())
def fail(label): print("NG " + label); raise SystemExit(1)
if json.loads((work / "check.json").read_text(encoding="ascii")) != {"failures": {}}: fail("positive")
if doc["format"] != "m6fe-add3-scenario-v1": fail("format")
if doc["media_order"] != ["L81", "L86", "L91", "L90'"]: fail("media_order")
if [len(doc["media"][arm]["entries"]) for arm in doc["media_order"]] != [81, 86, 91, 90]: fail("counts")
if [arm["id"] for arm in doc["arms"]] != ["P79", "P80", "P81", "L81", "L86", "L91", "L90'"]: fail("arms")
for arm, length in zip(doc["arms"][:3], (79, 80, 81)):
    if arm["drive2"] != "empty" or arm["command"].count("A") != length or arm["events"]: fail("print_plan")
if any(arm["drive2"] != arm["id"] or arm["command"] != "CLS:FILES 2" or arm["events"]
       for arm in doc["arms"][3:]): fail("files_plan")
raw = (work / "add3a/manifest.json").read_bytes()
if raw != (work / "add3b/manifest.json").read_bytes(): fail("determinism")
if hashlib.sha256(raw).hexdigest() != frozen["manifest_sha256"]: fail("freeze")
if (work / "add3a/L90p.d88").read_bytes() != (work / "add2/L90.d88").read_bytes(): fail("l90_bytes")

broken = bytearray((work / "add3a/L81.d88").read_bytes()); broken[32 + 164 * 4 + 16] ^= 1
(work / "broken.d88").write_bytes(broken)
proc = subprocess.run([sys.executable, str(repo / "tools/check_m6fe_disk.py"), "--addendum3",
    str(work / "add3a/manifest.json"), "--media", "L81", "--image", str(work / "broken.d88"), "--json"],
    text=True, capture_output=True)
if proc.returncode != 1 or json.loads(proc.stdout) != {"failures":{"L81":["body"]}}: fail("negative_body_set")
changed = work / "changed-manifest.json"; changed.write_bytes(raw + b" ")
proc = subprocess.run([sys.executable, str(repo / "tools/check_m6fe_disk.py"), "--addendum3",
    str(changed), "--image-dir", str(work / "add3a"), "--json"], text=True, capture_output=True)
if proc.returncode != 1 or json.loads(proc.stdout) != {"failures":{"manifest":["manifest_sha256"]}}: fail("negative_manifest_set")
print("OK add3_media_manifest_l90_and_negative_controls")
PY

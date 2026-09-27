#!/usr/bin/env bash
# m6f-g媒体生成器と独立検査器を、合成D88と陰性対照で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fg-disk.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
python3 "$REPO/tools/make_m6fg_disk.py" "$WORK/out1" >/dev/null
python3 "$REPO/tools/make_m6fg_disk.py" "$WORK/out2" >/dev/null

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
import hashlib, json, os, pathlib, struct, subprocess, sys
repo=pathlib.Path(os.environ["REPO"]); work=pathlib.Path(os.environ["WORK"])
out=work/"out1"; manifest_path=out/"manifest.json"
manifest=json.loads(manifest_path.read_text(encoding="ascii"))
checker=repo/"tools/check_m6fg_disk.py"

def fail(label): print("NG "+label); raise SystemExit(1)
def offsets(image):
 starts=sorted(v for v in [struct.unpack_from("<I",image,32+i*4)[0] for i in range(164)] if v)
 result={}
 for i,start in enumerate(starts):
  end=starts[i+1] if i+1<len(starts) else len(image); pos=start
  while pos<end:
   size=struct.unpack_from("<H",image,pos+14)[0]
   result[(image[pos],image[pos+1],image[pos+2])]=pos+16; pos+=16+size
 return result
def directory(off,pos): return off[(18,1,1+pos//16)]+(pos%16)*16
def fat(off,copy,unit): return off[(18,1,14+copy)]+unit
def check(media,path):
 p=subprocess.run([sys.executable,str(checker),str(manifest_path),"--media",media,
                   "--image",str(path),"--json"],text=True,capture_output=True)
 return p.returncode,json.loads(p.stdout)
def negative(media,label,mutate):
 image=bytearray((out/manifest["media"][media]["file"]).read_bytes()); off=offsets(image)
 mutate(image,off); path=work/("bad-"+label+".d88"); path.write_bytes(image)
 rc,value=check(media,path)
 if rc!=1 or value!={"failures":{media:[label]}}: fail("negative_"+label)

p=subprocess.run([sys.executable,str(checker),str(manifest_path),"--image-dir",str(out),"--json"],
                 text=True,capture_output=True)
if p.returncode or json.loads(p.stdout)!={"failures":{}}: fail("positive")
if "make_m6fg_disk" in checker.read_text(encoding="utf-8"): fail("independence")
if manifest_path.read_bytes()!=(work/"out2/manifest.json").read_bytes(): fail("determinism")
if [a["id"] for a in manifest["arms"]]!=["G-P","G-B","G-M","G-Z1","G-Z2"]: fail("arms")
if any(a["runs"]!=2 or a["command"]!="CLS:FILES 2" for a in manifest["arms"]): fail("plan")
if [e["type"] for e in manifest["media"]["G-M"]["entries"]]!=[0x80,0x00,0xA0,0x01,0x80]: fail("types")
z2=manifest["media"]["G-Z2"]["entries"][0]["units"]
if len(z2)!=158 or set(z2)!=(set(range(160))-{74,75}): fail("z2_units")

negative("G-P","file_type",lambda image,off:image.__setitem__(directory(off,0)+9,0x80))
def chain_bad(image,off):
 for copy in range(3): image[fat(off,copy,0)]=2
negative("G-Z1","chain",chain_bad)
def reserve_bad(image,off):
 for copy in range(3): image[fat(off,copy,74)]=0xFF
negative("G-Z1","reserved_units",reserve_bad)
negative("G-M","unit_unique",lambda image,off:image.__setitem__(directory(off,1)+10,0))

frozen=dict(line.split("\t") for line in (repo/"tools/m6fg_frozen.tsv").read_text(encoding="ascii").splitlines())
if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=frozen["manifest_sha256"]: fail("freeze")
changed=work/"changed.json"; changed.write_bytes(manifest_path.read_bytes()+b" ")
p=subprocess.run([sys.executable,str(checker),str(changed),"--image-dir",str(out),"--json"],
                 text=True,capture_output=True)
if p.returncode!=1 or json.loads(p.stdout)!={"failures":{"manifest":["manifest_sha256"]}}: fail("freeze_negative")
print("OK m6f-g媒体: 正例、種別、鎖、予約74/75、重複、G-Z2、凍結陰性対照")
PY

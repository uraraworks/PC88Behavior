#!/usr/bin/env bash
# 合成D88だけで旧値開示境界・構成差・実体パスG6を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
GEN="$REPO/tools/make_l3_testdisk.py"; DIFF="$REPO/tools/d88_diff.py"
python3 "$GEN" "$WORK/base.d88" --cylinders 1 --sectors-per-track 4 >/dev/null
python3 "$GEN" "$WORK/short.d88" --cylinders 1 --sectors-per-track 1 >/dev/null
python3 "$GEN" "$WORK/long.d88" --cylinders 1 --sectors-per-track 2 >/dev/null
python3 - "$WORK/base.d88" "$WORK/after.d88" <<'PY'
import struct,sys
base=bytearray(open(sys.argv[1],'rb').read()); after=bytearray(base)
track=struct.unpack_from('<I',base,32)[0]
def data(r): return track+(r-1)*(16+256)+16
def setpair(r,offset,old,new):
    base[data(r)+offset:data(r)+offset+len(old)]=old
    after[data(r)+offset:data(r)+offset+len(new)]=new
# R1: 区間では一様AAでも、同じセクタの他区間が非一様なので全伏せ。
setpair(1,10,b'\xAA'*3,b'\x01\x02\x03')
setpair(1,20,b'\x10\x11\x12',b'\x21\x22\x23')
setpair(1,100,b'\xDE\xAD\xBE\xEF',b'\xDE\xAD\xBE\xEF')
# R2: 異なる旧値の1バイト変化を散在させる。
for offset,old,new in ((1,0x91,0x11),(3,0xA3,0x22),(5,0xC7,0x33)):
    setpair(2,offset,bytes([old]),bytes([new]))
# R3/R4: 同一旧値の変化数7個/8個の境界。
setpair(3,40,b'\x77'*7,bytes(range(1,8)))
setpair(4,50,b'\x88'*8,bytes(range(0x30,0x38)))
open(sys.argv[1],'wb').write(base); open(sys.argv[2],'wb').write(after)
PY
python3 "$DIFF" "$WORK/base.d88" "$WORK/after.d88" --output "$WORK/diff.json"
python3 - "$WORK/diff.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); by_r={x['r']:x for x in d['changes']}
body=json.dumps(d,sort_keys=True,separators=(',',':'))
checks={
 'unchanged_not_emitted': 'DEADBEEF' not in body,
 'whole_sector_withheld': 'old_uniform' not in by_r[1] and all(x['old']=='withheld' for x in by_r[1]['ranges']),
 'scattered_old_withheld': all(f'"old":"{x}"' not in body and f'"old_uniform":"{x}"' not in body for x in ('91','A3','C7')),
 'seven_withheld': 'old_uniform' not in by_r[3] and by_r[3]['ranges'][0]['old']=='withheld',
 'eight_revealed': by_r[4].get('old_uniform')=='88',
 'range_old_withheld': all(span['old']=='withheld' for sector in d['changes'] for span in sector['ranges']),
 'position_and_new': by_r[1]['ranges'][0]=={'offset':10,'length':3,'new':'010203','old':'withheld'},
 'totals': d['changed_sectors']==4 and d['changed_bytes']==24,
}
bad={k for k,v in checks.items() if not v}
if bad: raise SystemExit('NG集合 '+str(bad))
for target in checks:
    negative=dict(checks); negative[target]=False
    if {k for k,v in negative.items() if not v}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {k for k,v in mutant.items() if not v}=={target}: raise SystemExit('常時真変異 '+target)
PY

# 追補2前の区間単位旧値開示では、散在した3個の目印が漏れて狙いの検査だけが落ちる。
sed 's/USE_RANGE_OLD_POLICY_FOR_SELFTEST = False/USE_RANGE_OLD_POLICY_FOR_SELFTEST = True/' "$DIFF" >"$WORK/mut-old.py"
PYTHONPATH="$REPO/tools" python3 - "$WORK/mut-old.py" "$WORK/base.d88" "$WORK/after.d88" "$WORK/mut-old.json" <<'PY'
import json,runpy,sys
ns=runpy.run_path(sys.argv[1]); result=ns['compare_images'](open(sys.argv[2],'rb').read(),open(sys.argv[3],'rb').read())
json.dump(result,open(sys.argv[4],'w'))
PY
python3 - "$WORK/mut-old.json" <<'PY'
import json,sys
body=json.dumps(json.load(open(sys.argv[1])),sort_keys=True,separators=(',',':'))
checks={'scattered_old_withheld':all(f'"old":"{x}"' not in body for x in ('91','A3','C7'))}
bad={k for k,v in checks.items() if not v}
raise SystemExit(0 if bad=={'scattered_old_withheld'} else 1)
PY

# 不変値を含める変異では、狙った不変値検査が落ちる。
sed 's/INCLUDE_UNCHANGED_FOR_SELFTEST = False/INCLUDE_UNCHANGED_FOR_SELFTEST = True/' "$DIFF" >"$WORK/mut-unchanged.py"
PYTHONPATH="$REPO/tools" python3 - "$WORK/mut-unchanged.py" "$WORK/base.d88" "$WORK/after.d88" "$WORK/mut-unchanged.json" <<'PY'
import json,runpy,sys
ns=runpy.run_path(sys.argv[1]); result=ns['compare_images'](open(sys.argv[2],'rb').read(),open(sys.argv[3],'rb').read())
json.dump(result,open(sys.argv[4],'w'))
PY
python3 - "$WORK/mut-unchanged.json" <<'PY'
import json,sys
body=json.dumps(json.load(open(sys.argv[1])),sort_keys=True)
checks={'unchanged_not_emitted':'DEADBEEF' not in body}
bad={k for k,v in checks.items() if not v}
raise SystemExit(0 if bad=={'unchanged_not_emitted'} else 1)
PY

python3 "$DIFF" "$WORK/short.d88" "$WORK/long.d88" --output "$WORK/layout.json"
python3 - "$WORK/layout.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); assert not d['sector_layout_equal']
assert d['before_only']==[] and d['after_only']==[{'c':0,'h':0,'r':2}]
assert d['changed_bytes']==0 and d['changes']==[]
PY

# 直接のrepo内と、外のsymlink経由で実体がrepo内になる場合をともに拒否する。
rm -f "$REPO/.m6fa-g6-probe.json"
if python3 "$DIFF" "$WORK/base.d88" "$WORK/after.d88" --output "$REPO/.m6fa-g6-probe.json" >/dev/null 2>&1; then exit 1; fi
[ ! -e "$REPO/.m6fa-g6-probe.json" ]
ln -s "$REPO" "$WORK/repo-link"
if python3 "$DIFF" "$WORK/base.d88" "$WORK/after.d88" --output "$WORK/repo-link/.m6fa-g6-probe.json" >/dev/null 2>&1; then exit 1; fi
[ ! -e "$REPO/.m6fa-g6-probe.json" ]
echo "d88_diff_selftest: 項目数=13、陰性対照=5、常時真変異=8件拒否、G6=2経路 OK"

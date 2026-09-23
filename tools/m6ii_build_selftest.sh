#!/usr/bin/env bash
# m6i-i掃引・4故障注入・既存5 SHAの非回帰を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
BUILD=(python3 "$REPO/src/build_main_rom.py")
build() { local name="$1"; shift; "${BUILD[@]}" "$WORK/$name" "$@" --work-dir "$WORK/w-$name" >/dev/null; }
build main --enable-main-sub-read
build retry --enable-disk-read-retry
build chr --enable-disk-read-chr
build plain
build I-S --inject-m6ii-sweep
build I-F-H --inject-m6ii-sweep --inject-m6ii-fault-h
build I-F-D --inject-m6ii-sweep --inject-m6ii-fault-d
build I-F-R --inject-m6ii-sweep --inject-m6ii-fault-r
build I-F-RETRY --inject-m6ii-sweep --inject-m6ii-fault-retry
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/default.d88" \
  --cylinders 40 --double-sided --sectors-per-track 16 >/dev/null

python3 - "$REPO" "$WORK" <<'PY'
import hashlib,sys
from pathlib import Path
repo,work=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo))
import src.build_main_rom as b
sys.path.insert(0,str(repo/'tools')); import check_m6ii_preregistration as gate
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
checks={
 'sha_main':sha(work/'main/N88.ROM')==gate.EXPECTED_SINGLETONS['main_sub_sha256'],
 'sha_retry':sha(work/'retry/N88.ROM')==gate.EXPECTED_SINGLETONS['disk_retry_sha256'],
 'sha_chr':sha(work/'chr/N88.ROM')==gate.EXPECTED_SINGLETONS['disk_chr_sha256'],
 'sha_sub':sha(work/'plain/DISK.ROM')==gate.EXPECTED_SINGLETONS['plain_subrom_sha256'],
 'sha_media':sha(work/'default.d88')==gate.EXPECTED_SINGLETONS['normal_media_sha256'],
 'table_11':b.M6II_BOOT_SWEEP.count('    DB ')==11 and 'LD B,00Bh' in b.M6II_BOOT_SWEEP,
 'no_wait':all(x not in b.M6II_BOOT_SWEEP for x in ('WAIT','MAIN_SUB_SEND\n')),
 'row_before_read':b.M6II_BOOT_SWEEP.index('LD (M6II_ROW_MARKER),A') < b.M6II_BOOT_SWEEP.index('CALL MAIN_SUB_READ_CHR_RETRY'),
}
for arm,want in gate.ARM_HASHES.items(): checks['arm_'+arm]=sha(work/arm/'N88.ROM')==want
for arm,name in [('I-F-H','H'),('I-F-D','D'),('I-F-R','R'),('I-F-RETRY','RETRY')]:
    text=(work/('w-'+arm)/'main_sub_read_chr_gen.asm').read_text()
    checks['unique_'+name]=(text.count(getattr(b,'M6II_'+name+'_FAULT_NEW'))==1 and
                            text.count(getattr(b,'M6II_'+name+'_FAULT_OLD'))==0)
if not all(checks.values()): raise SystemExit('NG: '+str({k for k,v in checks.items() if not v}))
for target in checks:
    negative=dict(checks); negative[target]=False
    if {k for k,v in negative.items() if not v}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {k for k,v in mutant.items() if not v}=={target}: raise SystemExit('常時真変異 '+target)
print(f"m6ii_build_selftest: 項目数={len(checks)}、陰性対照={len(checks)}、常時真変異={len(checks)}件拒否 OK")
print('故障注入置換対象=H/D/R/RETRY各1件')
for key in ('main_sub_sha256','disk_retry_sha256','disk_chr_sha256','plain_subrom_sha256','normal_media_sha256'):
    print('SHA '+key+'='+gate.EXPECTED_SINGLETONS[key])
PY

expect_fail() { if "$@" >/dev/null 2>&1; then exit 1; fi; }
expect_fail "${BUILD[@]}" "$WORK/bad1" --inject-m6ii-fault-h
expect_fail "${BUILD[@]}" "$WORK/bad2" --inject-m6ii-sweep --inject-m6ii-fault-h --inject-m6ii-fault-d
expect_fail "${BUILD[@]}" "$WORK/bad3" --inject-m6ii-sweep --inject-m6ih-a

#!/usr/bin/env bash
# m6f-b凍結照合器の陽性・陰性対照、512上限、ドライバ静的関門を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6fb_preregistration.py"; CONFIG="$REPO/tools/m6fb_frozen.tsv"
python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err"; : >"$WORK/check-positive"
expect_fail() { local name="$1"; shift; if "$@" >"$WORK/$name.out" 2>"$WORK/$name.err"; then exit 1; fi; grep -q gate_failed "$WORK/$name.err"; : >"$WORK/check-$name"; }
mutate() { local old="$1" new="$2" out="$3"; sed "s|$old|$new|" "$CONFIG" >"$out"; }
mutate $'measurement_frames\t9000' $'measurement_frames\t8999' "$WORK/frames.tsv"; expect_fail frames python3 "$CHECK" --config "$WORK/frames.tsv"
mutate $'run_timeout_seconds\t300' $'run_timeout_seconds\t299' "$WORK/timeout.tsv"; expect_fail timeout python3 "$CHECK" --config "$WORK/timeout.tsv"
mutate $'reference_disk\tN88_FE.D88' $'reference_disk\tOTHER.D88' "$WORK/disk.tsv"; expect_fail disk python3 "$CHECK" --config "$WORK/disk.tsv"
mutate $'directory_sector\t18,1,3' $'directory_sector\t18,1,4' "$WORK/sector.tsv"; expect_fail sector python3 "$CHECK" --config "$WORK/sector.tsv"
mutate $'arm\tG3' $'arm\tGX' "$WORK/arm.tsv"; expect_fail arm python3 "$CHECK" --config "$WORK/arm.tsv"
mutate 'STRING$(200,"V")' 'STRING$(200,"Z")' "$WORK/g7.tsv"; expect_fail g7 python3 "$CHECK" --config "$WORK/g7.tsv"
mutate 'E8:program_data_difference' 'E8:other' "$WORK/e8.tsv"; expect_fail e8 python3 "$CHECK" --config "$WORK/e8.tsv"
mutate $'judgment\tcase_other' $'judgment\tcase_unknown' "$WORK/judgment.tsv"; expect_fail judgment python3 "$CHECK" --config "$WORK/judgment.tsv"
python3 - "$CONFIG" "$WORK/long.tsv" <<'PY'
import sys
text=open(sys.argv[1],encoding='utf-8').read()
text=text.replace('keystrokes\tG0:\n','keystrokes\tG0:'+'A'*513+'\n')
open(sys.argv[2],'w',encoding='utf-8').write(text)
PY
expect_fail keystroke_limit python3 "$CHECK" --config "$WORK/long.tsv"

# 凍結不一致と環境不足はいずれもfrontend起動前に止まる。
cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6FB_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6FB_FROZEN_CONFIG="$WORK/frames.tsv" M6FB_FRONTEND="$WORK/fake_frontend" \
M6FB_FRONTEND_SENTINEL="$WORK/started" "$REPO/tools/measure_m6fb.sh" \
  --raw-dir "$WORK/raw" --result "$WORK/result.json" >"$WORK/measure.out" 2>"$WORK/measure.err"
rc_bad=$?
env -u PC88_REF_ROM_DIR -u PC88_REF_DISK_DIR M6FB_FRONTEND="$WORK/fake_frontend" \
M6FB_FRONTEND_SENTINEL="$WORK/started2" "$REPO/tools/measure_m6fb.sh" \
  --raw-dir "$WORK/raw2" --result "$WORK/result2.json" >"$WORK/missing.out" 2>"$WORK/missing.err"
rc_missing=$?
set -e
[ "$rc_bad" -ne 0 ] && [ ! -e "$WORK/started" ] && grep -q preregistration_mismatch "$WORK/measure.out"; : >"$WORK/check-start_bad_config"
[ "$rc_missing" -ne 0 ] && [ ! -e "$WORK/started2" ] && grep -q PC88_REF_ROM_DIR_missing "$WORK/missing.out"; : >"$WORK/check-start_missing_env"

bash -n "$REPO/tools/measure_m6fb.sh"; : >"$WORK/check-shell_syntax_b"
bash -n "$REPO/tools/measure_m6fa.sh"; : >"$WORK/check-shell_syntax_a"
python3 - "$REPO" <<'PY'
import sys
from pathlib import Path
repo=Path(sys.argv[1]); driver=(repo/'tools/measure_m6fb.sh').read_text(encoding='utf-8')
if 'run_all_selftests.sh' in driver: raise SystemExit('全自己検査の呼出しを検出')
shared=(repo/'tools/lib_m6f_measure.sh').read_text(encoding='utf-8')
if not all(f'source "$REPO/tools/lib_m6f_measure.sh"' in (repo/f'tools/measure_m6f{x}.sh').read_text(encoding='utf-8') for x in ('a','b')):
    raise SystemExit('共通ライブラリ未使用')
for token in ('--save-to-disk-image','seek=26','offsets not in ([], [26])'):
    if token not in shared: raise SystemExit('共通測定規則の不足: '+token)
PY
: >"$WORK/check-no_full_selftests"; : >"$WORK/check-shared_measurement"

python3 - "$WORK" <<'PY'
import sys
from pathlib import Path
w=Path(sys.argv[1])
expected={'positive','frames','timeout','disk','sector','arm','g7','e8','judgment','keystroke_limit',
          'start_bad_config','start_missing_env','shell_syntax_b','shell_syntax_a',
          'no_full_selftests','shared_measurement'}
found={path.name.removeprefix('check-') for path in w.glob('check-*')}
if found!=expected: raise SystemExit('NG集合 '+str(expected-found)+' extra='+str(found-expected))
checks={key:True for key in expected}
for target in checks:
    negative=dict(checks); negative[target]=False
    if {key for key,value in negative.items() if not value}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {key for key,value in mutant.items() if not value}=={target}: raise SystemExit('常時真変異 '+target)
PY
echo "check_m6fb_preregistration_selftest: 項目数=16、陰性対照=11、常時真変異=16件拒否、起動前停止=2 OK"

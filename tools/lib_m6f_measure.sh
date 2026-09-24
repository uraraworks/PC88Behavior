#!/usr/bin/env bash
# m6f-a/m6f-b 共通の測定部品。呼出側は gate_failed と M6F_* を定義する。

m6f_cfg() {
  awk -F '\t' -v key="$2" '$1==key {if (++n==1) v=$2} END {if (n==1) print v; else exit 1}' "$1"
}

m6f_keyed_cfg() {
  awk -F '\t' -v key="$2" -v subkey="$3" \
    '$1==key && index($2,subkey ":")==1 {if (++n==1) print substr($2,length(subkey)+2)} END {if (n!=1) exit 1}' "$1"
}

m6f_sha256() {
  python3 - "$1" <<'PY'
import hashlib,sys
h=hashlib.sha256()
with open(sys.argv[1],'rb') as f:
    for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
print(h.hexdigest())
PY
}

m6f_check_output_paths() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys
from pathlib import Path
repo=Path(sys.argv[1]).resolve()
for raw in sys.argv[2:]:
    path=Path(raw).resolve(strict=False)
    try: path.relative_to(repo)
    except ValueError: continue
    raise SystemExit(1)
PY
}

m6f_prepare_disk() {
  local disk="$1"
  local initial
  cp "$M6F_REFERENCE" "$disk" || gate_failed copy
  chmod u+w "$disk" || gate_failed copy_mode
  initial="$(m6f_sha256 "$disk")" || gate_failed copy_sha
  [ "$initial" = "$M6F_REFERENCE_SHA" ] || gate_failed G5
  # 参照像の値は読まず、使い捨て複製の D88 ヘッダ26バイト目だけを解除する。
  printf '\x00' | dd of="$disk" bs=1 seek=26 count=1 conv=notrunc status=none \
    || gate_failed clear_write_protect
  # G5b: 相違位置は無し、または解除した offset 26 だけでなければならない。
  python3 - "$M6F_REFERENCE" "$disk" <<'PY_G5B' || gate_failed G5b
import sys
a = open(sys.argv[1], "rb").read(); b = open(sys.argv[2], "rb").read()
if len(a) != len(b):
    raise SystemExit(1)
offsets = [i for i in range(len(a)) if a[i] != b[i]]
if offsets not in ([], [26]):
    raise SystemExit(1)
PY_G5B
  M6F_INITIAL_SHA="$initial"
}

m6f_run_one() {
  # bash 3.2 対応: 後続変数は arm/run の宣言と分ける。
  local arm="$1" run="$2"
  local disk="$M6F_WORK/$arm-r$run.d88"
  local iolog="$M6F_WORK/$arm-r$run.iolog.txt"
  local report="$M6F_WORK/$arm-r$run.report.txt"
  local stdout="$M6F_WORK/$arm-r$run.stdout.txt"
  local stderr="$M6F_WORK/$arm-r$run.stderr.txt"
  local raw="$M6F_RAW_DIR/$arm-r$run.diff.json"
  local safe="$M6F_WORK/$arm-r$run.safe.json"
  local stimulus initial after_ref
  stimulus="$(m6f_keyed_cfg "$M6F_CONFIG" keystrokes "$arm")" || gate_failed stimulus
  m6f_prepare_disk "$disk"
  initial="$M6F_INITIAL_SHA"
  local qargs=(--core "$M6F_CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk"
    --save-to-disk-image --frames "$M6F_FRAMES" --io-log "$iolog" --out "$report"
    --type-at "$M6F_BOOT_FRAME" --type '\n')
  if [ -n "$stimulus" ]; then
    qargs+=(--type-at "$M6F_STIMULUS_FRAME" --type "$stimulus")
  fi
  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$M6F_TIMEOUT" "$M6F_FRONTEND" "${qargs[@]}" \
    >"$stdout" 2>"$stderr" || gate_failed emulator_run
  # 画面レポートは存在だけを確認し、内容は開かない。
  [ -e "$report" ] && [ -s "$iolog" ] || gate_failed measurement_artifact
  after_ref="$(m6f_sha256 "$M6F_REFERENCE")" || gate_failed reference_sha_after
  [ "$after_ref" = "$M6F_REFERENCE_SHA" ] || gate_failed reference_changed
  python3 "$M6F_REPO/tools/d88_diff.py" "$M6F_REFERENCE" "$disk" --output "$raw" \
    || gate_failed G6_diff
  python3 - "$M6F_REPO" "$arm" "$run" "$iolog" "$raw" "$safe" \
    "$M6F_REFERENCE_SHA" "$initial" "$(m6f_sha256 "$disk")" "$M6F_CONTROL_ARM" <<'PY' \
    || gate_failed safe_summary
import hashlib,json,sys
from pathlib import Path
repo=Path(sys.argv[1]); sys.path.insert(0,str(repo/'tools'))
from analyze_main_to_sub import parse_iolog
from analyze_write_path import parse_commands
arm,run,iolog,raw,out,refsha,initial,final,control=sys.argv[2:]
rows,masked=parse_iolog(Path(iolog))
if sum(masked.values()): raise SystemExit(1)
commands=parse_commands(rows); writes=sum(c.opcode==0x05 for c in commands)
diff=json.load(open(raw,encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
changed_sectors=int(diff['changed_sectors']); changed_bytes=int(diff['changed_bytes'])
reached=True if arm==control else writes>0 and changed_bytes>0
body={'arm':arm,'repetition':int(run),'write_data_count':writes,
      'changed_sector_count':changed_sectors,'changed_byte_count':changed_bytes,
      'reached':reached,'reference_unchanged':refsha==initial,
      'reference_sha256':refsha,'copy_initial_sha256':initial,
      'copy_final_sha256':final,'diff_sha256':sha(raw),'iolog_sha256':sha(iolog)}
with open(out,'x',encoding='utf-8') as f: json.dump(body,f,sort_keys=True,separators=(',',':'))
PY
}

#!/usr/bin/env bash
# m7dv/m7dx/m7dyの事前登録どおり、自作空ファイル本数ラダーを駆動する。
# 生ログ・画面・媒体複製はPC88_LADDER_WORK_DIRだけへ置く。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$REPO/tools/ladder_dirfiles.py"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRAMES=9000
ENTRY_FRAME=700
TIMEOUT=300
DISK_NAME=N88_FE.D88

usage() {
  cat <<'EOF'
使い方:
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh init
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh calibrate
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh build 8|16|...|64
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh measure N
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh probe-create BASE NAME LABEL MARKER success|failure [FRAMES]
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh terminal-verify K [FRAMES]
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh full-verify K [FRAMES]
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh full-verify-selftest K [FRAMES]
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh m7ed-verify K [FRAMES]
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh measure-terminal N K
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh rebuild-candidate N
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh single-open N
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh summary N...
  tools/ladder_dirfiles.sh selftest

作業領域に既定値はない。参照ROM/ディスクはPC88_REF_ROM_DIR/
PC88_REF_DISK_DIRを使い、未設定時だけmeasure.shと同じリポジトリ内規定位置を使う。
自作媒体系列ではPC88_M7EB_WORK_DIRとPC88_LADDER_SOURCE_DISKを明示する。
EOF
}

die() { printf '不合格: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

if [ "${1:-}" = selftest ]; then
  exec "$REPO/tools/ladder_dirfiles_selftest.sh"
fi

if [ -n "${PC88_LADDER_WORK_DIR:-}" ]; then
  WORK="$PC88_LADDER_WORK_DIR"
elif [ -n "${PC88_M7EB_WORK_DIR:-}" ]; then
  WORK="$PC88_M7EB_WORK_DIR"
else
  die "PC88_LADDER_WORK_DIRまたはPC88_M7EB_WORK_DIRを明示してください"
fi
case "$WORK" in /*) ;; *) die "PC88_LADDER_WORK_DIRは絶対パスで指定してください" ;; esac
[ "$WORK" != / ] || die "作業領域に/は指定できません"
ROM_DIR="${PC88_REF_ROM_DIR:-$REPO/private/rom}"
DISK_DIR="${PC88_REF_DISK_DIR:-$REPO/private/disk}"
SOURCE_DISK="${PC88_LADDER_SOURCE_DISK:-$DISK_DIR/$DISK_NAME}"
BOOT_DISK="${PC88_LADDER_BOOT_DISK:-}"
NAME_PREFIX="${PC88_LADDER_NAME_PREFIX:-}"
FILES_COMMAND="${PC88_LADDER_FILES_COMMAND:-FILES}"
MANIFEST="$WORK/manifest.jsonl"
mkdir -p "$WORK/checkpoints" "$WORK/raw" "$WORK/safe" "$WORK/archive"
[ -d "$ROM_DIR" ] || die "参照ROMディレクトリが無い"
[ -f "$SOURCE_DISK" ] || die "参照ディスクが無い"
[ -z "$BOOT_DISK" ] || [ -f "$BOOT_DISK" ] || die "起動ディスクが無い"
[ -x "$FRONTEND" ] || make -s -C "$REPO/tools/harness/frontend"
CORE=""
for candidate in "$VENDOR"/quasi88_libretro.*; do
  if [ -f "$candidate" ]; then CORE="$candidate"; break; fi
done
[ -n "$CORE" ] || die "測定コアが無い"

name_for_n() {
  local n="$1" a b
  a=$((65 + (n - 1) / 26)); b=$((65 + (n - 1) % 26))
  printf 'QD'
  printf "$(printf '\\%03o' "$a")$(printf '\\%03o' "$b")"
}

file_ref() { printf '%s%s' "$NAME_PREFIX" "$1"; }

checkpoint() { printf '%s/checkpoints/n%03d.d88' "$WORK" "$1"; }

record_json() {
  local out="$1" stage="$2" n="$3" accepted="$4" media="${5:-}" summary="${6:-}"
  python3 - "$out" "$stage" "$n" "$accepted" "$media" "$summary" <<'PY'
import json, sys
out, stage, n, accepted, media, summary = sys.argv[1:]
record = {"schema": 1, "stage": stage, "n": int(n),
          "accepted": accepted == "true"}
if media:
    record["media_sha256"] = media
if summary:
    data = json.load(open(summary, encoding="utf-8"))
    for key, value in data.items():
        if key not in {"schema", "accepted"}:
            record[key] = value
with open(out, "w", encoding="utf-8") as fp:
    json.dump(record, fp, ensure_ascii=False, sort_keys=True)
    fp.write("\n")
PY
  python3 "$HELPER" manifest-add --manifest "$MANIFEST" --record "$out"
}

run_frontend() {
  local label="$1" disk="$2" save="$3" text="$4"
  local run_frames="${5:-$FRAMES}"
  shift 4
  local dir="$WORK/raw/$label" rc=0 start_ns end_ns
  mkdir -p "$dir"
  : >"$dir/stdout.txt"; : >"$dir/stderr.txt"
  local save_args=() disk_args=(--disk "$disk") boot_before=""
  [ "$save" = yes ] && save_args=(--save-to-disk-image)
  if [ -n "$BOOT_DISK" ]; then
    disk_args=(--disk "$BOOT_DISK" --disk2 "$disk")
    boot_before="$(python3 "$HELPER" media-sha "$BOOT_DISK")"
  fi
  start_ns="$(python3 -c 'import time; print(time.monotonic_ns())')"
  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" \
    "$FRONTEND" --core "$CORE" --rom-dir "$ROM_DIR" "${disk_args[@]}" \
    ${save_args[@]+"${save_args[@]}"} --frames "$run_frames" --io-log "$dir/iolog.txt" \
    --out "$dir/report.txt" --type-at 300 --type '\n' \
    --type-at "$ENTRY_FRAME" --type "$text" \
    >"$dir/stdout.txt" 2>"$dir/stderr.txt" || rc=$?
  end_ns="$(python3 -c 'import time; print(time.monotonic_ns())')"
  LAST_WALL_MILLIS=$(( (end_ns - start_ns) / 1000000 ))
  LAST_Q88_RC="$rc"
  LAST_RUN_FRAMES="$run_frames"
  if [ -n "$BOOT_DISK" ]; then
    [ "$boot_before" = "$(python3 "$HELPER" media-sha "$BOOT_DISK")" ] \
      || die "$label でドライブ1媒体SHAが変化"
  fi
  # 既知の終了時異常でも成果物が完全なら判定器へ渡す。欠落なら不合格。
  [ -s "$dir/report.txt" ] && [ -s "$dir/iolog.txt" ] || return "${rc:-1}"
  return 0
}

analyze_one() {
  local label="$1" kind="$2" marker="$3" out="$4"
  shift 4
  local args=()
  while [ "$#" -gt 0 ]; do args+=(--typed "$1"); shift; done
  local marker_args=()
  [ -n "$marker" ] && marker_args=(--marker "$marker")
  python3 "$HELPER" analyze --report "$WORK/raw/$label/report.txt" \
    --iolog "$WORK/raw/$label/iolog.txt" --kind "$kind" \
    ${marker_args[@]+"${marker_args[@]}"} ${args[@]+"${args[@]}"} --out "$out"
}

run_pair() {
  local prefix="$1" disk="$2" kind="$3" text="$4" marker="$5"
  shift 5
  local run label out
  for run in 1 2; do
    label="${prefix}-r${run}"
    local run_disk="$WORK/raw/${label}.d88"
    local stamp="$(date +%Y%m%d%H%M%S).$$.$run"
    if [ -e "$run_disk" ]; then
      mv "$run_disk" "$WORK/archive/${label}.$stamp.d88"
    fi
    if [ -d "$WORK/raw/$label" ]; then
      mv "$WORK/raw/$label" "$WORK/archive/${label}.$stamp.raw"
    fi
    cp "$disk" "$run_disk"
    run_frontend "$label" "$run_disk" no "$text" || die "$label が到達前に終了"
    out="$WORK/safe/${label}.json"
    analyze_one "$label" "$kind" "$marker" "$out" "$@" || die "$label を不合格に判定"
  done
  python3 "$HELPER" pair --a "$WORK/safe/${prefix}-r1.json" \
    --b "$WORK/safe/${prefix}-r2.json" --out "$WORK/safe/${prefix}.json" \
    || die "$prefix の2runが完全一致しない"
}

files_pair() {
  local n="$1" disk="$2" prefix
  prefix="files-n$(printf '%03d' "$n")"
  run_pair "$prefix" "$disk" files "$FILES_COMMAND"$'\n' ""
  if [ "$n" -gt 0 ]; then
    local prev="$WORK/safe/files-n$(printf '%03d' $((n - 1))).json"
    [ -f "$prev" ] || die "N=$((n - 1))のFILES基準が無い"
    python3 - "$prev" "$WORK/safe/$prefix.json" <<'PY' || exit 1
import json, sys
a, b = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:])
keys = ("screen_lines", "screen_chars", "screen_sha256")
raise SystemExit(0 if any(a[k] != b[k] for k in keys) else 1)
PY
    [ "$?" -eq 0 ] || die "N=${n}のFILES成果物がN=$((n - 1))から不変"
  fi
  local rec="$WORK/safe/record-files-n$(printf '%03d' "$n").json"
  record_json "$rec" files "$n" true "" "$WORK/safe/$prefix.json"
}

cmd_init() {
  local cp0; cp0="$(checkpoint 0)"
  if python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n 0 --disk "$cp0" 2>/dev/null; then
    note "N=0チェックポイントはmanifestとSHA-256が一致（再利用）"
    return
  fi
  if [ -e "$cp0" ]; then
    mv "$cp0" "$WORK/archive/n000.$(date +%Y%m%d%H%M%S).d88"
  fi
  cp "$SOURCE_DISK" "$cp0"
  chmod u+w "$cp0"
  printf '\x00' | dd of="$cp0" bs=1 seek=26 count=1 conv=notrunc status=none
  chmod a-w "$cp0"
  local digest rec="$WORK/safe/record-checkpoint-n000.json"
  digest="$(python3 "$HELPER" media-sha "$cp0")"
  record_json "$rec" checkpoint 0 true "$digest"
  note "N=0基準複製を作成し、媒体SHA-256をmanifestへ記録"
}

missing_ref="$(file_ref QZ9X)"
missing_text="10 ON ERROR GOTO 100\n20 OPEN \"$missing_ref\" FOR INPUT AS #1\n30 PRINT \"D9N\":END\n100 IF ERL<>20 THEN PRINT \"D9N\":END\n110 PRINT \"D9E\"\n120 RESUME 130\n130 PRINT \"D9C\":END\nRUN\n"
missing_typed=(
  '10 ON ERROR GOTO 100'
  "20 OPEN \"$missing_ref\" FOR INPUT AS #1"
  '30 PRINT "D9N":END'
  '100 IF ERL<>20 THEN PRINT "D9N":END'
  '110 PRINT "D9E"'
  '120 RESUME 130'
  '130 PRINT "D9C":END'
  'RUN'
)

cmd_calibrate() {
  cmd_init
  local cp0; cp0="$(checkpoint 0)"
  run_pair calibration-n000 "$cp0" missing "$missing_text" "" "${missing_typed[@]}"
  local rec="$WORK/safe/record-calibration-n000.json"
  record_json "$rec" calibration 0 true "" "$WORK/safe/calibration-n000.json"
  note "N=0校正合格: 固定不存在名のOPENはD9E/D9C/Okへ到達"
  files_pair 0 "$cp0"
}

archive_block() {
  local start="$1" end="$2" n path stamp
  stamp="$(date +%Y%m%d%H%M%S)"
  for ((n=start; n<=end; n++)); do
    path="$(checkpoint "$n")"
    if [ -e "$path" ]; then mv "$path" "$WORK/archive/n$(printf '%03d' "$n").$stamp.d88"; fi
  done
}

build_block() {
  local start="$1" end="$2" anchor=$((start - 1))
  local anchor_disk; anchor_disk="$(checkpoint "$anchor")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$anchor" \
    --disk "$anchor_disk" || die "N=${anchor}アンカーが未受理またはSHA不一致"
  archive_block "$start" "$end"
  local n prev cand name marker text label safe digest rec
  for ((n=start; n<=end; n++)); do
    prev="$(checkpoint $((n - 1)))"; cand="$(checkpoint "$n")"
    cp "$prev" "$cand"; chmod u+w "$cand"
    name="$(file_ref "$(name_for_n "$n")")"; marker="C$(printf '%03d' "$n")"
    text="10 OPEN \"$name\" FOR OUTPUT AS #1:CLOSE #1\n20 PRINT \"$marker\":END\nRUN\n"
    label="create-n$(printf '%03d' "$n")"
    run_frontend "$label" "$cand" yes "$text" || die "N=${n}作成runが到達前に終了"
    safe="$WORK/safe/$label.json"
    analyze_one "$label" create "$marker" "$safe" \
      "10 OPEN \"$name\" FOR OUTPUT AS #1:CLOSE #1" \
      "20 PRINT \"$marker\":END" RUN || die "N=${n}作成run不合格"
    chmod a-w "$cand"
    digest="$(python3 "$HELPER" media-sha "$cand")"
    local prev_digest; prev_digest="$(python3 "$HELPER" media-sha "$prev")"
    [ "$digest" != "$prev_digest" ] || die "N=${n}媒体SHAがN=$((n - 1))と同一"
    rec="$WORK/safe/record-checkpoint-n$(printf '%03d' "$n").json"
    record_json "$rec" checkpoint "$n" true "$digest" "$safe"
    files_pair "$n" "$cand"
    note "N=$n 作成・WRITE非0・媒体SHA差・FILES各2run一致"
  done

  local verify_text="" verify_typed=() line block_start=$((end - 7))
  for ((n=block_start; n<=end; n++)); do
    name="$(file_ref "$(name_for_n "$n")")"
    line="$(printf '%d' $((10 + (n - block_start) * 10))) OPEN \"$name\" FOR INPUT AS #1:CLOSE #1"
    verify_text+="$line\n"; verify_typed+=("$line")
  done
  marker="V$(printf '%03d' "$end")"
  line="90 PRINT \"$marker\":END"; verify_text+="$line\nRUN\n"; verify_typed+=("$line" RUN)
  label="verify-n$(printf '%03d' "$end")"
  local verify_disk="$WORK/raw/${label}.d88"
  local verify_stamp="$(date +%Y%m%d%H%M%S).$$"
  if [ -e "$verify_disk" ]; then
    mv "$verify_disk" "$WORK/archive/${label}.$verify_stamp.d88"
  fi
  if [ -d "$WORK/raw/$label" ]; then
    mv "$WORK/raw/$label" "$WORK/archive/${label}.$verify_stamp.raw"
  fi
  cp "$(checkpoint "$end")" "$verify_disk"
  run_frontend "$label" "$verify_disk" no "$verify_text" || die "N=${end}末端OPEN検証が到達前に終了"
  safe="$WORK/safe/$label.json"
  analyze_one "$label" verify "$marker" "$safe" "${verify_typed[@]}" \
    || die "N=${end}末端OPEN検証不合格"
  rec="$WORK/safe/record-block-n$(printf '%03d' "$end").json"
  record_json "$rec" block "$end" true "" "$safe"
  note "N=${end}ブロック末端: 新規8名の全OPEN検証合格、ブロック受理"
}

cmd_build() {
  local target="${1:-}"; [[ "$target" =~ ^(8|16|24|32|40|48|56|64)$ ]] \
    || die "build上限は8の倍数（8〜64）で指定"
  cmd_init
  if python3 "$HELPER" status --manifest "$MANIFEST" --stage calibration --n 0 2>/dev/null \
     && python3 "$HELPER" status --manifest "$MANIFEST" --stage files --n 0 2>/dev/null \
     && [ -f "$WORK/safe/files-n000.json" ]; then
    note "N=0校正・FILES基準は受理済み（再利用）"
  else
    cmd_calibrate
  fi
  local end start
  for ((end=8; end<=target; end+=8)); do
    if python3 "$HELPER" status --manifest "$MANIFEST" --stage block --n "$end" 2>/dev/null \
       && python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$end" \
          --disk "$(checkpoint "$end")" 2>/dev/null; then
      note "N=${end}ブロックは受理済み（再利用）"
      continue
    fi
    start=$((end - 7)); build_block "$start" "$end"
  done
}

cmd_measure() {
  local n="${1:-}"; [[ "$n" =~ ^([0-9]|[1-5][0-9]|6[0-4])$ ]] || die "Nは0〜64"
  local block=$(( (n + 7) / 8 * 8 ))
  [ "$n" -eq 0 ] || python3 "$HELPER" status --manifest "$MANIFEST" --stage block --n "$block" \
    || die "N=${n}を含むブロックが未受理"
  local disk; disk="$(checkpoint "$n")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$n" --disk "$disk" \
    || die "N=${n}チェックポイントが未受理またはSHA不一致"
  local prefix="missing-n$(printf '%03d' "$n")"
  run_pair "$prefix" "$disk" missing "$missing_text" "" "${missing_typed[@]}"
  local rec="$WORK/safe/record-measure-n$(printf '%03d' "$n").json"
  record_json "$rec" measure "$n" true "" "$WORK/safe/$prefix.json"
  note "N=$n 不存在OPEN公式2run合格・完全一致"
}

cmd_probe_create() {
  local base="${1:-}" name="${2:-}" label="${3:-}" marker="${4:-}" expect="${5:-}"
  local probe_frames="${6:-$FRAMES}"
  [[ "$base" =~ ^([0-9]|[1-5][0-9]|6[0-4])$ ]] || die "probe-createのBASEは0〜64"
  [[ "$name" =~ ^[A-Z0-9]{1,6}$ ]] || die "probe-createのNAMEは英大文字・数字1〜6文字"
  [[ "$label" =~ ^[a-z0-9-]+$ ]] || die "probe-createのLABELが不正"
  [[ "$marker" =~ ^[A-Z0-9]{1,6}$ ]] || die "probe-createのMARKERが不正"
  [ "$expect" = success ] || [ "$expect" = failure ] || die "期待分類はsuccess|failure"
  [[ "$probe_frames" =~ ^[0-9]+$ ]] && [ "$probe_frames" -gt 0 ] || die "FRAMESは正整数"
  local source; source="$(checkpoint "$base")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$base" --disk "$source" \
    || die "probe-createの基準チェックポイントが未受理"
  local run_label="probe-$label" disk="$WORK/raw/probe-$label.d88"
  local stamp="$(date +%Y%m%d%H%M%S).$$"
  if [ -e "$disk" ]; then mv "$disk" "$WORK/archive/probe-$label.$stamp.d88"; fi
  if [ -d "$WORK/raw/$run_label" ]; then
    mv "$WORK/raw/$run_label" "$WORK/archive/probe-$label.$stamp.raw"
  fi
  cp "$source" "$disk"; chmod u+w "$disk"
  local before after text safe ref rc=0
  ref="$(file_ref "$name")"
  before="$(python3 "$HELPER" media-sha "$disk")"
  text="10 OPEN \"$ref\" FOR OUTPUT AS #1:CLOSE #1\n20 PRINT \"$marker\":END\nRUN\n"
  run_frontend "$run_label" "$disk" yes "$text" "$probe_frames" || die "$label が到達前に終了"
  safe="$WORK/safe/probe-$label.json"
  analyze_one "$run_label" create "$marker" "$safe" \
    "10 OPEN \"$ref\" FOR OUTPUT AS #1:CLOSE #1" \
    "20 PRINT \"$marker\":END" RUN || rc=$?
  after="$(python3 "$HELPER" media-sha "$disk")"
  python3 - "$safe" "$base" "$ref" "$label" "$before" "$after" \
    "$LAST_RUN_FRAMES" "$LAST_WALL_MILLIS" "$LAST_Q88_RC" <<'PY'
import json,sys
p,base,name,label,before,after,frames,wall_ms,process_rc=sys.argv[1:]
x=json.load(open(p,encoding='utf-8'))
x.update({"probe_base_n":int(base),"probe_name":name,"probe_label":label,
          "media_changed":before!=after,"media_before_sha256":before,
          "media_after_sha256":after,"completed_frames":int(frames),
          "wall_millis":int(wall_ms),"process_rc":int(process_rc)})
with open(p,'w',encoding='utf-8') as f:
 json.dump(x,f,ensure_ascii=False,sort_keys=True); f.write('\n')
PY
  # 対照用媒体複製は系列へ使わず、集計後に明示的に破棄する。
  rm -f "$disk"
  python3 - "$safe" "$expect" "$rc" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); expect=sys.argv[2]
if expect=='success':
 ok=(x['accepted'] and x['screen_classification']=='normal_success'
     and x['write_count']>0 and x['media_changed']
     and x['main_dropped']==0 and x['sub_dropped']==0)
else:
 ok=(not x['accepted'] and x['screen_classification']=='error_display'
     and x['ok_after_error'] and x['write_count']==0 and not x['media_changed']
     and x['main_dropped']==0 and x['sub_dropped']==0)
print('分類=%s Ok直後=%s WRITE=%d 媒体差=%s 取りこぼし=%d/%d' %
      (x['screen_classification'],x['ok_after_error'],x['write_count'],
       x['media_changed'],x['main_dropped'],x['sub_dropped']))
raise SystemExit(0 if ok else 1)
PY
}

cmd_terminal_verify() {
  local k="${1:-}"; [[ "$k" =~ ^([1-9]|[1-5][0-9]|6[0-4])$ ]] || die "Kは1〜64"
  local verify_frames="${2:-$FRAMES}"
  [[ "$verify_frames" =~ ^[0-9]+$ ]] && [ "$verify_frames" -gt 0 ] || die "FRAMESは正整数"
  local disk_source; disk_source="$(checkpoint "$k")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$k" --disk "$disk_source" \
    || die "K=${k}チェックポイントが未受理"
  local marker="V$(printf '%03d' "$k")" label="terminal-verify-n$(printf '%03d' "$k")"
  [ "$verify_frames" -eq "$FRAMES" ] || label="${label}-f${verify_frames}"
  local text line disk="$WORK/raw/${label}.d88" safe rec
  text="10 K=$k\n20 FOR I=1 TO K\n30 F\$=\"QD\"+CHR\$(65+INT((I-1)/26))+CHR\$(65+((I-1) MOD 26))\n40 OPEN F\$ FOR INPUT AS #1:CLOSE #1\n50 NEXT I\n60 PRINT \"$marker\":END\nRUN\n"
  if [ -e "$disk" ]; then mv "$disk" "$WORK/archive/${label}.$(date +%Y%m%d%H%M%S).$$.d88"; fi
  if [ -d "$WORK/raw/$label" ]; then
    mv "$WORK/raw/$label" "$WORK/archive/${label}.$(date +%Y%m%d%H%M%S).$$.raw"
  fi
  cp "$disk_source" "$disk"
  run_frontend "$label" "$disk" no "$text" "$verify_frames" || die "K=${k}末端検証が到達前に終了"
  safe="$WORK/safe/$label.json"
  local analyze_rc=0
  analyze_one "$label" verify "$marker" "$safe" \
    "10 K=$k" "20 FOR I=1 TO K" \
    '30 F$="QD"+CHR$(65+INT((I-1)/26))+CHR$(65+((I-1) MOD 26))' \
    '40 OPEN F$ FOR INPUT AS #1:CLOSE #1' '50 NEXT I' \
    "60 PRINT \"$marker\":END" RUN || analyze_rc=$?
  python3 - "$safe" "$LAST_RUN_FRAMES" "$LAST_WALL_MILLIS" "$LAST_Q88_RC" <<'PY'
import json,sys
p,frames,wall_ms,process_rc=sys.argv[1:]
x=json.load(open(p,encoding='utf-8'))
x.update({"completed_frames":int(frames),"wall_millis":int(wall_ms),
          "process_rc":int(process_rc)})
with open(p,'w',encoding='utf-8') as f:
 json.dump(x,f,ensure_ascii=False,sort_keys=True); f.write('\n')
PY
  [ "$analyze_rc" -eq 0 ] || return 1
  rec="$WORK/safe/record-terminal-block-n$(printf '%03d' "$k").json"
  record_json "$rec" terminal-block "$k" true "" "$safe"
  note "K=${k}終端全名OPEN検証合格"
}

# m7dv規則4のN=1..Kを、1run最大8名のリテラルOPENへ分割して検査する。
# 全chunkの固有マーカー到達を要求するため、名前検査の省略はない。
full_verify_disk() {
  local k="$1" disk_source="$2" prefix="$3" verify_frames="$4"
  local start end n line marker text label disk safe stamp
  local checked_names=() chunk_safes=()
  for ((start=1; start<=k; start+=8)); do
    end=$((start + 7)); [ "$end" -le "$k" ] || end="$k"
    text=""; local typed=()
    for ((n=start; n<=end; n++)); do
      local name; name="$(file_ref "$(name_for_n "$n")")"; checked_names+=("$name")
      line="$(printf '%d' $((10 + (n - start) * 10))) OPEN \"$name\" FOR INPUT AS #1:CLOSE #1"
      text+="$line\n"; typed+=("$line")
    done
    marker="V$(printf '%02d%02d' "$k" "$start")"
    line="90 PRINT \"$marker\":END"; text+="$line\nRUN\n"; typed+=("$line" RUN)
    label="${prefix}-c$(printf '%03d' "$start")-$(printf '%03d' "$end")"
    disk="$WORK/raw/${label}.d88"; stamp="$(date +%Y%m%d%H%M%S).$$"
    if [ -e "$disk" ]; then mv "$disk" "$WORK/archive/${label}.${stamp}.d88"; fi
    if [ -d "$WORK/raw/$label" ]; then
      mv "$WORK/raw/$label" "$WORK/archive/${label}.${stamp}.raw"
    fi
    cp "$disk_source" "$disk"
    run_frontend "$label" "$disk" no "$text" "$verify_frames" \
      || die "K=${k} 全名検証chunk ${start}-${end}が到達前に終了"
    safe="$WORK/safe/${label}.json"
    analyze_one "$label" verify "$marker" "$safe" "${typed[@]}" || return 1
    chunk_safes+=("$safe")
  done

  local aggregate="$WORK/safe/${prefix}.json"
  python3 - "$aggregate" "$k" "${#checked_names[@]}" \
    "${checked_names[@]}" -- "${chunk_safes[@]}" <<'PY'
import hashlib,json,sys
out=sys.argv[1]; k=int(sys.argv[2]); count=int(sys.argv[3]); args=sys.argv[4:]
sep=args.index('--'); names=args[:sep]; paths=args[sep+1:]
chunks=[]
for path in paths:
 data=json.load(open(path,encoding='utf-8'))
 if not data.get('accepted'):
  raise SystemExit(1)
 chunks.append({'marker':data['marker'],'accepted':True,
                'safe_sha256':hashlib.sha256(open(path,'rb').read()).hexdigest()})
if len(names)!=count or count!=k or len(set(names))!=k:
 raise SystemExit(1)
blob=json.dumps(names,ensure_ascii=True,separators=(',',':')).encode('ascii')
result={'schema':1,'accepted':True,'k':k,'checked_count':count,
        'checked_names':names,'checked_names_sha256':hashlib.sha256(blob).hexdigest(),
        'chunk_count':len(chunks),'chunks':chunks}
with open(out,'w',encoding='utf-8') as f:
 json.dump(result,f,ensure_ascii=False,sort_keys=True); f.write('\n')
PY
}

cmd_full_verify() {
  local k="${1:-}" verify_frames="${2:-$FRAMES}"
  [[ "$k" =~ ^([1-9]|[1-5][0-9]|6[0-4])$ ]] || die "Kは1〜64"
  [[ "$verify_frames" =~ ^[0-9]+$ ]] && [ "$verify_frames" -gt 0 ] || die "FRAMESは正整数"
  local disk; disk="$(checkpoint "$k")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$k" --disk "$disk" \
    || die "K=${k}チェックポイントが未受理"
  local prefix="full-verify-k$(printf '%03d' "$k")"
  full_verify_disk "$k" "$disk" "$prefix" "$verify_frames" \
    || die "K=${k} 修正版全名OPEN検証不合格"
  local rec="$WORK/safe/record-full-block-n$(printf '%03d' "$k").json"
  record_json "$rec" full-block "$k" true "" "$WORK/safe/${prefix}.json"
  note "K=${k} 修正版全名OPEN検証合格（N=1..${k}、省略なし）"
}

cmd_full_verify_selftest() {
  local k="${1:-}" verify_frames="${2:-$FRAMES}"
  [[ "$k" =~ ^([1-9]|[1-5][0-9]|6[0-4])$ ]] || die "Kは1〜64"
  cmd_full_verify "$k" "$verify_frames"

  local source; source="$(checkpoint "$k")"
  local label="full-control-kill-k$(printf '%03d' "$k")"
  local disk="$WORK/raw/${label}.d88" marker="XKILL" safe before after
  if [ -e "$disk" ]; then mv "$disk" "$WORK/archive/${label}.$(date +%Y%m%d%H%M%S).$$.d88"; fi
  if [ -d "$WORK/raw/$label" ]; then
    mv "$WORK/raw/$label" "$WORK/archive/${label}.$(date +%Y%m%d%H%M%S).$$.raw"
  fi
  cp "$source" "$disk"; chmod u+w "$disk"
  before="$(python3 "$HELPER" media-sha "$disk")"
  local kill_ref; kill_ref="$(file_ref QDAA)"
  local text="10 KILL \"$kill_ref\"\n20 PRINT \"XKILL\":END\nRUN\n"
  run_frontend "$label" "$disk" yes "$text" "$verify_frames" \
    || die "陰性対照の故障注入runが到達前に終了"
  safe="$WORK/safe/${label}.json"
  analyze_one "$label" create "$marker" "$safe" \
    "10 KILL \"$kill_ref\"" '20 PRINT "XKILL":END' RUN \
    || die "陰性対照のKILLが成立しない"
  after="$(python3 "$HELPER" media-sha "$disk")"
  [ "$before" != "$after" ] || die "陰性対照の媒体SHAが変化しない"
  python3 - "$safe" "$before" "$after" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
x.update({'media_before_sha256':sys.argv[2],'media_after_sha256':sys.argv[3],
          'media_changed':sys.argv[2]!=sys.argv[3]})
with open(sys.argv[1],'w',encoding='utf-8') as f:
 json.dump(x,f,ensure_ascii=False,sort_keys=True); f.write('\n')
raise SystemExit(0 if x['accepted'] and x['write_count']>0 and
                 x['media_changed'] and x['main_dropped']==0 and
                 x['sub_dropped']==0 else 1)
PY
  note "陰性対照: 先頭自作名のKILL成立・WRITE非0・媒体SHA差を確認"

  if full_verify_disk "$k" "$disk" "full-control-negative-k$(printf '%03d' "$k")" \
       "$verify_frames"; then
    die "陰性対照を誤って合格にした"
  fi
  rm -f "$disk"
  note "陰性対照: 欠落1本を修正版全名OPEN検証で実際に不合格にした"
}

# m7ed固定規則: 各Kで、受理済みK=8を使った陽性・故障注入陰性対照を
# 対象Kの全名OPEN検証より先に実施する。
cmd_m7ed_verify() {
  local k="${1:-}" verify_frames="${2:-$FRAMES}"
  [[ "$k" =~ ^([1-9]|[1-5][0-9]|6[0-4])$ ]] || die "Kは1〜64"
  [[ "$verify_frames" =~ ^[0-9]+$ ]] && [ "$verify_frames" -gt 0 ] || die "FRAMESは正整数"
  local control; control="$(checkpoint 8)"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n 8 --disk "$control" \
    || die "K=8対照アンカーが未受理"

  full_verify_disk 8 "$control" "m7ed-control-positive-k$(printf '%03d' "$k")" \
    "$verify_frames" || die "K=${k}の陽性対照が不合格"
  note "K=${k}陽性対照: 受理済みK=8の全名OPEN検証合格"

  local label="m7ed-control-kill-k$(printf '%03d' "$k")"
  local disk="$WORK/raw/${label}.d88" marker="XKILL" safe before after kill_ref text
  kill_ref="$(file_ref QDAA)"
  if [ -e "$disk" ]; then mv "$disk" "$WORK/archive/${label}.$(date +%Y%m%d%H%M%S).$$.d88"; fi
  if [ -d "$WORK/raw/$label" ]; then
    mv "$WORK/raw/$label" "$WORK/archive/${label}.$(date +%Y%m%d%H%M%S).$$.raw"
  fi
  cp "$control" "$disk"; chmod u+w "$disk"
  before="$(python3 "$HELPER" media-sha "$disk")"
  text="10 KILL \"$kill_ref\"\n20 PRINT \"XKILL\":END\nRUN\n"
  run_frontend "$label" "$disk" yes "$text" "$verify_frames" \
    || die "K=${k}陰性対照の故障注入runが到達前に終了"
  safe="$WORK/safe/${label}.json"
  analyze_one "$label" create "$marker" "$safe" \
    "10 KILL \"$kill_ref\"" '20 PRINT "XKILL":END' RUN \
    || die "K=${k}陰性対照のKILLが成立しない"
  after="$(python3 "$HELPER" media-sha "$disk")"
  [ "$before" != "$after" ] || die "K=${k}陰性対照の媒体SHAが変化しない"
  python3 - "$safe" "$before" "$after" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
x.update({'media_before_sha256':sys.argv[2],'media_after_sha256':sys.argv[3],
          'media_changed':sys.argv[2]!=sys.argv[3]})
with open(sys.argv[1],'w',encoding='utf-8') as f:
 json.dump(x,f,ensure_ascii=False,sort_keys=True); f.write('\n')
raise SystemExit(0 if x['accepted'] and x['write_count']>0 and
                 x['media_changed'] and x['main_dropped']==0 and
                 x['sub_dropped']==0 else 1)
PY
  note "K=${k}陰性対照: 故障注入でWRITE非0・媒体SHA差を先に確認"
  if full_verify_disk 8 "$disk" "m7ed-control-negative-k$(printf '%03d' "$k")" \
       "$verify_frames"; then
    die "K=${k}陰性対照を誤って合格にした"
  fi
  rm -f "$disk"
  note "K=${k}陰性対照: 欠落1本を全名OPEN検証で実際に不合格にした"

  cmd_full_verify "$k" "$verify_frames"
}

cmd_measure_terminal() {
  local n="${1:-}" k="${2:-}"
  [[ "$n" =~ ^([0-9]|[1-5][0-9]|6[0-4])$ ]] || die "Nは0〜64"
  [[ "$k" =~ ^([1-9]|[1-5][0-9]|6[0-4])$ ]] || die "Kは1〜64"
  [ "$n" -le "$k" ] || die "NはK以下"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage full-block --n "$k" \
    || die "K=${k}修正版全名検証が未受理"
  local disk; disk="$(checkpoint "$n")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$n" --disk "$disk" \
    || die "N=${n}チェックポイントが未受理またはSHA不一致"
  local prefix="missing-n$(printf '%03d' "$n")"
  run_pair "$prefix" "$disk" missing "$missing_text" "" "${missing_typed[@]}"
  local rec="$WORK/safe/record-measure-n$(printf '%03d' "$n").json"
  record_json "$rec" measure "$n" true "" "$WORK/safe/$prefix.json"
  note "N=$n 不存在OPEN公式2run合格・完全一致（K=${k}終端検証採用）"
}

cmd_rebuild_candidate() {
  local target="${1:-}"
  [[ "$target" =~ ^([2-9]|[1-5][0-9]|6[0-4])$ ]] || die "候補Nは2〜64"
  local anchor=$(( (target - 1) / 8 * 8 ))
  local root="$WORK/rebuild/j$(printf '%03d' "$target")"
  local cpdir="$root/checkpoints" n prev cand name marker text label safe before after
  mkdir -p "$cpdir"
  cp "$(checkpoint "$anchor")" "$cpdir/n$(printf '%03d' "$anchor").d88"
  for ((n=anchor + 1; n<=target; n++)); do
    prev="$cpdir/n$(printf '%03d' $((n - 1))).d88"
    cand="$cpdir/n$(printf '%03d' "$n").d88"
    cp "$prev" "$cand"; chmod u+w "$cand"
    before="$(python3 "$HELPER" media-sha "$cand")"
    name="$(file_ref "$(name_for_n "$n")")"; marker="R$(printf '%03d' "$n")"
    text="10 OPEN \"$name\" FOR OUTPUT AS #1:CLOSE #1\n20 PRINT \"$marker\":END\nRUN\n"
    label="rebuild-j$(printf '%03d' "$target")-create-n$(printf '%03d' "$n")"
    run_frontend "$label" "$cand" yes "$text" || die "候補N=${target}の独立再構築N=${n}が到達前に終了"
    safe="$WORK/safe/${label}.json"
    analyze_one "$label" create "$marker" "$safe" \
      "10 OPEN \"$name\" FOR OUTPUT AS #1:CLOSE #1" \
      "20 PRINT \"$marker\":END" RUN || die "候補N=${target}の独立再構築N=${n}が不合格"
    chmod a-w "$cand"
    after="$(python3 "$HELPER" media-sha "$cand")"
    [ "$before" != "$after" ] || die "候補N=${target}の独立再構築N=${n}で媒体SHAが不変"

    local fp="rebuild-j$(printf '%03d' "$target")-files-n$(printf '%03d' "$n")"
    run_pair "$fp" "$cand" files "$FILES_COMMAND"$'\n' ""
    local prior_files
    if [ "$n" -eq $((anchor + 1)) ]; then
      prior_files="$WORK/safe/files-n$(printf '%03d' "$anchor").json"
    else
      prior_files="$WORK/safe/rebuild-j$(printf '%03d' "$target")-files-n$(printf '%03d' $((n - 1))).json"
    fi
    python3 - "$prior_files" "$WORK/safe/${fp}.json" <<'PY' || die "候補の独立再構築FILES成果物が直前Nから不変"
import json,sys
a,b=(json.load(open(p,encoding='utf-8')) for p in sys.argv[1:])
keys=('screen_lines','screen_chars','screen_sha256')
raise SystemExit(0 if any(a[k]!=b[k] for k in keys) else 1)
PY
  done

  for n in $((target - 1)) "$target"; do
    cand="$cpdir/n$(printf '%03d' "$n").d88"
    label="rebuild-j$(printf '%03d' "$target")-missing-n$(printf '%03d' "$n")"
    run_pair "$label" "$cand" missing "$missing_text" "" "${missing_typed[@]}"
  done
  note "候補N=${target}: 8本境界N=${anchor}から独立再構築し、N=$((target - 1))／${target}を各2run測定"
}

cmd_single_open() {
  local n="${1:-}"; [[ "$n" =~ ^([1-9]|[1-5][0-9]|6[0-4])$ ]] || die "Nは1〜64"
  local disk name marker text prefix rec
  disk="$(checkpoint "$n")"; name="$(file_ref "$(name_for_n "$n")")"; marker="S$(printf '%03d' "$n")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$n" --disk "$disk" \
    || die "N=${n}チェックポイントが未受理またはSHA不一致"
  text="10 OPEN \"$name\" FOR INPUT AS #1:CLOSE #1\n20 PRINT \"$marker\":END\nRUN\n"
  prefix="single-open-n$(printf '%03d' "$n")"
  run_pair "$prefix" "$disk" verify "$text" "$marker" \
    "10 OPEN \"$name\" FOR INPUT AS #1:CLOSE #1" \
    "20 PRINT \"$marker\":END" RUN
  rec="$WORK/safe/record-single-open-n$(printf '%03d' "$n").json"
  record_json "$rec" single-open "$n" true "" "$WORK/safe/$prefix.json"
  note "N=$n 自身の自作名INPUT OPEN公式2run合格・完全一致"
}

cmd_summary() {
  local n file prev fc read fdc delta_fc delta_read verdict
  for n in "$@"; do
    file="$WORK/safe/missing-n$(printf '%03d' "$n").json"
    [ -f "$file" ] || die "N=${n}の測定集計が無い"
    read -r fc read fdc < <(python3 - "$file" <<'PY'
import json, sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
print(x["entry_main_in_fc"], x["entry_read_count"], x["entry_fdc_count"])
PY
)
    delta_fc=-; delta_read=-; verdict=基準
    if [ "$n" -gt 0 ]; then
      prev="$WORK/safe/missing-n$(printf '%03d' $((n - 1))).json"
      if [ -f "$prev" ]; then
        read -r delta_fc delta_read < <(python3 - "$prev" "$file" <<'PY'
import json, sys
a,b=(json.load(open(p,encoding="utf-8")) for p in sys.argv[1:])
print(b["entry_main_in_fc"]-a["entry_main_in_fc"], b["entry_read_count"]-a["entry_read_count"])
PY
)
        if [ "$delta_fc" -eq 0 ] && [ "$delta_read" -eq 0 ]; then verdict=ゼロ差分; else verdict=差分変化; fi
      fi
    fi
    printf '%s\t%s\t%s\t%s\t%s/%s\t%s\n' "$n" "$fc" "$read" "$fdc" "$delta_fc" "$delta_read" "$verdict"
  done
}

case "${1:-}" in
  init) cmd_init ;;
  calibrate) cmd_calibrate ;;
  build) cmd_build "${2:-}" ;;
  measure) cmd_measure "${2:-}" ;;
  probe-create) cmd_probe_create "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}" "${7:-}" ;;
  terminal-verify) cmd_terminal_verify "${2:-}" "${3:-}" ;;
  full-verify) cmd_full_verify "${2:-}" "${3:-}" ;;
  full-verify-selftest) cmd_full_verify_selftest "${2:-}" "${3:-}" ;;
  m7ed-verify) cmd_m7ed_verify "${2:-}" "${3:-}" ;;
  measure-terminal) cmd_measure_terminal "${2:-}" "${3:-}" ;;
  rebuild-candidate) cmd_rebuild_candidate "${2:-}" ;;
  single-open) cmd_single_open "${2:-}" ;;
  summary) shift; [ "$#" -gt 0 ] || die "summaryにはNが必要"; cmd_summary "$@" ;;
  *) usage; exit 2 ;;
esac

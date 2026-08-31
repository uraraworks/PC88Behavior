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
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh probe-create BASE NAME LABEL MARKER success|failure
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh terminal-verify K
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh measure-terminal N K
  PC88_LADDER_WORK_DIR=... tools/ladder_dirfiles.sh summary N...
  tools/ladder_dirfiles.sh selftest

作業領域に既定値はない。参照ROM/ディスクはPC88_REF_ROM_DIR/
PC88_REF_DISK_DIRを使い、未設定時だけmeasure.shと同じリポジトリ内規定位置を使う。
EOF
}

die() { printf '不合格: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

if [ "${1:-}" = selftest ]; then
  exec "$REPO/tools/ladder_dirfiles_selftest.sh"
fi

: "${PC88_LADDER_WORK_DIR:?PC88_LADDER_WORK_DIRを明示してください}"
WORK="$PC88_LADDER_WORK_DIR"
case "$WORK" in /*) ;; *) die "PC88_LADDER_WORK_DIRは絶対パスで指定してください" ;; esac
[ "$WORK" != / ] || die "作業領域に/は指定できません"
ROM_DIR="${PC88_REF_ROM_DIR:-$REPO/private/rom}"
DISK_DIR="${PC88_REF_DISK_DIR:-$REPO/private/disk}"
SOURCE_DISK="$DISK_DIR/$DISK_NAME"
MANIFEST="$WORK/manifest.jsonl"
mkdir -p "$WORK/checkpoints" "$WORK/raw" "$WORK/safe" "$WORK/archive"
[ -d "$ROM_DIR" ] || die "参照ROMディレクトリが無い"
[ -f "$SOURCE_DISK" ] || die "参照ディスクが無い"
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
  shift 4
  local dir="$WORK/raw/$label" rc=0
  mkdir -p "$dir"
  : >"$dir/stdout.txt"; : >"$dir/stderr.txt"
  local save_args=()
  [ "$save" = yes ] && save_args=(--save-to-disk-image)
  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" \
    "$FRONTEND" --core "$CORE" --rom-dir "$ROM_DIR" --disk "$disk" \
    ${save_args[@]+"${save_args[@]}"} --frames "$FRAMES" --io-log "$dir/iolog.txt" \
    --out "$dir/report.txt" --type-at 300 --type '\n' \
    --type-at "$ENTRY_FRAME" --type "$text" \
    >"$dir/stdout.txt" 2>"$dir/stderr.txt" || rc=$?
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
  run_pair "$prefix" "$disk" files $'FILES\n' ""
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

missing_text=$'10 ON ERROR GOTO 100\n20 OPEN "QZ9X" FOR INPUT AS #1\n30 PRINT "D9N":END\n100 IF ERL<>20 THEN PRINT "D9N":END\n110 PRINT "D9E"\n120 RESUME 130\n130 PRINT "D9C":END\nRUN\n'
missing_typed=(
  '10 ON ERROR GOTO 100'
  '20 OPEN "QZ9X" FOR INPUT AS #1'
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
  files_pair 0 "$cp0"
  run_pair calibration-n000 "$cp0" missing "$missing_text" "" "${missing_typed[@]}"
  local rec="$WORK/safe/record-calibration-n000.json"
  record_json "$rec" calibration 0 true "" "$WORK/safe/calibration-n000.json"
  note "N=0校正合格: QZ9Xの不存在OPENはD9E/D9C/Okへ到達"
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
    name="$(name_for_n "$n")"; marker="C$(printf '%03d' "$n")"
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
    name="$(name_for_n "$n")"
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
  [[ "$base" =~ ^([0-9]|[1-5][0-9]|6[0-4])$ ]] || die "probe-createのBASEは0〜64"
  [[ "$name" =~ ^[A-Z0-9]{1,6}$ ]] || die "probe-createのNAMEは英大文字・数字1〜6文字"
  [[ "$label" =~ ^[a-z0-9-]+$ ]] || die "probe-createのLABELが不正"
  [[ "$marker" =~ ^[A-Z0-9]{1,6}$ ]] || die "probe-createのMARKERが不正"
  [ "$expect" = success ] || [ "$expect" = failure ] || die "期待分類はsuccess|failure"
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
  local before after text safe rc=0
  before="$(python3 "$HELPER" media-sha "$disk")"
  text="10 OPEN \"$name\" FOR OUTPUT AS #1:CLOSE #1\n20 PRINT \"$marker\":END\nRUN\n"
  run_frontend "$run_label" "$disk" yes "$text" || die "$label が到達前に終了"
  safe="$WORK/safe/probe-$label.json"
  analyze_one "$run_label" create "$marker" "$safe" \
    "10 OPEN \"$name\" FOR OUTPUT AS #1:CLOSE #1" \
    "20 PRINT \"$marker\":END" RUN || rc=$?
  after="$(python3 "$HELPER" media-sha "$disk")"
  python3 - "$safe" "$base" "$name" "$label" "$before" "$after" <<'PY'
import json,sys
p,base,name,label,before,after=sys.argv[1:]
x=json.load(open(p,encoding='utf-8'))
x.update({"probe_base_n":int(base),"probe_name":name,"probe_label":label,
          "media_changed":before!=after,"media_before_sha256":before,
          "media_after_sha256":after})
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
  local disk_source; disk_source="$(checkpoint "$k")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$k" --disk "$disk_source" \
    || die "K=${k}チェックポイントが未受理"
  local marker="V$(printf '%03d' "$k")" label="terminal-verify-n$(printf '%03d' "$k")"
  local text line disk="$WORK/raw/${label}.d88" safe rec
  text="10 K=$k\n20 FOR I=1 TO K\n30 F\$=\"QD\"+CHR\$(65+INT((I-1)/26))+CHR\$(65+((I-1) MOD 26))\n40 OPEN F\$ FOR INPUT AS #1:CLOSE #1\n50 NEXT I\n60 PRINT \"$marker\":END\nRUN\n"
  if [ -e "$disk" ]; then mv "$disk" "$WORK/archive/${label}.$(date +%Y%m%d%H%M%S).$$.d88"; fi
  if [ -d "$WORK/raw/$label" ]; then
    mv "$WORK/raw/$label" "$WORK/archive/${label}.$(date +%Y%m%d%H%M%S).$$.raw"
  fi
  cp "$disk_source" "$disk"
  run_frontend "$label" "$disk" no "$text" || die "K=${k}末端検証が到達前に終了"
  safe="$WORK/safe/$label.json"
  analyze_one "$label" verify "$marker" "$safe" \
    "10 K=$k" "20 FOR I=1 TO K" \
    '30 F$="QD"+CHR$(65+INT((I-1)/26))+CHR$(65+((I-1) MOD 26))' \
    '40 OPEN F$ FOR INPUT AS #1:CLOSE #1' '50 NEXT I' \
    "60 PRINT \"$marker\":END" RUN || return 1
  rec="$WORK/safe/record-terminal-block-n$(printf '%03d' "$k").json"
  record_json "$rec" terminal-block "$k" true "" "$safe"
  note "K=${k}終端全名OPEN検証合格"
}

cmd_measure_terminal() {
  local n="${1:-}" k="${2:-}"
  [[ "$n" =~ ^([0-9]|[1-5][0-9]|6[0-4])$ ]] || die "Nは0〜64"
  [[ "$k" =~ ^([1-9]|[1-5][0-9]|6[0-4])$ ]] || die "Kは1〜64"
  [ "$n" -le "$k" ] || die "NはK以下"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage terminal-block --n "$k" \
    || die "K=${k}終端検証が未受理"
  local disk; disk="$(checkpoint "$n")"
  python3 "$HELPER" status --manifest "$MANIFEST" --stage checkpoint --n "$n" --disk "$disk" \
    || die "N=${n}チェックポイントが未受理またはSHA不一致"
  local prefix="missing-n$(printf '%03d' "$n")"
  run_pair "$prefix" "$disk" missing "$missing_text" "" "${missing_typed[@]}"
  local rec="$WORK/safe/record-measure-n$(printf '%03d' "$n").json"
  record_json "$rec" measure "$n" true "" "$WORK/safe/$prefix.json"
  note "N=$n 不存在OPEN公式2run合格・完全一致（K=${k}終端検証採用）"
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
  probe-create) cmd_probe_create "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}" ;;
  terminal-verify) cmd_terminal_verify "${2:-}" ;;
  measure-terminal) cmd_measure_terminal "${2:-}" "${3:-}" ;;
  summary) shift; [ "$#" -gt 0 ] || die "summaryにはNが必要"; cmd_summary "$@" ;;
  *) usage; exit 2 ;;
esac

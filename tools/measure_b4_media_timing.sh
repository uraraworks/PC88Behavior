#!/usr/bin/env bash
# B4: 自作照合のドライブ1の媒体をいつ・何を入れれば公式と同値か。
# 事前登録: docs/notes/b4-media-timing-preregistration.md（第5〜8節）。
#
# 公式ROMは PC88_REF_ROM_DIR から *.ROM だけを作業場へ cp して使う（中身は読まない）。
# 参照ディスクは使わない（PC88_REF_DISK_DIR 等は外して走らせる）。媒体はすべて自作。
# 画面本文は出さない: 照合は files/load_conform_check.py の compare、目印は
# check_m6fc_markers.py だけが --out を読む。生iologは伏せてから gzip し、--out は消す。
#
# 使い方: B4_WORK=<作業場（存在しないこと）> PC88_REF_ROM_DIR=... tools/measure_b4_media_timing.sh
# 任意: B4_CORE（既定は find_l3_core）、B4_ONLY="P:FILES:L1 ..."（指定した走だけ。試走用）
# 出力: $B4_WORK/results.tsv（白リストの行だけ）
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
INSERT_AT=200
REPS=2
RUN_TIMEOUT=600

die() { printf 'NG %s\n' "$1" >&2; exit 2; }

[ -n "${B4_WORK:-}" ] || die B4_WORK未指定
[ ! -e "$B4_WORK" ] || die 作業先が既に存在する
[ -n "${PC88_REF_ROM_DIR:-}" ] && [ -d "$PC88_REF_ROM_DIR" ] || die reference_rom
WORK="$B4_WORK"
mkdir -p "$WORK"/{rom,base,add2,media,runs} || exit 2

source "$REPO/tools/lib_l3_measure.sh"
CORE="${B4_CORE:-$(find_l3_core)}"
[ -n "$CORE" ] && [ -f "$CORE" ] || die core
ensure_l3_frontend || die frontend
grep -q -- '"--insert-disk1"' "$REPO/tools/harness/frontend/main.c" || die insert_disk1_missing

for f in "$PC88_REF_ROM_DIR"/*.ROM; do
  [ -f "$f" ] && cp -p "$f" "$WORK/rom/" || die rom_copy
done

python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/base/fe" >/dev/null 2>"$WORK/base/fe.err" || die media_fe
python3 "$REPO/tools/make_m6fi_disk.py" "$WORK/base/fi" >/dev/null 2>"$WORK/base/fi.err" || die media_fi
python3 "$REPO/tools/make_m6fi_add2_disk.py" "$WORK/add2/fi" >/dev/null 2>"$WORK/add2/fi.err" || die media_fi_add2
python3 "$REPO/tools/b4_fill_boot_sector.py" "$WORK/base/fe/D1.d88" "$WORK/media/D1-c9.d88" --fill 0xC9 \
  >"$WORK/media/D1-c9.out" 2>&1 || die fill_d1
python3 "$REPO/tools/b4_fill_boot_sector.py" "$WORK/base/fi/ascii.d88" "$WORK/media/ascii-c9.d88" --fill 0xC9 \
  >"$WORK/media/ascii-c9.out" 2>&1 || die fill_ascii

sha() { shasum -a 256 "$1" | awk '{print $1}'; }
RESULTS="$WORK/results.tsv"
{
  printf '# b4-media-timing v1\n'
  printf '# repo_head\t%s\n' "$(git -C "$REPO" rev-parse --short HEAD)$(git -C "$REPO" diff --quiet HEAD -- tools || printf '+dirty')"
  printf '# core_sha256\t%s\n' "$(sha "$CORE")"
  printf '# frontend_sha256\t%s\n' "$(sha "$FRONTEND")"
  printf '# insert_at\t%s\n' "$INSERT_AT"
  printf '# kind\tconfig\tarm\trep\tframes\trc\tinsert_event\tcompare\tmismatch\tfirst_row\tbt\tread_001\tdropped\n'
} >"$RESULTS"

# --- 照合器具（conform_files.sh / conform_load.sh）と同じ打鍵・媒体 ---------
FILES_ARMS=(L1 L11 L96 D-1 D-2 D-omit E-3)
LOAD_ARMS=(I-1 I-3 "I-4'" E-3)

files_command() {
  case "$1" in
    L*) printf '%s' 'CLS:FILES 2\n' ;;
    D-omit) printf '%s' 'CLS:FILES\n' ;;
    D-1) printf '%s' 'CLS:FILES 1\n' ;;
    D-2) printf '%s' 'CLS:FILES 2\n' ;;
    E-3) printf '%s' '10 ON ERROR GOTO 100\n20 FILES 3\n30 END\n100 CLS:PRINT ERR\n110 RESUME 30\nRUN\n' ;;
    *) return 1 ;;
  esac
}
files_disk2() {
  case "$1" in
    L1|L11|L96) printf '%s/%s.d88' "$WORK/base/fe" "$1" ;;
    D-*|E-*) printf '%s' "$WORK/base/fe/D2.d88" ;;
    *) return 1 ;;
  esac
}
load_dir() {
  case "$1" in "I-4'"|E-3) printf '%s' "$WORK/add2/fi" ;; *) printf '%s' "$WORK/base/fi" ;; esac
}
load_command() {
  python3 - "$(load_dir "$1")/manifest.json" "$1" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="ascii"))
sys.stdout.write(next(a["command"] for a in doc["arms"] if a["id"] == sys.argv[2]))
PY
}

# 構成ごとのドライブ1の qargs。$1=構成 $2=kind(FILES/LOAD/M) $3=走の作業場
drive1_args() {
  local config="$1" kind="$2" dir="$3" src
  case "$kind" in FILES|M) src="$WORK/base/fe/D1.d88" ;; LOAD) src="$WORK/base/fi/ascii.d88" ;; esac
  case "$config" in
    P) cp "$src" "$dir/drive1.d88" && printf '%s\0' --disk "$dir/drive1.d88" ;;
    Q) cp "$src" "$dir/drive1.d88" && printf '%s\0' --insert-disk1 "$dir/drive1.d88" --insert-disk1-at "$INSERT_AT" ;;
    R)
      case "$kind" in FILES|M) src="$WORK/media/D1-c9.d88" ;; LOAD) src="$WORK/media/ascii-c9.d88" ;; esac
      cp "$src" "$dir/drive1.d88" && printf '%s\0' --disk "$dir/drive1.d88" ;;
    Z) : ;;
    *) return 1 ;;
  esac
}

wanted() {
  [ -z "${B4_ONLY:-}" ] && return 0
  case " $B4_ONLY " in *" $1:$2:$3 "*) return 0 ;; esac
  return 1
}

launch() {
  # 起動時クラッシュ(134)に限って2回まで再試行（既存ドライバと同じ）
  local out="$1" err="$2"; shift 2
  local attempt=0 rc
  while :; do
    attempt=$((attempt + 1)); rc=0
    env -u PC88_REF_DISK_DIR -u PC88_REF_DISKB -u PC88_GAME_DIR nice -n 10 \
      /usr/bin/perl -e 'alarm shift; exec @ARGV' "$RUN_TIMEOUT" "$FRONTEND" "$@" >"$out" 2>"$err" || rc=$?
    [ "$rc" -eq 134 ] && [ "$attempt" -lt 3 ] && continue
    return "$rc"
  done
}

insert_event() {
  local err="$1" config="$2"
  [ "$config" = Q ] || { printf '%s' -; return; }
  if grep -qF $'event\tinsert_disk1\tframe='"$INSERT_AT"$'\tsuccess=1' "$err"; then
    printf '%s' "frame=$INSERT_AT,success=1"
  else
    printf '%s' "missing_or_failed"
  fi
}

run_conform() {
  local kind="$1" config="$2" arm="$3" rep="$4"
  wanted "$config" "$kind" "$arm" || return 0
  local safe="${arm//\'/p}" dir frames command
  dir="$WORK/runs/$kind-$config-$safe-r$rep"; mkdir "$dir" || die run_dir
  local d1=() qargs=()
  while IFS= read -r -d '' x; do d1+=("$x"); done < <(drive1_args "$config" "$kind" "$dir")
  if [ "$kind" = FILES ]; then
    frames=8000; [ "$arm" = L96 ] && frames=12000
    command="$(files_command "$arm")" || die command
    qargs=(--core "$CORE" --rom-dir "$WORK/rom" "${d1[@]}" --disk2 "$(files_disk2 "$arm")"
      --frames "$frames" --screen-signature-only --screen-signature-at baseline:600
      --screen-signature-at "final:$((frames - 300))" --screen-signature-at "late:$frames"
      --out "$dir/signatures.tsv" --type-at 300 --type '\n' --type-at 500 --type 'CLS\n'
      --type-at 700 --type "$command")
  else
    frames=8000
    command="$(load_command "$arm")" || die command
    qargs=(--core "$CORE" --rom-dir "$WORK/rom" "${d1[@]}" --disk2 "$(load_dir "$arm")/ascii.d88"
      --frames 8000 --screen-signature-only
      --screen-signature-at baseline:600 --screen-signature-at final:7700
      --screen-signature-at late:8000 --out "$dir/signatures.tsv"
      --type-at 300 --type $'\n' --type-at 500 --type $'CLS\n'
      --type-at 700 --type "$command"$'\n')
    case "$arm" in
      I-1|I-2|I-3|E-3)
        qargs+=(--screen-signature-at load:3300 --screen-signature-at load_late:3600
          --type-at 4000 --type $'CLS:LIST\n') ;;
    esac
  fi
  local rc=0; launch "$dir/stdout.txt" "$dir/stderr.txt" "${qargs[@]}" || rc=$?
  local ev; ev="$(insert_event "$dir/stderr.txt" "$config")"
  local cmp=- mism=- first=-
  if [ "$rc" -eq 0 ] && [ -s "$dir/signatures.tsv" ]; then
    local crc=0 check
    if [ "$kind" = FILES ]; then check="$REPO/tools/files_conform_check.py"; exp="$REPO/tools/files_conform_expected.tsv"
    else check="$REPO/tools/load_conform_check.py"; exp="$REPO/tools/load_conform_expected.tsv"; fi
    python3 "$check" compare --expected "$exp" --arm "$arm" --report "$dir/signatures.tsv" \
      >"$dir/compare.out" 2>"$dir/compare.err" || crc=$?
    if [ "$crc" -eq 0 ]; then cmp=OK; mism=0
    elif [ "$crc" -eq 1 ]; then cmp=NG; IFS=$'\t' read -r _ mism first <"$dir/compare.out"
    else cmp=ERR; fi
  else
    cmp=RUN_FAILED
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t-\t-\t-\n' \
    "$kind" "$config" "$arm" "$rep" "$frames" "$rc" "$ev" "$cmp" "$mism" "$first" >>"$RESULTS"
}

run_marker() {
  local config="$1" rep="$2"
  wanted "$config" M M || return 0
  local dir="$WORK/runs/M-$config-r$rep"; mkdir "$dir" || die run_dir
  local d1=()
  while IFS= read -r -d '' x; do d1+=("$x"); done < <(drive1_args "$config" M "$dir")
  local qargs=(--core "$CORE" --rom-dir "$WORK/rom" "${d1[@]+"${d1[@]}"}" --frames 1500
    --io-log "$dir/iolog.txt" --out "$dir/report.txt"
    --type-at 300 --type '\n' --type-at 500 --type 'CLS\n'
    --type-at 700 --type 'print chr$(90);chr$(81);"bt"\n')
  local rc=0; launch "$dir/stdout.txt" "$dir/stderr.txt" "${qargs[@]}" || rc=$?
  local ev; ev="$(insert_event "$dir/stderr.txt" "$config")"
  local bt=- reads=- dropped=-
  if [ "$rc" -eq 0 ] && [ -s "$dir/report.txt" ]; then
    if python3 "$REPO/tools/check_m6fc_markers.py" --report "$dir/report.txt" >"$dir/markers.json" 2>/dev/null; then
      bt="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("yes" if any(m["tag"]=="bt" for m in d["markers"]) else "no")' "$dir/markers.json")"
    else
      bt=ERR
    fi
  fi
  if [ -s "$dir/iolog.txt" ]; then
    read -r reads dropped < <(python3 - "$REPO" "$dir/iolog.txt" <<'PY'
import re, sys
from pathlib import Path
repo, iolog = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
from analyze_main_to_sub import parse_iolog
from analyze_write_path import parse_commands
text = Path(iolog).read_text(encoding="utf-8", errors="replace")
dropped = sum(int(m.group(1)) for m in re.finditer(r"取りこぼし:\s*(\d+)件", text))
rows, masked = parse_iolog(Path(iolog))
if dropped or sum(masked.values()):
    print("-", dropped); sys.exit(0)
n = 0
for c in parse_commands(rows):
    if c.opcode != 0x06 or c.param_values is None or len(c.param_values) < 4:
        continue
    nsec = max(1, (c.result_bytes - 7) // 256) if c.result_bytes > 7 else 1
    cc, hh, rr = c.param_values[1], c.param_values[2], c.param_values[3]
    n += sum(1 for i in range(nsec) if (cc, hh, rr + i) == (0, 0, 1))
print(n, dropped)
PY
)
    python3 "$REPO/tools/redact_iolog.py" --in-place "$dir/iolog.txt" >/dev/null 2>&1 \
      && gzip -9 "$dir/iolog.txt" || rm -f "$dir/iolog.txt"
  fi
  rm -f "$dir/report.txt"   # 画面節を含むので残さない（目印の判定は済んだ）
  printf 'M\t%s\tM\t%s\t1500\t%s\t%s\t-\t-\t-\t%s\t%s\t%s\n' \
    "$config" "$rep" "$rc" "$ev" "$bt" "${reads:--}" "${dropped:--}" >>"$RESULTS"
}

# 目印の対照 Z を先に回す（第7節: Z で目印が出なければ J-basic を使わない）
for config in Z P Q R; do
  for rep in $(seq 1 "$REPS"); do run_marker "$config" "$rep"; done
done
for config in P Q R; do
  for arm in "${FILES_ARMS[@]}"; do
    for rep in $(seq 1 "$REPS"); do run_conform FILES "$config" "$arm" "$rep"; done
  done
  for arm in "${LOAD_ARMS[@]}"; do
    for rep in $(seq 1 "$REPS"); do run_conform LOAD "$config" "$arm" "$rep"; done
  done
done
printf 'done\n' >>"$RESULTS"

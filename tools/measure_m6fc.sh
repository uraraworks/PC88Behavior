#!/usr/bin/env bash
# m6f-c測定ドライバ。GB→SW(256腕)→A0→残りのA腕を各2走で実行する。
#
# **このスクリプトは公式ROMを使う本番の腕を回すためのものだが、
# このセッション自身はそれを実行しない**（作業指示により測定は回さない）。
# ここに置くのは器具そのものであり、関門(G1〜G7)と手順が事前登録
# docs/notes/m6f-c-blank-disk-acceptance-preregistration.md 第6節と
# 一致することを自己検査で確認するにとどめる。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${M6FC_FROZEN_CONFIG:-$REPO/tools/m6fc_frozen.tsv}"
FRONTEND="${M6FC_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }

# G7: 凍結照合は引数解釈・環境参照・frontend起動より先に行う。
python3 "$REPO/tools/check_m6fc_preregistration.py" --config "$CONFIG" >/dev/null 2>&1 \
  || gate_failed preregistration_mismatch
source "$REPO/tools/lib_m6f_measure.sh"

raw_dir=""; result=""; boot_fill=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --raw-dir) raw_dir="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    --boot-fill) boot_fill="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
[ -n "$raw_dir" ] && [ -n "$result" ] || exit 2
# --boot-fill 追補1(m6f-c-addendum1-boot-sector-sweep.md 第4節)の再走用。
# 指定時は0〜255(10進 or 0x接頭辞)、全腕の媒体で起動用セクタ(0,0,1)を
# その値にする。省略時はNoneのまま(全腕の生成器呼び出しに--boot-fillを渡さない)。
boot_fill_args=()
boot_fill_record=""
if [ -n "$boot_fill" ]; then
  boot_fill_record="$(python3 -c "import sys; v=int(sys.argv[1],0); assert 0<=v<=255; print(v)" \
    "$boot_fill")" || gate_failed boot_fill_range
  boot_fill_args=(--boot-fill "$boot_fill_record")
fi

[ -n "${PC88_REF_ROM_DIR:-}" ] || gate_failed PC88_REF_ROM_DIR_missing
[ -d "$PC88_REF_ROM_DIR" ] || gate_failed reference_rom_dir_missing

# 追補2(docs/notes/m6f-c-addendum2-blank-disk-in-drive2.md §2):
# 全腕でドライブ1に参照diskAの使い捨て複製(書き込み保護は解除しない)を
# 入れて起動し、ドライブ2に生成器の媒体を入れる。
[ -n "${PC88_REF_DISK_DIR:-}" ] || gate_failed PC88_REF_DISK_DIR_missing
[ -d "$PC88_REF_DISK_DIR" ] || gate_failed reference_disk_dir_missing
REF_DISK_NAME="$(m6f_cfg "$CONFIG" reference_disk)" || gate_failed reference_disk_config
REF_DISK="$PC88_REF_DISK_DIR/$REF_DISK_NAME"
[ -f "$REF_DISK" ] || gate_failed reference_disk_missing
REF_SHA="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha

# G6: 生の像・差分・入出力ログはリポジトリ外だけに置く。
m6f_check_output_paths "$REPO" "$raw_dir" "$result" || gate_failed G6
mkdir -p "$raw_dir" || gate_failed raw_dir
[ -d "$(dirname "$result")" ] || gate_failed result_parent
[ ! -e "$result" ] || gate_failed result_exists

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# G2
"$REPO/tools/check_cleanroom.sh" >"$WORK/g2.out" 2>"$WORK/g2.err" || gate_failed G2
# G3: 差分器・生成器・目印判定器の自己検査。
"$REPO/tools/d88_diff_selftest.sh" >"$WORK/g3a.out" 2>&1 || gate_failed G3_d88diff
"$REPO/tools/make_m6fc_blank_disk_selftest.sh" >"$WORK/g3b.out" 2>&1 || gate_failed G3_generator
"$REPO/tools/check_m6fc_markers_selftest.sh" >"$WORK/g3c.out" 2>&1 || gate_failed G3_markers

source "$REPO/tools/lib_l3_measure.sh"
# 試験用の口(既定は無効): M6FC_TEST_CORE を設定すると find_l3_core の結果を
# 上書きできる。tools/measure_m6fc_driver_selftest.sh がコア不在環境で
# 偽フロントエンドを差し込むために使う。未設定時は従来どおり find_l3_core
# の結果をそのまま使うので、本番の挙動は変わらない。
CORE="${M6FC_TEST_CORE:-$(find_l3_core)}"; [ -n "$CORE" ] || gate_failed core_missing
if [ "$FRONTEND" = "$REPO/tools/harness/frontend/q88measure" ]; then
  ensure_l3_frontend || gate_failed frontend_missing
else
  [ -x "$FRONTEND" ] || gate_failed frontend_missing
fi

BOOT_FRAME="$(m6f_cfg "$CONFIG" boot_return_frame)"
STIMULUS_FRAME="$(m6f_cfg "$CONFIG" stimulus_frame)"
TIMEOUT="$(m6f_cfg "$CONFIG" run_timeout_seconds)"

# G5: 生成器の決定性(測定に使う値そのものではなく、任意の(V,F)組で確認する)。
python3 "$REPO/tools/make_m6fc_blank_disk.py" "$WORK/g5a.d88" --fat-value 0xAA --filler 0x55 \
  ${boot_fill_args[@]+"${boot_fill_args[@]}"} >/dev/null 2>"$WORK/g5.err" || gate_failed G5_generate
python3 "$REPO/tools/make_m6fc_blank_disk.py" "$WORK/g5b.d88" --fat-value 0xAA --filler 0x55 \
  ${boot_fill_args[@]+"${boot_fill_args[@]}"} >/dev/null 2>>"$WORK/g5.err" || gate_failed G5_generate
[ "$(m6f_sha256 "$WORK/g5a.d88")" = "$(m6f_sha256 "$WORK/g5b.d88")" ] || gate_failed G5

mfc_frames() {
  python3 - "$REPO" "$1" <<'PY'
import sys
repo, arm = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo + "/tools")
import check_m6fc_preregistration as c
print(c.resolve_frames(arm))
PY
}
mfc_segments() {
  python3 - "$REPO" "$1" <<'PY'
import sys
repo, arm = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo + "/tools")
import check_m6fc_preregistration as c
# 本物の改行を含んだまま1行に出すと、bash の read で切れて Enter の打鍵が
# 失われる（2回目の本測定まで GB が陽性にならなかった原因）。ハーネスが
# Enter と解釈する「\\n」の2文字へ戻してから出す。凍結表と同じ書き方。
for frame, text in c.resolve_segments(arm):
    if "\t" in text or "\r" in text or "\\n" in text:
        raise SystemExit(3)
    print(f"{frame}\t" + text.replace("\n", "\\n"))
PY
}

RUNS_JSON="$WORK/runs.ndjson"; : > "$RUNS_JSON"
SAVE_DISK_ARMS=" A0 A1 A1b A2 A3 A4-1 A4-3 A4-6 A4-10 A4-17 A5 A5b A6 "

# 1走ぶんを実行し、runs.ndjson へ1行追記する。
# $1=arm $2=rep $3=fat_value(10進) $4=filler(10進)
mfc_run_one() {
  local arm="$1" rep="$2" fat="$3" filler="$4"
  local disk2="$WORK/$arm-r$rep.d88"
  local disk1="$WORK/$arm-r$rep.drive1.d88"
  local iolog="$WORK/$arm-r$rep.iolog.txt"
  local report="$WORK/$arm-r$rep.report.txt"
  local frames
  frames="$(mfc_frames "$arm")" || gate_failed frames_resolve
  [ -e "$disk2" ] && gate_failed disk_exists
  python3 "$REPO/tools/make_m6fc_blank_disk.py" "$disk2" --fat-value "$fat" --filler "$filler" \
    ${boot_fill_args[@]+"${boot_fill_args[@]}"} >/dev/null 2>"$WORK/$arm-r$rep.gen.err" || gate_failed generate_disk
  local initial_sha; initial_sha="$(m6f_sha256 "$disk2")" || gate_failed initial_sha

  # ドライブ1: 参照ディスクの使い捨て複製。書き込み保護は解除しない
  # (D88ヘッダの保護バイトには触れない。ファイルの書き込み権限だけ
  # chmod u+wで確保するのは、実際には書けないはずのものが書けて
  # しまわないかをG8で確かめるための入れ物にすぎない)。
  [ -e "$disk1" ] && gate_failed disk1_exists
  cp "$REF_DISK" "$disk1" || gate_failed disk1_copy
  chmod u+w "$disk1" || gate_failed disk1_mode
  local disk1_initial_sha; disk1_initial_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_sha
  [ "$disk1_initial_sha" = "$REF_SHA" ] || gate_failed disk1_copy_mismatch

  local qargs=(--core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$disk1" --disk2 "$disk2"
    --save-to-disk-image --frames "$frames" --io-log "$iolog" --out "$report"
    --type-at "$BOOT_FRAME" --type '\n')
  local nadded=0
  while IFS=$'\t' read -r seg_frame seg_text; do
    [ -n "$seg_frame" ] || continue
    case "$seg_frame" in *[!0-9]*) gate_failed segment_frame ;; esac
    qargs+=(--type-at "$seg_frame" --type "$seg_text")
    nadded=$((nadded + 1))
  done < <(mfc_segments "$arm")
  # 守り: 渡した区間の数が凍結表の区間の数と一致すること。
  local nseg; nseg="$(mfc_segments "$arm" | wc -l | tr -d ' ')" || gate_failed segments_resolve
  [ "$nadded" -eq "$nseg" ] || gate_failed segments_count

  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" "$FRONTEND" "${qargs[@]}" \
    >"$WORK/$arm-r$rep.stdout.txt" 2>"$WORK/$arm-r$rep.stderr.txt" || gate_failed emulator_run
  [ -e "$report" ] && [ -s "$iolog" ] || gate_failed measurement_artifact

  # G8: 参照ディスクの使い捨て複製(ドライブ1)は、測定後も複製直後と
  # 同じであること。参照ディスク本体も変わっていないこと。
  local disk1_final_sha; disk1_final_sha="$(m6f_sha256 "$disk1")" || gate_failed disk1_final_sha
  [ "$disk1_final_sha" = "$REF_SHA" ] || gate_failed G8
  local ref_sha_after; ref_sha_after="$(m6f_sha256 "$REF_DISK")" || gate_failed reference_sha_after
  [ "$ref_sha_after" = "$REF_SHA" ] || gate_failed G8

  local final_sha; final_sha="$(m6f_sha256 "$disk2")" || gate_failed final_sha

  local markers_json; markers_json="$(python3 "$REPO/tools/check_m6fc_markers.py" \
    --report "$report" --name QZ7A --name QZ7B)" || gate_failed markers

  local keep_disk=0
  case "$SAVE_DISK_ARMS" in *" $arm "*) keep_disk=1 ;; esac
  if [ "$keep_disk" -eq 1 ]; then
    # 測定後の媒体として保存するのはドライブ2の像だけ(ドライブ1は
    # 参照diskAの使い捨て複製で、公式ディスクの中身なので保存しない)。
    cp "$disk2" "$raw_dir/$arm-r$rep.d88" || gate_failed save_disk
  fi

  python3 - "$REPO" "$arm" "$rep" "$fat" "$filler" "$iolog" "$STIMULUS_FRAME" \
    "$initial_sha" "$final_sha" "$boot_fill_record" <<'PYEOF' >> "$RUNS_JSON" || gate_failed run_summary
import json, sys
from pathlib import Path
repo, arm, rep, fat, filler, iolog, stim, isha, fsha, boot_fill_raw = sys.argv[1:]
sys.path.insert(0, str(Path(repo) / "tools"))
from analyze_main_to_sub import parse_iolog
from analyze_write_path import parse_commands
from m6fc_fdc_by_drive import split_by_drive

rows, masked = parse_iolog(Path(iolog))
if sum(masked.values()):
    print("エラー: 伏せ字ログでは座標を安全に取り出せない", file=sys.stderr)
    sys.exit(1)

# 取りこぼし(容量超過)を検出する。黙って少なく数えない。
text = Path(iolog).read_text(encoding="utf-8", errors="replace")
import re
dropped_total = 0
for m in re.finditer(r"取りこぼし:\s*(\d+)件", text):
    dropped_total += int(m.group(1))
if dropped_total:
    print(f"エラー: I/Oログに取りこぼしが{dropped_total}件ある", file=sys.stderr)
    sys.exit(1)

commands = parse_commands(rows)
stim = int(stim)
# 追補2: 書いたセクタ・読んだセクタは装置番号1(ドライブ2)だけを数える。
# 装置番号0(ドライブ1)の件数はdrive1_read_count/drive1_write_countへ。
split = split_by_drive(commands, stim)
reads, writes = split["reads"], split["writes"]
write_data_count = split["write_data_count"]
drive1_read_count = split["drive1_read_count"]
drive1_write_count = split["drive1_write_count"]

boot_fill_value = int(boot_fill_raw) if boot_fill_raw != "" else None

body = {
    "arm": arm, "repetition": int(rep), "fat_value": int(fat), "filler": int(filler),
    "boot_fill": boot_fill_value,
    "initial_sha": isha, "final_sha": fsha,
    "reads": reads, "writes": writes, "write_data_count": write_data_count,
    "drive1_read_count": drive1_read_count, "drive1_write_count": drive1_write_count,
}
print(json.dumps(body, sort_keys=True, separators=(",", ":")))
PYEOF

  # markers_json(check_m6fc_markers.pyの出力)を安全な行に合流する
  # （bashのヒアドキュメントへJSON文字列を直接埋め込むと引用符の
  # エスケープが崩れやすいため、追記した最後の行にpythonで結合する）。
  python3 - "$RUNS_JSON" "$markers_json" <<'PY' || gate_failed run_summary_merge
import json, sys
path, markers_raw = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().splitlines()
last = json.loads(lines[-1])
markers = json.loads(markers_raw)
last["markers"] = markers["markers"]
last["malformed_marker_rows"] = markers["malformed_marker_rows"]
last["name_counts"] = markers["name_counts"]
lines[-1] = json.dumps(last, sort_keys=True, separators=(",", ":"))
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

write_result_and_exit() {
  local overall="$1"
  python3 - "$WORK" "$result" "$overall" <<'PY' || gate_failed result_write
import json, sys
from pathlib import Path
work, out, overall = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
runs = [json.loads(line) for line in (work / "runs.ndjson").read_text(encoding="utf-8").splitlines() if line]
body = {"schema": 1, "runs": runs, "overall": overall,
        "drive_layout": "drive1=reference_copy_protected;drive2=generated"}
with out.open("x", encoding="utf-8") as f:
    json.dump(body, f, sort_keys=True, separators=(",", ":")); f.write("\n")
PY
  printf 'm6f-c measurement complete: raw=%s result=%s overall=%s\n' "$raw_dir" "$result" "$overall"
  exit 0
}

# --- 段階0: GB(起動の関門) -------------------------------------------------
mfc_run_one GB-FF 1 255 255
mfc_run_one GB-FF 2 255 255
mfc_run_one GB-00 1 0 0
mfc_run_one GB-00 2 0 0

f_star="$(python3 - "$RUNS_JSON" <<'PY'
import json, sys
runs = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
by_key = {(r["arm"], r["repetition"]): r for r in runs}
def bt(arm, rep):
    r = by_key.get((arm, rep))
    return r is not None and any(m["tag"] == "bt" for m in r.get("markers", []))
if bt("GB-FF", 1) and bt("GB-FF", 2):
    print(255)
elif bt("GB-00", 1) and bt("GB-00", 2):
    print(0)
else:
    print("blocked")
PY
)"
if [ "$f_star" = "blocked" ]; then
  write_result_and_exit m6f_c_boot_blocked
fi

# --- 段階1: SW(空きの印の掃引、256腕) --------------------------------------
# 試験用の口(既定は無効): M6FC_TEST_SW_MAX を設定すると掃引の上限を狭められる
# (既定255=v=0..255の全腕。未設定時は従来と同じ範囲になる)。
# tools/measure_m6fc_driver_selftest.sh が偽フロントエンドで全256腕×2走を
# 回すと重いため、1腕だけに絞るのに使う。
SW_MAX="${M6FC_TEST_SW_MAX:-255}"
for v in $(seq 0 "$SW_MAX"); do
  hex="$(printf '%02X' "$v")"
  mfc_run_one "SW-$hex" 1 "$v" "$f_star"
  mfc_run_one "SW-$hex" 2 "$v" "$f_star"
done

v_star_line="$(python3 - "$REPO" "$RUNS_JSON" <<'PY'
import json, sys
from pathlib import Path
repo, path = sys.argv[1], sys.argv[2]
sys.path.insert(0, str(Path(repo) / "tools"))
from derive_m6fc import free_mark
runs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
result = {"schema": 1, "runs": runs}
fm = free_mark(result)
if fm["status"] == "not_found":
    print("none")
elif fm["status"] == "derived":
    print(fm["value"])
else:
    print(min(fm["value"]))
PY
)"
if [ "$v_star_line" = "none" ]; then
  write_result_and_exit m6f_c_no_free_mark
fi
v_star="$v_star_line"
if [ "$f_star" = 255 ]; then f_prime=0; else f_prime=255; fi

# --- 段階2: A0(陰性対照) + G4 -----------------------------------------------
mfc_run_one A0 1 "$v_star" "$f_star"
mfc_run_one A0 2 "$v_star" "$f_star"
python3 - "$RUNS_JSON" <<'PY' || gate_failed G4
import json, sys
runs = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
a0 = [r for r in runs if r["arm"] == "A0"]
ok = all(r["write_data_count"] == 0 and not r["writes"] and not r["markers"]
         and r["initial_sha"] == r["final_sha"] for r in a0)
sys.exit(0 if ok else 1)
PY

# --- 段階2: 残りのA腕 --------------------------------------------------------
for arm in A1 A1b A2 A3 A4-1 A4-3 A4-6 A4-10 A4-17 A5 A5b; do
  mfc_run_one "$arm" 1 "$v_star" "$f_star"
  mfc_run_one "$arm" 2 "$v_star" "$f_star"
  # 試験用の口(既定は無効): M6FC_TEST_STOP_AFTER_ARM を設定すると、
  # 一致した腕を2走終えた時点で打ち切る(未設定時は従来どおり最後まで回る)。
  if [ -n "${M6FC_TEST_STOP_AFTER_ARM:-}" ] && [ "$arm" = "$M6FC_TEST_STOP_AFTER_ARM" ]; then
    printf 'm6f-c measurement selftest: stopped after arm=%s\n' "$arm"
    exit 0
  fi
done
mfc_run_one A6 1 "$v_star" "$f_prime"
mfc_run_one A6 2 "$v_star" "$f_prime"

# --- 導出・判定 --------------------------------------------------------------
python3 - "$WORK" "$result" <<'PY' || gate_failed result_write
import json, sys
from pathlib import Path
work, out = Path(sys.argv[1]), Path(sys.argv[2])
runs = [json.loads(line) for line in (work / "runs.ndjson").read_text(encoding="utf-8").splitlines() if line]
body = {"schema": 1, "runs": runs,
        "drive_layout": "drive1=reference_copy_protected;drive2=generated"}
with out.open("x", encoding="utf-8") as f:
    json.dump(body, f, sort_keys=True, separators=(",", ":")); f.write("\n")
PY

overall="$(python3 - "$REPO" "$result" "$raw_dir" <<'PY'
import json, sys
from pathlib import Path
repo, result_path, raw_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(Path(repo) / "tools"))
from derive_m6fc import build, load_result
result = load_result(result_path)
derived = build(result, raw_dir)
print(derived["overall"])
PY
)"
printf 'm6f-c measurement complete: raw=%s result=%s overall=%s\n' "$raw_dir" "$result" "$overall"

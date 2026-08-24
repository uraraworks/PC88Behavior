#!/usr/bin/env bash
# 公式no_diskと混成環境の no_disk / 正常B: / 待ち介入を測る。
# 生iologと画面報告を含むため、出力先は必ずリポジトリ外に限定する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"

usage() {
  cat <<'EOF'
使い方:
  PC88_NO_DISK_SIGNAL_OPT_IN=1 \
  PC88_REF_ROM_DIR=/path/to/rom PC88_REF_DISK_DIR=/path/to/disk \
    tools/measure_no_disk_signals.sh --out-dir /path/to/output

4 runとも800F実行する。I/O記録は打鍵frame 700以降の100Fを丸ごと採る。
高密度が見込まれる公式ROM一式no_disk armを最初に測り、取りこぼし0件を
確認してから混成3 armへ進む。比較関門の合格後だけ介入armを走らせる。
公式armが溢れた場合は容量不足として比較を中止し、特例採用しない。
成功・不採用・失敗の各runは後段の成否にかかわらず即時保存する。
EOF
}

OUT_DIR=""
CAPTURE_FROM=700
FRAMES=800
while [ "$#" -gt 0 ]; do
  case "$1" in
    --out-dir)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      OUT_DIR="$2"; shift 2 ;;
    --capture-from-frame)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      CAPTURE_FROM="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "エラー: 未知の引数: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$CAPTURE_FROM" in
  ''|*[!0-9]*) echo "エラー: --capture-from-frame は整数で指定すること" >&2; exit 2 ;;
esac
if [ "$CAPTURE_FROM" -ge "$FRAMES" ]; then
  echo "エラー: 採取開始frameは $FRAMES 未満でなければならない" >&2
  exit 2
fi
if [ "${PC88_NO_DISK_SIGNAL_OPT_IN:-}" != "1" ]; then
  echo "SKIP: PC88_NO_DISK_SIGNAL_OPT_IN=1 が必要（実測未実行、rc=3）"
  exit 3
fi
if [ -z "${PC88_REF_ROM_DIR:-}" ] || [ -z "${PC88_REF_DISK_DIR:-}" ]; then
  echo "エラー: PC88_REF_ROM_DIR / PC88_REF_DISK_DIR が未設定" >&2
  exit 2
fi
if [ -z "$OUT_DIR" ]; then
  echo "エラー: --out-dir が必要" >&2
  exit 2
fi
mkdir -p "$OUT_DIR" || exit 1
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
case "$OUT_DIR/" in
  "$REPO/"*) echo "エラー: 生ログを含むためリポジトリ外を指定すること" >&2; exit 2 ;;
esac

targets=(
  no_disk.official.iolog.txt no_disk.official.report.txt no_disk.official.status.txt no_disk.official.meta.json
  no_disk.mixed-default.iolog.txt no_disk.mixed-default.report.txt no_disk.mixed-default.status.txt no_disk.mixed-default.meta.json
  drive2.mixed-default.iolog.txt drive2.mixed-default.report.txt drive2.mixed-default.status.txt drive2.mixed-default.meta.json
  no_disk.mixed-intervention.iolog.txt no_disk.mixed-intervention.report.txt no_disk.mixed-intervention.status.txt no_disk.mixed-intervention.meta.json
  no_disk-signals.txt no_disk-wait-screen.txt no_disk-suite-summary.txt
)
for target in "${targets[@]}"; do
  if [ -e "$OUT_DIR/$target" ]; then
    echo "エラー: 既存出力を上書きしない: $target" >&2
    exit 1
  fi
done

DISK="$PC88_REF_DISK_DIR/N88_FE.D88"
[ -f "$DISK" ] || { echo "エラー: 参照媒体が無い" >&2; exit 1; }
CORE="$(find_l3_core)"
[ -n "$CORE" ] || { echo "エラー: コアが無い。tools/setup_harness.sh が必要" >&2; exit 1; }
ensure_l3_frontend || exit 1

WORK="$(mktemp -d)"
ATTEMPTED=0
SUCCEEDED=0
REJECTED=0
FAILED=0
ANALYSIS_FAILED=0
FINALIZED=0

write_summary() {
  [ "$FINALIZED" -eq 0 ] || return
  FINALIZED=1
  local state="完全" saved=0 tag suffix
  for tag in no_disk.official no_disk.mixed-default drive2.mixed-default no_disk.mixed-intervention; do
    for suffix in iolog.txt report.txt meta.json; do
      [ -f "$OUT_DIR/$tag.$suffix" ] && saved=$((saved + 1))
    done
  done
  if [ "$SUCCEEDED" -ne 4 ] || [ "$ATTEMPTED" -ne 4 ] ||
     [ "$ANALYSIS_FAILED" -ne 0 ]; then
    state="部分的"
  fi
  {
    echo "# no_disk信号測定 一式集計"
    echo "状態: $state"
    echo "run試行数: ${ATTEMPTED}本"
    echo "採用成功数: ${SUCCEEDED}本"
    echo "不採用数（取りこぼし等）: ${REJECTED}本"
    echo "測定失敗数: ${FAILED}本"
    echo "解析失敗数: ${ANALYSIS_FAILED}件"
    echo "採用run成果物数: $((SUCCEEDED * 3))個（各run iolog+report+meta.json）"
    echo "保存済みrun成果物数: ${saved}個（不採用・失敗の診断用生成物を含む）"
    echo "期待run成果物数: $((ATTEMPTED * 3))個（各run iolog+report+meta.json）"
    if [ "$state" = "部分的" ]; then
      echo "注意: これは部分結果であり、4条件が揃った完全結果ではない。"
    else
      echo "注意: 4条件すべて採用済み。"
    fi
  } > "$OUT_DIR/no_disk-suite-summary.txt"
  echo "集計: ${ATTEMPTED}本試行／${SUCCEEDED}本採用成功／${REJECTED}本不採用／${FAILED}本失敗"
}
cleanup() {
  write_summary
  rm -rf "$WORK"
}
trap cleanup EXIT

publish_run_files() {
  local tag="$1" stage="$2" suffix
  for suffix in iolog.txt report.txt meta.json; do
    if [ -f "$stage/$tag.$suffix" ]; then
      mv "$stage/$tag.$suffix" "$OUT_DIR/$tag.$suffix"
    fi
  done
}

measure_one() {
  local tag="$1" scenario="$2" rom_config="$3" report_role="$4"
  local stage="$WORK/$tag" rom="$WORK/$tag.rom"
  local disk_a="$WORK/$tag.a.d88" disk_b="$WORK/$tag.b.d88"
  local media="$disk_a"
  local iolog="$stage/$tag.iolog.txt" report="$stage/$tag.report.txt"
  local stdout="$stage/$tag.stdout.txt" stderr="$stage/$tag.stderr.txt"
  local drops rom_label condition
  ATTEMPTED=$((ATTEMPTED + 1))
  mkdir -p "$stage"
  case "$scenario" in
    no_disk) condition="no_disk" ;;
    drive2) condition="normal_drive2" ;;
    *) echo "エラー: 未知の測定条件: $scenario" >&2; return 1 ;;
  esac
  case "$rom_config" in
    official_full)
      rom="$PC88_REF_ROM_DIR"
      rom_label="公式ROM一式"
      ;;
    mixed_default)
      rom_label="混成既定（公式main一式＋自作sub既定版）"
      build_mixed_rom "$PC88_REF_ROM_DIR" "$rom" || {
        FAILED=$((FAILED + 1)); echo "状態: 測定失敗（ROM構築）" > "$OUT_DIR/$tag.status.txt"; return 1;
      }
      ;;
    mixed_intervention)
      rom_label="混成介入（公式main一式＋自作sub待ち介入版）"
      build_mixed_rom "$PC88_REF_ROM_DIR" "$rom" --intervene-no-disk-wait || {
        FAILED=$((FAILED + 1)); echo "状態: 測定失敗（ROM構築）" > "$OUT_DIR/$tag.status.txt"; return 1;
      }
      ;;
    *) echo "エラー: 未知のROM構成: $rom_config" >&2; return 1 ;;
  esac
  python3 - "$stage/$tag.meta.json" "$tag" "$report_role" "$rom_config" "$condition" <<'PY'
import json, sys
from pathlib import Path
path, run_id, role, config, condition = sys.argv[1:]
Path(path).write_text(json.dumps({
    "schema": "pc88-no-disk-run-v1",
    "run_id": run_id,
    "report_role": role,
    "rom_configuration": config,
    "condition": condition,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  if [ "$?" -ne 0 ]; then
    FAILED=$((FAILED + 1)); echo "状態: 測定失敗（メタデータ生成）" > "$OUT_DIR/$tag.status.txt"; return 1
  fi
  cp "$DISK" "$disk_a" || {
    FAILED=$((FAILED + 1)); echo "状態: 測定失敗（媒体複製）" > "$OUT_DIR/$tag.status.txt"; return 1;
  }
  if [ "$scenario" = drive2 ]; then
    cp "$DISK" "$disk_b" || {
      FAILED=$((FAILED + 1)); echo "状態: 測定失敗（媒体複製）" > "$OUT_DIR/$tag.status.txt"; return 1;
    }
    printf '%s\n' "$disk_a" "$disk_b" > "$WORK/$tag.m3u"
    media="$WORK/$tag.m3u"
  fi
  run_q88measure_retry "$iolog" "$stdout" "$stderr" \
    --core "$CORE" --rom-dir "$rom" --disk "$media" --frames "$FRAMES" \
    --io-log "$iolog" --io-log-from-frame "$CAPTURE_FROM" --out "$report" \
    --type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'
  if [ "$?" -ne 0 ]; then
    publish_run_files "$tag" "$stage"
    FAILED=$((FAILED + 1))
    echo "状態: 測定失敗（生成済みファイルは診断用に保存）" > "$OUT_DIR/$tag.status.txt"
    echo "エラー: $tag の測定に失敗" >&2
    return 1
  fi
  drops="$(awk '/^# 取りこぼし:/ {gsub(/[^0-9]/, "", $3); sum += $3} END {print sum + 0}' "$iolog")"
  publish_run_files "$tag" "$stage"
  if [ "$drops" -ne 0 ]; then
    REJECTED=$((REJECTED + 1))
    {
      echo "状態: 不採用"
      echo "理由: I/Oログ取りこぼし ${drops}件"
      echo "生成物: 診断用に保存（解析の比較入力には使用しない）"
      echo "ROM構成: $rom_label"
    } > "$OUT_DIR/$tag.status.txt"
    echo "不採用: $tag のI/Oログに取りこぼしがある（成果物は保存）" >&2
    return 2
  fi
  SUCCEEDED=$((SUCCEEDED + 1))
  {
    echo "状態: 採用"
    echo "実行窓: ${FRAMES}F"
    echo "I/O採取窓: frame ${CAPTURE_FROM}以上 ${FRAMES}未満"
    echo "取りこぼし: 0件"
    echo "ROM構成: $rom_label"
  } > "$OUT_DIR/$tag.status.txt"
  echo "OK: ${tag}（${FRAMES}F、採取${CAPTURE_FROM}-${FRAMES}F、取りこぼし0件）"
  return 0
}

measure_one no_disk.official no_disk official_full official_no_disk || true

OFFICIAL_CAPACITY_OK=0
if grep -q '^状態: 採用$' "$OUT_DIR/no_disk.official.status.txt" 2>/dev/null; then
  OFFICIAL_CAPACITY_OK=1
  echo "OK: 公式ROM一式no_disk armの取りこぼし0件を先行確認（採取窓は共通関門で確認）"
else
  printf '%s\n' '# no_disk信号解析' '測定一式の状態: 部分的' \
    '公式ROM一式no_disk armが不採用または失敗。混成armは未実施。' \
    '判断: 高密度runを特例採用せず、I/O容量をさらに増やして再測定する。' \
    > "$OUT_DIR/no_disk-signals.txt"
fi

MIXED_READY=0
if [ "$OFFICIAL_CAPACITY_OK" -eq 1 ]; then
  measure_one no_disk.mixed-default no_disk mixed_default mixed_no_disk || true
  measure_one drive2.mixed-default drive2 mixed_default mixed_normal || true
fi

# 介入前の必須関門。公式1 armと混成既定2 armの必要区間・取りこぼし・
# 比較可能な公開ビットを確かめる。ここで「公式」は公式ROM一式だけを指す。
if [ "$OFFICIAL_CAPACITY_OK" -eq 1 ] &&
   grep -q '^状態: 採用$' "$OUT_DIR/no_disk.mixed-default.status.txt" 2>/dev/null &&
   grep -q '^状態: 採用$' "$OUT_DIR/drive2.mixed-default.status.txt" 2>/dev/null; then
  if python3 "$REPO/tools/analyze_no_disk_signals.py" \
    --no-disk "$OUT_DIR/no_disk.mixed-default.iolog.txt" \
    --no-disk-meta "$OUT_DIR/no_disk.mixed-default.meta.json" \
    --normal "$OUT_DIR/drive2.mixed-default.iolog.txt" \
    --normal-meta "$OUT_DIR/drive2.mixed-default.meta.json" \
    --official "$OUT_DIR/no_disk.official.iolog.txt" \
    --official-meta "$OUT_DIR/no_disk.official.meta.json" \
    --after-frame "$CAPTURE_FROM" --through-frame "$FRAMES" \
    --require-full-window \
    --suite-state "部分的（3/4 run採用、介入run未測定）" \
    --out "$OUT_DIR/no_disk-signals.txt"; then
    MIXED_READY=1
    echo "OK: 公式1 arm・混成既定2 armの必要区間・取りこぼし・比較可能項目を事前確認"
  else
    ANALYSIS_FAILED=$((ANALYSIS_FAILED + 1))
    printf '%s\n' '# no_disk信号解析' '測定一式の状態: 部分的' \
      '公式1 arm・混成既定2 armの事前検査に失敗した。介入armは未実施。' \
      'これは比較結果ではなく測定失敗である。生ログとstatusは保存済み。' \
      > "$OUT_DIR/no_disk-signals.txt"
  fi
else
  ANALYSIS_FAILED=$((ANALYSIS_FAILED + 1))
  if [ "$OFFICIAL_CAPACITY_OK" -eq 1 ]; then
    printf '%s\n' '# no_disk信号解析' '測定一式の状態: 部分的' \
      '公式ROM一式no_disk・混成既定no_disk・混成既定正常B:の採用runが揃わず測定失敗。介入armは未実施。' \
      > "$OUT_DIR/no_disk-signals.txt"
  fi
fi

if [ "$MIXED_READY" -eq 1 ]; then
  measure_one no_disk.mixed-intervention no_disk mixed_intervention mixed_intervention || true
else
  {
    echo "状態: 未実施"
    echo "理由: 公式1 arm・混成既定2 armの事前検査が不合格"
  } > "$OUT_DIR/no_disk.mixed-intervention.status.txt"
fi

if [ "$SUCCEEDED" -eq 4 ]; then
  tmp_analysis="$WORK/no_disk-signals.complete.txt"
  if python3 "$REPO/tools/analyze_no_disk_signals.py" \
      --no-disk "$OUT_DIR/no_disk.mixed-default.iolog.txt" \
      --no-disk-meta "$OUT_DIR/no_disk.mixed-default.meta.json" \
      --normal "$OUT_DIR/drive2.mixed-default.iolog.txt" \
      --normal-meta "$OUT_DIR/drive2.mixed-default.meta.json" \
      --official "$OUT_DIR/no_disk.official.iolog.txt" \
      --official-meta "$OUT_DIR/no_disk.official.meta.json" \
      --intervention "$OUT_DIR/no_disk.mixed-intervention.iolog.txt" \
      --intervention-meta "$OUT_DIR/no_disk.mixed-intervention.meta.json" \
      --after-frame "$CAPTURE_FROM" --through-frame "$FRAMES" \
      --require-full-window \
      --suite-state "完全（4/4 run採用）" --out "$tmp_analysis"; then
    mv "$tmp_analysis" "$OUT_DIR/no_disk-signals.txt"
  else
    SUCCEEDED=$((SUCCEEDED - 1))
    REJECTED=$((REJECTED + 1))
    {
      echo "状態: 不採用"
      echo "理由: 打鍵以降の全採取区間でSENSE反復または応答欠落を確認できない"
      echo "生成物: 診断用に保存"
    } > "$OUT_DIR/no_disk.mixed-intervention.status.txt"
  fi
fi

if grep -q '^状態: 採用$' "$OUT_DIR/no_disk.mixed-intervention.status.txt" 2>/dev/null; then
  screen_detail="$WORK/no_disk-wait-screen.detail.txt"
  python3 "$REPO/tools/check_l3_screen_output.py" \
    --report "$OUT_DIR/no_disk.mixed-intervention.report.txt" \
    --expected "$REPO/tests/conformance/expected_screen.tsv" --scenario no_disk \
    > "$screen_detail"
  screen_rc=$?
  {
    echo "参照run: no_disk.mixed-intervention［ROM構成: 混成介入（公式main一式＋自作sub待ち介入版）］"
    if [ "$SUCCEEDED" -eq 4 ]; then
      echo "測定一式の状態: 完全（4/4 run採用）"
    else
      echo "測定一式の状態: 部分的"
    fi
    cat "$screen_detail"
    if [ "$screen_rc" -eq 0 ]; then
      echo "仮説結果: 混成介入no_diskの800F画面は公式no_disk期待値と一致"
    elif [ "$screen_rc" -eq 1 ]; then
      echo "仮説結果: 混成介入no_diskの800F画面は公式no_disk期待値と不一致"
    else
      echo "解析不能: 待ち介入の画面報告を解析できない"
    fi
  } > "$OUT_DIR/no_disk-wait-screen.txt"
else
  printf '%s\n' '測定一式の状態: 部分的' \
    '介入runは不採用または失敗のため、画面判定なし。' > "$OUT_DIR/no_disk-wait-screen.txt"
fi

write_summary
if [ "$ATTEMPTED" -eq 4 ] && [ "$SUCCEEDED" -eq 4 ] &&
   [ "$REJECTED" -eq 0 ] && [ "$FAILED" -eq 0 ] &&
   [ "$ANALYSIS_FAILED" -eq 0 ]; then
  echo "完了: 4条件の生ログ・画面報告・runメタデータ・値なし解析報告を保存した"
  exit 0
fi
echo "未完了: 部分結果と不採用/失敗runを出力先へ保存した" >&2
exit 1

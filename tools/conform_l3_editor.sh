#!/usr/bin/env bash
# tools/conform_l3_editor.sh — l4-c6 スクリーンエディタ適合の場面固定。
#
# docs/spec/l3-main.md 第16節（l4-s1f本体+追補1-3）・第17節（l4-s1g本体+
# 追補）・第18節項5（l4-s1h、キーリピート）が確定した腕を、settle手順
# （RETURN x2、G11）つきで実行し、公式ROMと自作main ROM
# （src/build_main_rom.py）の判定名・座標・出力行署名を突き合わせる。
# l4-s1hの腕（s1h_*）は docs/notes/l4-s1h-key-repeat-results.md が確定
# したQ1(qキー時系列)・Q2(→の6腕)・Q3(→単発の列79越え)・G4/G5(対照)を
# そのまま流用（B4は遅延をB4の期待値に合わせ込んだ腕なので、キーリピート
# の独立な検証にはならない——l4-c6結果ノートの追補節を参照）。
# tools/conform_l4.sh と同じ二層方針:
#   - 自作ROM側の照合は、公式環境の有無に関わらず常に、コミット済みの
#     tests/conformance/expected_l4_editor.tsv とだけ照合して回る
#     （M8、公式環境が無い環境でも第三者がこのテストを回せる）
#   - 公式ROM(PC88_REF_ROM_DIR)がある場合だけ、期待値の再現性を確認する
#
# 期待値はtests/conformance/expected_l4_editor.tsvに置くが、値そのもの
# （文字コード・画面本文）は一切含まない。件数とSHA-256のみ（禁則事項4）。
# 正規化は tools/l4_editor_conform_normalize.py が行う（二重実装しない）。
#
# 使い方:
#   tools/conform_l3_editor.sh                          # 自作ROM側の照合のみ
#   PC88_REF_ROM_DIR=/path/to/rom tools/conform_l3_editor.sh --record  # 期待値を採取し直す(器具担当のみ)
#   PC88_REF_ROM_DIR=/path/to/rom tools/conform_l3_editor.sh           # 公式再現性+自作照合
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECORD="$REPO/tools/l4_editor_conform_record.py"
NORMALIZE="$REPO/tools/l4_editor_conform_normalize.py"
BUILD_MAIN="$REPO/src/build_main_rom.py"
EXPECTED="$REPO/tests/conformance/expected_l4_editor.tsv"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }

if [ ! -f "$EXPECTED" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED" >&2
  exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-editor-conform.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

overall_rc=0
RECORD_MODE=0
[ "${1:-}" = "--record" ] && RECORD_MODE=1

if [ -n "${PC88_REF_ROM_DIR:-}" ]; then
  say "公式ROMでの記録・再現性確認"
  if python3 "$RECORD" --rom-dir "$PC88_REF_ROM_DIR" --arm all --workdir "$WORK/official" \
      > "$WORK/official.json" 2> "$WORK/official.err.txt"; then
    ok "公式ROM: 全腕の走行が完了"
  else
    ng "公式ROM: 走行に失敗した"
    tail -20 "$WORK/official.err.txt" | sed 's/^/       /'
    overall_rc=1
  fi

  if [ "$RECORD_MODE" = 1 ]; then
    python3 "$NORMALIZE" --raw-json "$WORK/official.json" --status-rows official \
      --expected-tsv "$EXPECTED" --write-expected
    ok "期待値を採取し直した: $EXPECTED (コミットすること)"
    exit "$overall_rc"
  fi

  if python3 "$NORMALIZE" --raw-json "$WORK/official.json" --status-rows official \
      --expected-tsv "$EXPECTED" > "$WORK/official_cmp.json" 2> "$WORK/official_cmp.err.txt"; then
    ok "公式ROM: 期待値と再現一致"
  else
    ng "公式ROM: 期待値と不一致(器具・タイミングの変化の可能性、下記参照)"
    cat "$WORK/official_cmp.json" | sed 's/^/       /'
    overall_rc=1
  fi
fi

say "自作main ROMの組み立て"
SELF_ROMDIR="$WORK/self_rom"
mkdir -p "$SELF_ROMDIR"
if ! python3 "$BUILD_MAIN" "$SELF_ROMDIR" > "$WORK/self_build.txt" 2>&1; then
  echo "エラー: 自作main ROMの組み立てに失敗した" >&2
  cat "$WORK/self_build.txt" >&2
  exit 1
fi

say "自作ROMでの記録"
if python3 "$RECORD" --rom-dir "$SELF_ROMDIR" --arm all --workdir "$WORK/self" \
    > "$WORK/self.json" 2> "$WORK/self.err.txt"; then
  ok "自作ROM: 全腕の走行が完了"
else
  ng "自作ROM: 走行に失敗した"
  tail -20 "$WORK/self.err.txt" | sed 's/^/       /'
  overall_rc=1
fi

say "自作ROM: 期待値(公式ROM由来)との照合"
CMP_JSON="$WORK/self_cmp.json"
python3 "$NORMALIZE" --raw-json "$WORK/self.json" --status-rows self \
  --expected-tsv "$EXPECTED" > "$CMP_JSON" 2>"$WORK/self_cmp.err.txt"
CMP_RC=$?
MATCH_N="$(python3 -c 'import json;print(len(json.load(open("'"$CMP_JSON"'"))["match"]))' 2>/dev/null || echo '?')"
MISMATCH_LIST="$(python3 -c 'import json;print(",".join(json.load(open("'"$CMP_JSON"'"))["mismatch"]))' 2>/dev/null || echo '?')"
TOTAL_N=32
if [ "$CMP_RC" = 0 ]; then
  ok "自作ROM: ${MATCH_N}/${TOTAL_N}腕が期待値と一致"
else
  ng "自作ROM: ${MATCH_N}/${TOTAL_N}腕が一致。不一致腕: ${MISMATCH_LIST}"
  overall_rc=1
fi

say "結果まとめ"
if [ "$overall_rc" = 0 ]; then
  ok "全項目OK"
else
  ng "NGあり（上記参照）。不一致があっても本スクリプトは自作ROMを直さない（測定・照合専用）"
fi
exit "$overall_rc"

#!/usr/bin/env bash
# tools/conform_l3.sh — L3 適合テスト層のランナー（公式ROM・公式ディスクが要る）。
#
# tools/verify_l3.sh は**自己検証層**（自作ROM＋自作ディスクだけで回る。
# 公式ROM不要）。このスクリプトはその対になる**適合テスト層**で、
# docs/PLAN.md「次にやること（M6の続き）」1項で定めた二層方針の実装。
# say/ok/ng の作法・「わざと壊して検出力を確認する」・制限事項を
# 正直に書く構成は tools/verify_l3.sh / tools/verify_l1.sh を踏襲する。
#
# 期待値は tests/conformance/expected.tsv に置くが、**値そのものは
# 一切コミットしない**。件数とSHA-256だけ（CLAUDE.md 禁止事項4）。
# ハッシュ抽出は tools/hash_io_stream.py（tools/cmp_io.py の抽出ロジックを
# import して共有している）。
#
# 使い方:
#   PC88_REF_ROM_DIR=/path/to/rom PC88_REF_DISK_DIR=/path/to/disk \
#       tools/conform_l3.sh
#
# 環境変数が未設定なら、何が必要かを表示して SKIP（終了コード0）で戻る。
# 「検出力の自己検査」（下記）は環境変数の有無に関わらず常に実行する。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HASH="$REPO/tools/hash_io_stream.py"
EXPECTED="$REPO/tests/conformance/expected.tsv"
FILES_EXPECTED="$REPO/tests/conformance/expected_files.tsv"
LOAD_EXPECTED="$REPO/tests/conformance/expected_load.tsv"
LOAD_EXISTING_EXPECTED="$REPO/tests/conformance/expected_load_existing.tsv"
SEQFILE_EXPECTED="$REPO/tests/conformance/expected_seqfile.tsv"
KILL_EXPECTED="$REPO/tests/conformance/expected_kill.tsv"
NAME_EXPECTED="$REPO/tests/conformance/expected_name.tsv"
WRITE_PROTECT_EXPECTED="$REPO/tests/conformance/expected_write_protect.tsv"
NO_DISK_EXPECTED="$REPO/tests/conformance/expected_no_disk.tsv"
UNREADABLE_DISK_EXPECTED="$REPO/tests/conformance/expected_unreadable_disk.tsv"
DRIVE2_EXPECTED="$REPO/tests/conformance/expected_drive2.tsv"
SCREEN_EXPECTED="$REPO/tests/conformance/expected_screen.tsv"
SCREEN_CHECK="$REPO/tools/check_l3_screen_output.py"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
# build_mixed_rom は tools/lib_l3_measure.sh に切り出した（tools/diag_l3_mixed.sh
# と共有するため。二重実装を避ける。詳細はそのファイル冒頭のコメント参照）。
source "$REPO/tools/lib_l3_measure.sh"
# 検出力の自己検査は、公式ディスクの実測ログ(measurements/m6g-d0-boot-run1.iolog.txt)
# ではなく、tests/fixtures/ の合成フィクスチャを使う。2026-08-10、
# measurements/*.iolog.txt にデータポート伏せ字を適用したため、実測ログを
# hash_io_stream.py に通しても "--" が抽出されるだけで tests/conformance/
# expected.tsv と一致しなくなった（マスク後の値は元の値と一致しないのが
# 伏せ字の目的そのものなので、これは正しい動作）。自己検査に要るのは
# 「比較ロジックが機能しているか」だけで公式データは不要なので、
# 完全に自作の合成データに切り替える（docs/notes/disclosure-2026-08-10.md 3節）。
SELFTEST_LOG="$REPO/tests/fixtures/conform_l3_selftest.iolog.txt"
SELFTEST_EXPECTED="$REPO/tests/fixtures/conform_l3_selftest.expected.tsv"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }
na()  { printf '  \033[33m--\033[0m   %s\n' "$1"; }   # 判定不能（合否ではない）

if [ ! -f "$EXPECTED" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED" >&2
  exit 2
fi
if [ ! -f "$FILES_EXPECTED" ] || [ ! -f "$LOAD_EXPECTED" ]; then
  echo "エラー: FILES/LOAD入口の期待値ファイルが無い" >&2
  exit 2
fi
if [ ! -f "$LOAD_EXISTING_EXPECTED" ] || [ ! -f "$SEQFILE_EXPECTED" ] \
   || [ ! -f "$KILL_EXPECTED" ] || [ ! -f "$NAME_EXPECTED" ]; then
  echo "エラー: m7cg需要入口の期待値ファイルが無い" >&2
  exit 2
fi
if [ ! -f "$SCREEN_EXPECTED" ] || [ ! -f "$SCREEN_CHECK" ]; then
  echo "エラー: 画面出力の期待値または判定器が無い" >&2
  exit 2
fi
for path_expected in "$WRITE_PROTECT_EXPECTED" "$NO_DISK_EXPECTED" \
                     "$UNREADABLE_DISK_EXPECTED" "$DRIVE2_EXPECTED"; do
  if [ ! -f "$path_expected" ]; then
    echo "エラー: エラー／ドライブ2経路の期待値が無い: $path_expected" >&2
    exit 2
  fi
done
if [ ! -f "$SELFTEST_LOG" ]; then
  echo "エラー: 自己検査用の入力が無い: $SELFTEST_LOG" >&2
  exit 2
fi
if [ ! -f "$SELFTEST_EXPECTED" ]; then
  echo "エラー: 自己検査用の期待値が無い: $SELFTEST_EXPECTED" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

overall_rc=0

# -----------------------------------------------------------------------
# 照合の本体。iolog 1つと期待値TSV 1つを受け取り、各行を照合して結果を
# 表示する。戻り値は「1件でも不一致/エラーがあれば1」。
# 自己検査（このスクリプトが検出力を持つか）と本番（公式環境）の両方で
# 同じ関数を使う。二重実装を避けるため。
# -----------------------------------------------------------------------
run_conformance() {
  local iolog="$1" expected="$2" label="$3"
  local rc=0
  local line name cpu port kind count sha out a_count a_sha

  while IFS=$'\t' read -r name cpu port kind count sha; do
    [ -z "${name:-}" ] && continue
    case "$name" in \#*) continue ;; esac

    if out="$(python3 "$HASH" "$iolog" --cpu "$cpu" --port "$port" --kind "$kind" 2>"$WORK/err.$name")"; then
      a_count="$(printf '%s\n' "$out" | awk -F'\t' '$1=="count"{print $2}')"
      a_sha="$(printf '%s\n' "$out" | awk -F'\t' '$1=="sha256"{print $2}')"
    else
      ng "[$label] ${name}: 抽出に失敗（${cpu}/${kind}/${port}）"
      sed 's/^/       /' "$WORK/err.$name"
      rc=1
      continue
    fi

    if [ "$a_count" != "$count" ]; then
      ng "[$label] ${name}: 件数不一致（期待 ${count} 件 ／ 実測 ${a_count} 件。ハッシュ以前に検出）"
      rc=1
    elif [ "$a_sha" != "$sha" ]; then
      ng "[$label] ${name}: 件数(${a_count}件)は一致するがSHA-256が不一致"
      rc=1
    else
      ok "[$label] ${name}: 件数(${a_count})・SHA-256とも一致"
    fi
  done < "$expected"

  return "$rc"
}

# -----------------------------------------------------------------------
# テキスト画面の追加測定。5.2節の適合条件1〜5とは別の事実報告であり、
# 未到達・本文不一致を既存条件の失格にはしない。入力不備や判定器自身の
# 故障だけはテスト基盤の異常なので overall_rc に反映する。
# 画面本文は判定器からも本関数からも表示しない。
# -----------------------------------------------------------------------
report_screen_comparison() {
  local scenario="$1" label="$2" official_report="$3" mixed_report="$4"
  local mode report out rc

  say "画面出力 ${label}: ハッシュ・行数・文字数の追加測定（適合条件1〜5とは別）"
  for mode in official mixed; do
    if [ "$mode" = official ]; then report="$official_report"; else report="$mixed_report"; fi
    out="$WORK/screen.${scenario}.${mode}.txt"
    if python3 "$SCREEN_CHECK" --report "$report" --expected "$SCREEN_EXPECTED" \
         --scenario "$scenario" > "$out"; then
      ok "${label}-${mode}: 固定した画面期待値と一致"
    else
      rc=$?
      if [ "$rc" -eq 1 ]; then
        na "${label}-${mode}: 画面期待値と不一致（事実報告。適合条件1〜5の失格にはしない）"
        sed 's/^/       /' "$out"
      else
        ng "${label}-${mode}: 画面報告または期待値を解析できない"
        sed 's/^/       /' "$out"
        overall_rc=1
      fi
    fi
  done

  out="$WORK/screen.${scenario}.compare.txt"
  if python3 "$SCREEN_CHECK" --report "$official_report" \
       --compare-report "$mixed_report" > "$out"; then
    ok "${label}: 公式一式と混成の画面出力が完全一致"
  else
    rc=$?
    if [ "$rc" -eq 1 ]; then
      na "${label}: 公式一式と混成の画面出力が不一致（位置・分類は下記。失格にはしない）"
      sed 's/^/       /' "$out"
    else
      ng "${label}: 公式一式と混成の画面比較を実行できない"
      sed 's/^/       /' "$out"
      overall_rc=1
    fi
  fi
}

# -----------------------------------------------------------------------
# 検出力の自己検査（公式環境なしでも回せる。tests/fixtures/ の合成データを使う）
#
# a. 正しい入力・正しい期待値                → 全件一致（PASS）
# b. ハッシュを1文字書き換えた期待値のコピー  → 不一致で検出（NG）
# c. 件数を書き換えた期待値のコピー           → ハッシュ以前に件数不一致で検出
# d. 存在しないポートを指定した期待値のコピー → hash_io_stream.py 自体が
#                                                0件エラーで落ちる（黙って
#                                                「一致」に化けない）
# -----------------------------------------------------------------------
say "検出力の自己検査（比較ロジック自体をわざと壊して検出できるか）"

selftest_rc=0

echo "  -- a. 正しい入力・正しい期待値 → 一致するはず --"
if run_conformance "$SELFTEST_LOG" "$SELFTEST_EXPECTED" "自己検査a"; then
  :
else
  ng "自己検査a: 正しい入力のはずが不一致になった（期待値ファイル自体を疑うこと）"
  selftest_rc=1
fi

echo "  -- b. ハッシュを1文字壊した期待値 → 不一致で検出されるはず --"
awk 'BEGIN{FS=OFS="\t"} /^#/ || NF==0 {print; next}
     { sha=$6; last=substr(sha,length(sha),1)
       sha=substr(sha,1,length(sha)-1) (last=="0"?"f":"0")
       $6=sha; print }' "$SELFTEST_EXPECTED" > "$WORK/expected.bad_sha.tsv"
if run_conformance "$SELFTEST_LOG" "$WORK/expected.bad_sha.tsv" "自己検査b" >"$WORK/b.out" 2>&1; then
  cat "$WORK/b.out"
  ng "自己検査b: 壊したハッシュが誤って一致してしまった（検出力が無い）"
  selftest_rc=1
else
  cat "$WORK/b.out"
  ok "自己検査b: ハッシュを1文字壊した期待値は正しく不一致として検出された"
fi

echo "  -- c. 件数を壊した期待値 → 件数不一致で検出されるはず --"
awk 'BEGIN{FS=OFS="\t"} /^#/ || NF==0 {print; next}
     { $5 = $5 + 1; print }' "$SELFTEST_EXPECTED" > "$WORK/expected.bad_count.tsv"
if run_conformance "$SELFTEST_LOG" "$WORK/expected.bad_count.tsv" "自己検査c" >"$WORK/c.out" 2>&1; then
  cat "$WORK/c.out"
  ng "自己検査c: 件数を壊した期待値が誤って一致してしまった（検出力が無い）"
  selftest_rc=1
else
  cat "$WORK/c.out"
  if grep -q "件数不一致" "$WORK/c.out"; then
    ok "自己検査c: 件数不一致として（ハッシュ以前に）正しく検出された"
  else
    ng "自己検査c: 不一致にはなったが「件数不一致」として報告されていない"
    selftest_rc=1
  fi
fi

echo "  -- d. 存在しないポート → 抽出0件がエラーで落ちるはず（黙って一致に化けない） --"
awk 'BEGIN{FS=OFS="\t"} /^#/ || NF==0 {print; next}
     { $3 = "FFFE"; print }' "$SELFTEST_EXPECTED" > "$WORK/expected.bad_port.tsv"
if run_conformance "$SELFTEST_LOG" "$WORK/expected.bad_port.tsv" "自己検査d" >"$WORK/d.out" 2>&1; then
  cat "$WORK/d.out"
  ng "自己検査d: 存在しないポートの抽出が誤って通ってしまった"
  selftest_rc=1
else
  cat "$WORK/d.out"
  if grep -q "抽出に失敗" "$WORK/d.out"; then
    ok "自己検査d: 0件抽出は hash_io_stream.py 自体がエラーで落ち、それを検出できた"
  else
    ng "自己検査d: 不一致にはなったが想定した経路（抽出失敗）で落ちていない"
    selftest_rc=1
  fi
fi

if [ "$selftest_rc" -eq 0 ]; then
  ok "検出力の自己検査: 全項目OK"
else
  ng "検出力の自己検査: 失敗した項目がある（このスクリプト自体を信用できない状態）"
fi
overall_rc=$(( overall_rc || selftest_rc ))

# -----------------------------------------------------------------------
# 検出力の自己検査（続き）: 混成ROMディレクトリの「コピー＋サブROMだけ
# 差替」が実際に効いているかを、公式環境なしで確認する。
#
# ここで使う"公式ROM一式"はダミー（全部自作）。自作物同士なので中身を
# cmp で比較してよい（比較対象がどちらも自作である限り規律に触れない。
# 公式ROM・公式ディスクは一切登場しない）。
# -----------------------------------------------------------------------
say "検出力の自己検査（続き）: 混成ROMディレクトリの差し替えが実際に効いているか"

mixed_selftest_rc=0

DUMMY_OFFICIAL="$WORK/dummy_official_rom"
mkdir -p "$DUMMY_OFFICIAL"
python3 "$REPO/src/l3_service/make_subrom.py" "$DUMMY_OFFICIAL" --break-response >/dev/null
echo "dummy main-side rom for selftest only (not a real ROM)" > "$DUMMY_OFFICIAL/N88.ROM"
echo "dummy runtime state; must not enter mixed ROM" > "$DUMMY_OFFICIAL/stale.srm"

DUMMY_MIXED="$WORK/dummy_mixed_rom"
if ! build_mixed_rom "$DUMMY_OFFICIAL" "$DUMMY_MIXED"; then
  ng "自己検査e: build_mixed_rom 自体が失敗した"
  mixed_selftest_rc=1
fi

REFERENCE_SUBROM="$WORK/reference_subrom"
mkdir -p "$REFERENCE_SUBROM"
python3 "$REPO/src/l3_service/make_subrom.py" "$REFERENCE_SUBROM" >/dev/null

if [ -f "$DUMMY_MIXED/N88.ROM" ] && cmp -s "$DUMMY_MIXED/N88.ROM" "$DUMMY_OFFICIAL/N88.ROM"; then
  ok "自己検査e: main側ファイル(N88.ROM相当)はコピーされ内容も保持されている"
else
  ng "自己検査e: main側ファイルがコピーされていない、または内容が変わった"
  mixed_selftest_rc=1
fi

if [ -f "$DUMMY_MIXED/DISK.ROM" ] && cmp -s "$DUMMY_MIXED/DISK.ROM" "$REFERENCE_SUBROM/DISK.ROM"; then
  ok "自己検査f: DISK.ROMは自作サブROM(通常版)に正しく差し替わっている"
else
  ng "自己検査f: DISK.ROMが自作サブROM(通常版)と一致しない（差し替えが効いていない）"
  mixed_selftest_rc=1
fi

if [ -f "$DUMMY_MIXED/DISK.ROM" ] && cmp -s "$DUMMY_MIXED/DISK.ROM" "$DUMMY_OFFICIAL/DISK.ROM"; then
  ng "自己検査g: DISK.ROMが「公式」ダミー(break-response版)のまま残っている（上書きされていない）"
  mixed_selftest_rc=1
else
  ok "自己検査g: DISK.ROMは「公式」ダミーのままではなく、確かに上書きされている"
fi

if [ -e "$DUMMY_MIXED/stale.srm" ]; then
  ng "自己検査h: ROM以外の実行状態ファイルまで混成へコピーされた"
  mixed_selftest_rc=1
else
  ok "自己検査h: ROM以外の実行状態ファイルは混成へコピーされない"
fi

if [ "$mixed_selftest_rc" -eq 0 ]; then
  ok "混成ROMディレクトリ構築の自己検査: 全項目OK"
else
  ng "混成ROMディレクトリ構築の自己検査: 失敗した項目がある"
fi
overall_rc=$(( overall_rc || mixed_selftest_rc ))

# -----------------------------------------------------------------------
# 本番: 公式ROM・公式ディスクでの測定 → 期待値と照合
# -----------------------------------------------------------------------
say "適合テスト本体（公式ROM・公式ディスクが必要）"

if [ -z "${PC88_REF_ROM_DIR:-}" ] || [ -z "${PC88_REF_DISK_DIR:-}" ]; then
  cat <<'EOF'
  SKIP: 公式ROM・公式ディスクの環境変数が未設定。

  本体（公式環境での実測 → tests/conformance/expected.tsv との照合）には
  以下の2つの環境変数が要る。CLAUDE.md「パスの扱い」により、私物のパスは
  環境変数経由でのみ受け取る（リポジトリ内に絶対パスを焼き込まない）。

    PC88_REF_ROM_DIR   公式ROM（N88.ROM 等）の置き場
    PC88_REF_DISK_DIR  diskA（N88-BASIC）の D88 イメージの置き場
                        （ファイル名 N88_FE.D88 を想定。
                         measurements/m6g-d0-boot-run1.txt と同条件）

  使い方の例:
    PC88_REF_ROM_DIR=/path/to/rom PC88_REF_DISK_DIR=/path/to/disk \
        tools/conform_l3.sh

  上の「検出力の自己検査」は公式環境が無くても常に実行しており、
  そちらの結果はこのSKIPと無関係に独立して判定済み。
EOF
  echo
  if [ "$overall_rc" -eq 0 ]; then
    echo "conform_l3: 自己検査OK・本体はSKIP（公式環境未設定）"
  else
    echo "conform_l3: 自己検査で失敗あり（本体はSKIP）"
  fi
  exit "$overall_rc"
fi

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "エラー: コアが無い。先に tools/setup_harness.sh を実行すること" >&2
  exit 1
fi
if [ ! -x "$FRONTEND" ]; then
  say "フロントエンドをビルド"
  make -s -C "$REPO/tools/harness/frontend" || exit 1
fi

DISK="$PC88_REF_DISK_DIR/N88_FE.D88"
if [ ! -f "$DISK" ]; then
  echo "エラー: 参照ディスクが無い: $DISK" >&2
  exit 1
fi

say "diskA 起動を実測（frames 1800、measurements/m6g-d0-boot-run1.txt と同条件）"
run_q88measure_retry "$WORK/live.iolog.txt" "$WORK/live.stdout.txt" "$WORK/live.stderr.txt" \
    --core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$DISK" \
    --frames 1800 --io-log "$WORK/live.iolog.txt" --out "$WORK/live.report.txt" || {
  echo "エラー: q88measure が失敗した" >&2
  cat "$WORK/live.stderr.txt" >&2
  exit 1
}

say "期待値ファイル(tests/conformance/expected.tsv)の各行と照合"
if run_conformance "$WORK/live.iolog.txt" "$EXPECTED" "本番"; then
  :
else
  overall_rc=1
fi

# -----------------------------------------------------------------------
# 混成: 公式main側ROM一式 + 自作サブROM(DISK.ROM)で公式ディスクを起動
#
# 上の「本番」は公式ROM一式（サブROMも公式）で走らせており、これが
# 判定しているのは**公式環境の再現性（決定論性）**であって、
# 自作サブROM（src/l3_service/make_subrom.py）が公式ディスク相手に
# docs/spec/l3-subrom.md 5.2節条件1を満たすかは一度も判定していなかった。
# ここでサブROMだけを自作品に差し替えて同じ期待値と照合することで、
# それを判定する（docs/PLAN.md「次にやること（M6の続き）」2項）。
#
# 一致しないのが現時点の正常な想定である。自作サブROMはまだ起動時の
# 高速バルクモード（5635件、1.6節・1.10節）を実装していない
# （make_subrom.py 冒頭コメント参照）。したがって不一致を「不適合」と
# して正直に報告する。通すために期待値やテストを緩めることはしない。
# -----------------------------------------------------------------------
say "混成ROM適合テスト（公式main ROM一式 + 自作サブROM(DISK.ROM)を公式ディスクで起動）"

# 測定本体（混成ROMディレクトリ構築 + q88measure 実行）は
# tools/lib_l3_measure.sh の run_l3_mixed_measurement に切り出した
# （tools/diag_l3_mixed.sh と同条件で二重実装しないため）。
if ! run_l3_mixed_measurement "$PC88_REF_ROM_DIR" "$DISK" "$WORK" \
     "$WORK/mixed.iolog.txt" "$WORK/mixed.report.txt"; then
  exit 1
fi

report_screen_comparison disk_boot "diskA起動" \
  "$WORK/live.report.txt" "$WORK/mixed.report.txt"

say "混成ROMのI/Oストリームを期待値と照合"
if run_conformance "$WORK/mixed.iolog.txt" "$EXPECTED" "混成(自作サブROM)"; then
  ok "混成: 自作サブROMが適合条件1を満たした（想定より進んでいた場合。docs/PLAN.mdの状況認識を更新すること）"
else
  overall_rc=1
  # ---------------------------------------------------------------
  # 分岐点報告（値は一切出さない）。
  #
  # 設計判断: cmp_io.py の report_mismatch/fmt_event は不一致箇所の
  # value を表示する実装（値を伏せるモードを持たない）。今回はそこに
  # 手を入れて「値を伏せるオプション」を足す代わりに、conform_l3.sh
  # 側を「件数比較に留める」設計を選んだ。理由: expected.tsv には
  # そもそも値の列を持たせていない（ハッシュのみ。CLAUDE.md禁止事項4）
  # ので、「どの通し番号で値が食い違ったか」は原理的に導けない
  # （導けるとしたら値そのものを別途保持している場合だけで、それは
  # 今回やらないと決めたこと自体と矛盾する）。ここで出せるのは
  # 「受信件数」と、件数が期待に届かず打ち切られた場合の「最初に
  # 届かなかった通し番号」（=推定される分岐点）・その cpu/port/kind
  # （expected.tsv に既に載っているメタ情報。値ではない）まで。
  # 件数が一致しているのにSHA-256だけ違う場合は、値を持たない設計上
  # 「特定できない」と正直に言う。
  # ---------------------------------------------------------------
  echo
  echo "  --- 分岐点報告（値は出さない。件数と通し番号のみ） ---"
  while IFS=$'\t' read -r name cpu port kind count sha; do
    [ -z "${name:-}" ] && continue
    case "$name" in \#*) continue ;; esac
    if a_out="$(python3 "$HASH" "$WORK/mixed.iolog.txt" --cpu "$cpu" --port "$port" --kind "$kind" 2>/dev/null)"; then
      a_count="$(printf '%s\n' "$a_out" | awk -F'\t' '$1=="count"{print $2}')"
    else
      a_count=0
    fi
    if [ "$a_count" -eq 0 ]; then
      echo "  ${name}(${cpu}/${kind}/${port}): 対象イベントが1件も無い（通し番号1件目より前で分岐）"
    elif [ "$a_count" -lt "$count" ]; then
      echo "  ${name}(${cpu}/${kind}/${port}): ${a_count} 件受信した時点で途切れた（期待 ${count} 件）"
      echo "    最初に食い違ったと推定できる通し番号: $((a_count + 1)) 件目（以降を自作サブROMは未実装）"
    elif [ "$a_count" -eq "$count" ]; then
      echo "  ${name}(${cpu}/${kind}/${port}): 件数(${a_count})は一致するがSHA-256が不一致"
      echo "    値を保持しない設計のため、どの通し番号で食い違ったかはこの仕組みでは特定できない"
    else
      echo "  ${name}(${cpu}/${kind}/${port}): 想定より多い ${a_count} 件を受信（期待 ${count} 件）"
    fi
  done < "$EXPECTED"
fi

# -----------------------------------------------------------------------
# 現状の到達点（正直に書く。ごまかさない）
# -----------------------------------------------------------------------
# -----------------------------------------------------------------------
# 適合条件4（ネガティブコントロール、5.2節4項）— m7ar で新設。
#
# なぜ verify_l3.sh ではなくここなのか: 条件4「ディスク無しでサブCPUが
# 1命令も実行しない」は**相手役の main が公式でないと判定できない**。
# m7ar の2×2実測（ディスク無し・30/120フレーム、いずれも同じ傾向）:
#
#   main側  sub側   sub の I/O 件数
#   公式    公式    0            ← 仕様書1.1節の観測そのもの
#   公式    自作    0            ← 自作サブROMも同じく無音
#   自作    自作    2575         ← verify_l3.sh が NG と報告していた状態
#   自作    公式    208437       ← **公式サブROMでも無音にならない**
#
# つまり verify_l3.sh のネガティブコントロールが測っていたのは自作サブROM
# の性質ではなく、**試験用mainドライバがディスク無しでもサブを走らせて
# しまうこと**だった（公式サブROMを同じドライバで動かすと20万件出る）。
# 自作サブROMは0件で、無音になる/ならないは main 側で決まっている
# （ディスクが無いと公式mainはサブを起動しない）。
# 判定は公式mainを相手役にできるこの適合テスト層で行う。
# -----------------------------------------------------------------------
say "適合条件4のネガティブコントロール（ディスク無し・公式main + 自作サブROM）"
NEG_FRAMES=30
run_q88measure_retry "$WORK/nodisk_mixed.iolog.txt" "$WORK/nodisk_mixed.stdout.txt" "$WORK/nodisk_mixed.stderr.txt" \
    --core "$CORE" --rom-dir "$WORK/mixed_rom" --frames "$NEG_FRAMES" \
    --io-log "$WORK/nodisk_mixed.iolog.txt"
count_sub_events() {
  awk '/^# sub$/{f=1;next} /^# main$/{f=0} f && !/^#/ && NF' "$1" | wc -l | tr -d ' '
}
neg_sub="$(count_sub_events "$WORK/nodisk_mixed.iolog.txt")"
if [ "$neg_sub" = "0" ]; then
  ok "混成(公式main + 自作サブROM)はディスク無しでsubのI/Oが0件（適合条件4を満たす）"
else
  ng "混成はディスク無しでもsubが $neg_sub 件のI/Oを発行した（適合条件4を満たさない）"
  overall_rc=1
fi

# 検出力の確認（陽性対照）: 同じ数え方で、非0になる構成が実際に非0と出ること。
# ディスク無しでもサブを走らせてしまう試験用mainドライバ + 自作サブROM。
say "検出力の自己検査: 上の数え方が「非0」を検出できること（陽性対照）"
POSCTL="$WORK/negctl_positive"
mkdir -p "$POSCTL"
if python3 "$REPO/src/l3_service/make_subrom.py" "$POSCTL" >/dev/null 2>&1 \
   && python3 "$REPO/tools/make_l3_test_main.py" "$POSCTL" --requests "0:1" >/dev/null 2>&1; then
  run_q88measure_retry "$WORK/nodisk_posctl.iolog.txt" "$WORK/nodisk_posctl.stdout.txt" "$WORK/nodisk_posctl.stderr.txt" \
      --core "$CORE" --rom-dir "$POSCTL" --frames "$NEG_FRAMES" \
      --io-log "$WORK/nodisk_posctl.iolog.txt"
  pos_sub="$(count_sub_events "$WORK/nodisk_posctl.iolog.txt")"
  if [ "$pos_sub" != "0" ]; then
    ok "陽性対照: 試験用mainドライバ構成では $pos_sub 件と数えられた（0件判定は空検査ではない）"
  else
    ng "陽性対照: 非0になるはずの構成でも0件だった（数え方が壊れている可能性）"
    overall_rc=1
  fi
else
  ng "陽性対照の構成を組み立てられなかった"
  overall_rc=1
fi

# -----------------------------------------------------------------------
# 適合条件2（diskB起動時に sub が $FC を一切使わないこと、5.2節2項）
# — m7as で新設。diskB は市販ソフトのディスクで、実ファイル名は
# リポジトリにもノートにも残していない（docs/notes/m6-sub-invariant.md
# 第2版の方針）。したがってパスは環境変数 PC88_REF_DISKB でのみ受け取る
# （CLAUDE.md「私物のパスは環境変数経由でのみ」）。未設定ならSKIPする。
#
# 根拠（公式環境の実測、docs/notes/m6-sub-invariant.md 第2版）:
#   diskA d0-boot : sub OUT $FC = 5635 件
#   diskB boot    : sub OUT $FC = **0 件**（frames 600/1800/3600 いずれも）
# -----------------------------------------------------------------------
say "適合条件2（diskB起動で sub が \$FC を使わないこと）"
count_sub_fc() {   # $1 = iolog。抽出0件はエラー終了するので0として扱う
  local out
  if out="$(python3 "$HASH" "$1" --cpu sub --port FC --kind OUT 2>/dev/null)"; then
    printf '%s\n' "$out" | awk -F'\t' '$1=="count"{print $2}'
  else
    echo 0
  fi
}
if [ -z "${PC88_REF_DISKB:-}" ]; then
  echo "  SKIP: PC88_REF_DISKB が未設定（diskB の .D88 のフルパスを指定すると判定する）"
elif [ ! -f "$PC88_REF_DISKB" ]; then
  ng "PC88_REF_DISKB が指すファイルが無い"
  overall_rc=1
else
  run_q88measure_retry "$WORK/diskb_mixed.iolog.txt" "$WORK/diskb_mixed.stdout.txt" "$WORK/diskb_mixed.stderr.txt" \
      --core "$CORE" --rom-dir "$WORK/mixed_rom" --disk "$PC88_REF_DISKB" \
      --frames 1800 --io-log "$WORK/diskb_mixed.iolog.txt"
  b_fc="$(count_sub_fc "$WORK/diskb_mixed.iolog.txt")"
  if [ "${b_fc:-0}" = "0" ]; then
    ok "混成(公式main + 自作サブROM)はdiskB起動で sub OUT \$FC が0件（適合条件2を満たす）"
  else
    ng "diskB起動で sub が OUT \$FC を $b_fc 件発行した（適合条件2を満たさない）"
    overall_rc=1
  fi
  # 陽性対照: 同じ数え方で、非0になるはずのdiskA(混成)の実測が非0と出ること。
  a_fc="$(count_sub_fc "$WORK/mixed.iolog.txt")"
  if [ "${a_fc:-0}" != "0" ]; then
    ok "陽性対照: 同じ数え方でdiskA(混成)は $a_fc 件と数えられた（0件判定は空検査ではない）"
  else
    ng "陽性対照: 非0になるはずのdiskA(混成)でも0件だった（数え方が壊れている可能性）"
    overall_rc=1
  fi
fi

# -----------------------------------------------------------------------
# 適合条件3（サブの割り込み受理が、mainの直接のI/O操作を直前イベントと
# しないこと。1.3節・5.2節3項）— m7as で新設。
# 共通クロックで main+sub のI/Oイベントを1本にマージし、各割り込み受理点の
# 直前1件がどちらのCPUのイベントかを数える（tools/check_l3_cond3.py。
# 計算は analyze_sub_proto.py のQ3と同じ。出力は件数のみで値は出さない）。
# -----------------------------------------------------------------------
say "検出力の自己検査: 条件3の判定器が「直前1件がmain側」を検出できること"
COND3="$REPO/tools/check_l3_cond3.py"
python3 "$COND3" --iolog "$REPO/tests/fixtures/cond3_selftest_main_last.iolog.txt" \
                 --intlog "$REPO/tests/fixtures/cond3_selftest.intlog.txt" >/dev/null 2>&1
c3_pos=$?
python3 "$COND3" --iolog "$REPO/tests/fixtures/cond3_selftest_sub_last.iolog.txt" \
                 --intlog "$REPO/tests/fixtures/cond3_selftest.intlog.txt" >/dev/null 2>&1
c3_neg=$?
if [ "$c3_pos" -eq 1 ] && [ "$c3_neg" -eq 0 ]; then
  ok "条件3判定器: 陽性対照(直前main)で不合格・陰性対照(直前sub)で合格（検出力とfalse positive無しの両方）"
else
  ng "条件3判定器の検出力に問題がある（陽性対照rc=${c3_pos} 陰性対照rc=${c3_neg}。期待は 1 と 0）"
  overall_rc=1
fi

say "適合条件3（サブの割り込み受理の直前1件がmain側でないこと）"
run_q88measure_retry "$WORK/cond3.iolog.txt" "$WORK/cond3.stdout.txt" "$WORK/cond3.stderr.txt" \
    --core "$CORE" --rom-dir "$WORK/mixed_rom" --disk "$DISK" \
    --frames 1800 --io-log "$WORK/cond3.iolog.txt" --int-log "$WORK/cond3.intlog.txt"
if python3 "$COND3" --iolog "$WORK/cond3.iolog.txt" --intlog "$WORK/cond3.intlog.txt"; then
  ok "混成(公式main + 自作サブROM)は条件3を満たす（直前1件がmain側の受理点は0件）"
else
  c3_rc=$?
  if [ "$c3_rc" -eq 2 ]; then
    # m7as: 自作サブROMは割り込みをまったく使わない（ポーリングのみ）ため
    # 受理点が0件になる。条件3は「受理したときの性質」を定める条件なので、
    # 受理が1件も無い状態では破りようがない代わりに、判定もできない。
    # 黙ってOKにはせず、判定不能として毎回表示し、構造差そのものを
    # 記録として残す（同条件の公式subは13593件受理する。m7as実測）。
    na "条件3は判定不能: 自作サブROMは割り込みを1件も受理しない（ポーリングのみ）"
    echo "       同条件(diskA起動・1800フレーム)の公式サブROMは 13593 件受理し、"
    echo "       そのうち直前1件がmain側だったものは0件で条件3を満たす（自前の実測で1.3節を再現）。"
    echo "       自作サブROMが割り込みを使っていないこと自体は適合条件1・4には影響しないが、"
    echo "       公式との構造差として記録する。根拠: docs/notes/m7as-condition2-3-judging.md"
  else
    ng "条件3を満たさない（直前1件がmain側の受理点がある。上の件数を参照）"
    overall_rc=1
  fi
fi

# -----------------------------------------------------------------------
# 適合条件5（書き込み経路、1.35節）— m7az で新設。
# 期待値は tests/conformance/expected_write.tsv（件数・バイト数・SHA-256のみ）。
# m7bzで旧説明を訂正した。混成ROMはBASIC起動・打鍵受理・SAVE候補runまで
# 到達していたが、WRITE専用の2バイト受信位相を汎用1バイトRECVで処理して
# 相互待ちになっていた。WRITE DATA 0件なら、その実測済み到達点を報告し、
# 失格にも合格にもせず未到達とする。
# -----------------------------------------------------------------------
say "適合条件5（書き込み経路: 公式main + 自作サブROMでSAVEを実行）"
WEXPECTED="$REPO/tests/conformance/expected_write.tsv"
WDISK="$WORK/save.d88"
# 条件1の1800F実走後に同じ混成ROMディレクトリを再利用すると、コアが
# ROMディレクトリ側へ置く実行状態を条件5が継承し、8件・2112バイトでも
# SHAが対照と変わることをm7bzで再現した。各条件は独立実行なので、条件5用の
# 混成ROMを公式main一式+現在の自作subから作り直す（期待値の緩和ではない）。
WSAVE_ROM="$WORK/save_mixed_rom"
if ! build_mixed_rom "$PC88_REF_ROM_DIR" "$WSAVE_ROM"; then
  echo "エラー: 条件5用の混成ROMディレクトリ構築に失敗した" >&2
  exit 1
fi
cp "$DISK" "$WDISK"
printf '\x00' | dd of="$WDISK" bs=1 seek=26 count=1 conv=notrunc status=none
run_q88measure_retry "$WORK/save_mixed.iolog.txt" "$WORK/save_mixed.stdout.txt" "$WORK/save_mixed.stderr.txt" \
    --core "$CORE" --rom-dir "$WSAVE_ROM" --disk "$WDISK" \
    --frames 4200 --io-log "$WORK/save_mixed.iolog.txt" \
    --type-at 300 --type '\n' --type-at 700 --type '10 PRINT "T"\nSAVE"TQ"\n' 
w_out="$(python3 "$REPO/tools/hash_write_stream.py" "$WORK/save_mixed.iolog.txt" 2>/dev/null)"
w_cmds="$(printf '%s\n' "$w_out" | awk -F'\t' '$1=="commands"{print $2}')"
if [ "${w_cmds:-0}" = "0" ]; then
  na "条件5は未到達: SAVE候補runで停止（WRITE DATA 0件）"
  echo "       公式ROM一式なら同じ打鍵でWRITE DATAが8件出る。m7bzのI/O比較で混成も"
  echo "       BASIC起動・打鍵受理・SAVE候補runまでは到達すると確定しており、旧説明の"
  echo "       『BASIC起動途中』は誤り。根拠: docs/notes/m7bz-save-reachability.md"
else
  w_sha="$(printf '%s\n' "$w_out" | awk -F'\t' '$1=="sha256"{print $2}')"
  w_bytes="$(printf '%s\n' "$w_out" | awk -F'\t' '$1=="bytes"{print $2}')"
  e_line="$(grep -v '^#' "$WEXPECTED" | awk 'NF' | head -1)"
  e_cmds="$(printf '%s\n' "$e_line" | cut -f2)"
  e_bytes="$(printf '%s\n' "$e_line" | cut -f3)"
  e_sha="$(printf '%s\n' "$e_line" | cut -f4)"
  if [ "$w_cmds" = "$e_cmds" ] && [ "$w_bytes" = "$e_bytes" ] && [ "$w_sha" = "$e_sha" ]; then
    ok "混成: 書き込みストリームが期待値と一致（件数 ${w_cmds}・${w_bytes}バイト・SHA-256）"
  else
    ng "混成: 書き込みストリームが期待値と一致しない（件数 ${w_cmds}/${e_cmds}、${w_bytes}/${e_bytes}バイト）"
    overall_rc=1
  fi
fi

# -----------------------------------------------------------------------
# M6需要入口の到達判定（5.2節の適合条件1〜5とは別の追加測定）— m7cf/m7cg。
#
# FILES: 2400F、300FでRETURN、700FからFILES。
# LOAD : 4800F、使い捨て複製だけを書込可にし、SAVE→NEW→同名LOAD。
#
# LOADを媒体の既存ファイルに依存させない理由は、対象媒体に元からある内容を
# 期待値へ混ぜず、条件5で適合済みのSAVE直後からLOAD入口を確実に作るため。
# m7cgでは別プロセスで既存ファイルだけをLOADする入口も追加する。準備runだけ
# q88measure --save-to-disk-imageを使い、SAVE結果を使い捨てD88複製へ直接保存する。
# 完成した同じ複製を公式／混成の入力へ二分し、2回目はLOADだけを打鍵する。
# seqfile/KILL/NAMEも9000Fとし、対象コマンドの画面反映と直後Okを到達指標にする。
# 各実行は新規ROMディレクトリ・新規ディスク複製を使い、300秒で打ち切る。
# 期待値不一致のうち、列が公式件数へ届かないものは「未到達」であって
# 適合条件1〜5の失格にはしない。公式件数まで届いてハッシュだけ違う場合は、
# 到達後の内容差なので不一致として扱う。
# -----------------------------------------------------------------------
ENTRY_TIMEOUT=300
ENTRY_FDC_COMPARE="$REPO/tools/compare_l3_entry_fdc.py"
ENTRY_SCREEN_CHECK="$REPO/tools/check_l3_entry_screen.py"

copy_entry_roms() {
  local mode="$1" rom="$2" f copied=0
  mkdir -p "$rom"
  if [ "$mode" = "official" ]; then
    for f in "$PC88_REF_ROM_DIR"/*.ROM; do
      [ -f "$f" ] || continue
      cp -p "$f" "$rom"/ || return 1
      copied=1
    done
    [ "$copied" -eq 1 ] || return 1
  else
    build_mixed_rom "$PC88_REF_ROM_DIR" "$rom" || return 1
  fi
}

prepare_existing_load_disk() {
  local out_disk="$1"
  local attempt=1 rc=1 rom prep_iolog prep_report prep_cmds
  prep_iolog="$WORK/load_existing.prepare.iolog.txt"
  prep_report="$WORK/load_existing.prepare.report.txt"
  : > "$WORK/load_existing.prepare.stderr.txt"
  while [ "$attempt" -le "$Q88_MEASURE_ATTEMPTS" ]; do
    rom="$WORK/load_existing.prepare.attempt${attempt}.rom"
    copy_entry_roms official "$rom" || return 1
    cp "$DISK" "$out_disk" || return 1
    printf '\x00' | dd of="$out_disk" bs=1 seek=26 count=1 conv=notrunc status=none
    rm -f "$prep_iolog" "$prep_report"
    /usr/bin/perl -e 'alarm shift; exec @ARGV' "$ENTRY_TIMEOUT" \
        "$FRONTEND" --core "$CORE" --rom-dir "$rom" --disk "$out_disk" \
        --save-to-disk-image --frames 9000 --io-log "$prep_iolog" \
        --out "$prep_report" --type-at 300 --type '\n' --type-at 700 \
        --type '10 PRINT "T"\nSAVE"Q7L"\n' \
        >"$WORK/load_existing.prepare.stdout.txt" \
        2>>"$WORK/load_existing.prepare.stderr.txt"
    rc=$?
    if [ "$rc" -eq 0 ] \
       && python3 "$ENTRY_SCREEN_CHECK" --report "$prep_report" \
                  --scenario load_prepare >/dev/null 2>&1; then
      prep_cmds="$(python3 "$REPO/tools/hash_write_stream.py" "$prep_iolog" \
                    2>/dev/null | awk -F'\t' '$1=="commands"{print $2}')"
      if [ "${prep_cmds:-0}" -gt 0 ]; then
        ok "既存LOAD準備: SAVEの打鍵反映・直後Ok・WRITE DATA発行を確認"
        return 0
      fi
    fi
    echo "  [注記] 既存LOAD準備: 未到達または${ENTRY_TIMEOUT}秒上限"
    echo "         （${attempt}/${Q88_MEASURE_ATTEMPTS}回、rc=${rc}）。新規複製で再試行する。"
    attempt=$((attempt + 1))
  done
  return 3
}

run_entry_measurement() {
  local label="$1" mode="$2" scenario="$3" out_iolog="$4"
  local source_disk="${5:-$DISK}"
  local attempt=1 rc=1 rom disk report
  local frames
  local -a type_args

  case "$scenario" in
    files)
      frames=2400
      type_args=(--type-at 300 --type '\n' --type-at 700 --type 'FILES\n')
      ;;
    load)
      frames=4800
      type_args=(--type-at 300 --type '\n' --type-at 700 \
                 --type '10 PRINT "T"\nSAVE"LQ"\nNEW\nLOAD"LQ"\n')
      ;;
    load_existing)
      frames=9000
      type_args=(--type-at 300 --type '\n' --type-at 700 --type 'LOAD"Q7L"\n')
      ;;
    seqfile)
      frames=9000
      type_args=(--type-at 300 --type '\n' --type-at 700 \
                 --type 'OPEN "Q7S" FOR OUTPUT AS #1\nPRINT#1,"HI"\nCLOSE\nOPEN "Q7S" FOR INPUT AS #1\nINPUT#1,W$\nCLOSE\n')
      ;;
    kill)
      frames=9000
      type_args=(--type-at 300 --type '\n' --type-at 700 \
                 --type '10 PRINT "T"\nSAVE"Q7K"\nKILL"Q7K"\n')
      ;;
    name)
      frames=9000
      type_args=(--type-at 300 --type '\n' --type-at 700 \
                 --type '10 PRINT "T"\nSAVE"Q7N"\nNAME"Q7N" AS "Q7R"\n')
      ;;
    *)
      echo "エラー: 未知の入口シナリオ: $scenario" >&2
      return 2
      ;;
  esac

  : > "$WORK/${label}.stderr.txt"
  while [ "$attempt" -le "$Q88_MEASURE_ATTEMPTS" ]; do
    rom="$WORK/${label}.attempt${attempt}.rom"
    disk="$WORK/${label}.attempt${attempt}.d88"
    copy_entry_roms "$mode" "$rom" || return 1
    cp "$source_disk" "$disk" || return 1
    if [ "$scenario" = "load" ] || [ "$scenario" = "seqfile" ] \
       || [ "$scenario" = "kill" ] || [ "$scenario" = "name" ]; then
      printf '\x00' | dd of="$disk" bs=1 seek=26 count=1 conv=notrunc status=none
    fi

    report="$WORK/${label}.report.txt"
    rm -f "$out_iolog" "$report"
    /usr/bin/perl -e 'alarm shift; exec @ARGV' "$ENTRY_TIMEOUT" \
        "$FRONTEND" --core "$CORE" --rom-dir "$rom" --disk "$disk" \
        --frames "$frames" --io-log "$out_iolog" --out "$report" \
        "${type_args[@]}" \
        >"$WORK/${label}.stdout.txt" 2>>"$WORK/${label}.stderr.txt"
    rc=$?
    if [ "$rc" -eq 0 ]; then
      case "$scenario" in
        load_existing|seqfile|kill|name)
          if python3 "$ENTRY_SCREEN_CHECK" --report "$report" \
                     --scenario "$scenario" >/dev/null 2>&1; then
            ok "${label}: 対象打鍵の画面反映と直後Okを確認"
            return 0
          fi
          rc=3
          ;;
        *) return 0 ;;
      esac
    fi
    echo "  [注記] ${label}: q88measure失敗、入口未到達、または${ENTRY_TIMEOUT}秒上限"
    echo "         （${attempt}/${Q88_MEASURE_ATTEMPTS}回、rc=${rc}）。新規複製で再試行する。"
    attempt=$((attempt + 1))
  done
  return "$rc"
}

entry_expected_fault_selftest() {
  local iolog="$1" expected="$2" label="$3"
  local bad_sha="$WORK/${label}.bad-sha.tsv"
  local bad_count="$WORK/${label}.bad-count.tsv"
  local rc=0

  awk 'BEGIN{FS=OFS="\t"} /^#/ || NF==0 {print; next}
       { sha=$6; last=substr(sha,length(sha),1)
         $6=substr(sha,1,length(sha)-1) (last=="0"?"f":"0"); print }' \
      "$expected" > "$bad_sha"
  if run_conformance "$iolog" "$bad_sha" "${label}-hash故障" >/dev/null 2>&1; then
    ng "${label}: 壊したSHA-256が一致してしまった"
    rc=1
  else
    ok "${label}: SHA-256を壊した期待値コピーを不一致検出"
  fi

  awk 'BEGIN{FS=OFS="\t"} /^#/ || NF==0 {print; next}
       {$5=$5+1; print}' "$expected" > "$bad_count"
  if run_conformance "$iolog" "$bad_count" "${label}-件数故障" >/dev/null 2>&1; then
    ng "${label}: 壊した件数が一致してしまった"
    rc=1
  else
    ok "${label}: 件数を壊した期待値コピーを不一致検出"
  fi
  return "$rc"
}

entry_stream_is_short() {
  local iolog="$1" expected="$2"
  local name cpu port kind count sha out actual
  while IFS=$'\t' read -r name cpu port kind count sha; do
    [ -z "${name:-}" ] && continue
    case "$name" in \#*) continue ;; esac
    if out="$(python3 "$HASH" "$iolog" --cpu "$cpu" --port "$port" --kind "$kind" 2>/dev/null)"; then
      actual="$(printf '%s\n' "$out" | awk -F'\t' '$1=="count"{print $2}')"
    else
      actual=0
    fi
    if [ "$actual" -lt "$count" ]; then
      return 0
    fi
  done < "$expected"
  return 1
}

judge_entry() {
  local scenario="$1" expected="$2" label="$3"
  local official="$WORK/${scenario}.official.iolog.txt"
  local mixed="$WORK/${scenario}.mixed.iolog.txt"
  local official_ok=0 mixed_ok=0 fdc_rc=0 prepared=""

  say "需要入口 ${label}: 公式一式と混成を同条件で実測（各実行${ENTRY_TIMEOUT}秒上限）"
  if [ "$scenario" = "load_existing" ]; then
    prepared="$WORK/load_existing.prepared.d88"
    if ! prepare_existing_load_disk "$prepared"; then
      na "${label}: 準備SAVEが完了せず、2回目のLOAD入口は未到達"
      na "${label}: 画面比較も未測定（追加測定の事実。失格にはしない）"
      overall_rc=1
      return
    fi
  fi
  if ! run_entry_measurement "${scenario}.official" official "$scenario" "$official" "$prepared"; then
    na "${label}: 公式一式でも入口へ到達せず、期待値を判定不能"
    na "${label}: 画面比較も未測定（追加測定の事実。失格にはしない）"
    overall_rc=1
    return
  fi
  if ! run_entry_measurement "${scenario}.mixed" mixed "$scenario" "$mixed" "$prepared"; then
    na "${label}: 混成の測定が完了せず未到達（停止位置は測定ログ末尾）"
    na "${label}: 画面比較も未測定（追加測定の事実。失格にはしない）"
    return
  fi

  report_screen_comparison "$scenario" "$label" \
    "$WORK/${scenario}.official.report.txt" "$WORK/${scenario}.mixed.report.txt"

  if run_conformance "$official" "$expected" "${label}-公式"; then
    official_ok=1
  else
    ng "${label}: 公式実測が固定した期待値と一致しない"
    overall_rc=1
  fi
  if ! entry_expected_fault_selftest "$official" "$expected" "${label}判定器"; then
    overall_rc=1
  fi

  python3 "$ENTRY_FDC_COMPARE" --official "$official" --mixed "$mixed"
  fdc_rc=$?
  if [ "$fdc_rc" -eq 2 ]; then
    ng "${label}: FDCコマンド種別列を解析できない"
    overall_rc=1
  fi

  if run_conformance "$mixed" "$expected" "${label}-混成" >"$WORK/${scenario}.mixed-check.txt" 2>&1; then
    mixed_ok=1
    cat "$WORK/${scenario}.mixed-check.txt"
  elif entry_stream_is_short "$mixed" "$expected"; then
    na "${label}: 入口固有の受信列が公式件数へ届かず未到達"
    sed 's/NG/--/' "$WORK/${scenario}.mixed-check.txt"
  else
    cat "$WORK/${scenario}.mixed-check.txt"
    ng "${label}: 公式件数へ到達したが受信列の内容または長さが一致しない"
    overall_rc=1
  fi

  if [ "$official_ok" -eq 1 ] && [ "$mixed_ok" -eq 1 ] && [ "$fdc_rc" -eq 0 ]; then
    ok "${label}: 混成は入口終端まで到達（FDC種別列・main受信列とも公式と全長一致）"
  elif [ "$fdc_rc" -eq 1 ] && [ "$mixed_ok" -eq 0 ]; then
    na "${label}: FDCコマンド種別列の分岐位置で未到達"
  elif [ "$fdc_rc" -eq 1 ]; then
    ng "${label}: main受信列は一致したがFDCコマンド種別列に差がある"
    overall_rc=1
  fi
}

say "需要入口の到達判定器自己検査（合成画面による陽性・陰性対照）"
cat > "$WORK/entry-screen.positive.txt" <<'EOF'
  0| load"q7l"
  1| Ok
EOF
cat > "$WORK/entry-screen.negative.txt" <<'EOF'
  0| load"q7l"
  1| Synthetic failure
EOF
if python3 "$ENTRY_SCREEN_CHECK" --report "$WORK/entry-screen.positive.txt" \
           --scenario load_existing >/dev/null 2>&1 \
   && ! python3 "$ENTRY_SCREEN_CHECK" --report "$WORK/entry-screen.negative.txt" \
            --scenario load_existing >/dev/null 2>&1; then
  ok "到達判定器: 陽性対照を到達、直後Okを壊した陰性対照を未到達として検出"
else
  ng "到達判定器: 合成画面の陽性・陰性対照を正しく区別できない"
  overall_rc=1
fi

judge_entry files "$FILES_EXPECTED" FILES
judge_entry load "$LOAD_EXPECTED" LOAD
judge_entry load_existing "$LOAD_EXISTING_EXPECTED" "既存ファイル単独LOAD"
judge_entry seqfile "$SEQFILE_EXPECTED" "シーケンシャルファイル出力・入力"
judge_entry kill "$KILL_EXPECTED" KILL
judge_entry name "$NAME_EXPECTED" NAME

# -----------------------------------------------------------------------
# m7ci: 汎用256バイト経路とは別の、エラー結果相とB: unit/head経路。
# 公式diskA原本は必ず使い捨て複製にし、B:正常系は独立した同内容複製、
# 読めない媒体相当は規則生成D88をB:へ入れる。M3Uはコアの公開2ドライブ
# 経路であり、生ログ・画面・媒体複製と同じくWORKだけに置く。
# 5.2節の条件1〜5とは別の追加測定で、分岐は次周の実装境界として報告する。
# -----------------------------------------------------------------------

path_event_sha() {
  local iolog="$1"
  awk 'seen || /^# main$/ {seen=1; print}' "$iolog" | shasum -a 256 | awk '{print $1}'
}

path_stream_signature() {
  local iolog="$1" label="$2" port out count sha
  for port in FD FC; do
    if out="$(python3 "$HASH" "$iolog" --cpu main --port "$port" --kind IN 2>/dev/null)"; then
      count="$(printf '%s\n' "$out" | awk -F'\t' '$1=="count"{print $2}')"
      sha="$(printf '%s\n' "$out" | awk -F'\t' '$1=="sha256"{print $2}')"
      echo "  [署名] ${label} main IN \$${port}: 件数=${count} SHA-256=${sha}"
    else
      echo "  [署名] ${label} main IN \$${port}: 抽出不能"
    fi
  done
}

compare_path_streams() {
  local official="$1" mixed="$2" label="$3" port a b
  local ac as bc bs
  for port in FD FC; do
    a="$(python3 "$HASH" "$official" --cpu main --port "$port" --kind IN 2>/dev/null || true)"
    b="$(python3 "$HASH" "$mixed" --cpu main --port "$port" --kind IN 2>/dev/null || true)"
    ac="$(printf '%s\n' "$a" | awk -F'\t' '$1=="count"{print $2}')"
    as="$(printf '%s\n' "$a" | awk -F'\t' '$1=="sha256"{print $2}')"
    bc="$(printf '%s\n' "$b" | awk -F'\t' '$1=="count"{print $2}')"
    bs="$(printf '%s\n' "$b" | awk -F'\t' '$1=="sha256"{print $2}')"
    if [ -n "$ac" ] && [ "$ac" = "$bc" ] && [ "$as" = "$bs" ]; then
      ok "${label}: main IN \$${port}は件数・SHA-256とも公式と一致"
    else
      na "${label}: main IN \$${port}は分岐（公式${ac:-抽出不能}件／混成${bc:-抽出不能}件）"
    fi
  done
}

run_path_measurement() {
  local label="$1" mode="$2" scenario="$3" run="$4"
  local base="$WORK/path.${label}.${mode}.run${run}"
  local rom="${base}.rom" disk_a="${base}.a.d88" disk_b="${base}.b.d88"
  local media="${base}.media" report="${base}.report.txt" iolog="${base}.iolog.txt"
  local frames type_text rc

  copy_entry_roms "$mode" "$rom" || return 1
  cp "$DISK" "$disk_a" || return 1
  case "$scenario" in
    write_protect)
      # 公開D88ヘッダの保護フラグを使い捨て複製で明示的に立てる。
      printf '\x10' | dd of="$disk_a" bs=1 seek=26 count=1 conv=notrunc status=none
      media="$disk_a"
      frames=3600
      type_text='10 PRINT "T"\nSAVE"Q8P"\n'
      ;;
    no_disk)
      # A:だけを挿入してB:を空に保ち、起動後にB:を要求する。
      media="$disk_a"
      frames=800
      type_text='FILES 2\n'
      ;;
    unreadable_disk)
      python3 "$REPO/tools/make_l3_testdisk.py" "$disk_b" >/dev/null || return 1
      printf '%s\n' "$disk_a" "$disk_b" > "${base}.m3u"
      media="${base}.m3u"
      frames=3000
      type_text='FILES 2\n'
      ;;
    drive2)
      cp "$DISK" "$disk_b" || return 1
      printf '%s\n' "$disk_a" "$disk_b" > "${base}.m3u"
      media="${base}.m3u"
      frames=3000
      type_text='FILES 2\n'
      ;;
    *)
      echo "エラー: 未知のエラー／B:シナリオ: $scenario" >&2
      return 2
      ;;
  esac

  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$ENTRY_TIMEOUT" \
      "$FRONTEND" --core "$CORE" --rom-dir "$rom" --disk "$media" \
      --frames "$frames" --io-log "$iolog" --out "$report" \
      --type-at 300 --type '\n' --type-at 700 --type "$type_text" \
      >"${base}.stdout.txt" 2>"${base}.stderr.txt"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    na "${label}-${mode}-run${run}: q88measure失敗または${ENTRY_TIMEOUT}秒上限（rc=${rc}）"
    return "$rc"
  fi
  if grep -Eq '^# 取りこぼし: [1-9][0-9]*件' "$iolog"; then
    ng "${label}-${mode}-run${run}: I/Oログに取りこぼしがある"
    return 3
  fi
  ok "${label}-${mode}-run${run}: I/Oログ取りこぼし0件"
  return 0
}

check_path_determinism() {
  local label="$1" mode="$2" log1="$3" log2="$4" report1="$5" report2="$6"
  local h1 h2 out="$WORK/path.${label}.${mode}.screen-determinism.txt"
  h1="$(path_event_sha "$log1")"
  h2="$(path_event_sha "$log2")"
  if [ -n "$h1" ] && [ "$h1" = "$h2" ]; then
    ok "${label}-${mode}: main/sub全イベント列は2回決定論的に一致"
  else
    ng "${label}-${mode}: main/sub全イベント列が2回で一致しない"
    overall_rc=1
  fi
  if python3 "$SCREEN_CHECK" --report "$report1" --compare-report "$report2" > "$out"; then
    ok "${label}-${mode}: 画面出力は2回決定論的に一致"
  else
    ng "${label}-${mode}: 画面出力が2回で一致しない"
    sed 's/^/       /' "$out"
    overall_rc=1
  fi
}

judge_path() {
  local scenario="$1" expected="$2" label="$3"
  local mode run base official mixed report_off report_mix rows fdc_rc after_frame

  say "エラー／ドライブ2経路 ${label}: 公式一式・混成を同条件で各2回実測"
  for mode in official mixed; do
    for run in 1 2; do
      if ! run_path_measurement "$scenario" "$mode" "$scenario" "$run"; then
        ng "${label}-${mode}-run${run}: 測定不能"
        overall_rc=1
        return
      fi
      base="$WORK/path.${scenario}.${mode}.run${run}"
      if python3 "$ENTRY_SCREEN_CHECK" --report "${base}.report.txt" \
           --scenario "$scenario" >/dev/null 2>&1; then
        ok "${label}-${mode}-run${run}: 打鍵反映と期待結果分類への到達を確認"
      elif [ "$mode" = official ]; then
        ng "${label}-${mode}-run${run}: 公式でも期待結果分類へ到達していない"
        overall_rc=1
      else
        na "${label}-${mode}-run${run}: 混成は期待結果分類へ到達していない"
      fi
    done
  done

  check_path_determinism "$scenario" official \
    "$WORK/path.${scenario}.official.run1.iolog.txt" \
    "$WORK/path.${scenario}.official.run2.iolog.txt" \
    "$WORK/path.${scenario}.official.run1.report.txt" \
    "$WORK/path.${scenario}.official.run2.report.txt"
  check_path_determinism "$scenario" mixed \
    "$WORK/path.${scenario}.mixed.run1.iolog.txt" \
    "$WORK/path.${scenario}.mixed.run2.iolog.txt" \
    "$WORK/path.${scenario}.mixed.run1.report.txt" \
    "$WORK/path.${scenario}.mixed.run2.report.txt"

  official="$WORK/path.${scenario}.official.run1.iolog.txt"
  mixed="$WORK/path.${scenario}.mixed.run1.iolog.txt"
  report_off="$WORK/path.${scenario}.official.run1.report.txt"
  report_mix="$WORK/path.${scenario}.mixed.run1.report.txt"
  path_stream_signature "$official" "${label}-公式"
  path_stream_signature "$mixed" "${label}-混成"
  compare_path_streams "$official" "$mixed" "$label"

  rows="$(awk '!/^#/ && NF {n++} END{print n+0}' "$expected")"
  if [ "$rows" -eq 0 ]; then
    ng "${label}: 公式期待値が未固定（上の署名を確認すること）"
    overall_rc=1
  else
    if ! run_conformance "$official" "$expected" "${label}-公式run1"; then
      ng "${label}: 公式run1が固定期待値と一致しない"
      overall_rc=1
    fi
    if ! run_conformance "$WORK/path.${scenario}.official.run2.iolog.txt" \
         "$expected" "${label}-公式run2"; then
      ng "${label}: 公式run2が固定期待値と一致しない"
      overall_rc=1
    fi
    if ! entry_expected_fault_selftest "$official" "$expected" "${label}判定器"; then
      overall_rc=1
    fi
  fi

  echo "  [画面署名] ${label}-公式"
  python3 "$SCREEN_CHECK" --report "$report_off" | sed 's/^/       /'
  echo "  [画面署名] ${label}-混成"
  python3 "$SCREEN_CHECK" --report "$report_mix" | sed 's/^/       /'
  report_screen_comparison "$scenario" "$label" "$report_off" "$report_mix"

  after_frame=760
  fdc_extra=()
  if [ "$scenario" = write_protect ]; then
    after_frame=700
    python3 "$ENTRY_FDC_COMPARE" --official "$official" --mixed "$mixed" \
      --after-frame "$after_frame" --write-operation
  else
    python3 "$ENTRY_FDC_COMPARE" --official "$official" --mixed "$mixed" \
      --after-frame "$after_frame"
  fi
  fdc_rc=$?
  if [ "$fdc_rc" -eq 2 ]; then
    ng "${label}: FDCコマンド／結果分類を解析できない"
    overall_rc=1
  elif [ "$fdc_rc" -eq 1 ]; then
    na "${label}: FDCコマンド種別列は表示した位置で分岐"
  fi
}

say "エラー／ドライブ2画面到達判定器の故障注入自己検査（合成画面のみ）"
for scenario in write_protect no_disk unreadable_disk; do
  case "$scenario" in
    write_protect) synthetic_command='save"q8p"' ;;
    *) synthetic_command='files 2' ;;
  esac
  {
    printf '  0| %s\n' "$synthetic_command"
    printf '  1| Synthetic classified response\n'
  } > "$WORK/path-screen.${scenario}.positive.txt"
  {
    printf '  0| %s\n' "$synthetic_command"
    for synthetic_row in 1 2 3 4 5 6 7 8 9 10; do
      printf '  %s| Synthetic listing row\n' "$synthetic_row"
    done
    printf '  11| Ok\n'
  } > "$WORK/path-screen.${scenario}.negative.txt"
  if python3 "$ENTRY_SCREEN_CHECK" --report "$WORK/path-screen.${scenario}.positive.txt" \
       --scenario "$scenario" >/dev/null 2>&1 \
     && ! python3 "$ENTRY_SCREEN_CHECK" --report "$WORK/path-screen.${scenario}.negative.txt" \
       --scenario "$scenario" >/dev/null 2>&1; then
    ok "${scenario}: 1行応答をエラー分類、複数行一覧故障を非到達として検出"
  else
    ng "${scenario}: エラー分類の陽性・陰性対照を区別できない"
    overall_rc=1
  fi
done
{
  printf '  0| files 2\n'
  for synthetic_row in 1 2 3 4 5 6 7 8 9 10; do
    printf '  %s| Synthetic listing row\n' "$synthetic_row"
  done
  printf '  11| Ok\n'
} > "$WORK/path-screen.drive2.positive.txt"
{
  printf '  0| files 2\n'
  printf '  1| Synthetic classified response\n'
  printf '  2| Ok\n'
} > "$WORK/path-screen.drive2.negative.txt"
if python3 "$ENTRY_SCREEN_CHECK" --report "$WORK/path-screen.drive2.positive.txt" \
     --scenario drive2 >/dev/null 2>&1 \
   && ! python3 "$ENTRY_SCREEN_CHECK" --report "$WORK/path-screen.drive2.negative.txt" \
     --scenario drive2 >/dev/null 2>&1; then
  ok "drive2: 出力行後Okを到達、Ok欠落故障を非到達として検出"
else
  ng "drive2: 正常出力分類の陽性・陰性対照を区別できない"
  overall_rc=1
fi

judge_path write_protect "$WRITE_PROTECT_EXPECTED" "ライトプロテクト違反"
judge_path no_disk "$NO_DISK_EXPECTED" "B:媒体未挿入"
judge_path unreadable_disk "$UNREADABLE_DISK_EXPECTED" "B:規則生成媒体"
judge_path drive2 "$DRIVE2_EXPECTED" "B:正常操作"

say "現状の到達点"
cat <<'EOF'
  経緯（消さずに残す）: 当初は「本番」ステップ（公式ROM一式＝サブROMも
  公式）の合格を自作実装の合格と取り違えていた。あれは公式環境の再現性を
  確認しているだけで、自作サブROMの適合は一度も判定していなかった。その穴を
  埋めるために「混成」ステップ（公式main側はそのまま・サブROMだけ自作品）を
  足した。詳しい経緯は git 履歴のこの節の旧文面を参照。

  適合条件1〜5は、このスクリプトの各判定と対照検査により判定する。
  2026-08-23の割り込み駆動化後の公式環境実走では5条件すべてが判定・合格した。
  条件3は自作subの受理13362件すべてが判定対象となり、直前mainは0件だった。
  ただし公式subの受理13593件とは件数が一致せず、自作だけ受理直前にIN $FA という
  現れる外形差も残る。これは条件3の条件文外だが、公式との構造差として残す。
  根拠: docs/notes/m7ce-official-conformance-after-interrupt.md
EOF

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "conform_l3: 適合（このスクリプトが判定できる範囲）"
else
  echo "conform_l3: 不適合、または自己検査に失敗あり（上記参照）"
fi
exit "$overall_rc"

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
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
SELFTEST_LOG="$REPO/measurements/m6g-d0-boot-run1.iolog.txt"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }

if [ ! -f "$EXPECTED" ]; then
  echo "エラー: 期待値ファイルが無い: $EXPECTED" >&2
  exit 2
fi
if [ ! -f "$SELFTEST_LOG" ]; then
  echo "エラー: 自己検査用の入力が無い: $SELFTEST_LOG" >&2
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
      ng "[$label] ${name}: 抽出に失敗（$cpu/$kind/$port）"
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
# 検出力の自己検査（公式環境なしでも回せる。measurements/m6g-* を使う）
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
if run_conformance "$SELFTEST_LOG" "$EXPECTED" "自己検査a"; then
  :
else
  ng "自己検査a: 正しい入力のはずが不一致になった（期待値ファイル自体を疑うこと）"
  selftest_rc=1
fi

echo "  -- b. ハッシュを1文字壊した期待値 → 不一致で検出されるはず --"
awk 'BEGIN{FS=OFS="\t"} /^#/ || NF==0 {print; next}
     { sha=$6; last=substr(sha,length(sha),1)
       sha=substr(sha,1,length(sha)-1) (last=="0"?"f":"0")
       $6=sha; print }' "$EXPECTED" > "$WORK/expected.bad_sha.tsv"
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
     { $5 = $5 + 1; print }' "$EXPECTED" > "$WORK/expected.bad_count.tsv"
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
     { $3 = "FFFE"; print }' "$EXPECTED" > "$WORK/expected.bad_port.tsv"
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
"$FRONTEND" --core "$CORE" --rom-dir "$PC88_REF_ROM_DIR" --disk "$DISK" \
    --frames 1800 --io-log "$WORK/live.iolog.txt" \
    >"$WORK/live.stdout.txt" 2>"$WORK/live.stderr.txt" || {
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
# 現状の到達点（正直に書く。ごまかさない）
# -----------------------------------------------------------------------
say "現状の到達点"
cat <<'EOF'
  判定できる: 適合条件1（docs/spec/l3-subrom.md 5.2節1項）——
    diskA起動時、main が IN $FD で受け取る値の列の一致
    （tests/conformance/expected.tsv の m6g-d0-boot 行）。

  未判定のまま残す:
    条件2（diskB起動時に $FC を一切使わないこと。5.2節2項）
    条件3（サブの割り込み受理がmainの直接I/O操作を直前イベントとしないこと。
           5.2節3項）
    条件4（ディスク無しでsub相当が1命令も実行されないこと。5.2節4項。
           tools/verify_l3.sh のネガティブコントロールで自作実装側が
           既に未達成と報告している論点と同じ）
  これらは期待値エントリの追加とTSV照合ロジックの拡張で対応できる形に
  なっているが、今回のスコープ外として残す。
EOF

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "conform_l3: 適合（このスクリプトが判定できる範囲）"
else
  echo "conform_l3: 不適合、または自己検査に失敗あり（上記参照）"
fi
exit "$overall_rc"

# tools/lib_l3_measure.sh — 混成ROM測定の共通部分（tools/conform_l3.sh と
# tools/diag_l3_mixed.sh が共有する）。
#
# 設計判断: 単体で実行されるスクリプトではなく、source される「関数の
# 置き場」だけにする（トップレベルで副作用を起こさない。set -e 等も
# 呼び出し元に委ねる）。build_mixed_rom は元々 tools/conform_l3.sh に
# 実装されていたが、tools/diag_l3_mixed.sh も「conform_l3.sh の混成
# ステップと同条件」で測定する必要があり、コピペで二重実装すると
# 片方だけ直して食い違う事故の元になる（CLAUDE.md「繰り返しパターンの
# 一括処理」の精神と同じ理由）。ここに切り出して両方から source する。
#
# 使い方:
#   REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
#   source "$REPO/tools/lib_l3_measure.sh"

# -----------------------------------------------------------------------
# 混成ROMディレクトリを組み立てる（公式main ROM一式 + 自作サブROMのみ差替）。
#
# $1 = コピー元ROMディレクトリ（公式一式、または自己検査用ダミー）
# $2 = 出力先ディレクトリ
#
# 中身を一切読まずに cp するだけなのでクリーンルーム規律に触れない
# （CLAUDE.md「公式ROMファイルを cp でコピーするのは可」）。
# サブROMのファイル名は "DISK.ROM"（tools/harness/make_trap_rom.py・
# make_test_rom.py・docs/spec/l3-subrom.md 冒頭・docs/notes/m1-quasi88-survey.md
# で既に確定済みの名称。公式ROMディレクトリを ls して確認したのではなく、
# 既存のハーネスコード・仕様書側の記述から特定した）。
# -----------------------------------------------------------------------
build_mixed_rom() {
  local src="$1" dst="$2"
  local f copied=0
  mkdir -p "$dst"
  # m7bz: 旧`cp *`はROMと同居するコア実行状態（*.srm等）まで複製し、
  # 前段測定が後段条件のSAVE内容へ混入した。中身は読まず拡張子だけで
  # ROMファイルに限定する。公式ROM名の個別列挙や絶対パスは持ち込まない。
  for f in "$src"/*.ROM; do
    [ -f "$f" ] || continue
    cp -p "$f" "$dst"/ || return 1
    copied=1
  done
  [ "$copied" -eq 1 ] || return 1
  python3 "$REPO/src/l3_service/make_subrom.py" "$dst" >/dev/null 2>&1 || return 1
}

# -----------------------------------------------------------------------
# vendor/quasi88-libretro のコアパスを探す。見つからなければ空文字。
# -----------------------------------------------------------------------
find_l3_core() {
  local vendor="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
  ls "$vendor"/quasi88_libretro.* 2>/dev/null | head -1 || true
}

# -----------------------------------------------------------------------
# q88measure フロントエンドが無ければビルドする。
# -----------------------------------------------------------------------
ensure_l3_frontend() {
  local frontend="$REPO/tools/harness/frontend/q88measure"
  if [ ! -x "$frontend" ]; then
    make -s -C "$REPO/tools/harness/frontend" || return 1
  fi
}

# -----------------------------------------------------------------------
# q88measure を実行する。**起動時クラッシュに限って**再試行する。
#
# 背景（m7az、2026-08-19）: 公式ROM一式を --rom-dir に与えると、
# q88measure が起動時に `Abort trap: 6` で落ちることが **8回中3回** ある
# （自作ROM一式では8回中0回。ロケールには依存せず、C でも UTF-8 でも起きる）。
# 落ちるのは**フレームループへ入る前**で、ログファイルは1バイトも作られない
# ——つまり「部分的な測定結果を拾ってしまう」危険は無い。
#
# **この再試行は失敗を隠すためのものではない。** 再試行したことは必ず標準
# エラーへ出す。全部の試行が落ちたら失敗として返す。原因（第三者コア側の
# 起動処理と見られる）は未修正の既知欠陥として
# docs/notes/m7az-write-conformance.md に記録してある。
#
# $1 = 出力する iolog のパス（試行ごとに消してから走らせる）
# $2 = q88measure の標準出力の保存先
# $3 = q88measure の標準エラーの保存先
# 残りの引数はそのまま q88measure へ渡す。
#
# **注記は呼び出し元の標準エラーへ出す**（q88measure の出力と一緒にファイルへ
# 吸わせない）。最初の実装でそこを間違え、再試行が起きたことも全部失敗した
# ことも画面に出ないまま「ログが無い」という別の例外だけが見える状態になった。
# -----------------------------------------------------------------------
Q88_MEASURE_ATTEMPTS="${Q88_MEASURE_ATTEMPTS:-4}"
run_q88measure_retry() {
  local out_iolog="$1" out_stdout="$2" out_stderr="$3"; shift 3
  local frontend="$REPO/tools/harness/frontend/q88measure"
  local attempt=1 rc=0
  while [ "$attempt" -le "$Q88_MEASURE_ATTEMPTS" ]; do
    rm -f "$out_iolog"
    "$frontend" "$@" >"$out_stdout" 2>>"$out_stderr"
    rc=$?
    if [ "$rc" -eq 0 ]; then
      if [ "$attempt" -gt 1 ]; then
        echo "  [注記] q88measure の起動時クラッシュのため ${attempt} 回目で成功した" \
             "（既知欠陥。docs/notes/m7az-write-conformance.md）" >&2
      fi
      return 0
    fi
    echo "  [注記] q88measure が rc=${rc} で失敗した（${attempt}/${Q88_MEASURE_ATTEMPTS} 回目）" >&2
    attempt=$((attempt + 1))
  done
  echo "エラー: q88measure が ${Q88_MEASURE_ATTEMPTS} 回とも失敗した" >&2
  return 1
}

# -----------------------------------------------------------------------
# 混成ROM(公式main + 自作サブROM)でdiskA起動を測定する。
# conform_l3.sh の「混成ROM適合テスト」ステップと同条件
# （frames 1800、diskは $rom_dir/../disk 引数ではなく $disk 引数そのもの）。
#
# $1 = 公式ROMディレクトリ (PC88_REF_ROM_DIR)
# $2 = 公式ディスク .D88 のフルパス
# $3 = 作業ディレクトリ（混成ROM一式を作る場所）
# $4 = 出力する iolog のパス
# $5 = 任意。q88measure --out の出力先
#
# 戻り値: 成功0 / 失敗1（詳細は $3/mixed.stderr.txt）
# -----------------------------------------------------------------------
run_l3_mixed_measurement() {
  local rom_dir="$1" disk="$2" work="$3" out_iolog="$4"
  local out_report="${5:-}"

  local core
  core="$(find_l3_core)"
  if [ -z "$core" ]; then
    echo "エラー: コアが無い。先に tools/setup_harness.sh を実行すること" >&2
    return 1
  fi
  ensure_l3_frontend || return 1
  local frontend="$REPO/tools/harness/frontend/q88measure"

  if [ ! -f "$disk" ]; then
    echo "エラー: 参照ディスクが無い: $disk" >&2
    return 1
  fi

  local mixed_rom_dir="$work/mixed_rom"
  if ! build_mixed_rom "$rom_dir" "$mixed_rom_dir"; then
    echo "エラー: 混成ROMディレクトリの構築に失敗した" >&2
    return 1
  fi

  if [ -n "$out_report" ]; then
    run_q88measure_retry "$out_iolog" "$work/mixed.stdout.txt" "$work/mixed.stderr.txt" \
        --core "$core" --rom-dir "$mixed_rom_dir" --disk "$disk" \
        --frames 1800 --io-log "$out_iolog" --out "$out_report"
  else
    run_q88measure_retry "$out_iolog" "$work/mixed.stdout.txt" "$work/mixed.stderr.txt" \
        --core "$core" --rom-dir "$mixed_rom_dir" --disk "$disk" \
        --frames 1800 --io-log "$out_iolog"
  fi
  if [ "$?" -ne 0 ]; then
    echo "エラー: 混成ROMでの q88measure が失敗した" >&2
    cat "$work/mixed.stderr.txt" >&2
    return 1
  fi
}

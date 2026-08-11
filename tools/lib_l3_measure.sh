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
  mkdir -p "$dst"
  cp -p "$src"/* "$dst"/ || return 1
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
# 混成ROM(公式main + 自作サブROM)でdiskA起動を測定する。
# conform_l3.sh の「混成ROM適合テスト」ステップと同条件
# （frames 1800、diskは $rom_dir/../disk 引数ではなく $disk 引数そのもの）。
#
# $1 = 公式ROMディレクトリ (PC88_REF_ROM_DIR)
# $2 = 公式ディスク .D88 のフルパス
# $3 = 作業ディレクトリ（混成ROM一式を作る場所）
# $4 = 出力する iolog のパス
#
# 戻り値: 成功0 / 失敗1（詳細は $3/mixed.stderr.txt）
# -----------------------------------------------------------------------
run_l3_mixed_measurement() {
  local rom_dir="$1" disk="$2" work="$3" out_iolog="$4"

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

  "$frontend" --core "$core" --rom-dir "$mixed_rom_dir" --disk "$disk" \
      --frames 1800 --io-log "$out_iolog" \
      >"$work/mixed.stdout.txt" 2>"$work/mixed.stderr.txt" || {
    echo "エラー: 混成ROMでの q88measure が失敗した" >&2
    cat "$work/mixed.stderr.txt" >&2
    return 1
  }
}

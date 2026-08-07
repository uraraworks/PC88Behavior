#!/usr/bin/env bash
# 公式 ROM に対して測定を実行する。
#
# ROM の在り処は環境変数 PC88_REF_ROM_DIR から受け取る（docs/PLAN.md 第3節）。
# 引数にもスクリプト内にも私物のパスを書かない。理由は2つある。
#
#   1. リポジトリに個人環境の絶対パスを焼き込まないため
#   2. エージェントが private/ を含むコマンドを打たずに測定を開始できるようにするため。
#      permission の deny は「private/ を指すコマンド」を止める。これは
#      ROM の中身がエージェントの文脈に入る事故を防ぐためのもので、
#      測定の実行そのものを禁じたいわけではない
#
# ここで出るのは「どの番地にどの種類のアクセスがあったか」だけで、
# ROM のバイト列は一切含まれない。だから出力は private/ の外に置き、
# リポジトリで追跡する。測定コミットが実装コミットに先行する、という
# コミット規律はこの出力があって初めて成立する。
#
# 使い方:
#   PC88_REF_ROM_DIR=... tools/measure.sh <出力名> [q88measure への追加引数...]
#
# 例:
#   tools/measure.sh boot-idle --frames 600
#   tools/measure.sh boot-disk --frames 1800 --disk-name foo.d88
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
OUTDIR="$REPO/measurements"

if [ $# -lt 1 ]; then
  echo "使い方: PC88_REF_ROM_DIR=... $0 <出力名> [追加引数...]" >&2
  exit 2
fi
NAME="$1"; shift

# 環境変数が無ければリポジトリ内の規定位置を使う。
# これは個人環境の絶対パスではなく、このリポジトリの約束事（private/ に私物を置く）
# なので焼き込んでよい。第三者も同じ場所に置けば同じコマンドで動く。
if [ -z "${PC88_REF_ROM_DIR:-}" ] && [ -d "$REPO/private/rom" ]; then
  PC88_REF_ROM_DIR="$REPO/private/rom"
fi

if [ -z "${PC88_REF_ROM_DIR:-}" ]; then
  cat >&2 <<'MSG'
PC88_REF_ROM_DIR が設定されていない。

公式 ROM の置き場を環境変数で渡すこと。リポジトリには書かない。
  export PC88_REF_ROM_DIR=/path/to/rom

エージェントのセッションでは PC88/.claude/settings.local.json の env に
書いておく（このファイルは git 管理外なので個人パスが漏れない）。
MSG
  exit 1
fi

# 中身は見ないが、「何を測ろうとしているか」は確定させておく必要がある。
# ここが曖昧なまま走らせるのが一番まずい失敗の仕方なので。
if [ ! -d "$PC88_REF_ROM_DIR" ]; then
  echo "PC88_REF_ROM_DIR がディレクトリではない: $PC88_REF_ROM_DIR" >&2; exit 1
fi

# ディスクも私物なので、パスではなくファイル名で受け取る。
# --disk-name foo.d88  →  $PC88_REF_DISK_DIR/foo.d88
# こうしておけば測定コマンドにも測定結果にも私物のパスが現れない。
if [ -z "${PC88_REF_DISK_DIR:-}" ] && [ -d "$REPO/private/disk" ]; then
  PC88_REF_DISK_DIR="$REPO/private/disk"
fi
DISK_ARGS=()
DISK_WRITABLE=0
SCRATCH=""
# 末尾を必ず成功で終わらせる。set -e 下では EXIT トラップの終了値が
# スクリプト全体の終了値を上書きするので、ここで偽になると
# 測定が成功していても失敗として報告される（実際にそうなっていた）。
cleanup() { [ -n "$SCRATCH" ] && rm -rf "$SCRATCH"; return 0; }
trap cleanup EXIT
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --disk-name)
      [ -n "${PC88_REF_DISK_DIR:-}" ] || { echo "PC88_REF_DISK_DIR が未設定" >&2; exit 1; }
      d="$PC88_REF_DISK_DIR/$2"
      [ -f "$d" ] || { echo "ディスクイメージが無い: (PC88_REF_DISK_DIR)/$2" >&2; exit 1; }
      # 原本には絶対に書かせない。必ず使い捨ての複製を渡す。
      #
      # 理由は2つある。
      #   1. 測定は原本を変えてはいけない。SAVE や KILL を測った瞬間に
      #      27年物のディスクが書き換わるのでは測定にならない
      #   2. 原本が書き換わると以後の測定条件が変わり、再現性が壊れる。
      #      「同じ条件で同じ結果」が差分実行の前提なので、ここは譲れない
      SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-disk.XXXXXX")"
      cp "$d" "$SCRATCH/$2"
      DISK_COPY="$SCRATCH/$2"
      DISK_ARGS=(--disk "$DISK_COPY"); shift 2 ;;
    --disk-writable) DISK_WRITABLE=1; shift ;;
    *) args+=("$1"); shift ;;
  esac
done
set -- ${args[@]+"${args[@]}"}

# 書き込み経路を測るには、複製側のライトプロテクトを外す必要がある。
# D88 ヘッダのオフセット 0x1A がライトプロテクト（0x10 で保護）。
# 原本は触らない。外すのはあくまで使い捨ての複製だけ。
if [ "$DISK_WRITABLE" = 1 ]; then
  [ -n "${DISK_COPY:-}" ] || { echo "--disk-writable には --disk-name が要る" >&2; exit 1; }
  printf '\x00' | dd of="$DISK_COPY" bs=1 seek=26 count=1 conv=notrunc status=none
  echo "[measure] 複製のライトプロテクトを解除した（原本は変更していない）" >&2
fi

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || { echo "コアが無い。tools/setup_harness.sh を実行すること" >&2; exit 1; }
[ -x "$FRONTEND" ] || make -s -C "$REPO/tools/harness/frontend"

mkdir -p "$OUTDIR"
OUT="$OUTDIR/$NAME.txt"

"$FRONTEND" \
  --core "$CORE" \
  --rom-dir "$PC88_REF_ROM_DIR" \
  --out "$OUT" \
  ${DISK_ARGS[@]+"${DISK_ARGS[@]}"} \
  "$@"
status=$?

# 出力はリポジトリに追跡するので、個人環境の絶対パスを残さない。
# 測定の再現に必要なのは「どのコアで」「どの ROM 一式か」であって、
# それが誰のホームディレクトリの下にあったかではない。
if [ -f "$OUT" ]; then
  tmp="$OUT.tmp"
  sed -e "s|$PC88_REF_ROM_DIR|\$PC88_REF_ROM_DIR|g" \
      -e "s|${PC88_REF_DISK_DIR:-__none__}|\$PC88_REF_DISK_DIR|g" \
      -e "s|${SCRATCH:-__none__}|\$PC88_REF_DISK_DIR|g" \
      -e "s|$(cd "$REPO/.." && pwd)|\$WORKDIR|g" \
      -e "s|$HOME|~|g" "$OUT" > "$tmp" && mv "$tmp" "$OUT"
  # 画面に写り込んだディスクのファイル名を伏せる（私物の内容なので）
  python3 "$REPO/tools/redact.py" "$OUT" >/dev/null
fi

exit $status

#!/usr/bin/env bash
# tools/screen_data_disks.sh — private/disk 配下の各ディスクを B:（データ
# ディスク）として使えるか、名前を出さずに選別する。
#
# 位置づけ: docs/notes/m7gd-boot-disk-screening.md は「そのディスクから
# 起動したときL3サービスに入るか」だけを見た（10本中2本のみ該当）。
# しかし disk#8 から起動して `FILES 2` を打つと、B: のディレクトリを
# 読むために別途L3サービスが動く（FILES経路、交換#3/#11/#14 等）。
# この経路は「起動には使えない」とされた8本を含む全10本について、
# **B: のデータディスクとして**は未検証だった。本スクリプトは、その
# 選別を行う。詳細は docs/notes/m7gg-data-disk-screening.md。
#
# 設計判断（測定はROM一式=条件Oで行う）: 知りたいのは「ディスクの性質
# （B:として読めるか）」であって自作サブROM実装の挙動ではないため、
# 公式ROM一式で測るほうが交絡しない。tools/screen_boot_disks.sh が
# 既定の混成ROMを使うのとは異なる判断である点に注意。
#
# 測定手順: A: に disk#8（650cfac8、既知の起動可能ディスク）を固定し、
# B: に候補を入れて `FILES 2\n` を打鍵する（tools/conform_l3.shの
# FILES 2シナリオと同じ打鍵作法: --type-at 300 --type '\n' --type-at 700
# --type 'FILES 2\n'、frames=3000）。
#
# 先に参照2本の署名を取り、分類の物差しにする（自作の閾値を後から作らない）:
#   参照P（陽性）: B: に disk#8 の使い捨て複製を入れる（既知の読めるディスク）
#   参照N（陰性）: B: を空にする（no_disk相当）
#
# **重要: 本スクリプトはディスクの実ファイル名を一切標準出力に出さない。**
# tools/screen_boot_disks.sh と同じ規約（通し番号disk#N・basenameの
# SHA-256先頭8桁ダイジェストのみで識別）を踏襲する。番号付けも同じ
# （list_disk_basenames の並び順）にすることで、disk#8 という呼び名を
# docs/notes/m7gd・m7gf とそのまま共有できるようにしてある。
#
# 使い方:
#   PC88_REF_ROM_DIR=/path/to/rom [PC88_REF_DISK_DIR=/path/to/disk] \
#       tools/screen_data_disks.sh
#
# テスト用フック: 環境変数 SCREEN_DATA_DISKS_FAKE_DIR を設定すると、実際の
# q88measure を呼ぶ代わりに "$SCREEN_DATA_DISKS_FAKE_DIR/<tag>.iolog.txt" と
# "<tag>.report.txt" をそのまま使う（tag は refP/refN/disk1.. 等）。
# tools/screen_data_disks_selftest.sh 専用。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
source "$REPO/tools/lib_screen_boot_disks.sh"
source "$REPO/tools/lib_screen_data_disks.sh"

FRAMES=3000
AFTER_FRAME=700
# 既知の disk#8（docs/notes/m7gd-boot-disk-screening.md）。
# SCREEN_DATA_DISKS_A_DIGEST は selftest 専用の上書きフック
# （合成ディスク集合では実ファイル名のダイジェストを固定できないため）。
A_DIGEST_EXPECT="${SCREEN_DATA_DISKS_A_DIGEST:-650cfac8}"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }
na()  { printf '  \033[33m--\033[0m   %s\n' "$1"; }

# --- ディスク置き場の決定 ------------------------------------------------
if [ -z "${PC88_REF_DISK_DIR:-}" ] && [ -d "$REPO/private/disk" ]; then
  PC88_REF_DISK_DIR="$REPO/private/disk"
fi
if [ -z "${PC88_REF_DISK_DIR:-}" ]; then
  echo "エラー: PC88_REF_DISK_DIR が未設定で、既定位置 $REPO/private/disk も無い。" >&2
  exit 1
fi
if [ ! -d "$PC88_REF_DISK_DIR" ]; then
  echo "エラー: ディスク置き場がディレクトリではない" >&2
  exit 1
fi

FAKE_DIR="${SCREEN_DATA_DISKS_FAKE_DIR:-}"

if [ -z "$FAKE_DIR" ]; then
  if [ -z "${PC88_REF_ROM_DIR:-}" ] && [ -d "$REPO/private/rom" ]; then
    PC88_REF_ROM_DIR="$REPO/private/rom"
  fi
  if [ -z "${PC88_REF_ROM_DIR:-}" ]; then
    echo "エラー: PC88_REF_ROM_DIR が未設定で、既定位置 $REPO/private/rom も無い。" >&2
    exit 1
  fi
fi

# --- 列挙 ------------------------------------------------------------
DISK_NAMES=()
while IFS= read -r line; do
  [ -n "$line" ] && DISK_NAMES+=("$line")
done < <(list_disk_basenames "$PC88_REF_DISK_DIR")

TOTAL=${#DISK_NAMES[@]}
say "走査結果: ${TOTAL} 本のディスクイメージを検出した"
if [ "$TOTAL" -eq 0 ]; then
  na "対象ディスクが0本。判定できるものが無い"
  echo
  echo "screen_data_disks: 0本 (判定対象なし)"
  exit 0
fi
if [ "$TOTAL" -lt 8 ]; then
  echo "エラー: disk#8 が存在しない本数（${TOTAL}本）しかない。" >&2
  echo "        PC88_REF_DISK_DIR の中身が m7gd 実施時と変わっている可能性がある。" >&2
  exit 1
fi

A_NAME="${DISK_NAMES[7]}"   # 配列は0起点、disk#8 は index 7
A_DIGEST="$(digest_basename "$A_NAME")"
if [ "$A_DIGEST" != "$A_DIGEST_EXPECT" ]; then
  echo "エラー: disk#8 のダイジェストが期待値と違う(got=${A_DIGEST} expect=${A_DIGEST_EXPECT})。" >&2
  echo "        PC88_REF_DISK_DIR の中身または並び順が m7gd 実施時と変わっている。" >&2
  echo "        番号付けが食い違ったまま測定すると誤ったディスクをA:に使うため中断する。" >&2
  exit 1
fi
ok "disk#8(${A_DIGEST}) を検出し、既知のダイジェストと一致することを確認した"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 測定の準備（フェイクモードでは何もしない） ---------------------------
CORE=""
OFFICIAL_ROM=""
if [ -z "$FAKE_DIR" ]; then
  CORE="$(find_l3_core)"
  if [ -z "$CORE" ]; then
    echo "エラー: コアが無い。先に tools/setup_harness.sh を実行すること" >&2
    exit 1
  fi
  ensure_l3_frontend || { echo "エラー: フロントエンドをビルドできない" >&2; exit 1; }

  OFFICIAL_ROM="$WORK/official_rom"
  mkdir -p "$OFFICIAL_ROM"
  copied=0
  for f in "$PC88_REF_ROM_DIR"/*.ROM; do
    [ -f "$f" ] || continue
    cp -p "$f" "$OFFICIAL_ROM"/ || { echo "エラー: 公式ROMのコピーに失敗した" >&2; exit 1; }
    copied=1
  done
  if [ "$copied" -ne 1 ]; then
    echo "エラー: PC88_REF_ROM_DIR に *.ROM が無い" >&2
    exit 1
  fi
fi

FRONTEND="$REPO/tools/harness/frontend/q88measure"

# -----------------------------------------------------------------------
# $1 = tag（識別用。標準出力には出さない。ファイル名の一部になるだけ）
# $2 = B: に入れるbasename。空文字ならB:無し。
# 成功なら0を返し、$WORK/${tag}.iolog.txt・$WORK/${tag}.report.txt を作る。
# -----------------------------------------------------------------------
run_measurement() {
  local tag="$1" b_name="$2"
  local iolog="$WORK/${tag}.iolog.txt" report="$WORK/${tag}.report.txt"
  local a_copy="$WORK/${tag}.a.d88"

  if [ -n "$FAKE_DIR" ]; then
    if [ ! -f "$FAKE_DIR/${tag}.iolog.txt" ] || [ ! -f "$FAKE_DIR/${tag}.report.txt" ]; then
      echo "エラー: フェイクデータが無い: ${tag}" >&2
      return 1
    fi
    cp "$FAKE_DIR/${tag}.iolog.txt" "$iolog"
    cp "$FAKE_DIR/${tag}.report.txt" "$report"
    return 0
  fi

  cp "$PC88_REF_DISK_DIR/$A_NAME" "$a_copy" || return 1
  local disk2_args=()
  if [ -n "$b_name" ]; then
    local b_copy="$WORK/${tag}.b.d88"
    cp "$PC88_REF_DISK_DIR/$b_name" "$b_copy" || return 1
    disk2_args=(--disk2 "$b_copy")
  fi

  # bash 3.2(macOS既定)は空配列の "${arr[@]}" 展開を set -u 下で
  # unbound variable にする。この慣用句(${arr[@]+"${arr[@]}"})で回避する。
  run_q88measure_retry "$iolog" "$WORK/${tag}.stdout.txt" "$WORK/${tag}.stderr.txt" \
      --core "$CORE" --rom-dir "$OFFICIAL_ROM" --disk "$a_copy" \
      ${disk2_args[@]+"${disk2_args[@]}"} \
      --frames "$FRAMES" --io-log "$iolog" --out "$report" \
      --type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'
}

# $1 = tag。成功なら "line<TAB>char<TAB>sha<TAB>read_data_count<TAB>fc_count" を返す。
analyze_measurement() {
  local tag="$1"
  local iolog="$WORK/${tag}.iolog.txt" report="$WORK/${tag}.report.txt"
  local sig read_count fc_count
  sig="$(read_screen_signature "$REPO" "$report")"
  if [ -z "$sig" ]; then
    return 1
  fi
  read_count="$(read_read_data_count "$REPO" "$iolog" "$AFTER_FRAME")"
  fc_count="$(count_sub_fc "$REPO" "$iolog")"
  if [ -z "$read_count" ]; then
    return 1
  fi
  printf '%s\t%s\t%s\n' "$sig" "$read_count" "$fc_count"
}

# --- 段階1: 参照P・参照N ------------------------------------------------
say "参照P（B:=disk#8の複製）・参照N（B:無し）を測定"
if ! run_measurement "refP" "$A_NAME"; then
  echo "エラー: 参照Pの測定に失敗した。判定の物差しが無いため中断する。" >&2
  exit 1
fi
REFP_ROW="$(analyze_measurement refP)" || { echo "エラー: 参照Pの解析に失敗した" >&2; exit 1; }
IFS=$'\t' read -r REFP_LINE REFP_CHAR REFP_SHA REFP_READ REFP_FC <<<"$REFP_ROW"
ok "参照P: line=${REFP_LINE} char=${REFP_CHAR} sha=${REFP_SHA} readData=${REFP_READ} fc=${REFP_FC}"

if ! run_measurement "refN" ""; then
  echo "エラー: 参照Nの測定に失敗した。判定の物差しが無いため中断する。" >&2
  exit 1
fi
REFN_ROW="$(analyze_measurement refN)" || { echo "エラー: 参照Nの解析に失敗した" >&2; exit 1; }
IFS=$'\t' read -r REFN_LINE REFN_CHAR REFN_SHA REFN_READ REFN_FC <<<"$REFN_ROW"
ok "参照N: line=${REFN_LINE} char=${REFN_CHAR} sha=${REFN_SHA} readData=${REFN_READ} fc=${REFN_FC}"

# --- 段階2: 10本の候補 ---------------------------------------------------
say "各ディスクをB:に入れてFILES 2を打鍵（frames=${FRAMES}、after-frame=${AFTER_FRAME}）"

READABLE_COUNT=0
UNREADABLE_COUNT=0
UNCLEAR_COUNT=0
FAIL_COUNT=0
READABLE_ENTRIES=""

idx=0
for name in "${DISK_NAMES[@]}"; do
  idx=$((idx + 1))
  digest="$(digest_basename "$name")"
  tag="disk${idx}"

  if ! run_measurement "$tag" "$name"; then
    na "disk#${idx}(${digest}): 測定に失敗した"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
  fi
  row="$(analyze_measurement "$tag")"
  if [ -z "$row" ]; then
    na "disk#${idx}(${digest}): 解析に失敗した（画面節が無い等）"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
  fi
  IFS=$'\t' read -r line char sha read_count fc_count <<<"$row"

  verdict="$(classify_data_disk "$line" "$char" "$read_count" "$sha" \
      "$REFP_LINE" "$REFP_CHAR" "$REFP_SHA" "$REFN_LINE" "$REFN_CHAR" "$REFN_SHA")"

  echo "  disk#${idx}  ${digest}  READ_DATA(${AFTER_FRAME}F+)=${read_count}  OUT\$FC(全区間)=${fc_count}  画面=${line}行/${char}文字/${sha}  判定=${verdict}"

  case "$verdict" in
    読める) READABLE_COUNT=$((READABLE_COUNT + 1)); READABLE_ENTRIES="${READABLE_ENTRIES}${READABLE_ENTRIES:+ }disk#${idx}(${digest})" ;;
    読めない) UNREADABLE_COUNT=$((UNREADABLE_COUNT + 1)) ;;
    *) UNCLEAR_COUNT=$((UNCLEAR_COUNT + 1)) ;;
  esac
done

say "集計"
echo "  走査本数: ${TOTAL}"
echo "  測定失敗: ${FAIL_COUNT}"
echo "  読める: ${READABLE_COUNT} 本"
echo "  読めない: ${UNREADABLE_COUNT} 本"
echo "  どちらとも言えない: ${UNCLEAR_COUNT} 本"
if [ "$READABLE_COUNT" -gt 0 ]; then
  echo "  該当（読める）: ${READABLE_ENTRIES}"
fi

echo
echo "screen_data_disks: ${TOTAL}本中 読める${READABLE_COUNT}本 読めない${UNREADABLE_COUNT}本 不明${UNCLEAR_COUNT}本（測定失敗${FAIL_COUNT}本）"
exit 0

#!/usr/bin/env bash
# tools/screen_boot_disks.sh — private/disk 配下に追加されたディスクの中に
# L3ディスクサービスに入る起動ディスクがあるかを、名前を出さずに選別する。
#
# 位置づけ: docs/notes/m7gb-odd-cylinder-condition-search-results.md が
# 「使える起動ディスクは事実上1択（N88_FE.D88）」で行き詰まった件を受け、
# 新規に追加されたディスクの中に、もう1本 L3 サービスへ入る起動ディスクが
# あるかを選別する。詳細は docs/notes/m7gd-boot-disk-screening.md。
#
# 判別基準（docs/notes/m6-sub-invariant.md 第2版の実測。
# tools/lib_screen_boot_disks.sh の classify_l3_entry と同じ規約）:
#   diskA（N88-BASIC）起動: sub OUT $FC が多数（実測5635件）→ L3サービスに入る
#   diskB（市販ソフト）起動: sub OUT $FC が0件（600/1800/3600フレームいずれも）
#     → サブCPU総I/OはdiskAの5.2倍あるのに応答経路を一度も使わない
#       ＝L3サービスに入らない
#
# **重要: 本スクリプトはディスクの実ファイル名を一切標準出力に出さない。**
# 各ディスクは「通し番号(disk#N、ファイル名でソートした順)」と
# 「ファイル名(basenameのみ、パスを含まない)のSHA-256先頭8桁のダイジェスト」
# だけで識別する。標準エラーにもファイル名は出さない設計にしてある。
#
# 使い方:
#   PC88_REF_ROM_DIR=/path/to/rom [PC88_REF_DISK_DIR=/path/to/disk] \
#       tools/screen_boot_disks.sh
#
# PC88_REF_DISK_DIR を省略した場合はリポジトリ内既定位置 private/disk への
# フォールバックする（tools/measure.sh と同じ約束事。私物の絶対パスを
# リポジトリに焼き込まないためのもの）。
#
# 測定に使うROMは既定の混成ROM(tools/lib_l3_measure.sh の build_mixed_rom を
# 引数なしで呼ぶ。探針フラグは使わない)。フレーム数は600と1800の両方で測る
# （判定を1つの値に依存させないため。docs/notes/m6-sub-invariant.md 第2版に倣う）。
#
# テスト用フック: 環境変数 SCREEN_BOOT_DISKS_FAKE_IOLOG_DIR を設定すると、
# 実際の q88measure を呼ぶ代わりに "$SCREEN_BOOT_DISKS_FAKE_IOLOG_DIR/diskN.iolog.txt"
# (Nはソート順の通し番号)をそのまま iolog として使う。公式ROM・実ディスクの
# バイト列を一切必要とせずに、列挙・ダイジェスト計算・判定・出力の
# 「名前を出さない」性質を tools/screen_boot_disks_selftest.sh から検査する
# ためのもの。通常の測定では使わない。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
source "$REPO/tools/lib_screen_boot_disks.sh"

FRAME_LIST="600 1800"

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
  echo "        export PC88_REF_DISK_DIR=/path/to/disk などで指定すること。" >&2
  exit 1
fi
if [ ! -d "$PC88_REF_DISK_DIR" ]; then
  echo "エラー: ディスク置き場がディレクトリではない（環境変数の値を確認すること）" >&2
  exit 1
fi

FAKE_DIR="${SCREEN_BOOT_DISKS_FAKE_IOLOG_DIR:-}"

# 実測を行うモードでは公式ROMの置き場も要る。フェイクモード(selftest)では
# q88measureを一切呼ばないので不要。
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
  na "対象ディスクが0本。判定できるものが無い（PC88_REF_DISK_DIR の中身・拡張子を確認すること）"
  echo
  echo "screen_boot_disks: 0本 (判定対象なし)"
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 測定の準備（フェイクモードでは何もしない） ---------------------------
CORE=""
MIXED_ROM=""
if [ -z "$FAKE_DIR" ]; then
  CORE="$(find_l3_core)"
  if [ -z "$CORE" ]; then
    echo "エラー: コアが無い。先に tools/setup_harness.sh を実行すること" >&2
    exit 1
  fi
  ensure_l3_frontend || { echo "エラー: フロントエンドをビルドできない" >&2; exit 1; }

  MIXED_ROM="$WORK/mixed_rom"
  if ! build_mixed_rom "$PC88_REF_ROM_DIR" "$MIXED_ROM"; then
    echo "エラー: 混成ROMディレクトリの構築に失敗した" >&2
    exit 1
  fi
fi

say "各ディスクを A: に挿入して起動測定（frames: ${FRAME_LIST}）"

L3_COUNT=0
L3_ENTRIES=""
FAIL_COUNT=0

idx=0
for name in "${DISK_NAMES[@]}"; do
  idx=$((idx + 1))
  digest="$(digest_basename "$name")"

  disk_ok=1
  line="disk#${idx}  ${digest}"
  counts=""

  if [ -n "$FAKE_DIR" ]; then
    fake_iolog="$FAKE_DIR/disk${idx}.iolog.txt"
    if [ ! -f "$fake_iolog" ]; then
      echo "エラー: フェイクiologが無い: disk${idx} 分（テストの組み立てを確認すること）" >&2
      exit 1
    fi
  fi

  for frames in $FRAME_LIST; do
    iolog="$WORK/disk${idx}.f${frames}.iolog.txt"
    if [ -n "$FAKE_DIR" ]; then
      cp "$FAKE_DIR/disk${idx}.iolog.txt" "$iolog"
    else
      disk_copy="$WORK/disk${idx}.d88"
      cp "$PC88_REF_DISK_DIR/$name" "$disk_copy"
      if ! run_q88measure_retry "$iolog" \
            "$WORK/disk${idx}.f${frames}.stdout.txt" \
            "$WORK/disk${idx}.f${frames}.stderr.txt" \
            --core "$CORE" --rom-dir "$MIXED_ROM" --disk "$disk_copy" \
            --frames "$frames" --io-log "$iolog"; then
        ng "disk#${idx}(${digest}): frames=${frames} の測定に失敗した"
        disk_ok=0
        break
      fi
    fi
    c="$(count_sub_fc "$REPO" "$iolog")"
    counts="${counts}${counts:+ }${c}"
    line="${line}  OUT\$FC(${frames}F)=${c}"
  done

  if [ "$disk_ok" -eq 0 ]; then
    na "disk#${idx}(${digest}): 測定に失敗した項目があり判定不能"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
  fi

  verdict="$(classify_l3_entry $counts)"
  line="${line}  判定=${verdict}"
  echo "  ${line}"
  if [ "$verdict" = "L3に入る" ]; then
    L3_COUNT=$((L3_COUNT + 1))
    L3_ENTRIES="${L3_ENTRIES}${L3_ENTRIES:+ }disk#${idx}(${digest})"
  fi
done

say "集計"
echo "  走査本数: ${TOTAL}"
echo "  測定失敗: ${FAIL_COUNT}"
echo "  L3に入ると判定: ${L3_COUNT} 本"
if [ "$L3_COUNT" -gt 0 ]; then
  echo "  該当: ${L3_ENTRIES}"
fi

echo
echo "screen_boot_disks: ${TOTAL}本中${L3_COUNT}本がL3に入ると判定（測定失敗${FAIL_COUNT}本）"
exit 0

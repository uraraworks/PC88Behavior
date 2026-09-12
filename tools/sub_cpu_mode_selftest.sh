#!/usr/bin/env bash
# tools/sub_cpu_mode_selftest.sh — m7lt: フロントエンドの`--sub-cpu-mode`
# selftest（公式ROM不要）。
#
# 背景: no_diskの+0要求長5対6が「起動時交換の時間の形」に由来するかを
# 調べる前に、計測ハーネスがQUASI88のサブCPU駆動方式（q88_sub_cpu_mode。
# 0=main/sub排他切替・1=交互1命令・2=5μsずつ交互）をモード0に固定して
# いないかをふるい分ける（tools/search_error_response_candidate.pyの
# `cpu-mode-screen`）。本selftestはその足場である`--sub-cpu-mode`引数
# 自体の検査で、公式ROM・公式ディスクは使わない。
#
# 自作サブROM（src/l3_service/make_subrom.py）+ 試験用mainドライバ
# （tools/make_l3_test_main.py）+ 自作テストディスク（tools/make_l3_testdisk.py）
# の組み合わせは tools/verify_l3.sh と同じ「公式ROM無しで計測ハーネスを
# 走らせる」型を踏襲する。
#
# 検査項目:
#   1. --sub-cpu-mode 不正値（3, -1, 文字）を拒否して非0終了すること
#   2. --sub-cpu-mode 2 指定時、stderrのcore_option行がrequested>=1・
#      returned=2になること
#   3. --sub-cpu-mode 無指定時、core_option行がreturned=noneになること
#      （requestedは無指定でも数える）
#   4. （可能なら）--sub-cpu-mode 2 でこの試験用ROM一式のI/Oログが
#      無指定と変わること。変わらない場合はselftestを失敗させず、
#      変わらない旨を報告するだけにする（試験用ドライバの単純な
#      SEND/RECV手順ではモード差が現れない形もありうるため）。
#
# 値（交換値・FDC生値・画面本文）は表示しない。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
GEN_SUB="$REPO/src/l3_service/make_subrom.py"
GEN_MAIN="$REPO/tools/make_l3_test_main.py"
GEN_DISK="$REPO/tools/make_l3_testdisk.py"

REQUESTS="0:1,3:5,7:8"
FRAMES=120

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }

overall_rc=0

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "コアが無い。先に tools/setup_harness.sh を実行すること" >&2; exit 1
fi
if [ ! -x "$FRONTEND" ]; then
  say "フロントエンドをビルド"
  make -s -C "$REPO/tools/harness/frontend" || exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say "自作サブROM + 試験用mainドライバ + 自作テストディスクを組み立てる（公式ROM不要）"
mkdir -p "$WORK/rom"
python3 "$GEN_SUB" "$WORK/rom" --force-post-bulk-active || exit 1
python3 "$GEN_MAIN" "$WORK/rom" --requests "$REQUESTS" || exit 1
python3 "$GEN_DISK" "$WORK/test.d88" || exit 1

# --- 1. 不正値の拒否 ---------------------------------------------------
say "--sub-cpu-mode 不正値（3, -1, 文字）を拒否すること"
for bad in 3 -1 x; do
  "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --disk "$WORK/test.d88" \
      --frames "$FRAMES" --sub-cpu-mode "$bad" \
      >"$WORK/bad.stdout.txt" 2>"$WORK/bad.stderr.txt"
  rc=$?
  if [ "$rc" != "0" ]; then
    ok "--sub-cpu-mode $bad を非0終了(rc=$rc)で拒否"
  else
    ng "--sub-cpu-mode $bad が受理されてしまった（rc=0）"
    overall_rc=1
  fi
done

# --- 2/3. core_option証跡（requested/returned） -------------------------
run_with_mode() {
  # $1: sub-cpu-modeの値（空文字なら無指定）, $2: 出力タグ
  local mode="$1" tag="$2"
  local extra=()
  if [ -n "$mode" ]; then
    extra=(--sub-cpu-mode "$mode")
  fi
  "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --disk "$WORK/test.d88" \
      --frames "$FRAMES" --io-log "$WORK/${tag}.iolog.txt" \
      "${extra[@]+"${extra[@]}"}" \
      >"$WORK/${tag}.stdout.txt" 2>"$WORK/${tag}.stderr.txt"
}

say "--sub-cpu-mode 2 指定時のcore_option証跡"
run_with_mode "2" "mode2"
LINE_MODE2="$(grep -o 'q88h: core_option q88_sub_cpu_mode requested=[0-9]\+ returned=[^ ]\+' \
  "$WORK/mode2.stderr.txt" | tail -1 || true)"
if [ -n "$LINE_MODE2" ]; then
  echo "  観測: $LINE_MODE2"
fi
REQ2="$(echo "$LINE_MODE2" | sed -E -n 's/.*requested=([0-9]+).*/\1/p')"
RET2="$(echo "$LINE_MODE2" | sed -E -n 's/.*returned=([^ ]+).*/\1/p')"
if [ -n "$REQ2" ] && [ "$REQ2" -ge 1 ] 2>/dev/null && [ "$RET2" = "2" ]; then
  ok "--sub-cpu-mode 2でrequested>=1・returned=2の証跡が出る"
else
  ng "--sub-cpu-mode 2の証跡が想定と異なる（requested=$REQ2 returned=${RET2}）"
  overall_rc=1
fi

say "--sub-cpu-mode 無指定時のcore_option証跡（returned=noneのはず）"
run_with_mode "" "none"
LINE_NONE="$(grep -o 'q88h: core_option q88_sub_cpu_mode requested=[0-9]\+ returned=[^ ]\+' \
  "$WORK/none.stderr.txt" | tail -1 || true)"
if [ -n "$LINE_NONE" ]; then
  echo "  観測: $LINE_NONE"
fi
RET_NONE="$(echo "$LINE_NONE" | sed -E -n 's/.*returned=([^ ]+).*/\1/p')"
if [ "$RET_NONE" = "none" ]; then
  ok "--sub-cpu-mode 無指定でreturned=noneの証跡が出る"
else
  ng "--sub-cpu-mode 無指定なのにreturned=noneでない（returned=${RET_NONE}）"
  overall_rc=1
fi

# --- 4. I/Oログが変わるか（可能なら。失敗にはしない） --------------------
say "--sub-cpu-mode 2でこの試験用ROM一式のI/Oログが無指定と変わるか（参考情報）"
if [ -f "$WORK/mode2.iolog.txt" ] && [ -f "$WORK/none.iolog.txt" ]; then
  H_MODE2="$(shasum -a 256 "$WORK/mode2.iolog.txt" | awk '{print $1}')"
  H_NONE="$(shasum -a 256 "$WORK/none.iolog.txt" | awk '{print $1}')"
  if [ "$H_MODE2" != "$H_NONE" ]; then
    ok "モード2でこの試験用ROM一式のI/Oログが無指定（モード0）と変わった"
  else
    echo "  観測: 変わらなかった。理由: 試験用mainドライバ（tools/make_l3_test_main.py）は"
    echo "  仕様書どおりのSEND/RECV手順を待ち合わせで行うだけの単純な固定手順で、"
    echo "  公式mainのような『空き時間の使い方』の違いが生じる余地が無い可能性がある。"
    echo "  この観測はselftestを失敗させない（m7lt cpu-mode-screenの実測が本題）。"
  fi
else
  ng "I/Oログが生成されなかった"
  overall_rc=1
fi

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "==> 全項目 OK"
else
  echo "==> 一部 NG"
fi
exit "$overall_rc"

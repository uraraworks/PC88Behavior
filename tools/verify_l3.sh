#!/usr/bin/env bash
# tools/verify_l3.sh — 自作 L3 サブROM（DISK.ROM相当）を検証する。
#
# tools/verify_l1.sh（M4）と同じ型（**公式ROM不要で回せる**）を踏襲する。
# L1 は「自作 N88.ROM を丸ごと走らせ、リポジトリ内の基準ログと比べる」
# ことで公式ROM無しの検証を成立させていた。L3 では main 側（N88.ROM）も
# 未実装（BASIC の再実装は L4 の範囲、docs/spec/l3-subrom.md 0節）なので、
# 同じ型を「main 側も、仕様書1.10・1.12・1.13節に書かれている手順**だけ**
# を行う試験用ドライバ（tools/make_l3_test_main.py）で置き換える」形に
# している。公式ROM・公式ディスクは一度も要らない。
#
# 検証すること（仕様書6節の実装要件のうち、公式ROM無しで検証できる範囲）:
#   1. SEND/RECV の1バイト送受信ハンドシェイクが正しく機能すること
#   2. 256バイト単位の読み出し要求（固定8バイトヘッダ）を解釈できること
#   3. μPD765経由のセクタ読み出しが、自作テストディスクの内容と
#      機械的に一致する256バイトを返すこと
#   4. ディスク無しではサブCPUが1命令も実行されないこと（仕様書1.1節・
#      5.2条件4。ネガティブコントロール）
#   5. 上のいずれかをわざと壊すと検出できること
#
# **検証しないこと（正直に書く）**:
#   diskA 起動時の高速バルクモード（5635件、仕様書1.6節・5.2条件1）の
#   公式ログとの完全一致は、ここでは判定しない。理由は下の「制限事項」。
#
# 使い方: tools/verify_l3.sh

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
GEN_SUB="$REPO/src/l3_service/make_subrom.py"
GEN_MAIN="$REPO/tools/make_l3_test_main.py"
GEN_DISK="$REPO/tools/make_l3_testdisk.py"
CHECK="$REPO/tools/check_l3_response.py"

REQUESTS="0:1,3:5,7:8"   # cyl:sec の列。make_l3_testdisk.py の範囲内(cyl<8,sec 1-8)
FRAMES=120

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }

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

overall_rc=0

# --------------------------------------------------------------------
# 1〜3. SEND/RECV + 256バイト読み出し要求 + FDC 経由セクタ読み出し
# --------------------------------------------------------------------
say "自作サブROM + 試験用mainドライバ + 自作テストディスクを組み立てる"
mkdir -p "$WORK/rom_ok"
python3 "$GEN_SUB" "$WORK/rom_ok" || exit 1
python3 "$GEN_MAIN" "$WORK/rom_ok" --requests "$REQUESTS" || exit 1
python3 "$GEN_DISK" "$WORK/test.d88" || exit 1

say "走らせる（$FRAMES フレーム、要求: $REQUESTS）"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_ok" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/ok.iolog.txt" \
    >"$WORK/ok.stdout.txt" 2>"$WORK/ok.stderr.txt"

say "main が受け取った256バイト×3件を判定する"
if python3 "$CHECK" "$WORK/ok.iolog.txt" --requests "$REQUESTS"; then
  ok "SEND/RECVハンドシェイク・256バイト読み出し要求・FDCセクタ読み出しが一致"
else
  ng "自作サブROMの応答が自作テストディスクの内容と一致しない"
  overall_rc=1
fi

# --------------------------------------------------------------------
# 4. ディスク無し = ネガティブコントロール（仕様書1.1節・5.2条件4）
# --------------------------------------------------------------------
say "ネガティブコントロール（ディスク無し）"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_ok" \
    --frames 30 --io-log "$WORK/nodisk.iolog.txt" \
    >"$WORK/nodisk.stdout.txt" 2>"$WORK/nodisk.stderr.txt"

sub_events="$(awk '/^# sub$/{f=1;next} /^# main$/{f=0} f && !/^#/ && NF' "$WORK/nodisk.iolog.txt" | wc -l | tr -d ' ')"
if [ "$sub_events" = "0" ]; then
  ok "ディスク無しでは sub の I/O イベントが0件（仕様書1.1節のとおり）"
else
  # 正直に書く: 失格にはしない。仕様書1.1節「ディスクが無いとサブCPUは
  # 1命令も実行しない」は公式DISK.ROMの実測結果であり、ハードウェアの
  # 事実なのか公式ROM側のソフトウェア的なチェック（ディスク無しを検出
  # して即座に停止する）なのかは仕様書からは判別できない（未確定）。
  # 自作サブROMはディスク有無を検出せず素朴にFDCコマンドを発行するため、
  # 少なくとも今の実装ではこの条件を満たさない。これは既知の未達成
  # 項目として報告する（誤魔化して OK にはしない）。
  ng "ディスク無しでも sub が $sub_events 件の I/O を発行した（1.1節を満たさない。既知の未達成——下記「制限事項」参照）"
  overall_rc=1
fi

# --------------------------------------------------------------------
# 5. わざと壊して検出できることを確認する（このリポジトリの規律）
# --------------------------------------------------------------------
say "わざと壊す: 応答の先頭バイトを1ビット反転させた版で検証が落ちるか"
mkdir -p "$WORK/rom_broken"
python3 "$GEN_SUB" "$WORK/rom_broken" --break-response || exit 1
python3 "$GEN_MAIN" "$WORK/rom_broken" --requests "$REQUESTS" || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_broken" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/broken.iolog.txt" \
    >"$WORK/broken.stdout.txt" 2>"$WORK/broken.stderr.txt"

if python3 "$CHECK" "$WORK/broken.iolog.txt" --requests "$REQUESTS" >"$WORK/broken.check.txt" 2>&1; then
  ng "壊した版が誤って PASS した（検証器が検出力を持たない）"
  cat "$WORK/broken.check.txt"
  overall_rc=1
else
  ok "壊した版は正しく不一致として検出された"
  grep "不一致" "$WORK/broken.check.txt" | sed 's/^/       /'
fi

# --------------------------------------------------------------------
# 制限事項（正直に書く。ごまかさない）
# --------------------------------------------------------------------
say "制限事項（未検証のまま残すこと）"
cat <<'EOF'
  diskA 起動時の高速バルクモード（sub OUT $FC が5635件連続、
  仕様書1.6節・5.2条件1）の公式ログ（measurements/m6g-d0-boot-run1.iolog.txt）
  との完全一致は、ここでは検証していない。理由は2つある。

  (a) 仕様書自身が「サブが要求を受けてから最初に応答するまでの遅延・
      手順」を未着手・未確定と明記している（3節）。バルクモードの
      起動条件・トリガーの具体的な手順が仕様書に無いため、それを
      駆動する試験用mainドライバを仕様書だけから正しく書けない。
  (b) 5635件のバイト列そのものは diskA（N88-BASIC）のブートローダの
      実データであり、クリーンルーム規律により読んでいない。
      自作テストディスクは自作の式で中身を生成しているので、
      「値そのもの」が公式ログと一致することは構造的に確認しようが
      ない（値が分かっていれば、それは読んだことになってしまう）。

  加えて、5.2条件4（ディスク無しで sub が1命令も実行しない）は現在の
  実装では満たさない（上のネガティブコントロールの結果を参照）。
  自作サブROMはディスクの有無を検出せず、リセット直後から FDC 初期化
  （SPECIFY・RECALIBRATE）を素朴に発行する。この条件がハードウェア
  レベルの事実（ディスクドライブ実装がサブCPUの動作電源/クロックを
  握っている等）なのか、公式DISK.ROM側のソフトウェア的な自己診断
  （ディスク無しを検出して即座に停止する）なのかは仕様書からは
  判別できない（未確定）。後者であれば、ディスク検出ロジックを
  足せば満たせる可能性がある——次のマイルストーンの宿題として残す。

  ここで検証したのは、仕様書6節1〜3・5・6項（SEND/RECVハンドシェイク・
  256バイト読み出し要求・FDC経由のセクタ読み出し）が、仕様書に書かれた
  手順を行う相手に対して正しく機能することの、公式ROM無しでの確認である。
EOF

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "L3 (このスクリプトが検証できる範囲) 適合"
else
  echo "L3 不適合（上記参照）"
fi
exit "$overall_rc"

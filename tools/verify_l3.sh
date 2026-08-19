#!/usr/bin/env bash
# tools/verify_l3.sh — 自作 L3 サブROM（DISK.ROM相当）を検証する。
#
# これは二層のうちの**自己検証層**（公式ROM不要）。もう一方の
# **適合テスト層**（公式ROM・公式ディスクが要る。期待値はハッシュのみ
# コミット）は tools/conform_l3.sh（docs/PLAN.md「次にやること」1項）。
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
#   2. 交換#3（固定8バイト要求→1バイト応答）と交換#4
#      （2バイト要求→256バイト応答）の境界を解釈できること
#   3. μPD765経由のセクタ読み出しが、自作テストディスクの内容と
#      機械的に一致する256バイトを返すこと
#   4. （m7arで移設）ディスク無しのネガティブコントロール（仕様書1.1節・
#      5.2条件4）は**この層では判定できない**ことが分かったので、判定は
#      tools/conform_l3.sh へ移した。ここでは判定不能である旨と根拠を
#      表示するだけにしている（下の該当箇所のコメント参照）。
#   5. 上のいずれかをわざと壊すと検出できること
#
# **検証しないこと（正直に書く）**:
#   diskA 起動時の高速バルクモード（5635件、仕様書1.6節・5.2条件1）の
#   公式ログとの完全一致は、ここでは判定しない。理由は下の「制限事項」。
#
# **この検証の限界（第6版で追記）**: ここで組ませている相手役
#   （tools/make_l3_test_main.py）は公式 main ROM ではなく、こちらも
#   自作である。したがって「PASSした」ことが示すのは"仕様書
#   （docs/spec/l3-subrom.md）に書かれた手順をそのまま行う相手と
#   通信できる"ことであって、"公式 main ROM と通信できる"ことの証明
#   ではない。過去に一度、自作サブROMと自作mainドライバの両方が
#   同じ誤解（ポートCのたすき掛け理論・$FEへの直接書き込み）を共有した
#   まま辻褄を合わせてしまい、このスクリプトが誤ってPASSし続けていた
#   ことがある（混成ROM実走で公式main一式と組ませて初めて発覚した。
#   `docs/notes/m6k-mixed-divergence.md`）。両ファイルは互いに参照せず
#   仕様書だけを別々の根拠として書くという規律を保っているが、
#   それでも「両者が同じ仕様書読解ミスを共有する」可能性そのものは
#   このスクリプトの構造上排除できない。公式ROMでの実走確認
#   （適合テスト層、tools/conform_l3.sh）が最終的な裏付けになる。
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
na()  { printf '  \033[33m--\033[0m   %s\n' "$1"; }   # 判定不能（合否ではない）

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

say "走らせる（${FRAMES} フレーム、要求: ${REQUESTS}）"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_ok" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/ok.iolog.txt" \
    >"$WORK/ok.stdout.txt" 2>"$WORK/ok.stderr.txt"

say "main が受け取った交換#3/#4応答を判定する"
if python3 "$CHECK" "$WORK/ok.iolog.txt" --requests "$REQUESTS"; then
  ok "SEND/RECV・交換#3/#4境界・FDCセクタ読み出しが一致"
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
# ---- m7ar（2026-08-18）で帰属が確定したので判定を改めた ----
# 以前はここで「ディスク無しでも sub が N 件の I/O を発行した」を NG
# （既知の未達成）として数えていた。**その帰属が誤りだった。**
# ディスク無し・2×2の実測（30フレーム/120フレームとも同じ傾向）:
#
#   main側  sub側   sub の I/O 件数
#   公式    公式    0            ← 仕様書1.1節の観測そのもの
#   公式    自作    0            ← 自作サブROMも同じく無音
#   自作    自作    2575         ← ここが NG と報告されていた状態
#   自作    公式    208437       ← **公式サブROMでも無音にならない**
#
# 4行目が決定的で、**同じ試験用mainドライバを相手にすると公式サブROMも
# 20万件を出す**。つまりこの数字はサブROM側の性質ではなく、
# 「ディスクが無くてもサブを走らせてしまう試験用mainドライバ」の性質
# だった（公式mainはディスクが無いとサブを起動しない。だから1〜2行目は
# 0件になる）。自作サブROMを公式main相手に置けば0件で、条件4を満たす。
#
# したがってこの自己検証層では条件4を**判定できない**（相手役の main が
# 公式でないと成立しない条件だから）。判定は tools/conform_l3.sh の
# 「適合条件4のネガティブコントロール」へ移した（公式main + 自作サブROM
# で0件、陽性対照つき）。ここでは黙って OK にはせず、判定不能である
# ことと、その根拠と、どこで判定しているかを毎回表示する。
if [ "$sub_events" = "0" ]; then
  ok "ディスク無しでは sub の I/O イベントが0件（この構成では珍しい。ドライバ側の挙動が変わった可能性を確認すること）"
else
  na "条件4（ディスク無しでsubが1命令も実行しない）はこの層では判定不能"
  echo "       試験用mainドライバがディスク無しでもサブを起動するため、sub は $sub_events 件の I/O を発行する。"
  echo "       同じドライバでは公式サブROMも 20万件規模を発行する（m7ar の2×2実測）ので、"
  echo "       この数字はサブROM側の性質ではない。判定は tools/conform_l3.sh"
  echo "       「適合条件4のネガティブコントロール」（公式main + 自作サブROM）で行う。"
  echo "       根拠: docs/notes/m7ar-negative-control-attribution.md"
fi

# --------------------------------------------------------------------
# 5. ディスパッチャの戻り先（make_subrom.py 第9版の回帰テスト）
# --------------------------------------------------------------------
# 背景: 公式環境での混成ROM実走で、RECV/SENDプリミティブを1回終えても
# IDLE_DISPATCHへ戻らず「8バイトヘッダ・256バイト応答は一塊」と
# 決め打ちしていた旧構造がデッドロックを起こすことが分かった
# （src/l3_service/make_subrom.py 第9版のモジュールdocstring参照）。
# 上の1〜3の通常シナリオは、自作main・自作subの両方が同じ「8バイト→
# 256バイトの塊」という前提を共有しているため、この種のバグを検出
# できない（このスクリプトの構造上の限界、上の「この検証の限界」参照）。
# tools/make_l3_test_main.py --dispatch-switch-test は、仕様書1.10節の
# 範囲内（SEND/RECVプリミティブは自由に組み合わせられる）で「8バイトの
# ヘッダをSENDしたあと、応答は1バイト目だけRECVしてすぐ次へ進む」
# 割り込みを挟み、そのあとで通常の要求列(REQUESTS)が壊れずに完了するかを
# 見る。
say "ディスパッチャの戻り先: 割り込みシナリオを挟んでも通常の要求列が壊れないか"
mkdir -p "$WORK/rom_dispatch_ok"
python3 "$GEN_SUB" "$WORK/rom_dispatch_ok" || exit 1
python3 "$GEN_MAIN" "$WORK/rom_dispatch_ok" --requests "$REQUESTS" --dispatch-switch-test || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_dispatch_ok" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/dispatch_ok.iolog.txt" \
    >"$WORK/dispatch_ok.stdout.txt" 2>"$WORK/dispatch_ok.stderr.txt"

if python3 "$CHECK" "$WORK/dispatch_ok.iolog.txt" --requests "$REQUESTS" --skip-prefix-bytes 257; then
  ok "割り込み後も通常の3要求が正しく完了した（プリミティブごとにディスパッチャへ戻る現行実装）"
else
  ng "割り込みシナリオを挟むと現行実装でも要求列が壊れた"
  overall_rc=1
fi

say "検出力の確認: 修正前と同型の版（--break-dispatch-return）で同じシナリオが落ちるか"
mkdir -p "$WORK/rom_dispatch_broken"
python3 "$GEN_SUB" "$WORK/rom_dispatch_broken" --break-dispatch-return || exit 1
python3 "$GEN_MAIN" "$WORK/rom_dispatch_broken" --requests "$REQUESTS" --dispatch-switch-test || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_dispatch_broken" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/dispatch_broken.iolog.txt" \
    >"$WORK/dispatch_broken.stdout.txt" 2>"$WORK/dispatch_broken.stderr.txt"

if python3 "$CHECK" "$WORK/dispatch_broken.iolog.txt" --requests "$REQUESTS" --skip-prefix-bytes 257 >"$WORK/dispatch_broken.check.txt" 2>&1; then
  ng "修正前相当の版が割り込みシナリオでも誤ってPASSした（回帰テストが検出力を持たない）"
  cat "$WORK/dispatch_broken.check.txt"
  overall_rc=1
else
  ok "修正前相当の版は割り込みシナリオで正しく不一致/未達として検出された"
  grep -m5 "不一致\|足りない" "$WORK/dispatch_broken.check.txt" | sed 's/^/       /'
fi

# --------------------------------------------------------------------
# 6. run境界（連続SENDの途中でOUT $FF 0Fが省略される場合）でも
#    デッドロックしないか（make_subrom.py 第11版の回帰テスト）
# --------------------------------------------------------------------
# 背景: 公式環境での混成ROM実走で、mainが複数バイト連続SEND(run)の
# 継続バイトで`OUT $FF 0F`を省略して直接`bit1=1`待ちに入っているのに、
# 自作subがRECVを1バイト完遂するたびに無条件でIDLE_DISPATCHへ戻り、
# そこで何も書かずに$FEを読みに行くだけだったため、main/subが相互に
# 相手の書き込みを待ち続けてデッドロックしていた
# （docs/notes/m6n-run-boundary.md、仕様書1.20節）。
# tools/make_l3_test_main.py --run-continuation-test は、仕様書1.10節が
# 明記する「OUT $FF 0Fは省略される場合がある」の範囲内で、8バイト
# ヘッダの1バイト目だけ通常のSEND、2〜8バイト目は0Fを省略したSENDで
# 送るrunを再現する。
say "run境界: 連続SENDの継続バイトで0Fを省略してもデッドロックしないか"
mkdir -p "$WORK/rom_run_cont"
python3 "$GEN_SUB" "$WORK/rom_run_cont" || exit 1
python3 "$GEN_MAIN" "$WORK/rom_run_cont" --requests "$REQUESTS" --run-continuation-test || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_run_cont" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/run_cont.iolog.txt" \
    >"$WORK/run_cont.stdout.txt" 2>"$WORK/run_cont.stderr.txt"

if python3 "$CHECK" "$WORK/run_cont.iolog.txt" --requests "$REQUESTS" --skip-prefix-bytes 257; then
  ok "0F省略runのあとも通常の3要求が正しく完了した（run境界判別、現行実装）"
else
  ng "0F省略runを挟むと現行実装でも要求列が壊れた/デッドロックした"
  overall_rc=1
fi

say "検出力の確認: 修正前と同型の版（--break-run-continuation）で同じシナリオが落ちるか"
mkdir -p "$WORK/rom_run_cont_broken"
python3 "$GEN_SUB" "$WORK/rom_run_cont_broken" --break-run-continuation || exit 1
python3 "$GEN_MAIN" "$WORK/rom_run_cont_broken" --requests "$REQUESTS" --run-continuation-test || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_run_cont_broken" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/run_cont_broken.iolog.txt" \
    >"$WORK/run_cont_broken.stdout.txt" 2>"$WORK/run_cont_broken.stderr.txt"

if python3 "$CHECK" "$WORK/run_cont_broken.iolog.txt" --requests "$REQUESTS" --skip-prefix-bytes 257 >"$WORK/run_cont_broken.check.txt" 2>&1; then
  ng "修正前相当の版が0F省略runシナリオでも誤ってPASSした（回帰テストが検出力を持たない）"
  cat "$WORK/run_cont_broken.check.txt"
  overall_rc=1
else
  ok "修正前相当の版は0F省略runシナリオで正しく不一致/未達として検出された"
  grep -m5 "不一致\|足りない" "$WORK/run_cont_broken.check.txt" | sed 's/^/       /'
fi

# --------------------------------------------------------------------
# 6b. わざと壊して検出できることを確認する（このリポジトリの規律）
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
# 7. SENSE INTERRUPT STATUSの結果バイト数（μPD765データシート適合）
# --------------------------------------------------------------------
# 背景: 公式環境での混成ROM実走で、sub側がIN $FA(FDCステータス)を延々
# ポーリングして止まっているのが観測された（measurements配下の混成ROM
# ログ解析）。μPD765/8272データシートでは、SENSE INTERRUPT STATUSは
# 保留中の割り込みが無い状態で発行されると結果フェーズがST0
# (Invalid Command=80H)の1バイトだけで終わり、通常の2バイト目(PCN)は
# 来ない。旧実装のFDC_SENSE_INTは常に2バイト読んでおり、来ないはずの
# 2バイト目を待ち続けて無限スピンし得た（make_subrom.pyのFDC_SENSE_INT
# 参照）。
#
# tools/make_l3_test_main.py 側は変更していない——このバグはsubの内部の
# FDCコマンド往復（$FA/$FB）だけで完結し、main向けのSEND/RECV手順
# ($FC/$FD/$FE/$FF)には現れないため、通常のREQUESTSシナリオと同じ
# 試験用mainドライバで検証できる。sub側にだけ
# `--inject-spurious-sense-int`（RECALIBRATE/SEEKを一度も発行していない
# 起動直後にSENSE INTERRUPT STATUSをもう1回よけいに呼び、「保留中の
# 割り込みが無い」状況を意図的に作る）を足して、修正後の実装がこれを
# 正しく1バイトで打ち切れるかを見る。
say "SENSE INTERRUPT STATUSの結果バイト数: 保留中の割り込みが無い状況を挟んでも壊れないか"
mkdir -p "$WORK/rom_sense_int_ok"
python3 "$GEN_SUB" "$WORK/rom_sense_int_ok" --inject-spurious-sense-int || exit 1
python3 "$GEN_MAIN" "$WORK/rom_sense_int_ok" --requests "$REQUESTS" || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_sense_int_ok" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/sense_int_ok.iolog.txt" \
    >"$WORK/sense_int_ok.stdout.txt" 2>"$WORK/sense_int_ok.stderr.txt"

if python3 "$CHECK" "$WORK/sense_int_ok.iolog.txt" --requests "$REQUESTS"; then
  ok "保留中の割り込みが無いSENSE INTERRUPT STATUS呼び出しを挟んでも通常の3要求が完了した"
else
  ng "SENSE INTERRUPT STATUSの結果バイト数の扱いが壊れている"
  overall_rc=1
fi

say "検出力の確認: 修正前と同型の版（--break-sense-int-result-count）で同じシナリオを走らせる"
mkdir -p "$WORK/rom_sense_int_broken"
python3 "$GEN_SUB" "$WORK/rom_sense_int_broken" \
    --inject-spurious-sense-int --break-sense-int-result-count || exit 1
python3 "$GEN_MAIN" "$WORK/rom_sense_int_broken" --requests "$REQUESTS" || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_sense_int_broken" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/sense_int_broken.iolog.txt" \
    >"$WORK/sense_int_broken.stdout.txt" 2>"$WORK/sense_int_broken.stderr.txt"
python3 "$CHECK" "$WORK/sense_int_broken.iolog.txt" --requests "$REQUESTS" \
    >"$WORK/sense_int_broken.check.txt" 2>&1 || true

# 正直に書く: この版でも256バイト×3件の内容自体は一致し得る
# （$WORK/sense_int_broken.check.txt を参照）。
#
# 第12版の追記: 上のsense_int_brokenは--break-sense-int-result-countのみ
# （FDC_IN自体は本版の修正済み実装のまま）で生成している。本版のFDC_IN
# は、待つ前に「RQM=1かつDIO=0（μPD765/8272データシートの規定で、結果
# フェーズが終わりコマンドフェーズへ戻った状態）」を検出すると、
# タイムアウトの65,535回はおろかFDC_WAIT_TIMEOUT回のポーリングすら
# 待たずに即座に中断する。したがって来ないはずの2バイト目を待つこの
# シナリオでは、$F9（タイムアウトマーカー）はもはや**一度も**現れない
# ——これは退行ではなく、本版のDIO判定がタイムアウトより先に効いている
# ことの証拠である。下で確認する。

say "SENSE INTERRUPT STATUSの結果バイト数バグ単体では、タイムアウトを待たずにDIO判定で即座に中断するか"
sense_int_ok_timeouts="$(awk '/^# sub$/{f=1;next} /^# main$/{f=0} f && $5=="OUT" && $6=="00F9"' "$WORK/sense_int_ok.iolog.txt" | wc -l | tr -d ' ')"
sense_int_broken_timeouts="$(awk '/^# sub$/{f=1;next} /^# main$/{f=0} f && $5=="OUT" && $6=="00F9"' "$WORK/sense_int_broken.iolog.txt" | wc -l | tr -d ' ')"
if [ "$sense_int_ok_timeouts" = "0" ]; then
  ok "修正後の実装ではFDCステータス待ちタイムアウトが一度も発生しなかった"
else
  ng "修正後の実装でもFDCステータス待ちタイムアウトが $sense_int_ok_timeouts 件発生した"
  overall_rc=1
fi
if [ "$sense_int_broken_timeouts" = "0" ]; then
  ok "結果バイト数バグ単体でもDIO判定が先に効き、タイムアウトが1件も記録されなかった（想定どおり）"
else
  ng "結果バイト数バグ単体なのにFDCステータス待ちタイムアウトが $sense_int_broken_timeouts 件記録された（DIO判定が効いていない）"
  overall_rc=1
fi

# --------------------------------------------------------------------
# 8. タイムアウト時・DIO不一致検出時に読み書きしない（第12版）
# --------------------------------------------------------------------
# 背景: ユーザーが2026-08-12に公式環境の混成ROM実走で報告した症状
# （commit ce3bd5b時点）は、「IN $FAを65,535回ポーリング→タイムアウト
# して$F9を記録→タイムアウトしたのにそのままIN $FBを読む」という3つ組が
# 15回繰り返され、測定イベント上限を食い潰すというものだった。
# 原因はFDC_IN/FDC_OUTの構造そのもの（タイムアウト分岐と正常分岐が
# 同じ着地点に合流しており、タイムアウト後も無条件で$FBに触れていた）
# にあった。上のセクション7で見たとおり、通常このバグはDIO判定で
# タイムアウトより先に検出されてしまうため、「本当にタイムアウトが
# 発生し、なおかつタイムアウト後に読んでしまう」旧構造そのものを
# 再現するには --break-fdc-timeout-reads-anyway でDIO判定自体を
# 無効化する必要がある。
say "検出力の確認: 旧構造（--break-fdc-timeout-reads-anyway）はタイムアウト後もIN \$FB を読んでしまうか"
mkdir -p "$WORK/rom_fdc_timeout_broken"
python3 "$GEN_SUB" "$WORK/rom_fdc_timeout_broken" \
    --inject-spurious-sense-int --break-sense-int-result-count \
    --break-fdc-timeout-reads-anyway || exit 1
python3 "$GEN_MAIN" "$WORK/rom_fdc_timeout_broken" --requests "$REQUESTS" || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_fdc_timeout_broken" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/fdc_timeout_broken.iolog.txt" \
    >"$WORK/fdc_timeout_broken.stdout.txt" 2>"$WORK/fdc_timeout_broken.stderr.txt"

# 「OUT $F9の直後にIN $FBが来る」パターン(=タイムアウトしたのにそのまま
# 読む旧構造の指紋)がsubのイベント列に現れるかを確認する。
fdc_timeout_broken_spurious="$(awk '
  /^# sub$/{f=1;next} /^# main$/{f=0}
  f {
    if (prev5=="OUT" && prev6=="00F9" && $5=="IN" && $6=="00FB") c++
    prev5=$5; prev6=$6
  }
  END{print c+0}
' "$WORK/fdc_timeout_broken.iolog.txt")"
fdc_timeout_broken_marks="$(awk '/^# sub$/{f=1;next} /^# main$/{f=0} f && $5=="OUT" && $6=="00F9"' "$WORK/fdc_timeout_broken.iolog.txt" | wc -l | tr -d ' ')"
if [ "$fdc_timeout_broken_marks" != "0" ] && [ "$fdc_timeout_broken_spurious" != "0" ]; then
  ok "旧構造では実際にタイムアウトが発生し($fdc_timeout_broken_marks 件)、直後に \$FB を読んでいた($fdc_timeout_broken_spurious 件)——検出力を確認した"
else
  ng "旧構造の再現版でタイムアウト後の読み取りパターンを検出できなかった(marks=$fdc_timeout_broken_marks spurious=$fdc_timeout_broken_spurious)"
  overall_rc=1
fi

say "修正後の実装は、同じ強制シナリオでもタイムアウト後に \$FB を読まないか"
# rom_sense_int_broken（--inject-spurious-sense-int --break-sense-int-result-count
# のみ、本版のFDC_IN）は上のセクション7で確認したとおりタイムアウト自体が
# 発生しないので、ここでは「タイムアウト直後のIN $FB」パターンが0件で
# あることを、そのログ上で確認する（本版はタイムアウトを待たずに中断
# する分、なおのこと$FBを読まない）。
sense_int_broken_spurious="$(awk '
  /^# sub$/{f=1;next} /^# main$/{f=0}
  f {
    if (prev5=="OUT" && prev6=="00F9" && $5=="IN" && $6=="00FB") c++
    prev5=$5; prev6=$6
  }
  END{print c+0}
' "$WORK/sense_int_broken.iolog.txt")"
if [ "$sense_int_broken_spurious" = "0" ]; then
  ok "修正後の実装では「タイムアウト直後にIN \$FB を読む」パターンが1件も現れなかった"
else
  ng "修正後の実装でも「タイムアウト直後にIN \$FB を読む」パターンが $sense_int_broken_spurious 件現れた"
  overall_rc=1
fi

# --------------------------------------------------------------------
# 9. run境界を「通算8バイト」ではなくbit1の観測で決めているか
#    （make_subrom.py 第13版の回帰テスト）
# --------------------------------------------------------------------
# 背景: 公式環境での混成ROM実走で、自作subがラウンド境界を無視して
# 受信バイトを通算8バイト貯めてから8バイトヘッダとして解釈していたため、
# 起動シーケンスのラウンド0〜2（2+1+5=8バイト、仕様書1.18節）を1つの
# 256バイト読み出し要求ヘッダに取り違え、mainとsubが両方「送る側」に
# なって固着することが分かった（docs/notes/m6k-mixed-divergence.md
# 第10部）。tools/make_l3_test_main.py --fixed-byte-cutoff-test は、
# 2バイト・1バイト・5バイトの独立した3ラウンド（それぞれSEND直後に
# 1バイトRECV、1.18節が確定した「ラウンドごとに応答が返る」構造）を
# 送り、値の並びだけを見れば8バイトの読み出し要求ヘッダと同じ形になる
# ように仕組む。
say "run境界: 2+1+5バイトの独立した3ラウンドを挟んでも通算8バイトに取り違えないか"
mkdir -p "$WORK/rom_fbc_ok"
python3 "$GEN_SUB" "$WORK/rom_fbc_ok" || exit 1
python3 "$GEN_MAIN" "$WORK/rom_fbc_ok" --requests "$REQUESTS" --fixed-byte-cutoff-test || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_fbc_ok" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/fbc_ok.iolog.txt" \
    >"$WORK/fbc_ok.stdout.txt" 2>"$WORK/fbc_ok.stderr.txt"

if python3 "$CHECK" "$WORK/fbc_ok.iolog.txt" --requests "$REQUESTS" --skip-prefix-bytes 3; then
  ok "2+1+5バイトの3ラウンドのあとも通常の3要求が正しく完了した（run境界駆動、現行実装）"
else
  ng "2+1+5バイトの3ラウンドを挟むと現行実装でも要求列が壊れた"
  overall_rc=1
fi

say "検出力の確認: 修正前と同型の版（--fixed-byte-cutoff-test）で同じシナリオが落ちるか"
mkdir -p "$WORK/rom_fbc_broken"
python3 "$GEN_SUB" "$WORK/rom_fbc_broken" --fixed-byte-cutoff-test || exit 1
python3 "$GEN_MAIN" "$WORK/rom_fbc_broken" --requests "$REQUESTS" --fixed-byte-cutoff-test || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_fbc_broken" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/fbc_broken.iolog.txt" \
    >"$WORK/fbc_broken.stdout.txt" 2>"$WORK/fbc_broken.stderr.txt"

if python3 "$CHECK" "$WORK/fbc_broken.iolog.txt" --requests "$REQUESTS" --skip-prefix-bytes 3 >"$WORK/fbc_broken.check.txt" 2>&1; then
  ng "修正前相当の版が2+1+5バイトシナリオでも誤ってPASSした（回帰テストが検出力を持たない）"
  cat "$WORK/fbc_broken.check.txt"
  overall_rc=1
else
  ok "修正前相当の版は2+1+5バイトシナリオで正しく不一致/未達として検出された"
  grep -m5 "不一致\|足りない" "$WORK/fbc_broken.check.txt" | sed 's/^/       /'
fi

# --------------------------------------------------------------------
# 10. バルク直後の受信runは先頭バイトの表引きでrun長・座標が決まるか
#    （仕様書1.36節、make_subrom.py 第65版・m7bjの回帰テスト）
# --------------------------------------------------------------------
# 背景: 自作subは「受信runが6バイトなら一般読み出し要求」で判別して
# いたが（第64版・m7bg）、公式にレコード長6は1件も存在しない。1.36節が
# 新規実測（148 run）で確定させたのは、受信runの先頭バイトがrun長を
# 一意に決める表引きであり、直後に必ずREADが続き座標フィールド位置
# （末尾相対: 論理トラック=位置-1、R=位置0）も確定しているのは先頭
# バイト0x02・長さ5だけだった。tools/make_l3_test_main.py
# --post-bulk-read-test は、この先頭バイト0x02・長さ5のrunを送り、
# 末尾2バイトから作られる座標のセクタが正しく返るかを見る。
POST_BULK_REQUEST="5:6"   # cyl:sec。make_l3_testdisk.pyの範囲内(cyl<8,sec 1-8)
say "1.36節: 先頭バイト0x02・長さ5のrunから正しい座標([論理トラック,R])が作られるか"
mkdir -p "$WORK/rom_pbr_ok"
python3 "$GEN_SUB" "$WORK/rom_pbr_ok" || exit 1
python3 "$GEN_MAIN" "$WORK/rom_pbr_ok" --requests "$POST_BULK_REQUEST" --post-bulk-read-test || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_pbr_ok" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/pbr_ok.iolog.txt" \
    >"$WORK/pbr_ok.stdout.txt" 2>"$WORK/pbr_ok.stderr.txt"

if python3 "$CHECK" "$WORK/pbr_ok.iolog.txt" --requests "$POST_BULK_REQUEST" --skip-prefix-bytes 1; then
  ok "先頭バイト0x02・長さ5のrunの末尾2バイトから正しいセクタが読めた（現行実装）"
else
  ng "先頭バイト0x02・長さ5のrunに対する読み出し座標が自作テストディスクの内容と一致しない"
  overall_rc=1
fi

say "検出力の確認: 旧判別（受信runが6バイトなら一般読み出し要求）へ戻すと落ちるか"
mkdir -p "$WORK/rom_pbr_broken"
python3 "$GEN_SUB" "$WORK/rom_pbr_broken" --restore-request-kind-length6 || exit 1
python3 "$GEN_MAIN" "$WORK/rom_pbr_broken" --requests "$POST_BULK_REQUEST" --post-bulk-read-test || exit 1

"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_pbr_broken" --disk "$WORK/test.d88" \
    --frames "$FRAMES" --io-log "$WORK/pbr_broken.iolog.txt" \
    >"$WORK/pbr_broken.stdout.txt" 2>"$WORK/pbr_broken.stderr.txt"

if python3 "$CHECK" "$WORK/pbr_broken.iolog.txt" --requests "$POST_BULK_REQUEST" --skip-prefix-bytes 1 >"$WORK/pbr_broken.check.txt" 2>&1; then
  ng "旧判別（run長6）を復元した版でも誤ってPASSした（回帰テストが検出力を持たない）"
  cat "$WORK/pbr_broken.check.txt"
  overall_rc=1
else
  ok "旧判別（run長6）を復元した版は、長さ5のrunを一般読み出し要求と認識できず正しく不一致/未達として検出された"
  grep -m5 "不一致\|足りない" "$WORK/pbr_broken.check.txt" | sed 's/^/       /'
fi

# --------------------------------------------------------------------
# 制限事項（正直に書く。ごまかさない）
# --------------------------------------------------------------------
# --------------------------------------------------------------------
# 書き込み経路（仕様書1.35節、第54版・m7av）
# --------------------------------------------------------------------
say "書き込み経路: 受信列の末尾256バイトをそのままWRITE DATAへ流すか"
mkdir -p "$WORK/rom_write"
python3 "$GEN_SUB" "$WORK/rom_write" || exit 1
python3 "$GEN_MAIN" "$WORK/rom_write" --requests "3:5" --write-test || exit 1
cp "$WORK/test.d88" "$WORK/write.d88"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_write" --disk "$WORK/write.d88" \
    --frames "$FRAMES" --io-log "$WORK/write.iolog.txt" \
    >"$WORK/write.stdout.txt" 2>"$WORK/write.stderr.txt"
if python3 "$REPO/tools/check_l3_write.py" "$WORK/write.iolog.txt"; then
  ok "WRITE DATAのデータ部が、subがそのrunで最後に受け取った256バイトと全位置一致"
else
  ng "WRITE DATAのデータ部が受信列の末尾256バイトと一致しない（1.35節を満たさない）"
  overall_rc=1
fi

say "検出力の確認: データ部の窓を1バイトずらした版が不一致として検出されること"
mkdir -p "$WORK/rom_write_broken"
python3 "$GEN_SUB" "$WORK/rom_write_broken" --break-write-data-window || exit 1
python3 "$GEN_MAIN" "$WORK/rom_write_broken" --requests "3:5" --write-test || exit 1
cp "$WORK/test.d88" "$WORK/write_broken.d88"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_write_broken" --disk "$WORK/write_broken.d88" \
    --frames "$FRAMES" --io-log "$WORK/write_broken.iolog.txt" \
    >"$WORK/write_broken.stdout.txt" 2>"$WORK/write_broken.stderr.txt"
if python3 "$REPO/tools/check_l3_write.py" "$WORK/write_broken.iolog.txt" >/dev/null 2>&1; then
  ng "窓をずらした版が合格してしまった（この検査に検出力が無い）"
  overall_rc=1
else
  ok "窓を1バイトずらした版は正しく不一致として検出された"
fi

say "検出力の確認: 座標の導出を壊した版が不一致として検出されること"
mkdir -p "$WORK/rom_write_coords"
python3 "$GEN_SUB" "$WORK/rom_write_coords" --break-write-coords || exit 1
python3 "$GEN_MAIN" "$WORK/rom_write_coords" --requests "3:5" --write-test || exit 1
cp "$WORK/test.d88" "$WORK/write_coords.d88"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_write_coords" --disk "$WORK/write_coords.d88" \
    --frames "$FRAMES" --io-log "$WORK/write_coords.iolog.txt" \
    >"$WORK/write_coords.stdout.txt" 2>"$WORK/write_coords.stderr.txt"
if python3 "$REPO/tools/check_l3_write.py" "$WORK/write_coords.iolog.txt" >/dev/null 2>&1; then
  ng "座標の導出を壊した版が合格してしまった（座標検査に検出力が無い）"
  overall_rc=1
else
  ok "論理トラックからC/Hを導く規則を壊した版は正しく不一致として検出された"
fi

say "検出力の確認: 書き込み応答を送らない版が不一致として検出されること"
mkdir -p "$WORK/rom_write_ack"
python3 "$GEN_SUB" "$WORK/rom_write_ack" --break-write-ack || exit 1
python3 "$GEN_MAIN" "$WORK/rom_write_ack" --requests "3:5" --write-test || exit 1
cp "$WORK/test.d88" "$WORK/write_ack.d88"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom_write_ack" --disk "$WORK/write_ack.d88" \
    --frames "$FRAMES" --io-log "$WORK/write_ack.iolog.txt" \
    >"$WORK/write_ack.stdout.txt" 2>"$WORK/write_ack.stderr.txt"
if python3 "$REPO/tools/check_l3_write.py" "$WORK/write_ack.iolog.txt" >/dev/null 2>&1; then
  ng "応答を送らない版が合格してしまった（応答の検査に検出力が無い）"
  overall_rc=1
else
  ok "書き込み応答を送らない版は正しく不一致として検出された"
fi

# ディスクへの反映（書いたものを読み戻せるか）は**このハーネスでは判定できない**。
# 根拠: 公式ROM一式で SAVE を実行し WRITE DATA が15件発行された実測でも、
# 与えたディスクイメージのファイルは1バイトも変化しなかった（m7av。
# 変化したのは事前にこちらが外したライトプロテクトの1バイトだけ）。
# つまり書き込みがファイルへ落ちないのはハーネス側の性質であって、
# 自作サブROMの性質ではない。ここで黙って「往復OK」とは言わない。
na "書いた内容をディスクから読み戻せるかは、このハーネスでは判定不能"
echo "       公式ROMのSAVE（WRITE DATA 15件）でもイメージファイルは変化しない。"
echo "       根拠: docs/notes/m7av-write-path-implementation.md"

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

  5.2条件4（ディスク無しで sub が1命令も実行しない）は、この層では
  判定できない（m7ar で帰属が確定した。上のネガティブコントロールの
  コメント参照）。ここで数えている件数は「試験用mainドライバが
  ディスク無しでもサブを走らせる」ことの結果であって、サブROM側の
  性質ではない——**同じドライバでは公式サブROMも20万件規模を出す**。
  自作サブROMを公式main相手に置くと0件になり条件4を満たす。判定は
  tools/conform_l3.sh の「適合条件4のネガティブコントロール」で行う
  （公式main + 自作サブROM、陽性対照つき。2026-08-18時点で合格）。
  この条件が「ハードウェアの事実か、公式ROMのソフトウェア的な自己診断か」
  という長らくの未確定も、これで前者と分かった——公式サブROMは
  ソフトウェア的には無音にならない（ドライバ次第で20万件出す）ので、
  無音にしているのは main 側／ハード側である。

  ここで検証したのは、仕様書6節1〜3・5・6項（SEND/RECVハンドシェイク・
  交換#3/#4の応答境界・FDC経由のセクタ読み出し）が、仕様書に書かれた
  手順を行う相手に対して正しく機能することの、公式ROM無しでの確認である。

  交換#3/#4の訂正根拠はm7kの公式側交換境界と混成側状態遷移である。
  この自己検証は自作mainと自作subの組み合わせなので、同じ誤解が両側へ
  入る危険を排除できない。公式mainを片側にした混成実走を最終根拠とする。
EOF

echo
if [ "$overall_rc" -eq 0 ]; then
  echo "L3 (このスクリプトが検証できる範囲) 適合"
else
  echo "L3 不適合（上記参照）"
fi
exit "$overall_rc"

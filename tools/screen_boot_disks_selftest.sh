#!/usr/bin/env bash
# tools/screen_boot_disks_selftest.sh — tools/screen_boot_disks.sh /
# tools/lib_screen_boot_disks.sh を公式ROM・公式ディスク無しで検査する。
#
# 既存の *_selftest.sh の作法（合成フィクスチャのみ使用、わざと壊して
# 検出できることまで確かめる）を踏襲する。
# tools/screen_boot_disks.sh 本体は SCREEN_BOOT_DISKS_FAKE_IOLOG_DIR
# フックにより、実際の q88measure を呼ばずに合成 iolog で全経路
# （列挙→ダイジェスト計算→測定ループ→判定→出力）を通す。
#
# 使い方: tools/screen_boot_disks_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCREEN="$SCRIPT_DIR/screen_boot_disks.sh"
LIB="$SCRIPT_DIR/lib_screen_boot_disks.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# =========================================================================
# 1. lib_screen_boot_disks.sh の各関数を直接検査する
# =========================================================================
source "$LIB"

# --- a. digest_basename: 既知のbasenameのSHA-256先頭8桁と一致するか -------
KNOWN_NAME="EXAMPLE_TITLE.D88"
EXPECT_DIGEST="$(python3 -c 'import hashlib; print(hashlib.sha256("EXAMPLE_TITLE.D88".encode()).hexdigest()[:8])')"
GOT_DIGEST="$(digest_basename "$KNOWN_NAME")"
if [ "$GOT_DIGEST" = "$EXPECT_DIGEST" ]; then
  pass "a. digest_basename は既知のファイル名から期待どおりのダイジェストを計算する"
else
  fail "a. digest_basename 不一致 (got=$GOT_DIGEST expect=$EXPECT_DIGEST)"
fi
# 異なる名前なら異なるダイジェストになること（衝突しない設計であることの弱い確認）
DIGEST2="$(digest_basename "OTHER_TITLE.D88")"
if [ "$GOT_DIGEST" != "$DIGEST2" ]; then
  pass "a. digest_basename は異なるファイル名で異なるダイジェストを返す"
else
  fail "a. digest_basename が異なるファイル名で衝突した"
fi

# --- b. list_disk_basenames: 拡張子で列挙・大小混在の重複を作らない・ソート済み ---
DISKDIR="$WORK/diskdir"
mkdir -p "$DISKDIR"
: > "$DISKDIR/ZZZ_LAST.D88"
: > "$DISKDIR/AAA_FIRST.d88"
: > "$DISKDIR/MMM_MID.D88"
: > "$DISKDIR/not_a_disk.txt"
LISTED="$(list_disk_basenames "$DISKDIR")"
EXPECT_LISTED="$(printf '%s\n%s\n%s' 'AAA_FIRST.d88' 'MMM_MID.D88' 'ZZZ_LAST.D88')"
if [ "$LISTED" = "$EXPECT_LISTED" ]; then
  pass "b. list_disk_basenames はD88拡張子(大小混在)だけをソートして列挙する"
else
  fail "b. list_disk_basenames の列挙結果が期待と違う: [$LISTED]"
fi
COUNT_LISTED="$(printf '%s\n' "$LISTED" | grep -c . )"
if [ "$COUNT_LISTED" = "3" ]; then
  pass "b. list_disk_basenames は3本を3本として数える（重複が無い）"
else
  fail "b. list_disk_basenames の本数が3ではない: $COUNT_LISTED"
fi

# --- c. count_sub_fc: 合成iologから sub OUT \$FC の件数を正しく数える -------
IOLOG_NONZERO="$WORK/nonzero.iolog.txt"
cat > "$IOLOG_NONZERO" <<'EOF'
core      : (テスト用ダミー、公式データ不使用)
frames    : 10

# main
# seq  frame  cpu   kind  port  value  pc
     1      0  main  IN    00FA   80   1000

# sub
# seq  frame  cpu   kind  port  value  pc
     1      0  sub   IN    00FA   00   2000
     2      1  sub   OUT   00FC   11   2004
     3      2  sub   OUT   00FC   22   2008
     4      3  sub   OUT   00FC   33   200C
     5      4  sub   OUT   00FB   44   2010
     6      5  sub   IN    00FC   55   2014
EOF
C_NONZERO="$(count_sub_fc "$REPO_ROOT" "$IOLOG_NONZERO")"
if [ "$C_NONZERO" = "3" ]; then
  pass "c. count_sub_fc: sub OUT \$FC が3件のiologから3を返す"
else
  fail "c. count_sub_fc: 期待3件のところ $C_NONZERO 件になった"
fi

IOLOG_ZERO="$WORK/zero.iolog.txt"
cat > "$IOLOG_ZERO" <<'EOF'
core      : (テスト用ダミー、公式データ不使用)
frames    : 10

# main
# seq  frame  cpu   kind  port  value  pc
     1      0  main  IN    00FA   80   1000

# sub
# seq  frame  cpu   kind  port  value  pc
     1      0  sub   IN    00FA   00   2000
     2      1  sub   OUT   00FF   11   2004
     3      2  sub   OUT   00FD   22   2008
     4      3  sub   IN    00FC   33   200C
EOF
C_ZERO="$(count_sub_fc "$REPO_ROOT" "$IOLOG_ZERO")"
if [ "$C_ZERO" = "0" ]; then
  pass "c. count_sub_fc: sub OUT \$FC が0件のiologから0を返す(抽出0件はhash_io_stream.py側でエラーになるが黙って一致に化けず0として扱う)"
else
  fail "c. count_sub_fc: 期待0件のところ $C_ZERO 件になった"
fi

# --- d. classify_l3_entry: 判定ロジック ----------------------------------
V1="$(classify_l3_entry 0 0)"
[ "$V1" = "入らない" ] && pass "d. classify_l3_entry(0,0) = 入らない" || fail "d. classify_l3_entry(0,0) が [$V1]"
V2="$(classify_l3_entry 5635 5635)"
[ "$V2" = "L3に入る" ] && pass "d. classify_l3_entry(5635,5635) = L3に入る" || fail "d. classify_l3_entry(5635,5635) が [$V2]"
V3="$(classify_l3_entry 0 3)"
[ "$V3" = "L3に入る" ] && pass "d. classify_l3_entry(0,3): 1フレームだけ非0でもL3に入ると判定する" || fail "d. classify_l3_entry(0,3) が [$V3]"

# =========================================================================
# 2. 検出力の自己検査（陽性対照・陰性対照）:
#    classify_l3_entry が「常にL3に入る」「常に入らない」を返す壊れた実装
#    ではないことを確認する（わざと壊した実装で確かに違う結果になるか）。
# =========================================================================
broken_always_enter() { echo "L3に入る"; }
broken_always_skip() { echo "入らない"; }
if [ "$(broken_always_enter 0 0)" != "$(classify_l3_entry 0 0)" ]; then
  pass "e. 陽性対照: 「常にL3に入る」という壊れた実装なら(0,0)で本来と違う結果になる（検出力がある）"
else
  fail "e. 陽性対照が機能していない（壊れた実装と区別できていない）"
fi
if [ "$(broken_always_skip 5635 5635)" != "$(classify_l3_entry 5635 5635)" ]; then
  pass "e. 陽性対照: 「常に入らない」という壊れた実装なら(5635,5635)で本来と違う結果になる（検出力がある）"
else
  fail "e. 陽性対照(2)が機能していない"
fi

# =========================================================================
# 3. 本体スクリプトをフェイクiolog経由で通し、末端の出力を検査する。
#    ここが「名前を出さない」性質そのものの検査。
# =========================================================================
FAKEDISKDIR="$WORK/fake_diskdir"
mkdir -p "$FAKEDISKDIR"
# わざと目立つ名前にする。もし本体スクリプトが標準出力にファイル名を
# 出す実装だったら、この文字列がそのまま出力に現れるはずで検出できる。
SECRET1="TOPSECRET_ALPHA_TITLE.D88"
SECRET2="TOPSECRET_BETA_TITLE.d88"
SECRET3="TOPSECRET_GAMMA_TITLE.D88"
: > "$FAKEDISKDIR/$SECRET1"
: > "$FAKEDISKDIR/$SECRET2"
: > "$FAKEDISKDIR/$SECRET3"
# list_disk_basenames と同じソート順(LC_ALL=C)で通し番号を割り振る前提を
# 自前でも再現し、期待するダイジェストを事前に計算しておく。
SORTED="$(list_disk_basenames "$FAKEDISKDIR")"
D1_NAME="$(printf '%s\n' "$SORTED" | sed -n '1p')"
D2_NAME="$(printf '%s\n' "$SORTED" | sed -n '2p')"
D3_NAME="$(printf '%s\n' "$SORTED" | sed -n '3p')"
D1_DIGEST="$(digest_basename "$D1_NAME")"
D2_DIGEST="$(digest_basename "$D2_NAME")"
D3_DIGEST="$(digest_basename "$D3_NAME")"

FAKEIOLOGDIR="$WORK/fake_iologs"
mkdir -p "$FAKEIOLOGDIR"
# disk1: diskA相当（sub OUT $FCが多数）→ L3に入る
cp "$IOLOG_NONZERO" "$FAKEIOLOGDIR/disk1.iolog.txt"
# disk2: diskB相当（0件）→ 入らない
cp "$IOLOG_ZERO" "$FAKEIOLOGDIR/disk2.iolog.txt"
# disk3: diskB相当（0件）→ 入らない
cp "$IOLOG_ZERO" "$FAKEIOLOGDIR/disk3.iolog.txt"

RUN_OUT="$WORK/run.out.txt"
RUN_ERR="$WORK/run.err.txt"
PC88_REF_DISK_DIR="$FAKEDISKDIR" PC88_REF_ROM_DIR="$WORK/unused_rom_dir" \
  SCREEN_BOOT_DISKS_FAKE_IOLOG_DIR="$FAKEIOLOGDIR" \
  "$SCREEN" >"$RUN_OUT" 2>"$RUN_ERR"
RUN_RC=$?

if [ "$RUN_RC" -eq 0 ]; then
  pass "f. 本体スクリプトがフェイクiolog経由で正常終了した(rc=0)"
else
  fail "f. 本体スクリプトが異常終了した(rc=$RUN_RC)。stderr:"
  sed 's/^/       /' "$RUN_ERR"
fi

# --- g. 出力にファイル名(basename)が一切現れないこと -----------------------
LEAKED=0
for s in "$SECRET1" "$SECRET2" "$SECRET3" "TOPSECRET"; do
  if grep -qF "$s" "$RUN_OUT" "$RUN_ERR"; then
    LEAKED=1
    fail "g. 出力にファイル名由来の文字列が漏れている: $s"
  fi
done
[ "$LEAKED" = 0 ] && pass "g. 標準出力・標準エラーのいずれにもディスクの実ファイル名が含まれない"

# --- h. 通し番号・ダイジェスト・判定が期待どおり出力されている -------------
if grep -qF "disk#1  ${D1_DIGEST}" "$RUN_OUT" && grep -q "disk#1.*判定=L3に入る" "$RUN_OUT"; then
  pass "h. disk#1(${D1_DIGEST}相当)がL3に入ると判定され、通し番号・ダイジェストが出力されている"
else
  fail "h. disk#1 の出力行が期待と一致しない"
  sed 's/^/       /' "$RUN_OUT"
fi
if grep -qF "disk#2  ${D2_DIGEST}" "$RUN_OUT" && grep -q "disk#2.*判定=入らない" "$RUN_OUT"; then
  pass "h. disk#2(${D2_DIGEST}相当)が入らないと判定されている"
else
  fail "h. disk#2 の出力行が期待と一致しない"
fi
if grep -qF "disk#3  ${D3_DIGEST}" "$RUN_OUT" && grep -q "disk#3.*判定=入らない" "$RUN_OUT"; then
  pass "h. disk#3(${D3_DIGEST}相当)が入らないと判定されている"
else
  fail "h. disk#3 の出力行が期待と一致しない"
fi
if grep -q "L3に入ると判定: 1 本" "$RUN_OUT"; then
  pass "h. 集計: L3に入ると判定 1本 が出力されている"
else
  fail "h. 集計行が期待と違う"
fi

# --- i. 陽性対照(続き): 全ディスクを0件にすると集計も0本に変わること -------
FAKEIOLOGDIR_ALLZERO="$WORK/fake_iologs_allzero"
mkdir -p "$FAKEIOLOGDIR_ALLZERO"
cp "$IOLOG_ZERO" "$FAKEIOLOGDIR_ALLZERO/disk1.iolog.txt"
cp "$IOLOG_ZERO" "$FAKEIOLOGDIR_ALLZERO/disk2.iolog.txt"
cp "$IOLOG_ZERO" "$FAKEIOLOGDIR_ALLZERO/disk3.iolog.txt"
RUN_OUT2="$WORK/run2.out.txt"
PC88_REF_DISK_DIR="$FAKEDISKDIR" PC88_REF_ROM_DIR="$WORK/unused_rom_dir" \
  SCREEN_BOOT_DISKS_FAKE_IOLOG_DIR="$FAKEIOLOGDIR_ALLZERO" \
  "$SCREEN" >"$RUN_OUT2" 2>"$WORK/run2.err.txt"
if grep -q "L3に入ると判定: 0 本" "$RUN_OUT2"; then
  pass "i. 陽性対照: 全ディスクを0件のフィクスチャに差し替えると集計も0本に変わる（判定が固定値を返す壊れた実装ではない）"
else
  fail "i. 陽性対照: 全ディスク0件にしても集計が0本に変わらなかった（検出力が無い可能性）"
  sed 's/^/       /' "$RUN_OUT2"
fi

# --- j. ディスクが0本の場合を明示的に報告すること（黙ってOKにしない） -------
EMPTYDIR="$WORK/empty_diskdir"
mkdir -p "$EMPTYDIR"
RUN_OUT3="$WORK/run3.out.txt"
PC88_REF_DISK_DIR="$EMPTYDIR" PC88_REF_ROM_DIR="$WORK/unused_rom_dir" \
  SCREEN_BOOT_DISKS_FAKE_IOLOG_DIR="$FAKEIOLOGDIR" \
  "$SCREEN" >"$RUN_OUT3" 2>"$WORK/run3.err.txt"
RUN3_RC=$?
if [ "$RUN3_RC" -eq 0 ] && grep -q "0本" "$RUN_OUT3"; then
  pass "j. ディスク0本のとき「0本」であることを明示的に報告する(rc=0だが黙ってOKにはしない)"
else
  fail "j. ディスク0本の扱いが期待と違う(rc=$RUN3_RC)"
  sed 's/^/       /' "$RUN_OUT3"
fi

# =========================================================================
echo
if [ "$FAIL" -eq 0 ]; then
  echo "screen_boot_disks_selftest: 全項目OK"
else
  echo "screen_boot_disks_selftest: 失敗した項目がある"
fi
exit "$FAIL"

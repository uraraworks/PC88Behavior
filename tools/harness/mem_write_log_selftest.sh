#!/usr/bin/env bash
# 範囲指定の書き込み記録（M7 段階1の器具2、--mem-write-log/--mem-write-range）
# の自己検査。公式ROMは不要。
#
# 自作 L1 IPL（src/l1_ipl/make_ipl_rom.py --font-sample）がテキストVRAMへ
# 書き込む一連の LD (nn),A を、実際にハーネスで走らせて記録し、生成器の
# 規則から独立に計算した「番地・値・発生順」の期待列と一致することを
# 確かめる。発行元PCについては ROM 内の具体的な番地を手で書き写さず、
# 「直線コード（分岐なし）なので発行元PCは単調非減少であるはず」という
# 構造的な性質だけを検査する（対応する q88h_mem_write の呼び出しが本当に
# その場で実行された命令の先頭番地を指しているなら、途中に飛び先が無い
# 限りPCは戻らない）。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND_DIR="$REPO/tools/harness/frontend"
FRONTEND="$FRONTEND_DIR/q88measure"
CORE_DIR="$REPO/tools/harness/core"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88h-memwritelog.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || ng "コア成果物が無い。先に tools/setup_harness.sh を実行すること"

make -s -C "$FRONTEND_DIR"

mkdir -p "$WORK/rom"
python3 "$REPO/src/l1_ipl/make_ipl_rom.py" "$WORK/rom" --font-sample >"$WORK/gen.txt"

RANGE_LO=F3C8
RANGE_HI=F524   # F3C8 + 3行ぶん(120x3=360)の範囲を少し内側で切る
                # (範囲フィルタが端で正しく切れているかも一緒に確かめる)

# --- 期待列の独立計算 -----------------------------------------------------
# emit_font_sample の命令発行順（行ごとに: アトリビュート40バイト → 文字80
# バイト）をそのままなぞって (addr, value) の列を作る。アキュムレータの
# 状態遷移は vram_dump_selftest.sh と同じ理由（実測で確認済み、docstringの
# 「毎行0クリア」という主張ではなく実際の命令列の結果を再現する）。
python3 - "$WORK/expected.tsv" <<'PYEOF'
import sys
COLS, STRIDE, ATTR_BYTES, ROWS = 80, 120, 40, 3
CODE_FIRST, CODE_COUNT, PAD = 0x20, 0x100 - 0x20, 0x20
BASE = 0xF3C8
LO, HI = 0xF3C8, 0xF524

a_reg = 0
idx = 0
out = []
for r in range(ROWS):
    row_base = BASE + r * STRIDE
    for i in range(ATTR_BYTES):
        addr = row_base + COLS + i
        if LO <= addr <= HI:
            out.append((addr, a_reg))
    for c in range(COLS):
        code = (CODE_FIRST + idx) if idx < CODE_COUNT else PAD
        a_reg = code
        addr = row_base + c
        if LO <= addr <= HI:
            out.append((addr, a_reg))
        idx += 1

with open(sys.argv[1], "w") as f:
    for addr, value in out:
        f.write("%04X\t%02X\n" % (addr, value))
PYEOF
EXPECTED_N="$(wc -l < "$WORK/expected.tsv" | tr -d ' ')"
[ "$EXPECTED_N" -gt 0 ] || ng "期待列の生成が空"
ok "期待列(番地・値・発生順)を生成器の命令発行順から独立に計算 (${EXPECTED_N}件)"

# --- 陽性: 記録され、件数・順序・番地・値が期待列と一致 -------------------
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 60 \
  --mem-write-log "$WORK/mwl.txt" --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  --out "$WORK/trace.txt" \
  >"$WORK/positive.stdout" 2>"$WORK/positive.stderr" \
  || ng "陽性対照の実行が失敗した"

[ -f "$WORK/mwl.txt" ] || ng "--mem-write-log の出力ファイルが作られていない"
grep -q "^range     : ${RANGE_LO}-${RANGE_HI}\$" "$WORK/mwl.txt" || ng "見出しに範囲が正しく出ていない"
grep -q '取りこぼし: 0件' "$WORK/mwl.txt" || ng "取りこぼしが0件でない"

# データ行だけ取り出して (addr, value) を actual.tsv にする
awk '/^[[:space:]]*[0-9]+[[:space:]]/{print $4"\t"$5}' "$WORK/mwl.txt" > "$WORK/actual.tsv"
ACTUAL_N="$(wc -l < "$WORK/actual.tsv" | tr -d ' ')"
[ "$ACTUAL_N" = "$EXPECTED_N" ] || ng "記録件数が期待と不一致 (actual=$ACTUAL_N expected=$EXPECTED_N)"
cmp -s "$WORK/actual.tsv" "$WORK/expected.tsv" \
  || ng "記録された(番地,値)の列が期待列と順序どおりに一致しない"
ok "件数・順序・番地・値が期待列と一致 (${ACTUAL_N}件)"

# seq が 1..N の連番であることも確認
awk -v n="$EXPECTED_N" '
  /^[[:space:]]*[0-9]+[[:space:]]/ { c++; if ($1 != c) bad=1 }
  END { exit !(c==n && !bad) }
' "$WORK/mwl.txt" || ng "seqが1始まりの連番になっていない"
ok "seqが1始まりの連番"

# 発行元PCが単調非減少であることを確認（直線コード・分岐なしなので
# 途中で番地が戻ることは無いはず——命令先頭番地の取り方が正しいことの
# 構造的な裏付け）。macOSのawk(BWK awk)にはstrtonumが無いのでpython3で判定する。
awk '/^[[:space:]]*[0-9]+[[:space:]]/{print $3}' "$WORK/mwl.txt" > "$WORK/pcs.txt"
python3 -c '
import sys
prev = -1
for line in open(sys.argv[1]):
    pc = int(line.strip(), 16)
    if pc < prev:
        sys.exit(1)
    prev = pc
sys.exit(0)
' "$WORK/pcs.txt" || ng "発行元PCが単調非減少でない(直線コードのはずなのに番地が戻った)"
ok "発行元PCが単調非減少（分岐の無い直線コードとして辻褄が合う）"

# PC がすべて異なる命令を指している(349件349通り)ことも確認——LDIRのような
# 反復1命令が複数バイトを書く場合はここで同じPCが繰り返し現れるはずだが、
# font_sampleは1バイトずつ別のLD (nn),Aなので全件別PCになるはず。
UNIQ_PC="$(awk '/^[[:space:]]*[0-9]+[[:space:]]/{print $3}' "$WORK/mwl.txt" | sort -u | wc -l | tr -d ' ')"
[ "$UNIQ_PC" = "$EXPECTED_N" ] || ng "PCの相異なる数(${UNIQ_PC})が件数(${EXPECTED_N})と一致しない"
ok "全${EXPECTED_N}件が相異なるPC(1バイトごとに別命令)"

# --- 陽性: --mem-write-from-frame で開始を遅らせても範囲・値は変わらない ---
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 60 \
  --mem-write-log "$WORK/mwl_late.txt" --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  --mem-write-from-frame 0 \
  >/dev/null 2>"$WORK/late.stderr" \
  || ng "from-frame指定の実行が失敗した"
grep -q '^from-frame: 0$' "$WORK/mwl_late.txt" || ng "from-frameが見出しに出ていない"
ok "--mem-write-from-frame が見出しに反映される"

# --- --mem-write-range 必須の確認 -----------------------------------------
set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 5 \
  --mem-write-log "$WORK/norange.txt" >/dev/null 2>"$WORK/norange.stderr"
norange_rc=$?
set -e
[ "$norange_rc" -eq 2 ] || ng "--mem-write-range無しを弾けない(rc=${norange_rc})"
grep -q -- '--mem-write-log には --mem-write-range が要る' "$WORK/norange.stderr" \
  || ng "分類メッセージが無い"
ok "--mem-write-log 単独指定(--mem-write-range無し)はエラーになる"

# --- 出力先の安全策: リポジトリ内(tmp/以外)は拒否 / tmp/配下は許可 --------
set +e
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 5 \
  --mem-write-log "$REPO/measurements/should_not_write.txt" \
  --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  >/dev/null 2>"$WORK/unsafe.stderr"
unsafe_rc=$?
set -e
[ "$unsafe_rc" -ne 0 ] || ng "リポジトリ内(tmp/以外)への出力を拒否できない"
[ ! -e "$REPO/measurements/should_not_write.txt" ] || {
  rm -f "$REPO/measurements/should_not_write.txt"
  ng "拒否されたはずなのにファイルが作られていた"
}
ok "リポジトリ内(tmp/以外)への出力先を拒否"

mkdir -p "$REPO/tmp"
"$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" --frames 5 \
  --mem-write-log "$REPO/tmp/mwl_selftest_probe.txt" \
  --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  >/dev/null 2>"$WORK/tmpok.stderr" \
  || { cat "$WORK/tmpok.stderr" >&2; ng "tmp/配下への出力が拒否された(許可されるべき)"; }
[ -f "$REPO/tmp/mwl_selftest_probe.txt" ] || ng "tmp/配下へ書けていない"
rm -f "$REPO/tmp/mwl_selftest_probe.txt"
ok "リポジトリ内の tmp/ 配下への出力は許可"

# --- 故障注入: 取りこぼし数を増やさずに1件を黙って落とす -------------------
Q88MEASURE_FAULT_DROP_MEMLOG_EVENT=1 "$FRONTEND" --core "$CORE" --rom-dir "$WORK/rom" \
  --frames 60 --mem-write-log "$WORK/dropped.txt" \
  --mem-write-range "${RANGE_LO}-${RANGE_HI}" \
  >/dev/null 2>"$WORK/dropped.stderr" \
  || ng "故障注入版の実行が失敗した"
grep -q '取りこぼし: 0件' "$WORK/dropped.txt" \
  || ng "前提が崩れている(故障注入で取りこぼし数自体が増えてしまった)"
DROPPED_N="$(awk '/^[[:space:]]*[0-9]+[[:space:]]/{c++} END{print c+0}' "$WORK/dropped.txt")"
if [ "$DROPPED_N" = "$EXPECTED_N" ]; then
  ng "故障注入(1件の黙落とし)後も件数が期待値と一致してしまい、取りこぼし数だけを見る検査では検出できないことを確認できなかった"
fi
ok "故障注入(取りこぼし数を増やさない黙落とし)により件数比較がNGになることを確認(取りこぼし表示は0件のまま・実際の件数は${DROPPED_N}件で期待${EXPECTED_N}件と不一致)"

# --- 容量: バッファ容量を変えても容量内の記録内容が変わらないこと ----------
cat > "$WORK/probe.c" <<'EOF'
#include <stdio.h>
#include "q88h_memlog.h"

int main(void)
{
    unsigned i;
    q88h_memlog_t *m;
    retro_q88h_memlog_reset();
    retro_q88h_memlog_set_range(0x1000, 0x2000);
    retro_q88h_memlog_set_enabled(1);
    m = retro_q88h_memlog();
    for (i = 0; i < 6; i++) {
        retro_q88h_memlog_set_frame(900 + i);
        q88h_memlog_record(m, (uint16_t)(0x1000 + i), (uint8_t)(0x10 + i),
                            (uint16_t)(0x8000 + i));
    }
    printf("events=%u dropped=%u\n", m->n_events, m->n_dropped);
    for (i = 0; i < m->n_events; i++)
        printf("%u %u %u %u %u\n", m->ev[i].seq, m->ev[i].frame,
               m->ev[i].pc, m->ev[i].addr, m->ev[i].value);
    return 0;
}
EOF

for capacity in 6 12; do
  cc -std=c99 -Wall -Wextra -Werror -DQ88H_MEMLOG_MAX_EVENTS="$capacity" \
    -I"$CORE_DIR" "$WORK/probe.c" "$CORE_DIR/q88h_memlog.c" \
    -o "$WORK/probe-$capacity"
  "$WORK/probe-$capacity" > "$WORK/probeout-$capacity"
done
cmp -s "$WORK/probeout-6" "$WORK/probeout-12" \
  || ng "容量を変えても容量内6イベントの記録内容が不変であるはずなのに変化した"
ok "容量(Q88H_MEMLOG_MAX_EVENTS)を変えても容量内イベントの記録内容は不変"

# 容量を超えた分は取りこぼし数として正しく数えられ、上書きしないこと
cat > "$WORK/probe_over.c" <<'EOF'
#include <stdio.h>
#include "q88h_memlog.h"

int main(void)
{
    unsigned i;
    q88h_memlog_t *m;
    retro_q88h_memlog_reset();
    retro_q88h_memlog_set_range(0x1000, 0x2000);
    retro_q88h_memlog_set_enabled(1);
    m = retro_q88h_memlog();
    for (i = 0; i < 10; i++)
        q88h_memlog_record(m, (uint16_t)(0x1000 + i), (uint8_t)i, (uint16_t)(0x8000 + i));
    printf("events=%u dropped=%u first_addr=%04X last_addr=%04X\n",
           m->n_events, m->n_dropped, m->ev[0].addr, m->ev[m->n_events - 1].addr);
    return 0;
}
EOF
cc -std=c99 -Wall -Wextra -Werror -DQ88H_MEMLOG_MAX_EVENTS=4 \
  -I"$CORE_DIR" "$WORK/probe_over.c" "$CORE_DIR/q88h_memlog.c" -o "$WORK/probe_over"
OVER_OUT="$("$WORK/probe_over")"
echo "$OVER_OUT" | grep -q '^events=4 dropped=6 first_addr=1000 last_addr=1003$' \
  || ng "容量超過時の件数・取りこぼし数・先頭/末尾番地が期待どおりでない: $OVER_OUT"
ok "容量超過分は取りこぼし数として数え、既存イベントを上書きしない(先頭を保持)"

ok "全項目合格"

#!/usr/bin/env bash
# m6f-e 器具A（行別画面署名・比較器）の自己検査。
# 合成画面だけを使い、本文はプロセス内で署名化してreportへ書かない。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPARE="$REPO/tools/compare_screen_signatures.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88-screen-signature.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

# 値そのものは成功・失敗メッセージへ出さない。
CANARY="ZQSCREENLEAK7F3D1A9E"

# C側のSHA-256・画面正規化・複数snapshot report書出しを、コアやvendorに
# 依存しない小さな翻訳単位として実行する。合成本文は標準出力へ出さない。
${CC:-cc} -std=c99 -Wall -Wextra -Werror \
  -I"$REPO/tools/harness/frontend" -x c -o "$WORK/c_writer" - <<'CEOF'
#include <stdio.h>
#include <string.h>
#include "screen_signature.h"

static void put(unsigned char *screen, unsigned row, unsigned col, const char *text)
{
    size_t i;
    for (i = 0; text[i] && col + i < Q88_SCREEN_SIGNATURE_COLS; i++)
        screen[row * Q88_SCREEN_SIGNATURE_COLS + col + i] = (unsigned char)text[i];
}

int main(int argc, char **argv)
{
    unsigned char screen[Q88_SCREEN_SIGNATURE_ROWS * Q88_SCREEN_SIGNATURE_COLS];
    q88_screen_signature_t result[2];
    unsigned i;
    FILE *fp;
    if (argc != 2) return 2;
    memset(screen, ' ', sizeof(screen));
    memset(result, 0, sizeof(result));
    strcpy(result[0].snapshot_id, "snap0");
    strcpy(result[1].snapshot_id, "snap1");
    put(screen, 2, 0, "ZQSCREENLEAK7F3D1A9E");
    put(screen, 7, 3, "SYNTHETIC");
    for (i = 0; i < Q88_SCREEN_SIGNATURE_COLS; i++)
        screen[12 * Q88_SCREEN_SIGNATURE_COLS + i] = 'L';
    q88_screen_signature_capture(&result[0], screen);
    put(screen, 7, 12, "X");
    q88_screen_signature_capture(&result[1], screen);
    fp = fopen(argv[1], "w");
    if (!fp) return 2;
    if (!q88_screen_signature_write_report(fp, result, 2)) return 2;
    return fclose(fp) == 0 ? 0 : 2;
}
CEOF
"$WORK/c_writer" "$WORK/c_report.tsv" >"$WORK/c_writer.out" 2>"$WORK/c_writer.err"

# 既存 check_l3_screen_output.py の signature() を直接呼び、本文をファイルへ
# 一度も書かずに同じ合成画面の期待署名を作る。C reportとの一致が、既存の
# 本文ありreportから得る署名との互換性を保証する。
python3 - "$REPO" "$WORK/legacy_expected.tsv" "$CANARY" <<'PYEOF'
import importlib.util
import pathlib
import sys

repo, output, canary = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
spec = importlib.util.spec_from_file_location("legacy", repo / "tools/check_l3_screen_output.py")
legacy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = legacy
spec.loader.exec_module(legacy)
rows = [(2, canary), (7, "   SYNTHETIC"), (12, "L" * 80)]
whole = legacy.signature(rows)
with output.open("w", encoding="utf-8", newline="") as target:
    target.write("snapshot_id\tsnap0\nphysical_row\tchar_count\tsha256\n")
    for row, body in rows:
        one = legacy.signature([(row, body)])
        target.write(f"{row}\t{len(body)}\t{one.sha256}\n")
    target.write(f"line_count\t{whole.line_count}\nchar_count\t{whole.char_count}\nsha256\t{whole.sha256}\n")
PYEOF

if python3 "$COMPARE" --actual "$WORK/c_report.tsv" \
    --expected "$WORK/legacy_expected.tsv" --snapshot-id snap0 \
    >"$WORK/compat.out" 2>"$WORK/compat.err"; then
  ok "C署名器は既存check_l3_screen_output.pyの正準形と一致"
else
  ng "C署名器と既存画面署名の互換性が無い"
fi

# 比較器用reportをすべて本文から直接署名化する。本文そのものは出力しない。
python3 - "$WORK" "$CANARY" <<'PYEOF'
import hashlib
import pathlib
import sys

work, canary = pathlib.Path(sys.argv[1]), sys.argv[2]

def write(name, rows, *, corrupt_summary=False):
    path = work / f"{name}.tsv"
    canonical = b""
    encoded_rows = []
    for row, body in rows:
        encoded = f"{row}\t{body}\n".encode("utf-8")
        canonical += encoded
        encoded_rows.append((row, len(body), hashlib.sha256(encoded).hexdigest()))
    whole = hashlib.sha256(canonical).hexdigest()
    if corrupt_summary:
        whole = ("0" if whole[0] != "0" else "1") + whole[1:]
    with path.open("w", encoding="utf-8", newline="") as target:
        target.write("snapshot_id\tcase\nphysical_row\tchar_count\tsha256\n")
        for row, chars, digest in encoded_rows:
            target.write(f"{row}\t{chars}\t{digest}\n")
        target.write(f"line_count\t{len(rows)}\nchar_count\t{sum(len(body) for _, body in rows)}\nsha256\t{whole}\n")

base = [(1, canary + " A"), (5, "tail  "), (9, "third")]
write("base", base)
write("same", list(base))
write("replace", [(1, canary + " B"), base[1], base[2]])
write("space_more", [base[0], (5, "tail   "), base[2]])
write("space_less", [base[0], (5, "tail "), base[2]])
write("swap", [(1, base[1][1]), (5, base[0][1]), base[2]])
write("row_shift", [(2, base[0][1]), base[1], base[2]])
write("summary_sha", base, corrupt_summary=True)
PYEOF

judge() {
  local name="$1" expected_rc="$2" rc
  set +e
  python3 "$COMPARE" --actual "$WORK/$name.tsv" --expected "$WORK/base.tsv" \
    --snapshot-id case >"$WORK/$name.out" 2>"$WORK/$name.err"
  rc=$?
  set -e
  [ "$rc" -eq "$expected_rc" ] || ng "$name の比較終了コードが期待と異なる"
}

judge same 0
ok "正例を一致として受理"
judge replace 1
ok "1文字置換を不一致として検出"
judge space_more 1
judge space_less 1
ok "末尾空白の増減を不一致として検出"
judge swap 1
ok "行入替を不一致として検出"
judge row_shift 1
ok "物理行番号ずれを不一致として検出"
judge summary_sha 1
ok "画面全体SHA-256だけの破損も不一致として検出"

# 判定JSONは4フィールドの許可リストだけで、値も所定どおりでなければならない。
python3 - "$WORK" <<'PYEOF'
import json
import pathlib
import sys
work = pathlib.Path(sys.argv[1])
allowed = {"match", "mismatch_line_count", "first_mismatch_physical_row", "char_count_difference"}
expected = {
    "same": (True, 0, None, False),
    "replace": (False, 1, 1, False),
    "space_more": (False, 1, 5, True),
    "space_less": (False, 1, 5, True),
    "swap": (False, 2, 1, True),
    "row_shift": (False, 2, 1, False),
    "summary_sha": (False, 0, None, False),
}
for name, wanted in expected.items():
    with (work / f"{name}.out").open(encoding="utf-8") as source:
        value = json.load(source)
    if set(value) != allowed:
        raise SystemExit(1)
    actual = (value["match"], value["mismatch_line_count"],
              value["first_mismatch_physical_row"], value["char_count_difference"])
    if actual != wanted:
        raise SystemExit(1)
PYEOF
ok "判定出力は許可リスト4フィールドのみで、差分集計も所定どおり"

# 例外経路へ入力値を反射しないことも確認する。
printf 'snapshot_id\tcase\nphysical_row\tchar_count\tsha256\tbody\n' \
  >"$WORK/malformed.tsv"
printf '1\t1\t%064d\t%s\n' 0 "$CANARY" >>"$WORK/malformed.tsv"
set +e
python3 "$COMPARE" --actual "$WORK/malformed.tsv" --expected "$WORK/base.tsv" \
  --snapshot-id case >"$WORK/malformed.out" 2>"$WORK/malformed.err"
malformed_rc=$?
set -e
[ "$malformed_rc" -eq 2 ] || ng "不正入力が入力エラーにならない"

# stdout/stderr、正常な署名report、期待report、判定JSON、例外出力を監査する。
if grep -qF "$CANARY" \
    "$WORK/c_writer.out" "$WORK/c_writer.err" "$WORK/c_report.tsv" \
    "$WORK/legacy_expected.tsv" "$WORK/compat.out" "$WORK/compat.err" \
    "$WORK/base.tsv" "$WORK/same.tsv" "$WORK/replace.tsv" \
    "$WORK/space_more.tsv" "$WORK/space_less.tsv" "$WORK/swap.tsv" \
    "$WORK/row_shift.tsv" "$WORK/summary_sha.tsv" \
    "$WORK"/*.out "$WORK"/*.err; then
  ng "合成画面の漏えい目印が出力へ現れた"
fi
ok "漏えい目印はstdout/stderr/report/期待値/判定/例外経路のいずれにも無い"

# 陰性対照: 本文列を持つ壊れたreportなら、同じ漏えい監査が必ず検出する。
cp "$WORK/malformed.tsv" "$WORK/broken_report.tsv"
if grep -qF "$CANARY" "$WORK/broken_report.tsv"; then
  ok "陰性対照: 本文を出す壊れたreportを漏えい監査が検出"
else
  ng "陰性対照: 壊れたreportの本文漏えいを検出できない"
fi

ok "全項目合格"

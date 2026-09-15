#!/usr/bin/env python3
"""l4-c2-error-signature-diagnosis 用の候補生成・照合器具。

docs/spec/l4-basic.md 6.1節「エラーメッセージの番号と文言」の51件について、
tools/l4_vram_probe.py の row_signature と**同じ正規化**
(normalize_row_for_signature: 文字域80バイトのうち末尾の空白(0x20)だけを
rstripし、先頭は保持したうえでSHA-256)で候補のSHA-256を作り、公式ROMの
row_sha256(値そのものではなく、この道具の呼び出し元が別途測定して渡す
16進文字列)と一致するかどうかだけを返す。

文言は自分で作った候補(マニュアルの資料の記載)であり、公式ROMの画面文言
そのものではないため、候補の文言と番号を標準出力へ出すこと自体は禁止事項7
に触れない(事前登録・タスク指示どおり)。公式側の値はこの道具の引数として
16進文字列(署名)だけを受け取り、他の形では一切扱わない。
"""
import argparse
import hashlib
import sys

# docs/spec/l4-basic.md 6.1節の表をそのまま転記(番号, 文言)。
MESSAGES = [
    (1, "NEXT without FOR"),
    (2, "Syntax error"),
    (3, "RETURN without GOSUB"),
    (4, "Out of DATA"),
    (5, "Illegal function call"),
    (6, "Overflow"),
    (7, "Out of memory"),
    (8, "Undefined line number"),
    (9, "Subscript out of range"),
    (10, "Duplicate Definition"),
    (11, "Division by zero"),
    (12, "Illegal direct"),
    (13, "Type mismatch"),
    (14, "Out of string space"),
    (15, "String too long"),
    (16, "String formula too complex"),
    (17, "Can't continue"),
    (18, "Undefined user function"),
    (19, "No RESUME"),
    (20, "RESUME without error"),
    (21, "Unprintable error"),
    (22, "Missing operand"),
    (23, "Line buffer overflow"),
    (26, "FOR without NEXT"),
    (27, "Tape read ERROR"),
    (29, "WHILE without WEND"),
    (30, "WEND without WHILE"),
    (31, "Duplicate label"),
    (32, "Undefined label"),
    (33, "Feature not available"),
    (50, "FIELD overflow"),
    (51, "Internal error"),
    (52, "Bad file number"),
    (53, "File not found"),
    (54, "File already open"),
    (55, "Input past end"),
    (56, "Bad file name"),
    (57, "Direct statement in file"),
    (58, "Sequential after PUT"),
    (59, "Sequential I/O only"),
    (60, "File not OPEN"),
    (61, "File write protected"),
    (62, "Disk offline"),
    (64, "Disk I/O error"),
    (65, "File already exists"),
    (68, "Disk full"),
    (69, "Bad allocation table"),
    (70, "Bad drive number"),
    (71, "Bad track/sector"),
    (72, "Deleted record"),
    (73, "Rename across disks"),
]

ROW_BYTES = 80


def normalize_row_for_signature(row: bytes) -> bytes:
    """tools/l4_vram_probe.py の同名関数と同一の処理(末尾の空白(0x20)を
    rstrip、先頭は保持)。二重実装を避けるため、値ではなく処理だけを
    ここに複写し、呼び出し元コミットのdiffで両者を目視突き合わせできる
    ようにする(インポートで済ませない理由は下記run_selftestを参照)。"""
    return row.rstrip(b"\x20")


def build_row(text: str) -> bytes:
    b = text.encode("ascii")
    if len(b) > ROW_BYTES:
        raise ValueError(f"候補文言が{ROW_BYTES}バイトを超える: {text!r}")
    return b + b" " * (ROW_BYTES - len(b))


def make_variants(text: str) -> "list[tuple[str, str]]":
    """1つの文言から作る表記ゆれ候補。(variant_label, variant_text)の並び。
    候補はすべて0桁目から文言そのものが書かれ、残りが空白の80バイト行。"""
    variants = []
    variants.append(("plain", text))
    variants.append(("qmark", "?" + text))
    upper = text.upper()
    if upper != text:
        variants.append(("plain_upper", upper))
        variants.append(("qmark_upper", "?" + upper))
    return variants


def sha_for_text(text: str) -> str:
    row = build_row(text)
    normalized = normalize_row_for_signature(row)
    return hashlib.sha256(normalized).hexdigest()


def nonblank_count_of(text: str) -> int:
    return sum(1 for ch in text if ch != " ")


def run_selftest() -> bool:
    """normalize_row_for_signatureがl4_vram_probe.pyの実装と同一処理か
    どうかを、既知の入出力(自分で決めた無害な文字列)で照合する自己検査。
    公式ROM・候補文言のどちらも使わない。"""
    sys.path.insert(0, "tools")
    import l4_vram_probe as probe  # noqa: E402

    ok = True
    tests = [b"abc" + b" " * 77, b" x" + b" " * 78, b" " * 80]
    for t in tests:
        a = probe.normalize_row_for_signature(t)
        b = normalize_row_for_signature(t)
        if a != b:
            print(f"[selftest] 不一致: input={t!r} probe={a!r} local={b!r}", file=sys.stderr)
            ok = False
    if ok:
        print("[selftest] OK: normalize_row_for_signatureはl4_vram_probe.pyと同一処理", file=sys.stderr)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--official-sha256", action="append", default=[],
                     metavar="LABEL=HEX",
                     help="公式ROM側のrow_sha256(別途l4_vram_probe.py --row-signatureで"
                          "測定した16進文字列)。LABEL=HEX の形。複数可")
    ap.add_argument("--selftest", action="store_true",
                     help="正規化処理がl4_vram_probe.pyと同一かどうかだけを確認して終了")
    args = ap.parse_args()

    if args.selftest:
        return 0 if run_selftest() else 1

    if not run_selftest():
        print("エラー: 正規化の自己検査に失敗した。照合を中止する", file=sys.stderr)
        return 1

    officials = {}
    for kv in args.official_sha256:
        if "=" not in kv:
            print(f"エラー: --official-sha256 は LABEL=HEX 形式: {kv}", file=sys.stderr)
            return 2
        label, hexval = kv.split("=", 1)
        officials[label] = hexval.strip().lower()

    # 候補を全部作る
    candidates = []  # (label_text, number, variant_label, sha256, nonblank)
    for num, msg in MESSAGES:
        for variant_label, text in make_variants(msg):
            sha = sha_for_text(text)
            candidates.append((num, msg, variant_label, text, sha, nonblank_count_of(text)))

    print(f"候補文言 {len(MESSAGES)} 件、表記ゆれ込みで {len(candidates)} 件を生成した")

    for label, official_hex in officials.items():
        official_hex = official_hex.lower()
        matches = [c for c in candidates if c[4] == official_hex]
        print(f"\n[{label}] 公式row_sha256={official_hex}")
        if matches:
            for num, msg, variant_label, text, sha, nb in matches:
                print(f"  一致: 番号{num} 文言=\"{text}\" (variant={variant_label}) nonblank={nb}")
        else:
            print("  一致する候補は無かった（一覧の文言だけの行ではない可能性）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

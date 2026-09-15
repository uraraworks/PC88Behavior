#!/usr/bin/env python3
"""
l4_extract_keywords.py — リファレンスマニュアルの目次から命令語を機械抽出する

docs/notes/l4-token-design.md の追記（2026-09-15）が前提とする「マニュアル索引の
全語」を作るためのスクリプト。tools/basic_surface.tsv は M3 の測定条件表であり、
COLORAT・GETAT のような造語や GET@/PUT@ の2語1行まとめを含むため、そのまま
トークン番号の元にはできない（詳細は docs/notes/l4-keywords-extraction.md）。

出典は N88-BASIC リファレンスマニュアルの「第2章 基本命令」「第3章 拡張命令」の
目次（本文中で「vii〜xviiページの機能別索引とは別に、章の先頭に置かれた単純な
アルファベット順の目次」。1.13節が言う基本命令・拡張命令の分類そのもの）。
機能別索引（vii〜xviii、コマンド/ステートメント/関数などにさらに細分）は
OCRノイズと解説文が同じ行に混在していて機械抽出が著しく不安定なため採らない。

入力はマニュアルのテキスト（OCR済み）で、パスは環境変数 PC88_REF_MANUAL_TXT から
受け取る（リポジトリにパスを焼き込まない。CLAUDE.md「パスの扱い」）。
実体は本リポジトリの外 refs/manual.txt。

出力は TSV（語・分類・頁）を標準出力へ。分類は "基本命令"（第2章目次）
または "拡張命令"（第3章目次）で、マニュアル自身の章立てそのもの。
命令語の名前と頁だけを出し、説明の文は一切読み取らない
（目次は元々「語＋リーダー（点線）＋頁番号」だけの行なので、説明文は含まれない）。

使い方:
  PC88_REF_MANUAL_TXT=/path/to/manual.txt tools/l4_extract_keywords.py > src/l4_basic/keywords.tsv
"""

import hashlib
import os
import re
import sys

# ---------------------------------------------------------------------------
# 章の境界を探す（OCRは文字間にランダムな空白を挟むことがあるので、
# マーカー文字列は「1文字ずつの間に \s* を許す」正規表現にして探す）
# ---------------------------------------------------------------------------


def spaced(literal: str) -> str:
    return r"\s*".join(re.escape(c) for c in literal)


CHAP2_MARK = "第2章基本命令"
CHAP3_MARK = "第3章拡張命令"
APPENDIX_MARK = "資料1"

# 目次1行 = 「語 + リーダー(・や.の連続) + 頁番号(N-NNN)」。
# 頁番号を先に全部見つけて、前の頁番号の直後から次の頁番号の手前までを
# 「語」の生テキストとして切り出す（語の文字集合を先に決め打ちすると、
# OCRが規則からこぼす記号(?など)で行がずれて後続行を巻き込むため、
# 頁番号という一番安定した目印から逆算する）。
PAGE_RE = re.compile(r"(\d(?:\s?\d){0,2})\s*-\s*(\d(?:\s?\d){0,2})")

# 目次の行間リーダー（点線）に使われる記号。OCRにより全角・半角・中黒・
# 中点・ビュレットが入り混じる。
LEADER_CHARS = r"\s・.•‥…·．，、"
STRIP_TRAIL_RE = re.compile(r"[" + LEADER_CHARS + r"]+$")

# 日本語文字（ひらがな・カタカナ・漢字）。全角の句読点・記号(．，など)は
# 含めない — Unicode の「全角形」ブロックには全角ピリオド(U+FF0E)も
# 入っており、これをCJK扱いにすると目次内の点線リーダーまで
# 「日本語の混入」と誤判定してしまう（実際に踏んだ不具合。
# docs/notes/l4-keywords-extraction.md 参照）。
CJK_RE = re.compile(r"[぀-ヿ一-鿿]")

# ページ境界のノンブル（ローマ数字 ii, iii, iv, vii など）がOCRで
# 数字や単独のアルファベットに化け、直前・直後の語に融合することがある。
# 一般規則での自動判別が難しかった既知の数箇所だけ、抽出後に個別補正する。
# キーは (抽出直後の語, 抽出直後の頁) so マニュアルの版が変わって
# この行の周辺が変わったら (self-test で) 気づけるようにしてある。
KNOWN_OCR_FIXUPS = {
    # "CHAI N ... 2- 15" の直後にノンブル "ii"(→"11") がOCRで隣接し、
    # 頁番号の続きとして誤って飲み込まれた（正しくは 2-15）。
    ("CHAIN", "2-151"): ("CHAIN", "2-15"),
    # ノンブル "iii"(→"III")がLINEの直前に融合した。
    ("IIILINE", "2-124"): ("LINE", "2-124"),
    # ノンブル "iv"(→"1v") がSETの直前に融合した。
    ("VSET", "2-213"): ("SET", "2-213"),
    # ノンブル "-v" がCMDSTOPMの直前に融合した。
    ("-VCMDSTOPM", "3-40"): ("CMDSTOPM", "3-40"),
    # 索引の印字が「SQR」を「SOR」と誤OCRしている（Qの誤認）。
    # tools/basic_surface.tsv の SQR 行に付けた注記と同じ既知差異。
    ("SOR", "2-218"): ("SQR", "2-218"),
}



# OCRテキストにはPDF内の飾り記号や制御文字（例: \x7f）が混じることがある。
# 語として意味を持ちうる文字集合（英数字・記号・空白・リーダー・CJK判定用の
# 範囲）以外は、判定前に無条件で捨てる。
ALLOWED_CHAR_RE = re.compile(
    r"[A-Za-z0-9$@()./=#?\-" + LEADER_CHARS + r"぀-ヿ一-鿿]"
)


def sanitize(raw: str) -> str:
    return "".join(ch for ch in raw if ALLOWED_CHAR_RE.match(ch))


def clean_name(raw: str) -> str:
    raw = sanitize(raw)
    name = STRIP_TRAIL_RE.sub("", raw)
    name = re.sub(r"\s+", "", name)
    # 日本語（バナーや見出しの混入）が残っていたら、最後に出てくる
    # 日本語文字より後ろだけを語として採る。
    cjk_hits = [m.end() for m in CJK_RE.finditer(name)]
    if cjk_hits:
        name = name[cjk_hits[-1]:]
    # OCRの l(小文字エル) と 1(数字) の混同。マニュアルの命令語は
    # 記号(@ $ ( ) / . = #)を除きすべて大文字なので、小文字が残るのは
    # 常にOCRノイズと判断してよい。
    name = name.replace("l", "1")
    # 語頭に数字が残っていたら、それはノンブルの残骸（命令語が数字で
    # 始まることはない）なので削る。
    name = re.sub(r"^[0-9]+", "", name)
    return name.upper()


def extract_toc(text: str) -> list[tuple[str, str]]:
    pages = list(PAGE_RE.finditer(text))
    out = []
    prev_end = 0
    for m in pages:
        seg = text[prev_end:m.start()]
        name = clean_name(seg)
        page = re.sub(r"\s+", "", m.group(1)) + "-" + re.sub(r"\s+", "", m.group(2))
        if name:
            key = (name, page)
            fixed = KNOWN_OCR_FIXUPS.get(key)
            if fixed:
                name, page = fixed
            out.append((name, page))
        prev_end = m.end()
    return out


def strip_page_markers(text: str) -> str:
    text = re.sub(r"=====\s*page_\d+\s*=====", " ", text)
    text = re.sub(r"\bPage\s*\d+\b", " ", text)
    return text


def main() -> int:
    manual_path = os.environ.get("PC88_REF_MANUAL_TXT")
    if not manual_path:
        print(
            "PC88_REF_MANUAL_TXT が未設定です。マニュアルのOCRテキストへの"
            "絶対パスを環境変数で渡してください（例: refs/manual.txt）。",
            file=sys.stderr,
        )
        return 2
    if not os.path.isfile(manual_path):
        print(f"ファイルが見つかりません: {manual_path}", file=sys.stderr)
        return 2

    with open(manual_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def find_all(mark):
        return [m.start() for m in re.finditer(spaced(mark), text)]

    chap2_marks = find_all(CHAP2_MARK)
    chap3_marks = find_all(CHAP3_MARK)
    appendix_marks = find_all(APPENDIX_MARK)
    if len(chap2_marks) < 2 or len(chap3_marks) < 2 or not appendix_marks:
        print(
            "章境界のマーカーが期待どおりに見つかりませんでした"
            f"（第2章:{len(chap2_marks)}件, 第3章:{len(chap3_marks)}件,"
            f" 資料1:{len(appendix_marks)}件）。"
            "マニュアルOCRの版が変わった可能性があります。",
            file=sys.stderr,
        )
        return 3

    # 1つめの出現はまえがき等での言及、2つめが実際の目次見出し。
    chap2_start = chap2_marks[1]
    chap2_hdr_end = re.match(spaced(CHAP2_MARK), text[chap2_start:]).end()
    chap3_start = chap3_marks[1]
    chap3_hdr_end = re.match(spaced(CHAP3_MARK), text[chap3_start:]).end()
    appendix_start = appendix_marks[0]

    chap2_text = strip_page_markers(text[chap2_start + chap2_hdr_end: chap3_start])
    chap3_text = strip_page_markers(text[chap3_start + chap3_hdr_end: appendix_start])

    basic_entries = extract_toc(chap2_text)
    ext_entries = extract_toc(chap3_text)

    print("# N88-BASIC 命令語一覧（マニュアル目次からの機械抽出）")
    print("# 出典: 環境変数 PC88_REF_MANUAL_TXT が指すマニュアルOCRテキスト")
    print("#       （実体は refs/manual.txt。パスは焼き込まない。CLAUDE.md「パスの扱い」）")
    print(f"# 出典sha256: {digest}")
    print("# 生成: tools/l4_extract_keywords.py")
    print("# 列: word<TAB>category<TAB>pages")
    print("# category: 基本命令(第2章目次) / 拡張命令(第3章目次)")
    print(
        "# 同名の語が複数頁に出る場合（MID$/VIEW/WINDOW。関数形と文形の"
        "両方が索引にあるため）は1行に統合し、pagesを';'で連結する。"
    )

    def emit(entries, category):
        merged: dict[str, list[str]] = {}
        order: list[str] = []
        for name, page in entries:
            if name not in merged:
                merged[name] = []
                order.append(name)
            if page not in merged[name]:
                merged[name].append(page)
        for name in order:
            print(f"{name}\t{category}\t{';'.join(merged[name])}")

    emit(basic_entries, "基本命令")
    emit(ext_entries, "拡張命令")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

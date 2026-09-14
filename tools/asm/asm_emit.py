"""
asm_emit.py — 既存の Asm クラス（make_ipl_rom.py / make_subrom.py）が
発行した命令を、z80text.py が読める .asm テキストとして書き出すための
共通ヘルパ。

## 設計方針: バイト列を作る処理には一切触れない

`install_note_templates()` は各命令メソッド（`ld_a` や `jp` など）を
ラップし、**呼び出し前後の self.pc の差分（=そのメソッドが実際に書いた
バイト数）を測るだけ**で、命令の符号化ロジック自体は元のメソッドを
そのまま呼ぶ。したがって `--emit-asm` を付けない既定の実行では
バイト出力に一切影響しない。

テンプレートに登録していないメソッド、あるいはメソッドを介さず
`self.db(...)` を直接呼んでいる箇所（テーブルデータ等）は、
`db 0x.., 0x..` という素のバイト列として書き出す（M7 の依頼文書が
明示的に許容している経路）。これも byte-for-byte 同一に組み直せる。

## Asm クラス側に必要な最小限の変更

1. `__init__` に `self._emit_asm = []` と `self._note_suppress = 0` を追加。
2. `db()` の先頭で、抑止されていなければ生データとして 1 件記録する
   （このモジュールの `note_raw_db()` を呼ぶ）。
3. クラス定義の直後に、命令メソッド名→テキスト生成関数の辞書を作り
   `install_note_templates(Asm, TEMPLATES)` を呼ぶ。

いずれもバイト生成ロジックには触れない、純粋な追記。
"""


def hex8(v):
    return f"0x{v & 0xFF:02X}"


def hex16(v):
    return f"0x{v & 0xFFFF:04X}"


def note_raw_db(self, bs):
    """Asm.db() の先頭から呼ぶ。抑止中（=命令メソッドの内部から来た
    呼び出し、または data() 経由の呼び出し）でなければ、生バイト列
    として1件記録する。

    ここに記録が残るのは「名前の付いた命令メソッドを介さず、かつ
    data() でもない db() 直呼び」だけ——つまり素通りしている命令の
    直書きを意味する。asm_selftest.sh はこの件数が0であることを検査する。"""
    if not bs:
        return
    if getattr(self, "_emit_asm", None) is None:
        return
    if getattr(self, "_note_suppress", 0) != 0:
        return
    self._emit_asm.append(("raw", self.pc, len(bs), list(bs)))


def note_data(self, bs):
    """Asm.data() から呼ぶ。self.db(*bs) を「命令メソッドの内部」と
    同じ扱いで抑止しつつ実行し、"data"（テーブル／番地合わせの詰め物）
    として1件記録する。note_raw_db の「素の db 直書き」検出からは
    意図的に除外される——データであることを呼び出し側が明示した経路
    なので、命令の素通りではない。"""
    bs = tuple(bs)
    if getattr(self, "_emit_asm", None) is None:
        self.db(*bs)
        return
    start = self.pc
    self._note_suppress = getattr(self, "_note_suppress", 0) + 1
    try:
        self.db(*bs)
    finally:
        self._note_suppress -= 1
    if bs and self._note_suppress == 0:
        self._emit_asm.append(("data", start, len(bs), list(bs)))


def count_kinds(asm_obj):
    """asm_obj._emit_asm の内訳を {"instr": n, "data": n, "raw": n} で返す。
    asm_selftest.sh がROムごとの内訳表示と「生db 0件」検査に使う。"""
    counts = {"instr": 0, "data": 0, "raw": 0}
    for kind, _start, _length, _payload in asm_obj._emit_asm:
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def install_note_templates(cls, templates):
    """cls の各メソッドをラップし、呼び出しの前後で self.pc の差分を
    測って (開始pc, 長さ, テキスト) を self._emit_asm に積む。

    templates: {メソッド名: callable(*args, **kwargs) -> str}
    """
    for name, tmpl in templates.items():
        if not hasattr(cls, name):
            raise AttributeError(f"{cls.__name__} に {name} が無い（テンプレートの誤記）")
        orig = getattr(cls, name)

        def make_wrapper(orig=orig, tmpl=tmpl, name=name):
            def wrapper(self, *args, **kwargs):
                start = self.pc
                self._note_suppress = getattr(self, "_note_suppress", 0) + 1
                try:
                    result = orig(self, *args, **kwargs)
                finally:
                    self._note_suppress -= 1
                if (getattr(self, "_emit_asm", None) is not None
                        and self._note_suppress == 0):
                    text = tmpl(*args, **kwargs)
                    length = self.pc - start
                    if length > 0:
                        self._emit_asm.append(("instr", start, length, text))
                return result
            wrapper.__name__ = f"noted_{name}"
            return wrapper

        setattr(cls, name, make_wrapper())


def render_asm(asm_obj, header_comment=""):
    """asm_obj（Asm インスタンス。resolve() 済みでなくてよい）の
    `_emit_asm` と `labels` から .asm テキストを組み立てる。"""
    entries = sorted(asm_obj._emit_asm, key=lambda e: e[1])

    addr_labels = {}
    for name, addr in asm_obj.labels.items():
        addr_labels.setdefault(addr, []).append(name)

    lines = []
    if header_comment:
        for hl in header_comment.splitlines():
            lines.append(f"; {hl}" if hl.strip() else ";")
    lines.append(f"    org {hex16(asm_obj.org)}")

    pc = asm_obj.org
    for kind, start, length, payload in entries:
        for name in addr_labels.get(start, []):
            lines.append(f"{name}:")
        if kind == "instr":
            lines.append(f"    {payload}")
        else:
            hexed = ", ".join(hex8(b) for b in payload)
            lines.append(f"    db {hexed}")
        pc = start + length
    for name in addr_labels.get(pc, []):
        lines.append(f"{name}:")

    return "\n".join(lines) + "\n"

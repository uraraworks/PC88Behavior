; print_dispatch.asm — src/l4_basic/make_print_dispatch.py が生成
; 手で編集しない（再実行で再生成する）。
; 入力: src/l4_basic/tokens.tsv。PRINTの語形とトークン番号は
; word列から "PRINT" に完全一致する行を機械的に
; 探して取り出した（make_print_dispatch.py 参照）。
;
; 用途: 直接モードの行頭キーワード照合（interp.asm TRY_MATCH_PRINT）。
; '?'の代替表記は l4-token-design.md の追記により字句解析側で
; 別扱いする（この表の対象外）。

TOK_PRINT_LEN EQU 5
TOK_PRINT_TEXT:
    DB "PRINT"
TOK_PRINT_TOKEN_LEN EQU 2
TOK_PRINT_TOKEN:
    DB 0xFF, 0x88

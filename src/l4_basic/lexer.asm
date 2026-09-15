; lexer.asm — M7段階3b: L4_TOKEN_TABLE（tokens.asm、段階3a生成）を引く
; 汎用の最長一致照合 LEX_MATCH_WORD と、その自己検査 LEX_SELFTEST。
;
; 根拠: docs/notes/l4-token-design.md（番号の規則）・
; src/l4_basic/make_token_table.py のヘッダコメント（並び順＝語長降順、
; 表の終端は語長0の番兵行、拡張語は0xFFに続けて2バイト目）。
; tokens.asm・make_token_table.py 自体は変更しない（参照のみ）。
;
; LEX_MATCH_WORD は「入力テキストの現在位置」と「利用可能な残りバイト数」
; を受け取り、L4_TOKEN_TABLE を先頭（語長降順）から順に見て、その位置の
; テキストと大文字ASCIIで完全一致する最初の（＝最長の）エントリを返す
; 汎用の照合であり、PRINT 以外の語（IF...THEN...ELSE 等、マニュアル目次の
; 見出しをそのまま抽出したため複数語や記号"..."を含む語形もある）も
; 区別なく同じ規則で照合する。実際の直接モードの行頭キーワード認識
; （interp.asm の TRY_MATCH_PRINT）はこの汎用照合を使わず、
; print_dispatch.asm が機械抽出した"PRINT"単体の語形を専用に照合する
; （理由は make_print_dispatch.py のヘッダコメント参照）。
; LEX_SELFTEST はこの汎用照合そのものの自己検査であり、
; 「表の全語が正しい番号に変換される」ことを、各エントリ自身の語の
; バイト列をそのまま入力として与えることで確かめる。

; ---- RAM変数（keyboard.asmのLINE_BUF(E82B-E87A)より後ろ）----
ERROR_FLAG        EQU 0E880h
LINE_END          EQU 0E881h   ; 2バイト
CUR_PTR           EQU 0E883h   ; 2バイト
SUPPRESS_NL       EQU 0E885h
MATCH_FOUND       EQU 0E886h
MATCH_LEN         EQU 0E887h
MATCH_TOKLEN      EQU 0E888h
MATCH_TOK0        EQU 0E889h
MATCH_TOK1        EQU 0E88Ah
LMW_INPUT_PTR     EQU 0E88Bh   ; 2バイト
LMW_AVAIL         EQU 0E88Dh
LMW_TABPTR        EQU 0E88Eh   ; 2バイト
LMW_WORDLEN       EQU 0E890h
SELFTEST_PASS     EQU 0E891h
SELFTEST_FAILIX   EQU 0E892h
SELFTEST_TOTAL    EQU 0E893h
SELFTEST_TABPTR   EQU 0E894h   ; 2バイト
LST_EXPECT_LEN    EQU 0E896h
LST_EXPECT_B0     EQU 0E897h
LST_EXPECT_B1     EQU 0E898h
LST_ENTRY_WORDLEN EQU 0E899h

; ---------------------------------------------------------------------
; LEX_MATCH_WORD — 入力: HL=入力テキストの先頭ポインタ, C=利用可能な
;   残りバイト数。L4_TOKEN_TABLE を先頭から順に見て、語長がC以下の
;   エントリのうち、HL位置のテキストと大文字ASCIIで完全一致する最初の
;   （＝並び順が語長降順のため最長一致の）エントリを探す。
;   出力: MATCH_FOUND(0/1), MATCH_LEN(一致した語の長さ),
;         MATCH_TOKLEN(1か2), MATCH_TOK0/MATCH_TOK1(トークンバイト列)。
;   AF,BC,DE,HL は破壊する。
; ---------------------------------------------------------------------
LEX_MATCH_WORD:
    LD (LMW_INPUT_PTR),HL
    LD A,C
    LD (LMW_AVAIL),A
    LD HL,L4_TOKEN_TABLE
    LD (LMW_TABPTR),HL

_l4lmw_loop:
    LD HL,(LMW_TABPTR)
    LD A,(HL)
    OR A
    JR Z,_l4lmw_none
    LD (LMW_WORDLEN),A

    LD C,A
    LD A,(LMW_AVAIL)
    CP C
    JR C,_l4lmw_advance        ; avail < 語長 なら比較せず次のエントリへ

    PUSH HL                   ; エントリ先頭(語長バイトのアドレス)を退避
    LD DE,(LMW_INPUT_PTR)
    LD HL,(LMW_TABPTR)
    INC HL                     ; HL -> エントリの語の先頭
    LD B,C                     ; B = 比較する文字数(=語長)
_l4lmw_cmp:
    LD A,(DE)
    CP (HL)
    JR NZ,_l4lmw_mismatch
    INC HL
    INC DE
    DJNZ _l4lmw_cmp
    ; 完全一致。HL は語の直後(トークンバイト列の先頭)を指している。
    POP DE                     ; スタック平衡のためだけに戻す(値は不要)
    LD A,(LMW_WORDLEN)
    LD (MATCH_LEN),A
    LD A,(HL)
    CP 0FFh
    JR NZ,_l4lmw_one_byte
    LD (MATCH_TOK0),A
    INC HL
    LD A,(HL)
    LD (MATCH_TOK1),A
    LD A,2
    LD (MATCH_TOKLEN),A
    JR _l4lmw_found
_l4lmw_one_byte:
    LD (MATCH_TOK0),A
    XOR A
    LD (MATCH_TOK1),A
    LD A,1
    LD (MATCH_TOKLEN),A
_l4lmw_found:
    LD A,1
    LD (MATCH_FOUND),A
    RET
_l4lmw_mismatch:
    POP HL                     ; エントリ先頭アドレスに戻す(平衡のみ、値は使わない)
_l4lmw_advance:
    LD HL,(LMW_TABPTR)
    LD A,(LMW_WORDLEN)
    LD C,A
    LD B,0
    INC HL                      ; 語長バイトの分
    ADD HL,BC                   ; 語の分 → トークン先頭
    LD A,(HL)
    CP 0FFh
    JR NZ,_l4lmw_adv_one
    INC HL
    INC HL
    JR _l4lmw_store_tab
_l4lmw_adv_one:
    INC HL
_l4lmw_store_tab:
    LD (LMW_TABPTR),HL
    JR _l4lmw_loop
_l4lmw_none:
    XOR A
    LD (MATCH_FOUND),A
    RET

; ---------------------------------------------------------------------
; LEX_SELFTEST — L4_TOKEN_TABLE の全項目について、項目自身の語の
;   バイト列を入力としてLEX_MATCH_WORDへ渡し、返るトークンが項目自身の
;   トークンと一致するか数える。
;   出力: SELFTEST_TOTAL(検査した項目数), SELFTEST_PASS(一致数),
;         SELFTEST_FAILIX(最初に不一致だった項目の通し番号(0始まり)、
;         全部一致なら0xFF)。
; ---------------------------------------------------------------------
LEX_SELFTEST:
    XOR A
    LD (SELFTEST_TOTAL),A
    LD (SELFTEST_PASS),A
    LD A,0FFh
    LD (SELFTEST_FAILIX),A
    LD HL,L4_TOKEN_TABLE
    LD (SELFTEST_TABPTR),HL
_l4lst_loop:
    LD HL,(SELFTEST_TABPTR)
    LD A,(HL)
    OR A
    RET Z                        ; 表の終端＝検査終了

    LD (LST_ENTRY_WORDLEN),A
    LD C,A
    PUSH HL
    INC HL                        ; HL -> 語の先頭（LEX_MATCH_WORDの入力に使う）
    CALL LEX_MATCH_WORD            ; C=語長ちょうどをそのまま渡す
    POP HL                         ; HL = エントリ先頭(語長バイトのアドレス)

    LD A,(SELFTEST_TOTAL)
    INC A
    LD (SELFTEST_TOTAL),A

    LD A,(MATCH_FOUND)
    OR A
    JR Z,_l4lst_fail

    PUSH HL
    LD A,(LST_ENTRY_WORDLEN)
    LD C,A
    LD B,0
    INC HL
    ADD HL,BC                      ; HL -> このエントリ本来のトークン先頭
    LD A,(HL)
    LD B,A                          ; B = 期待トークンバイト0
    CP 0FFh
    JR NZ,_l4lst_expect_one
    INC HL
    LD A,(HL)
    LD C,A                          ; C = 期待トークンバイト1
    LD A,2
    JR _l4lst_have_expect
_l4lst_expect_one:
    LD C,0
    LD A,1
_l4lst_have_expect:
    POP HL                          ; エントリ先頭に戻す(以後は_l4lst_advanceで再利用)
    LD (LST_EXPECT_LEN),A
    LD A,B
    LD (LST_EXPECT_B0),A
    LD A,C
    LD (LST_EXPECT_B1),A

    LD A,(MATCH_TOKLEN)
    LD B,A
    LD A,(LST_EXPECT_LEN)
    CP B
    JR NZ,_l4lst_fail
    LD A,(MATCH_TOK0)
    LD B,A
    LD A,(LST_EXPECT_B0)
    CP B
    JR NZ,_l4lst_fail
    LD A,(MATCH_TOKLEN)
    CP 2
    JR NZ,_l4lst_pass
    LD A,(MATCH_TOK1)
    LD B,A
    LD A,(LST_EXPECT_B1)
    CP B
    JR NZ,_l4lst_fail
_l4lst_pass:
    LD A,(SELFTEST_PASS)
    INC A
    LD (SELFTEST_PASS),A
    JP _l4lst_advance
_l4lst_fail:
    LD A,(SELFTEST_FAILIX)
    CP 0FFh
    JR NZ,_l4lst_advance             ; 既に記録済みなら上書きしない(最初の不一致だけ残す)
    LD A,(SELFTEST_TOTAL)
    DEC A                           ; 0始まりの通し番号にする
    LD (SELFTEST_FAILIX),A
_l4lst_advance:
    LD HL,(SELFTEST_TABPTR)
    LD A,(HL)
    LD C,A
    LD B,0
    INC HL
    ADD HL,BC
    LD A,(HL)
    CP 0FFh
    JR NZ,_l4lst_adv_one
    INC HL
    INC HL
    JR _l4lst_store
_l4lst_adv_one:
    INC HL
_l4lst_store:
    LD (SELFTEST_TABPTR),HL
    JP _l4lst_loop

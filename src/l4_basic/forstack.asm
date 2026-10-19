; l4-s9d追補1/3（依頼で提示された観測）。公式ROMのバイト列は参照しない。
; FORの後ろにNEXTキーワードが一つでも必要。明示名は呼出側で照合する。
; 途中のFORはIYに記録し、その場合の名前照合は従来どおりNEXT時に任せる。
; 位置は呼出側で保存/復元する。字句/式/フレーム作業域は触らず、文字列・REM・DATAを除外する。
; PAINT前処理とKEY入口の間。既存の文字列/REM/DATA除外の後だけ呼ぶ。
    ORG 0x7281
s9n_check_for:
    PUSH HL
    LD IX,s9n_for
    LD B,3
    CALL s9n_word
    JR NZ,s9n_not_for
    LD IY,1
s9n_not_for:
    POP HL
    RET
s9n_for: DB "for"
s9n_next: DB "next"
s9n_rem: DB "rem"
s9n_data: DB "data"
s9n_missing:
    LD A,26
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_FLAG),A
    RET

    ORG 0x7EE0
; 入力: IY=0。成功: CUR_PTR/LINE_END=最初のNEXT直後/その行末、途中のFORありならIY=1。
; ERROR_FLAG/KINDで結果を返す。呼出側は位置とIYを必ず復元する。
S9D_REQUIRE_NEXT:
    LD HL,(RUN_CUR_RECORD)
    PUSH HL
    LD HL,(CUR_PTR)
    LD DE,(LINE_END)
s9n_scan:
    CALL s9n_more
    JR NC,s9n_line
    LD A,(HL)
    CP '"'
    JR Z,s9n_string
    CP 027h
    JR Z,s9n_line
    CALL s9n_ident
    JR NC,s9n_char
    LD IX,s9n_next
    LD B,4
    CALL s9n_word
    JR Z,s9n_found
    LD IX,s9n_rem
    LD B,3
    CALL s9n_word
    JR Z,s9n_line
    LD IX,s9n_data
    LD B,4
    CALL s9n_word
    JR Z,s9n_data_scan
    CALL s9n_check_for
s9n_skip_ident:
    INC HL
    CALL s9n_more
    JR NC,s9n_line
    LD A,(HL)
    CALL s9n_ident
    JR C,s9n_skip_ident
    JR s9n_scan
s9n_char:
    INC HL
    JR s9n_scan
s9n_string:
    CALL s9n_quote
    JR s9n_scan
s9n_data_scan:
    CALL s9n_more
    JR NC,s9n_line
    LD A,(HL)
    CP ':'
    JR Z,s9n_char
    CP '"'
    JR NZ,s9n_data_char
    CALL s9n_quote
    JR s9n_data_scan
s9n_data_char:
    INC HL
    JR s9n_data_scan
s9n_line:
    POP HL                    ; 直接モードは現在行の残りだけ
    LD A,(HL)
    INC HL
    OR (HL)
    JP Z,s9n_missing
    INC HL
    LD C,(HL)
    LD B,0
    INC HL
    ADD HL,BC
    LD A,(HL)
    INC HL
    AND (HL)
    INC A
    JP Z,s9n_missing          ; 行番号FFFFは番兵
    DEC HL
    PUSH HL
    INC HL
    INC HL
    LD C,(HL)
    LD B,0
    INC HL
    PUSH HL
    ADD HL,BC
    EX DE,HL
    POP HL
    JP s9n_scan
s9n_found:
    LD (CUR_PTR),HL           ; NEXT直後とその行末（呼出側で必ず復元）
    LD (LINE_END),DE
    POP HL
    XOR A
    LD (ERROR_FLAG),A
    RET
s9n_more:                    ; HL < DEならCF=1
    PUSH HL
    OR A
    SBC HL,DE
    POP HL
    RET
s9n_quote:
    INC HL
s9n_quote_loop:
    CALL s9n_more
    RET NC
    LD A,(HL)
    INC HL
    CP '"'
    JR NZ,s9n_quote_loop
    RET
s9n_ident:                   ; 識別子構成文字ならCF=1
    CP '_'
    JR Z,s9n_ident_yes
    CP '$'
    JR Z,s9n_ident_yes
    CP '%'
    JR Z,s9n_ident_yes
    CP '#'
    JR Z,s9n_ident_yes
    CP '0'
    JR C,s9n_ident_no
    CP '9'+1
    JR C,s9n_ident_yes
    OR 20h
    CP 'a'
    JR C,s9n_ident_no
    CP 'z'+1
    JR C,s9n_ident_yes
s9n_ident_no:
    OR A
    RET
s9n_ident_yes:
    SCF
    RET
s9n_word:                    ; 一致ならZ=1/HLを語末へ、それ以外はHL不変
    PUSH HL
s9n_word_loop:
    CALL s9n_more
    JR NC,s9n_word_no
    LD A,(HL)
    OR 20h
    CP (IX+0)
    JR NZ,s9n_word_no
    INC IX
    INC HL
    DJNZ s9n_word_loop
    CALL s9n_more
    JR NC,s9n_word_yes
    LD A,(HL)
    CALL s9n_ident
    JR C,s9n_word_no
s9n_word_yes:
    POP BC
    XOR A
    RET
s9n_word_no:
    POP HL
    LD A,1
    OR A
    RET

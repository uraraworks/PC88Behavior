; l4-graphics 第6版12節・l4-program 第14.16版4.10.8から独立実装。
; LINE作業域を排他的に再利用。式評価中も保持される領域。
; 番地はar_elem、容量は自作配列レコードの論理長、画面番地はgx_addrを使う。
; VRAM選択中はレジスタと画面だけに触れ、DI〜OUT 5F〜EIでVSYNCから守る。
; 自作判断: 未DIMの添字省略はERR5、幅/高さ0はERR5。
; 明示色は1プレーンとして復号し、色の下位3bit（白黒は非0）を使う。
; x=7,w=9の余りは先頭有効バイトから作る。別の模様/高さでの動作は自作判断。
GP_X EQU MM_GP_X
GP_Y EQU MM_GP_Y
GP_W EQU MM_GP_W
GP_H EQU MM_GP_H
GP_PTR EQU MM_GP_PTR
GP_END EQU MM_GP_END
GP_MODE EQU MM_GP_MODE
GP_OP EQU MM_GP_OP
GP_COL EQU MM_GP_COL
GP_FG EQU MM_GP_FG
GP_BG EQU MM_GP_BG
GP_Q EQU MM_GP_Q
GP_ROW EQU MM_GP_ROW
GP_PLANE EQU MM_GP_PLANE
GP_M EQU MM_GP_M
GP_N EQU MM_GP_N
GP_BYTE EQU MM_GP_BYTE
GP_BITS EQU MM_GP_BITS
GP_LEFT EQU MM_GP_LEFT
GP_ADDR EQU MM_GP_ADDR
GP_MASK EQU MM_GP_MASK
GP_PREV EQU MM_GP_PREV
GP_PAD EQU MM_GP_PAD
    ORG 0x6B43
gput_stmt:
    LD A,(MM_RUN_STMT_KIND)
    SUB 51
    LD (GP_MODE),A              ; GET=0 PUT=1
    XOR A
    LD (GP_COL),A
    LD (GP_PAD),A
    CALL s2_skip
    CALL s2_peek
    CP '@'
    CALL Z,s2_adv
    CALL s2_skip
    CALL s2_peek
    CP '('
    JP NZ,gx_err2              ; 第1座標のSTEPは禁止
    CALL gput_coord
    RET NZ
    LD HL,(MM_GFX_LPX)
    LD (GP_X),HL
    LD HL,(MM_GFX_LPY)
    LD (GP_Y),HL
    LD A,(GP_MODE)
    OR A
    JR NZ,gput_array
    LD A,'-'
    CALL gx_expect
    CALL gx_bad
    RET NZ
    CALL gput_coord
    RET NZ
    LD HL,(GP_X)
    LD DE,(MM_GFX_LPX)
    CALL gput_axis
    LD (GP_X),DE
    LD (GP_W),HL
    LD HL,(GP_Y)
    LD DE,(MM_GFX_LPY)
    CALL gput_axis
    LD (GP_Y),DE
    LD (GP_H),HL
gput_array:
    LD A,','
    CALL gx_expect
    CALL gx_bad
    RET NZ
    CALL ar_skip
    CALL ar_ident
    OR A
    JP Z,gx_err2
    CALL ar_skip
    CALL ar_peek
    CP '('
    JR Z,gput_index
    CALL ar_find
    OR A
    JP Z,gx_err5              ; 未DIMは未測定
    PUSH HL
    LD DE,13
    ADD HL,DE
    LD A,(HL)
    LD (MM_AR_NDIM),A
    LD B,A
    LD HL,MM_AR_ARGS
    XOR A
gput_zero_index:
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    DJNZ gput_zero_index
    POP HL
    CALL ar_elem
    JR gput_resolved
gput_index:
    CALL ar_resolve
gput_resolved:
    CALL gx_bad
    RET NZ
    LD (GP_PTR),HL
    PUSH HL
    LD HL,(MM_AR_REC)
    LD DE,11
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD HL,(MM_AR_REC)
    ADD HL,DE
    LD DE,8
    ADD HL,DE                 ; 生きた論理領域の終端（再利用枠の物理長は使わない）
    LD (GP_END),HL
    POP HL
    LD A,(MM_GFX_MONO)
    LD B,3
    OR A
    JR Z,gput_planes
    LD B,1
gput_planes:
    LD A,B
    LD (GP_M),A
    LD (GP_N),A
    LD A,(GP_MODE)
    OR A
    JP Z,gput_dimensions
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    LD (GP_W),DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (GP_H),DE
    LD A,4                   ; 既定XOR
    LD (GP_OP),A
    CALL gx_at_end
    JR Z,gput_put_bounds
    LD A,','
    CALL gx_expect
    CALL gx_bad
    RET NZ
    CALL s2_skip
    LD IX,gput_ops
    CALL k2_match_word
    OR A
    JP Z,gx_err2
    DEC A
    LD (GP_OP),A
    CALL gx_at_end
    JR Z,gput_put_bounds
    LD A,','
    CALL gx_expect
    CALL gx_bad
    RET NZ
    CALL gx_parse_int
    CALL gx_bad
    RET NZ
    LD A,E
    LD (GP_FG),A
    LD A,','
    CALL gx_expect
    CALL gx_bad
    RET NZ
    CALL gx_parse_int
    CALL gx_bad
    RET NZ
    LD A,E
    LD (GP_BG),A
    LD A,1
    LD (GP_COL),A
    LD (GP_M),A              ; 明示色は1プレーンとして復号（一般化は自作判断）
gput_put_bounds:
    LD HL,(GP_X)
    LD DE,(GP_W)
    ADD HL,DE
    DEC HL
    PUSH HL
    LD HL,(GP_Y)
    LD DE,(GP_H)
    ADD HL,DE
    DEC HL
    EX DE,HL
    POP HL
    CALL gx_addr
    JP C,gx_err5
gput_dimensions:
    LD HL,(GP_W)
    LD A,H
    OR L
    JP Z,gx_err5
    LD DE,7
    ADD HL,DE
    SRL H
    RR L
    SRL H
    RR L
    SRL H
    RR L
    LD (GP_Q),HL
    LD DE,(GP_H)
    LD A,D
    OR E
    JP Z,gx_err5
    CALL ar_mul
    JP C,gx_err5
    LD A,(GP_M)
    LD E,A
    LD D,0
    CALL ar_mul
    JP C,gx_err5
    LD DE,4
    ADD HL,DE
    JP C,gx_err5
    LD DE,(GP_PTR)
    ADD HL,DE
    JP C,gx_err5
    LD DE,(GP_END)
    OR A
    SBC HL,DE
    JP C,gput_capacity_ok
    JP NZ,gx_err5
gput_capacity_ok:
    CALL gx_stmt_end
    RET NZ
    LD HL,(GP_PTR)
    LD A,(GP_MODE)
    OR A
    JR NZ,gput_header_done
    LD DE,(GP_W)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(GP_H)
    LD (HL),E
    INC HL
    LD (HL),D
    DEC HL
    DEC HL
    DEC HL
    ; 限定観測: x=7,w=9 の余り。模様をテーブル化せず有効先頭バイトから得る。
    LD DE,(GP_X)
    LD A,D
    OR A
    JR NZ,gput_header_done
    LD A,E
    CP 7
    JR NZ,gput_header_done
    LD DE,(GP_W)
    LD A,D
    OR A
    JR NZ,gput_header_done
    LD A,E
    CP 9
    JR NZ,gput_header_done
    LD (GP_PAD),A
gput_header_done:
    LD DE,4
    ADD HL,DE
    LD (GP_PTR),HL
    LD HL,(GP_Y)
    LD (GP_ROW),HL
gput_row:
    XOR A
    LD (GP_PLANE),A
gput_plane:
    LD HL,(GP_X)
    LD DE,(GP_ROW)
    CALL gx_addr
    LD (GP_ADDR),HL
    LD A,B
    LD (GP_MASK),A
    LD HL,(GP_W)
    LD (GP_LEFT),HL
    XOR A
    LD (GP_PREV),A
gput_byte:
    LD HL,(GP_PTR)
    LD A,(GP_MODE)
    OR A
    LD A,0
    JR Z,gput_byte_start
    LD A,(HL)
gput_byte_start:
    LD (GP_BYTE),A
    LD A,8
    LD (GP_BITS),A
gput_bit:
    LD HL,(GP_ADDR)
    LD A,(GP_MASK)
    LD B,A
    LD A,(GP_PLANE)
    LD C,A
    LD A,(MM_GFX_MONO)
    OR A
    JR Z,gput_port
    LD A,(MM_GFX_APAGE)
    LD C,A
gput_port:
    LD A,C
    ADD A,05Ch
    LD C,A
    LD A,(GP_MODE)
    OR A
    JR NZ,gput_write
    DI
    OUT (C),A
    LD A,(HL)
    AND B
    OUT (05Fh),A
    EI
    ADD A,0FFh
    LD HL,GP_BYTE
    RL (HL)
    JR gput_advance
gput_write:
    LD A,(GP_BYTE)
    RLCA
    LD (GP_BYTE),A
    SBC A,A
    LD E,A
    LD A,(GP_COL)
    OR A
    JR Z,gput_write_raw
    LD A,E
    OR A
    LD A,(GP_BG)
    JR Z,gput_map_color
    LD A,(GP_FG)
gput_map_color:
    LD E,A
    LD A,(MM_GFX_MONO)
    OR A
    LD A,E
    JR Z,gput_map_plane
    ADD A,0FFh
    JR gput_map_done
gput_map_plane:
    LD A,(GP_PLANE)
    INC A
    LD D,A
    LD A,E
gput_map_shift:
    SRL A
    DEC D
    JR NZ,gput_map_shift
gput_map_done:
    SBC A,A
    LD E,A
gput_write_raw:
    LD A,(GP_OP)
    LD D,A
    DI
    OUT (C),A
    LD A,D
    OR A
    LD A,E
    JR Z,gput_store
    DEC D
    JR NZ,gput_logic
    CPL
    JR gput_store
gput_logic:
    DEC D
    JR NZ,gput_and
    OR (HL)
    JR gput_store
gput_and:
    DEC D
    JR NZ,gput_xor
    AND (HL)
    JR gput_store
gput_xor:
    XOR (HL)
gput_store:
    XOR (HL)
    AND B
    XOR (HL)
    LD (HL),A
    OUT (05Fh),A
    EI
gput_advance:
    LD A,(GP_MASK)
    RRCA
    LD (GP_MASK),A
    JR NC,gput_same_addr
    LD HL,(GP_ADDR)
    INC HL
    LD (GP_ADDR),HL
gput_same_addr:
    LD HL,(GP_LEFT)
    DEC HL
    LD (GP_LEFT),HL
    LD A,H
    OR L
    JR Z,gput_last_byte
    LD HL,GP_BITS
    DEC (HL)
    JP NZ,gput_bit
    CALL gput_save_byte
    JP gput_byte
gput_last_byte:
    LD A,(GP_MODE)
    OR A
    JR NZ,gput_end_plane
    LD A,(GP_BITS)
    DEC A
    JR Z,gput_last_ready
    LD B,A
    LD A,(GP_BYTE)
gput_pad_shift:
    ADD A,A
    DJNZ gput_pad_shift
    LD (GP_BYTE),A
    LD A,(GP_PAD)
    OR A
    JR Z,gput_last_ready
    LD A,(GP_PREV)
    AND 07Fh
    LD B,A
    LD A,(GP_BYTE)
    OR B
    LD (GP_BYTE),A
gput_last_ready:
    CALL gput_save_byte
    JR gput_plane_next
gput_end_plane:
    LD HL,(GP_PTR)
    INC HL
    LD (GP_PTR),HL
gput_plane_next:
    LD HL,GP_PLANE
    INC (HL)
    LD A,(GP_N)
    CP (HL)
    JR Z,gput_next_row
    LD A,(GP_COL)
    OR A
    JR Z,gput_next_plane
    LD HL,(GP_PTR)
    LD DE,(GP_Q)
    OR A
    SBC HL,DE
    LD (GP_PTR),HL
gput_next_plane:
    JP gput_plane
gput_next_row:
    LD HL,(GP_ROW)
    INC HL
    LD (GP_ROW),HL
    LD HL,(GP_H)
    DEC HL
    LD (GP_H),HL
    LD A,H
    OR L
    JP NZ,gput_row
    JP gx_ok
gput_save_byte:
    LD HL,(GP_PTR)
    LD A,(GP_MODE)
    OR A
    JR NZ,gput_save_next
    LD A,(GP_BYTE)
    LD (HL),A
    LD (GP_PREV),A
gput_save_next:
    INC HL
    LD (GP_PTR),HL
    RET
gput_coord:
    CALL gx_coord
    CALL gx_bad
    RET NZ
    LD HL,(MM_GFX_LPX)
    LD DE,(MM_GFX_LPY)
    CALL gx_addr
    JP C,gput_coord_bad
    XOR A
    RET
gput_coord_bad:
    CALL gx_err5
    OR A
    RET
gput_axis:
    OR A
    SBC HL,DE
    JR NC,gput_axis_done
    ADD HL,DE
    EX DE,HL
    OR A
    SBC HL,DE
gput_axis_done:
    INC HL
    RET
gput_ops:
    DB 4,1,"PSET",6,2,"PRESET",2,3,"OR",3,4,"AND",3,5,"XOR",0
gput_end:

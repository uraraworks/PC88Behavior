; main_sub_read.asm — main側通信プリミティブと既知1セクタREAD入口
;
; 根拠は docs/spec/l3-subrom.md 1.10, 1.12, 1.13, 1.19, 1.31,
; 1.36, 1.37, 1.46, 1.63節、および tools/make_l3_test_main.py の
; SEND_MAIN/SEND_MAIN_CONT/SEND_MAIN_PAIR/RECV_MAIN/RECV_MAIN_PAIR手順だけ。
; BASICのFILES/LOAD/SAVEとは接続しない。build_main_rom.pyの
; --enable-main-sub-readを指定した検査用ビルドだけに連結される。
;
; MAIN_SUB_READ_KNOWN:
;   入力 A bit0 = ドライブ選択 (0=A, 1=B)。
;   C=0/H=0/R=1（論理トラック0、既知セクタ1）を1回READし、
;   MAIN_SUB_SECTOR_BUFへ256位置を保存する。主・副レジスタのうち
;   主側AF/BC/DE/HL/IX/IYを保存して戻る。
;
; timeout上限は各待ちループにつき65535回。16bitカウンタで表せる最大値を
; 選び、正常なFDC処理への余裕を最大にしつつ、媒体なしでも必ず有限復帰する。
;
; RAM配置: 既存のrun.asm使用終端0xDEC0より後、screen.asm使用開始0xE800
; より前の未使用域に、256バイト受信域とマーカーを置く。

MAIN_SUB_SECTOR_BUF       EQU 0DF00h ; 0xDF00-0xDFFF (256バイト)
MAIN_SUB_MARK_REQUEST     EQU 0E000h ; 5位置の要求run完了
MAIN_SUB_MARK_RECV256     EQU 0E001h ; 256位置受信完了
MAIN_SUB_MARK_SUCCESS     EQU 0E002h ; 既知READ成功完了
MAIN_SUB_MARK_TIMEOUT     EQU 0E003h ; 有限上限で打切り
MAIN_SUB_MARK_FAULT_WAIT  EQU 0E004h ; 待ち判定故障箇所を通過
MAIN_SUB_MARK_FAULT_CONT  EQU 0E005h ; 継続SEND故障箇所を通過
MAIN_SUB_MARK_FAULT_PAIR  EQU 0E006h ; PAIR故障箇所を通過
MAIN_SUB_DRIVE_SELECT     EQU 0E007h ; 入口引数bit0の一時退避
MAIN_SUB_BOOT_DONE        EQU 0E008h ; 定常ループからの自動実行を1回に制限

MAIN_SUB_TIMEOUT_LIMIT    EQU 0FFFFh ; 65535回（上記理由で16bit最大）

MAIN_SUB_LINK_START:

; Cのマスクが1になるまで待つ。成功CY=0、timeout CY=1。破壊AF,DE。
MAIN_SUB_WAIT_SET:
    LD DE,MAIN_SUB_TIMEOUT_LIMIT
_ms_wait_set_loop:
    IN A,(0FEh)
    AND C
    RET NZ
    DEC DE
    LD A,D
    OR E
    JR NZ,_ms_wait_set_loop
    SCF
    RET

; Cのマスクが0になるまで待つ。成功CY=0、timeout CY=1。破壊AF,DE。
MAIN_SUB_WAIT_CLEAR:
    LD DE,MAIN_SUB_TIMEOUT_LIMIT
_ms_wait_clear_loop:
    IN A,(0FEh)
    AND C
    JR Z,_ms_wait_clear_ok
    DEC DE
    LD A,D
    OR E
    JR NZ,_ms_wait_clear_loop
    SCF
    RET
_ms_wait_clear_ok:
    OR A
    RET

; Aを1位置送信。成功CY=0、timeout CY=1。破壊AF,C,DE。
MAIN_SUB_SEND:
    PUSH AF
    LD A,00Fh
    OUT (0FFh),A
_ms_send_wait_before_site:
    NOP
    NOP
    NOP
    NOP
    NOP
    LD C,002h
    CALL MAIN_SUB_WAIT_SET
_ms_send_wait_before_site_end:
    JR C,_ms_send_timeout_pop
    LD A,00Eh
    OUT (0FFh),A
    POP AF
    OUT (0FDh),A
    LD A,009h
    OUT (0FFh),A
    LD C,004h
    CALL MAIN_SUB_WAIT_SET
    JR C,_ms_send_timeout
    LD A,008h
    OUT (0FFh),A
    IN A,(0FEh)                 ; 結果ステータスは単発読取り
    OR A
    RET
_ms_send_timeout_pop:
    POP AF
_ms_send_timeout:
    SCF
    RET

; Aを継続1位置送信。先頭のOUT $FF,0Fだけを省略する。
; 成功CY=0、timeout CY=1。破壊AF,C,DE。
MAIN_SUB_SEND_CONT:
    PUSH AF
    LD C,002h
    CALL MAIN_SUB_WAIT_SET
    JR C,_ms_send_cont_timeout_pop
    LD A,00Eh
    OUT (0FFh),A
    POP AF
    OUT (0FDh),A
    LD A,009h
    OUT (0FFh),A
    LD C,004h
    CALL MAIN_SUB_WAIT_SET
    JR C,_ms_send_cont_timeout
    LD A,008h
    OUT (0FFh),A
    IN A,(0FEh)
    OR A
    RET
_ms_send_cont_timeout_pop:
    POP AF
_ms_send_cont_timeout:
    SCF
    RET

; HLの連続2位置を1フェーズで送信しHLを2進める。
; 成功CY=0、timeout CY=1。破壊AF,C,DE,HL。
MAIN_SUB_SEND_PAIR:
    LD A,00Fh
    OUT (0FFh),A
    LD C,002h
    CALL MAIN_SUB_WAIT_SET
    RET C
    LD A,00Eh
    OUT (0FFh),A
    LD A,(HL)
    OUT (0FDh),A
    INC HL
    LD A,009h
    OUT (0FFh),A
    LD C,004h
    CALL MAIN_SUB_WAIT_SET
    RET C
    LD A,(HL)
    OUT (0FDh),A
    INC HL
    LD A,008h
    OUT (0FFh),A
    IN A,(0FEh)
    OR A
    RET

; 1位置受信。成功CY=0かつA=受信値、timeout CY=1。破壊AF,C,DE。
MAIN_SUB_RECV:
    LD A,00Bh
    OUT (0FFh),A
    LD C,001h
    CALL MAIN_SUB_WAIT_SET
    RET C
    LD A,00Ah
    OUT (0FFh),A
    IN A,(0FCh)
    PUSH AF
    LD A,00Dh
    OUT (0FFh),A
    LD C,001h
    CALL MAIN_SUB_WAIT_CLEAR
    JR C,_ms_recv_timeout_pop
    LD A,00Ch
    OUT (0FFh),A
    POP AF
    OR A
    RET
_ms_recv_timeout_pop:
    POP AF
    SCF
    RET

; 連続2位置を1フェーズで受信し(HL),(HL+1)へ保存、HLを2進める。
; 成功CY=0、timeout CY=1。破壊AF,C,DE,HL。
MAIN_SUB_RECV_PAIR:
    LD A,00Bh
    OUT (0FFh),A
    LD C,001h
    CALL MAIN_SUB_WAIT_SET
    RET C
    LD A,00Ah
    OUT (0FFh),A
    IN A,(0FCh)
    LD (HL),A
    INC HL
    LD A,00Dh
    OUT (0FFh),A
    LD C,001h
    CALL MAIN_SUB_WAIT_CLEAR
    RET C
    IN A,(0FCh)
    LD (HL),A
    INC HL
    LD A,00Ch
    OUT (0FFh),A
    OR A
    RET

; PAIR陰性対照用。1フェーズ2位置ではなく単発RECVを2回行う。
MAIN_SUB_RECV_PAIR_BROKEN:
    CALL MAIN_SUB_RECV
    RET C
    LD (HL),A
    INC HL
    CALL MAIN_SUB_RECV
    RET C
    LD (HL),A
    INC HL
    OR A
    RET

; 5位置要求の継続位置を送る故障注入点。通常はCONTを呼ぶ。
MAIN_SUB_SEND_REQUEST_CONT:
_ms_cont_call_site:
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    CALL MAIN_SUB_SEND_CONT
_ms_cont_call_site_end:
    RET

; 256位置受信のPAIR故障注入点。通常は1フェーズ2位置を呼ぶ。
MAIN_SUB_RECV_REQUEST_PAIR:
_ms_pair_call_site:
    NOP
    NOP
    NOP
    NOP
    NOP
    CALL MAIN_SUB_RECV_PAIR
_ms_pair_call_site_end:
    RET

; A bit0=ドライブ選択。既知座標(論理track=0,R=1)を1回READする。
MAIN_SUB_READ_KNOWN:
    PUSH AF
    PUSH BC
    PUSH DE
    PUSH HL
    PUSH IX
    PUSH IY

    AND 001h
    LD (MAIN_SUB_DRIVE_SELECT),A
    XOR A
    LD (MAIN_SUB_MARK_REQUEST),A
    LD (MAIN_SUB_MARK_RECV256),A
    LD (MAIN_SUB_MARK_SUCCESS),A
    LD (MAIN_SUB_MARK_TIMEOUT),A
    LD (MAIN_SUB_MARK_FAULT_WAIT),A
    LD (MAIN_SUB_MARK_FAULT_CONT),A
    LD (MAIN_SUB_MARK_FAULT_PAIR),A

    LD A,002h                   ; 先頭0x02は通常SEND
    CALL MAIN_SUB_SEND
    JP C,_ms_read_timeout
    XOR A                       ; 位置2
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    LD A,(MAIN_SUB_DRIVE_SELECT); 位置3 bit0=ドライブ選択
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    XOR A                       ; 位置4=論理トラック0
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    LD A,001h                   ; 位置5=R 1
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    LD A,001h
    LD (MAIN_SUB_MARK_REQUEST),A

    LD A,006h
    CALL MAIN_SUB_SEND
    JP C,_ms_read_timeout
    CALL MAIN_SUB_RECV          ; 仕様上のack 0xC0
    JP C,_ms_read_timeout
    CP 0C0h
    JP NZ,_ms_read_return       ; 不一致は成功印を立てない
    LD A,012h
    CALL MAIN_SUB_SEND
    JP C,_ms_read_timeout

    LD HL,MAIN_SUB_SECTOR_BUF
    LD B,080h                   ; 2位置PAIRを128回
_ms_read_256_loop:
    CALL MAIN_SUB_RECV_REQUEST_PAIR
    JP C,_ms_read_timeout
    DJNZ _ms_read_256_loop
    LD A,001h
    LD (MAIN_SUB_MARK_RECV256),A
    LD (MAIN_SUB_MARK_SUCCESS),A
    JR _ms_read_return

_ms_read_timeout:
    LD A,001h
    LD (MAIN_SUB_MARK_TIMEOUT),A
_ms_read_return:
    POP IY
    POP IX
    POP HL
    POP DE
    POP BC
    POP AF
    RET

; --enable-main-sub-read時の定常ループ用。入口自体は反復呼出し可能だが、
; 自動呼出しは1回だけにする。既定ドライブA(bit0=0)を選ぶ。
MAIN_SUB_READ_INIT:
    XOR A
    LD (MAIN_SUB_BOOT_DONE),A
    RET

MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET

MAIN_SUB_LINK_END:

; disk_read_retry.asm — 既知1セクタREADの上限1回再試行
;
; この形の根拠は docs/notes/m6i-h-drop-the-fixed-wait-results.md の測定結果
; （特に§5・§8）。通常READ前のフレーム待ちも起動専用の空送信も置かず、
; 初回失敗時だけ再試行する。測定で確認したのは「再試行1回で足りる」こと
; だけなので、上限はちょうど1回に固定し、2回以上・無制限にはしない。
; 入力AFは初回より前に明示的に退避し、失敗時にPOP AFしてドライブ選択を
; 2回目へそのまま渡す。m6i-hの測定はXOR AのドライブAしか通していないため、
; この引継ぎはtools/disk_read_retry_z80_selftest.shのZ80実走で検査する。

; 入力 A bit0 = ドライブ選択。成功CY=0、2回とも失敗ならCY=1。
MAIN_SUB_READ_KNOWN_RETRY:
    PUSH AF
    CALL MAIN_SUB_READ_KNOWN
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A
    JR NZ,_ms_retry_first_success
    POP AF                       ; 入力Aとフラグを復元して2回目へ渡す
    CALL MAIN_SUB_READ_KNOWN
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A                         ; 成功時CY=0を明示（POP AFのCYに依存しない）
    RET NZ                       ; 2回目成功: CY=0
    SCF
    RET                          ; 2回とも失敗: CY=1
_ms_retry_first_success:
    POP AF                       ; 入力フラグのCYも復元される
    OR A                         ; そのCYを必ず0にして成功を返す
    RET
MAIN_SUB_READ_KNOWN_RETRY_END:

; STEADY_WAITからの自動呼出しを1回だけにする。既定ドライブA(bit0=0)。
DISK_READ_RETRY_INIT:
    XOR A
    LD (MAIN_SUB_BOOT_DONE),A
    RET

DISK_READ_RETRY_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN_RETRY
    RET


; c1: SAVE捕捉もmainの窓を復元してからbank1へ入る。
LIST_RENDER_ALL:
    PUSH AF
    LD A,1
    LD IX,0x7FB9
    JP CAPACITY_BANK_CALL

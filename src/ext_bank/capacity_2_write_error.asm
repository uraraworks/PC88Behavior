; FAT書き込みの誤りは番号を設定し、呼び出し元へCF=1を返す。
    ORG 0x666B
s2_flush_error:
    CALL s2_disk_error
    SCF
    RET

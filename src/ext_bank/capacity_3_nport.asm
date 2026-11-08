; BASICの可変ポート出力も31hの写しを更新する。
    ORG 0x704B
t3_record_port:
    LD A,E
    JR NZ,t3_record_done
    LD (MM_SCR_P31),A
t3_record_done:
    OUT (C),A
    JP S9_OK

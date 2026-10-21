; 書き込み保護の分岐の余地を作るため、既存の中継を空きへ移す。
    ORG 0x6663
s2_write:
    JP s2_write_stream

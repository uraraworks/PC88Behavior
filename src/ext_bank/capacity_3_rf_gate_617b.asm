; RF関数だけの中継。通常関数はここを通らない。
    ORG 0x617B
rf_func_bridge:
    JP RF3_FUNC

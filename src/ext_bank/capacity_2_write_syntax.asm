; 固定配置の割当順入口を動かさず、保護判定の4Bを確保する。
    ORG 0x667B
s2_syntax:
    LD A,2
    JP s2_error

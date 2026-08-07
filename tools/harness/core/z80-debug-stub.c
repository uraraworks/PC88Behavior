/*
 * z80-debug-stub.c — PC88Behavior 計測ハーネス用
 *
 * 上流の src/z80-debug.c（Z80 逆アセンブラ）を置き換えるスタブ。
 *
 * 本プロジェクトはクリーンルーム規律により、公式 ROM の逆アセンブルを禁じている
 * （PC88Behavior/CLAUDE.md 禁止事項 2）。運用で「使わない」と決めるだけでは、
 * ハーネスのバイナリ自体が公式 ROM に向けられる逆アセンブラを内蔵したままになる。
 * 能力そのものを持たない状態にするため、命令テーブルとデコード処理を丸ごと落とす。
 *
 * z80.h が両関数を extern 宣言しているのでシンボルだけ残す。
 * 実際の呼び出し元は上流にも存在しない（z80_debug から z80_line_disasm を呼ぶ
 * 自己参照のみ）ため、これで機能欠落は起きない。
 */

#include "quasi88.h"
#include "z80.h"

int z80_line_disasm(z80arch *z80, word pc)
{
    (void)z80;
    (void)pc;
    /* 逆アセンブラは意図的に存在しない。1 命令ぶん進んだことにして返す。 */
    return 1;
}

void z80_debug(z80arch *z80, char *mes)
{
    (void)z80;
    (void)mes;
    /* 何もしない */
}

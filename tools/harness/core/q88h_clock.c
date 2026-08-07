/*
 * q88h_clock.c — PC88Behavior 計測ハーネス / 両CPU共通の単調増加クロック
 * 詳細は q88h_clock.h を参照。
 */

#include "q88h_clock.h"

static uint32_t g_clock;

uint32_t q88h_clock_tick(void)
{
    g_clock++;
    return g_clock;
}

void retro_q88h_clock_reset(void)
{
    g_clock = 0;
}

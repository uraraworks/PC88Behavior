/*
 * q88h_fontsrc.c — PC88Behavior 計測ハーネス / フォント供給源の可視化
 * 詳細は q88h_fontsrc.h を参照。
 */

#include <string.h>
#include "q88h_fontsrc.h"

static q88h_fontsrc_t g_fontsrc;

static q88h_fontsrc_t *ensure(void)
{
    if (g_fontsrc.magic != Q88H_FONTSRC_MAGIC) {
        /* 初回アクセス時に初期化する。コア側の初期化順にもフロントエンド側の
         * 呼び出し順にも依存したくないため（他の q88h_* と同じ考え方）。 */
        memset(&g_fontsrc, 0, sizeof(g_fontsrc));
        g_fontsrc.magic   = Q88H_FONTSRC_MAGIC;
        g_fontsrc.version = Q88H_FONTSRC_VERSION;
    }
    return &g_fontsrc;
}

q88h_fontsrc_t *retro_q88h_fontsrc(void) { return ensure(); }

void retro_q88h_fontsrc_reset(void)
{
    memset(&g_fontsrc, 0, sizeof(g_fontsrc));
    ensure();
}

/* 標準的な CRC32 (IEEE 802.3 多項式 0xEDB88320)。テーブル無しのビット単位実装
 * ——起動シーケンス中に何度も呼ばれる規模ではないので速度は要らない。
 * 依存を増やしたくないので自前で書く（zlib 等の外部実装を持ち込まない）。 */
static uint32_t crc32_update(uint32_t crc, const uint8_t *data, uint32_t len)
{
    uint32_t i, j;
    crc = ~crc;
    for (i = 0; i < len; i++) {
        crc ^= data[i];
        for (j = 0; j < 8; j++) {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

void q88h_fontsrc_set(int region, uint8_t src, const uint8_t *data, uint32_t len)
{
    q88h_fontsrc_t *f = ensure();
    if (region < 0 || region >= Q88H_FONTSRC_REGION_COUNT) return;

    f->region_src[region] = src;
    f->region_writes[region]++;
    f->region_crc32[region] = (data && len) ? crc32_update(0, data, len)
                                             : crc32_update(0, NULL, 0);
}

void q88h_fontsrc_set_tag(int region, uint8_t src)
{
    q88h_fontsrc_t *f = ensure();
    if (region < 0 || region >= Q88H_FONTSRC_REGION_COUNT) return;

    f->region_src[region] = src;
    f->region_writes[region]++;
    /* CRC は変えない——呼び手がデータを渡していないので、直前の値を保持する
     * （0 埋めなど「意味のある空」の場合は呼び手が q88h_fontsrc_set 側を使うこと）。 */
}

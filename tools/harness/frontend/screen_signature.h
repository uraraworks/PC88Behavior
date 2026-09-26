#ifndef Q88MEASURE_SCREEN_SIGNATURE_H
#define Q88MEASURE_SCREEN_SIGNATURE_H

/*
 * 画面本文を外へ出さず、check_l3_screen_output.py と同じ正準形を
 * プロセス内で SHA-256 にする小部品。外部ライブラリへ依存させないのは、
 * q88measure の既存ビルド条件を変えず、本文を別過程へ渡す経路も作らないため。
 */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define Q88_SCREEN_SIGNATURE_ROWS 25
#define Q88_SCREEN_SIGNATURE_COLS 80
#define Q88_SCREEN_SIGNATURE_ID_MAX 63
#define Q88_SCREEN_SIGNATURE_MAX 32

typedef struct {
    uint32_t state[8];
    uint64_t bit_count;
    uint8_t block[64];
    size_t block_len;
} q88_sha256_t;

static uint32_t q88_sha256_rotr(uint32_t value, unsigned count)
{
    return (value >> count) | (value << (32u - count));
}

static void q88_sha256_transform(q88_sha256_t *ctx, const uint8_t block[64])
{
    static const uint32_t constants[64] = {
        0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,
        0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
        0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,
        0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
        0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,
        0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
        0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,
        0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
        0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,
        0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
        0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,
        0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
        0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,
        0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
        0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,
        0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
    };
    uint32_t words[64];
    uint32_t a, b, c, d, e, f, g, h;
    unsigned i;

    for (i = 0; i < 16; i++) {
        words[i] = ((uint32_t)block[i * 4] << 24) |
                   ((uint32_t)block[i * 4 + 1] << 16) |
                   ((uint32_t)block[i * 4 + 2] << 8) |
                   (uint32_t)block[i * 4 + 3];
    }
    for (i = 16; i < 64; i++) {
        uint32_t s0 = q88_sha256_rotr(words[i - 15], 7) ^
                      q88_sha256_rotr(words[i - 15], 18) ^ (words[i - 15] >> 3);
        uint32_t s1 = q88_sha256_rotr(words[i - 2], 17) ^
                      q88_sha256_rotr(words[i - 2], 19) ^ (words[i - 2] >> 10);
        words[i] = words[i - 16] + s0 + words[i - 7] + s1;
    }
    a = ctx->state[0]; b = ctx->state[1]; c = ctx->state[2]; d = ctx->state[3];
    e = ctx->state[4]; f = ctx->state[5]; g = ctx->state[6]; h = ctx->state[7];
    for (i = 0; i < 64; i++) {
        uint32_t sum1 = q88_sha256_rotr(e, 6) ^ q88_sha256_rotr(e, 11) ^
                        q88_sha256_rotr(e, 25);
        uint32_t choose = (e & f) ^ ((~e) & g);
        uint32_t temp1 = h + sum1 + choose + constants[i] + words[i];
        uint32_t sum0 = q88_sha256_rotr(a, 2) ^ q88_sha256_rotr(a, 13) ^
                        q88_sha256_rotr(a, 22);
        uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = sum0 + majority;
        h = g; g = f; f = e; e = d + temp1;
        d = c; c = b; b = a; a = temp1 + temp2;
    }
    ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c; ctx->state[3] += d;
    ctx->state[4] += e; ctx->state[5] += f; ctx->state[6] += g; ctx->state[7] += h;
}

static void q88_sha256_init(q88_sha256_t *ctx)
{
    static const uint32_t initial[8] = {
        0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
        0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u
    };
    memcpy(ctx->state, initial, sizeof(initial));
    ctx->bit_count = 0;
    ctx->block_len = 0;
}

static void q88_sha256_update(q88_sha256_t *ctx, const void *data_value, size_t len)
{
    const uint8_t *data = (const uint8_t *)data_value;
    ctx->bit_count += (uint64_t)len * 8u;
    while (len > 0) {
        size_t room = sizeof(ctx->block) - ctx->block_len;
        size_t take = len < room ? len : room;
        memcpy(ctx->block + ctx->block_len, data, take);
        ctx->block_len += take;
        data += take;
        len -= take;
        if (ctx->block_len == sizeof(ctx->block)) {
            q88_sha256_transform(ctx, ctx->block);
            ctx->block_len = 0;
        }
    }
}

static void q88_sha256_final(q88_sha256_t *ctx, uint8_t digest[32])
{
    uint64_t bits = ctx->bit_count;
    unsigned i;
    ctx->block[ctx->block_len++] = 0x80;
    if (ctx->block_len > 56) {
        while (ctx->block_len < 64) ctx->block[ctx->block_len++] = 0;
        q88_sha256_transform(ctx, ctx->block);
        ctx->block_len = 0;
    }
    while (ctx->block_len < 56) ctx->block[ctx->block_len++] = 0;
    for (i = 0; i < 8; i++)
        ctx->block[56 + i] = (uint8_t)(bits >> (56u - i * 8u));
    q88_sha256_transform(ctx, ctx->block);
    for (i = 0; i < 8; i++) {
        digest[i * 4] = (uint8_t)(ctx->state[i] >> 24);
        digest[i * 4 + 1] = (uint8_t)(ctx->state[i] >> 16);
        digest[i * 4 + 2] = (uint8_t)(ctx->state[i] >> 8);
        digest[i * 4 + 3] = (uint8_t)ctx->state[i];
    }
}

static void q88_sha256_hex(const uint8_t digest[32], char hex[65])
{
    static const char digits[] = "0123456789abcdef";
    unsigned i;
    for (i = 0; i < 32; i++) {
        hex[i * 2] = digits[digest[i] >> 4];
        hex[i * 2 + 1] = digits[digest[i] & 15];
    }
    hex[64] = '\0';
}

typedef struct {
    unsigned physical_row;
    unsigned char_count;
    char sha256[65];
} q88_screen_signature_row_t;

typedef struct {
    char snapshot_id[Q88_SCREEN_SIGNATURE_ID_MAX + 1];
    unsigned frame;
    int done;
    unsigned line_count;
    unsigned char_count;
    char sha256[65];
    q88_screen_signature_row_t rows[Q88_SCREEN_SIGNATURE_ROWS];
} q88_screen_signature_t;

static void q88_screen_signature_hash_row(q88_sha256_t *ctx, unsigned row,
                                          const char *body, size_t body_len)
{
    char prefix[16];
    int prefix_len = snprintf(prefix, sizeof(prefix), "%u\t", row);
    q88_sha256_update(ctx, prefix, (size_t)prefix_len);
    q88_sha256_update(ctx, body, body_len);
    q88_sha256_update(ctx, "\n", 1);
}

/* p_text() の80桁を既存 write_screen()/check_l3_screen_output.py と同じく
 * ASCII可視文字へ写し、空行を除き、末尾空白だけを落とす。その後は strip、
 * 大小変換、空白圧縮を一切行わない。本文はこの関数の外へ返さない。 */
static void q88_screen_signature_capture(q88_screen_signature_t *out,
                                         const uint8_t screen[Q88_SCREEN_SIGNATURE_ROWS *
                                                              Q88_SCREEN_SIGNATURE_COLS])
{
    q88_sha256_t whole;
    unsigned row, col;
    q88_sha256_init(&whole);
    out->line_count = 0;
    out->char_count = 0;
    for (row = 0; row < Q88_SCREEN_SIGNATURE_ROWS; row++) {
        char body[Q88_SCREEN_SIGNATURE_COLS];
        size_t body_len = Q88_SCREEN_SIGNATURE_COLS;
        int any = 0;
        q88_sha256_t one;
        uint8_t digest[32];
        q88_screen_signature_row_t *result;
        for (col = 0; col < Q88_SCREEN_SIGNATURE_COLS; col++) {
            uint8_t value = screen[row * Q88_SCREEN_SIGNATURE_COLS + col];
            body[col] = (value >= 0x20 && value < 0x7f) ? (char)value : ' ';
            if (value >= 0x21 && value < 0x7f) any = 1;
        }
        while (body_len > 0 && body[body_len - 1] == ' ') body_len--;
        if (!any) continue;
        result = &out->rows[out->line_count++];
        result->physical_row = row;
        result->char_count = (unsigned)body_len;
        q88_sha256_init(&one);
        q88_screen_signature_hash_row(&one, row, body, body_len);
        q88_sha256_final(&one, digest);
        q88_sha256_hex(digest, result->sha256);
        q88_screen_signature_hash_row(&whole, row, body, body_len);
        out->char_count += (unsigned)body_len;
    }
    {
        uint8_t digest[32];
        q88_sha256_final(&whole, digest);
        q88_sha256_hex(digest, out->sha256);
    }
    out->done = 1;
}

/* TSVの名前は事前登録で許した6種だけに限定する。自由記述欄は設けない。
 * snapshot_id は呼出側で [A-Za-z0-9_.-]+ を検証済み。 */
static int q88_screen_signature_write_report(FILE *fp,
                                             const q88_screen_signature_t *items,
                                             int count)
{
    int i;
    for (i = 0; i < count; i++) {
        unsigned row;
        fprintf(fp, "snapshot_id\t%s\n", items[i].snapshot_id);
        fprintf(fp, "physical_row\tchar_count\tsha256\n");
        for (row = 0; row < items[i].line_count; row++) {
            const q88_screen_signature_row_t *value = &items[i].rows[row];
            fprintf(fp, "%u\t%u\t%s\n", value->physical_row,
                    value->char_count, value->sha256);
        }
        fprintf(fp, "line_count\t%u\n", items[i].line_count);
        fprintf(fp, "char_count\t%u\n", items[i].char_count);
        fprintf(fp, "sha256\t%s\n", items[i].sha256);
    }
    return ferror(fp) ? 0 : 1;
}

#endif

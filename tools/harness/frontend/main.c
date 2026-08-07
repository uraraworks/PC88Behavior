/*
 * q88measure — PC88Behavior 計測ハーネスのフロントエンド
 *
 * libretro コアを dlopen し、RetroArch を介さずに直接回す。
 * ファジングでは決定論的に走らせたいので、フレームループを自分で握る必要がある。
 * 画面も音も入力も要らないので、コールバックはすべて捨てる。
 *
 * 出力するのは「どの番地に、どの種類のアクセスがあったか」だけ。
 * ROM の内容は読まないし出さない。
 *
 * 使い方:
 *   q88measure --core <core.so|dylib> --rom-dir <dir> [--disk <a.d88>]
 *              [--frames N] [--out <file>] [--expect-exec ADDR]...
 *
 *   --rom-dir      公式 ROM の置き場。PC88_REF_ROM_DIR でも指定できる
 *   --frames       走らせるフレーム数（既定 600 ≒ 10 秒）
 *   --out          採取結果の書き出し先（省略時は書かない）
 *   --expect-exec  この番地が実行されていなければ異常終了する。
 *                  フックが末端まで生きていることを検査するために使う
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <dlfcn.h>

#include "libretro.h"
#include "q88h_trace.h"

/* ---- コアの関数ポインタ ------------------------------------------------ */
static void (*p_set_environment)(retro_environment_t);
static void (*p_set_video_refresh)(retro_video_refresh_t);
static void (*p_set_audio_sample)(retro_audio_sample_t);
static void (*p_set_audio_sample_batch)(retro_audio_sample_batch_t);
static void (*p_set_input_poll)(retro_input_poll_t);
static void (*p_set_input_state)(retro_input_state_t);
static void (*p_init)(void);
static void (*p_deinit)(void);
static bool (*p_load_game)(const struct retro_game_info *);
static void (*p_unload_game)(void);
static void (*p_run)(void);
static void (*p_get_system_av_info)(struct retro_system_av_info *);

static q88h_trace_t *(*p_trace)(void);
static void          (*p_trace_reset)(void);
static void          (*p_text)(uint8_t *, uint32_t, uint32_t, uint32_t);

/* ---- 設定 -------------------------------------------------------------- */
static char g_rom_dir[1024] = { 0 };
static bool g_verbose       = false;

/* ---- キー入力の再生 -----------------------------------------------------
 * アイドル起動だけを測っても需要は増えない。ROM はキーボードを走査して
 * 待っているだけで、入力が無ければ新しい経路は踏まれないため。
 * 決まった打鍵列を決まったフレームで再生し、条件を再現可能にする。
 *
 * コアは handle_key(KEY88_A + i, RETROK_a + i) のように写しているので、
 * 英字は小文字の RETROK コードを送れば大文字として入る。
 * 32〜63 の記号・数字は handle_key(i, i) でそのまま通る。
 * ------------------------------------------------------------------------ */
#define MAX_KEYSTROKES 512

typedef struct { unsigned start, end; uint16_t key; int shift; } keyev_t;
static keyev_t  g_keyev[MAX_KEYSTROKES];
static int      g_n_keyev = 0;
static unsigned g_frame   = 0;

/* PC-88 のキーボードで SHIFT が要る文字と、その土台になるキー。
 *
 * コアは KEY88 コードをそのまま受け取るので、ASCII をそのまま送ると
 * 「そのキーの非シフト側の文字」が入る。実際 '=' が '-' に、'*' が ':' に
 * なっていた（測定結果の画面を見て気づいた。数字だけ見ていたら
 * 「BASIC が動いた」と誤認したまま進んでいた）。
 *
 * JIS 配列の刻印どおりの対応:
 *   ! " # $ % & ' ( )  →  1 2 3 4 5 6 7 8 9
 *   =  →  -      +  →  ;      *  →  :
 *   <  →  ,      >  →  .      ?  →  /
 */
static const struct { char ch; char base; } SHIFTED[] = {
    { '!', '1' }, { '"', '2' }, { '#', '3' }, { '$', '4' }, { '%', '5' },
    { '&', '6' }, { '\'', '7' }, { '(', '8' }, { ')', '9' },
    { '=', '-' }, { '+', ';' }, { '*', ':' },
    { '<', ',' }, { '>', '.' }, { '?', '/' },
};

/* ASCII 1 文字を (RETROK コード, SHIFT の要否) に直す。打てない文字は 0 */
static uint16_t ascii_to_retrok(char c, int *need_shift)
{
    size_t i;
    *need_shift = 0;
    if (c >= 'A' && c <= 'Z') return (uint16_t)(RETROK_a + (c - 'A'));
    if (c >= 'a' && c <= 'z') return (uint16_t)(RETROK_a + (c - 'a'));
    if (c == '\n' || c == '\r') return RETROK_RETURN;
    for (i = 0; i < sizeof(SHIFTED)/sizeof(SHIFTED[0]); i++) {
        if (SHIFTED[i].ch == c) { *need_shift = 1; return (uint16_t)SHIFTED[i].base; }
    }
    if ((unsigned char)c >= 32 && (unsigned char)c < 64) return (uint16_t)c;
    return 0;
}

/* 打鍵列を組み立てる。hold フレーム押して gap フレーム離す */
static int schedule_typing(const char *text, unsigned at,
                           unsigned hold, unsigned gap)
{
    unsigned t = at;
    for (; *text; text++) {
        uint16_t k;
        int shift = 0;
        if (text[0] == '\\' && text[1] == 'n') { k = RETROK_RETURN; text++; }
        else k = ascii_to_retrok(*text, &shift);

        if (!k) {
            fprintf(stderr, "[q88measure] 打てない文字を無視: 0x%02X\n",
                    (unsigned char)*text);
            continue;
        }
        if (g_n_keyev >= MAX_KEYSTROKES) {
            fprintf(stderr, "[q88measure] 打鍵列が長すぎる\n");
            return 0;
        }
        g_keyev[g_n_keyev].start = t;
        g_keyev[g_n_keyev].end   = t + hold;
        g_keyev[g_n_keyev].key   = k;
        g_keyev[g_n_keyev].shift = shift;
        g_n_keyev++;
        t += hold + gap;
    }
    return 1;
}

/* ---- libretro コールバック --------------------------------------------- */

static void log_printf(enum retro_log_level level, const char *fmt, ...)
{
    static const char *tag[] = { "DEBUG", "INFO", "WARN", "ERROR" };
    va_list ap;
    if (level == RETRO_LOG_DEBUG && !g_verbose)
        return;
    fprintf(stderr, "[core:%s] ", tag[level < 4 ? level : 1]);
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

static bool environment_cb(unsigned cmd, void *data)
{
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
        ((struct retro_log_callback *)data)->log = log_printf;
        return true;

    /* ROM の探索はここで渡すディレクトリが起点になる。
     * コアは <dir>/quasi88/<name> と <dir>/<name> を見る。 */
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_CORE_ASSETS_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = g_rom_dir;
        return true;

    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        return true;   /* 画面は捨てるので何でもよい */

    case RETRO_ENVIRONMENT_GET_VARIABLE:
        ((struct retro_variable *)data)->value = NULL;  /* 既定値を使わせる */
        return false;

    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool *)data = false;
        return true;

    case RETRO_ENVIRONMENT_GET_CAN_DUPE:
        *(bool *)data = true;
        return true;

    case RETRO_ENVIRONMENT_SET_VARIABLES:
    case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO:
        return true;

    default:
        return false;   /* 知らないものは黙って断る */
    }
}

static void video_cb(const void *d, unsigned w, unsigned h, size_t p)
{ (void)d; (void)w; (void)h; (void)p; }

static void audio_cb(int16_t l, int16_t r) { (void)l; (void)r; }
static size_t audio_batch_cb(const int16_t *d, size_t f) { (void)d; return f; }
static void input_poll_cb(void) { }
static int16_t input_state_cb(unsigned port, unsigned device,
                              unsigned index, unsigned id)
{
    int i;
    (void)port; (void)index;
    if (device != RETRO_DEVICE_KEYBOARD)
        return 0;
    for (i = 0; i < g_n_keyev; i++) {
        if (g_frame < g_keyev[i].start || g_frame >= g_keyev[i].end)
            continue;
        if (g_keyev[i].key == id)
            return 1;
        /* SHIFT は土台のキーと同じ区間だけ押しておく */
        if (g_keyev[i].shift && id == RETROK_LSHIFT)
            return 1;
    }
    return 0;
}

/* ---- コアの読み込み ---------------------------------------------------- */

#define SYM(var, name)                                                       \
    do {                                                                     \
        *(void **)(&var) = dlsym(h, name);                                   \
        if (!var) { fprintf(stderr, "シンボルが無い: %s\n", name); return false; } \
    } while (0)

static bool load_core(const char *path)
{
    void *h = dlopen(path, RTLD_NOW);
    if (!h) { fprintf(stderr, "コアを開けない: %s\n", dlerror()); return false; }

    SYM(p_set_environment,        "retro_set_environment");
    SYM(p_set_video_refresh,      "retro_set_video_refresh");
    SYM(p_set_audio_sample,       "retro_set_audio_sample");
    SYM(p_set_audio_sample_batch, "retro_set_audio_sample_batch");
    SYM(p_set_input_poll,         "retro_set_input_poll");
    SYM(p_set_input_state,        "retro_set_input_state");
    SYM(p_init,                   "retro_init");
    SYM(p_deinit,                 "retro_deinit");
    SYM(p_load_game,              "retro_load_game");
    SYM(p_unload_game,            "retro_unload_game");
    SYM(p_run,                    "retro_run");
    SYM(p_get_system_av_info,     "retro_get_system_av_info");

    /* 計測フックが入っていないコアを黙って使うと、
     * 「アクセスが無かった」と「観測していない」の区別がつかなくなる。 */
    SYM(p_trace,       "retro_q88h_trace");
    SYM(p_trace_reset, "retro_q88h_trace_reset");
    SYM(p_text,        "retro_q88h_text");
    return true;
}

/* ---- 採取結果の出力 ---------------------------------------------------- */

/* 連続する区間にまとめて出す。番地の羅列は読めないので */
static void dump_ranges(FILE *fp, const char *label,
                        const uint8_t *map, size_t n)
{
    size_t i = 0;
    unsigned count = 0;
    fprintf(fp, "[%s]\n", label);
    while (i < n) {
        if (map[i]) {
            size_t start = i;
            while (i < n && map[i]) i++;
            fprintf(fp, "  %04zX-%04zX  (%zu)\n", start, i - 1, i - start);
            count++;
        } else i++;
    }
    if (!count) fprintf(fp, "  (なし)\n");
}

static const char *g_typed = NULL;
static void (*p_text_fn)(uint8_t *, uint32_t, uint32_t, uint32_t);

/* テキスト画面を人が読める形で書き出す。
 * 測定結果に残すのは「その条件が意図どおりだったか」を結果自身で
 * 検証できるようにするため。条件が違っていたのに気づかず数字だけ
 * 眺めるのが一番危ない（実際に一度やった）。 */
static void write_screen(FILE *fp)
{
    static uint8_t scr[Q88H_TEXT_ROWS * Q88H_TEXT_COLS];
    unsigned r, c;
    if (!p_text_fn) return;
    p_text_fn(scr, Q88H_TEXT_ROWS, Q88H_TEXT_COLS, Q88H_TEXT_STRIDE);
    fprintf(fp, "[測定終了時のテキスト画面]\n");
    for (r = 0; r < Q88H_TEXT_ROWS; r++) {
        char line[Q88H_TEXT_COLS + 1];
        int any = 0;
        for (c = 0; c < Q88H_TEXT_COLS; c++) {
            uint8_t v = scr[r * Q88H_TEXT_COLS + c];
            line[c] = (v >= 0x20 && v < 0x7F) ? (char)v : ' ';
            if (v >= 0x21 && v < 0x7F) any = 1;
        }
        line[Q88H_TEXT_COLS] = 0;
        while (c > 0 && line[c-1] == ' ') line[--c] = 0;
        if (any) fprintf(fp, "  %2u| %s\n", r, line);
    }
    fprintf(fp, "\n");
}

static void write_report(FILE *fp, const q88h_trace_t *t,
                         const char *core, const char *romdir,
                         const char *disk, unsigned frames)
{
    fprintf(fp, "# PC88Behavior バスアクセス採取結果\n");
    fprintf(fp, "# 記録しているのはアドレスとアクセス種別のみ。ROM の内容は含まない。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    fprintf(fp, "frames    : %u\n", frames);
    fprintf(fp, "type      : %s\n\n", g_typed ? g_typed : "(なし)");
    fprintf(fp, "総アクセス回数: exec=%llu read=%llu write=%llu in=%llu out=%llu\n\n",
            (unsigned long long)t->n_exec,  (unsigned long long)t->n_read,
            (unsigned long long)t->n_write, (unsigned long long)t->n_in,
            (unsigned long long)t->n_out);

    write_screen(fp);

    dump_ranges(fp, "実行された番地 (fetch)",       t->mem_exec,  Q88H_MEM_SIZE);
    dump_ranges(fp, "データとして読まれた番地",     t->mem_read,  Q88H_MEM_SIZE);
    dump_ranges(fp, "書き込まれた番地",             t->mem_write, Q88H_MEM_SIZE);
    dump_ranges(fp, "入力された I/O ポート",        t->io_in,     Q88H_IO_SIZE);
    dump_ranges(fp, "出力された I/O ポート",        t->io_out,    Q88H_IO_SIZE);
}

/* ---- main -------------------------------------------------------------- */

static void usage(void)
{
    fprintf(stderr,
        "使い方: q88measure --core <path> [--rom-dir <dir>] [--disk <path>]\n"
        "                   [--frames N] [--out <file>] [--verbose]\n"
        "                   [--type \"TEXT\"] [--type-at FRAME]\n"
        "                   [--key-hold N] [--key-gap N]\n"
        "                   [--expect-exec ADDR] [--expect-read ADDR]\n"
        "                   [--expect-write ADDR] [--expect-io-in PORT]\n"
        "                   [--expect-io-out PORT]\n");
}

int main(int argc, char **argv)
{
    const char *core = NULL, *disk = NULL, *out = NULL;
    unsigned frames = 600, next_at = 180, key_hold = 4, key_gap = 4;
    static char typed[1024]; size_t typed_len = 0;
    bool dump_text = false;
    /* 5 種類のフックをそれぞれ独立に検査できるようにしておく。
     * まとめて 1 つ確認しただけでは、どれが死んでいるか分からない。 */
    struct { const char *name; const uint8_t *map; size_t size; unsigned a[16]; int n; } chk[] = {
        { "exec",  NULL, Q88H_MEM_SIZE, {0}, 0 },
        { "read",  NULL, Q88H_MEM_SIZE, {0}, 0 },
        { "write", NULL, Q88H_MEM_SIZE, {0}, 0 },
        { "io-in", NULL, Q88H_IO_SIZE,  {0}, 0 },
        { "io-out",NULL, Q88H_IO_SIZE,  {0}, 0 },
    };
    const char *env;
    int i, k;

    if ((env = getenv("PC88_REF_ROM_DIR")))
        snprintf(g_rom_dir, sizeof(g_rom_dir), "%s", env);

    for (i = 1; i < argc; i++) {
        if      (!strcmp(argv[i], "--core")    && i + 1 < argc) core = argv[++i];
        else if (!strcmp(argv[i], "--disk")    && i + 1 < argc) disk = argv[++i];
        else if (!strcmp(argv[i], "--out")     && i + 1 < argc) out  = argv[++i];
        else if (!strcmp(argv[i], "--frames")  && i + 1 < argc) frames = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--rom-dir") && i + 1 < argc)
            snprintf(g_rom_dir, sizeof(g_rom_dir), "%s", argv[++i]);
        /* --type-at で打ち始めるフレームを決め、--type で打つ。
         * 何度でも繰り返せる。起動時の "How many files" のような
         * 途中のプロンプトを挟む場合に要る（実際に必要だった）。 */
        else if (!strcmp(argv[i], "--type-at")   && i + 1 < argc) next_at = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--type")      && i + 1 < argc) {
            const char *txt = argv[++i];
            if (!schedule_typing(txt, next_at, key_hold, key_gap)) return 1;
            next_at = g_n_keyev ? g_keyev[g_n_keyev - 1].end + key_gap : next_at;
            typed_len += (size_t)snprintf(typed + typed_len,
                                          sizeof(typed) - typed_len,
                                          "%s%s", typed_len ? " | " : "", txt);
        }
        else if (!strcmp(argv[i], "--key-hold")  && i + 1 < argc) key_hold= (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--key-gap")   && i + 1 < argc) key_gap = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--dump-text")) dump_text = true;
        else if (!strcmp(argv[i], "--verbose")) g_verbose = true;
        else {
            /* --expect-<種別> ADDR */
            int matched = 0;
            for (k = 0; k < 5; k++) {
                char opt[32];
                snprintf(opt, sizeof(opt), "--expect-%s", chk[k].name);
                if (!strcmp(argv[i], opt) && i + 1 < argc) {
                    if (chk[k].n < 16)
                        chk[k].a[chk[k].n++] = (unsigned)strtoul(argv[++i], NULL, 0);
                    matched = 1;
                    break;
                }
            }
            if (!matched) { usage(); return 2; }
        }
    }
    if (!core || !g_rom_dir[0]) { usage(); return 2; }

    /* 何を測ったのかが後から辿れるように、必ず出す。
     * ここが取り違えられていると測定結果そのものが無意味になる。 */
    fprintf(stderr, "[q88measure] core    = %s\n", core);
    fprintf(stderr, "[q88measure] rom-dir = %s\n", g_rom_dir);
    fprintf(stderr, "[q88measure] disk    = %s\n", disk ? disk : "(なし)");

    if (!load_core(core)) return 1;

    p_set_environment(environment_cb);
    p_set_video_refresh(video_cb);
    p_set_audio_sample(audio_cb);
    p_set_audio_sample_batch(audio_batch_cb);
    p_set_input_poll(input_poll_cb);
    p_set_input_state(input_state_cb);

    p_init();

    {
        struct retro_game_info info;
        memset(&info, 0, sizeof(info));
        info.path = disk;
        if (!p_load_game(disk ? &info : NULL)) {
            fprintf(stderr,
                "[q88measure] 起動に失敗した。公式 ROM が --rom-dir に揃っているか確認すること。\n"
                "             （疑似BIOSへのフォールバックは意図的に無効化してある）\n");
            p_deinit();
            return 1;
        }
    }

    if (g_n_keyev) {
        unsigned last = g_keyev[g_n_keyev - 1].end;
        g_typed = typed;
        fprintf(stderr, "[q88measure] 打鍵: %s (%d キー, フレーム %u まで)\n",
                typed, g_n_keyev, last);
        if (frames <= last)
            fprintf(stderr, "[q88measure] 警告: --frames %u は打鍵の終わり %u より短い。"
                            "打ち切られる\n", frames, last);
    }

    /* 測定区間はここから。ロード中のアクセスは数えない */
    p_trace_reset();
    for (g_frame = 0; g_frame < frames; g_frame++)
        p_run();

    {
        q88h_trace_t *t = p_trace();
        int failed = 0;

        if (t->magic != Q88H_TRACE_MAGIC) {
            fprintf(stderr, "[q88measure] 採取バッファが不正 (magic=%08X)\n", t->magic);
            return 1;
        }

        /* 打鍵やコマンドが本当に効いたかは、画面を見るのが一番確実。
         * 需要が増えていないとき、それが「その機能を使わなかった」のか
         * 「そもそも入力が届いていない」のかを区別できないと詰む。 */
        p_text_fn = p_text;
        if (dump_text) write_screen(stderr);

        write_report(stdout, t, core, g_rom_dir, disk, frames);
        if (out) {
            FILE *fp = fopen(out, "w");
            if (!fp) { perror(out); return 1; }
            write_report(fp, t, core, g_rom_dir, disk, frames);
            fclose(fp);
            fprintf(stderr, "[q88measure] 書き出した: %s\n", out);
        }

        /* フックが末端まで生きていることの検査。
         * 「アクセスが無かった」のか「観測できていなかった」のかを
         * 区別できないまま先へ進まないための関門。 */
        if (t->n_exec == 0) {
            fprintf(stderr, "[q88measure] NG: 実行アクセスが 1 件も記録されていない。"
                            "フックが繋がっていない可能性が高い。\n");
            failed = 1;
        }
        chk[0].map = t->mem_exec;  chk[1].map = t->mem_read;
        chk[2].map = t->mem_write; chk[3].map = t->io_in;
        chk[4].map = t->io_out;

        for (k = 0; k < 5; k++) {
            for (i = 0; i < chk[k].n; i++) {
                unsigned a = chk[k].a[i];
                if (a < chk[k].size && chk[k].map[a]) {
                    fprintf(stderr, "[q88measure] OK: %s %04X を観測\n", chk[k].name, a);
                } else {
                    fprintf(stderr, "[q88measure] NG: %s %04X が観測されていない\n",
                            chk[k].name, a);
                    failed = 1;
                }
            }
        }

        p_unload_game();
        p_deinit();
        return failed;
    }
}

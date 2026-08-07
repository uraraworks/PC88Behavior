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

/* ---- 設定 -------------------------------------------------------------- */
static char g_rom_dir[1024] = { 0 };
static bool g_verbose       = false;

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
static int16_t input_state_cb(unsigned a, unsigned b, unsigned c, unsigned d)
{ (void)a; (void)b; (void)c; (void)d; return 0; }

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

static void write_report(FILE *fp, const q88h_trace_t *t,
                         const char *core, const char *romdir,
                         const char *disk, unsigned frames)
{
    fprintf(fp, "# PC88Behavior バスアクセス採取結果\n");
    fprintf(fp, "# 記録しているのはアドレスとアクセス種別のみ。ROM の内容は含まない。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    fprintf(fp, "frames    : %u\n\n", frames);
    fprintf(fp, "総アクセス回数: exec=%llu read=%llu write=%llu in=%llu out=%llu\n\n",
            (unsigned long long)t->n_exec,  (unsigned long long)t->n_read,
            (unsigned long long)t->n_write, (unsigned long long)t->n_in,
            (unsigned long long)t->n_out);

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
        "                   [--expect-exec ADDR] [--expect-read ADDR]\n"
        "                   [--expect-write ADDR] [--expect-io-in PORT]\n"
        "                   [--expect-io-out PORT]\n");
}

int main(int argc, char **argv)
{
    const char *core = NULL, *disk = NULL, *out = NULL;
    unsigned frames = 600;
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

    /* 測定区間はここから。ロード中のアクセスは数えない */
    p_trace_reset();
    for (i = 0; i < (int)frames; i++)
        p_run();

    {
        q88h_trace_t *t = p_trace();
        int failed = 0;

        if (t->magic != Q88H_TRACE_MAGIC) {
            fprintf(stderr, "[q88measure] 採取バッファが不正 (magic=%08X)\n", t->magic);
            return 1;
        }

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

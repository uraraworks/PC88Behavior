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
#include "q88h_trap.h"
#include "q88h_iolog.h"
#include "q88h_intlog.h"
#include "q88h_fontsrc.h"

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
static q88h_trace_t *(*p_trace_sub)(void);
static void          (*p_trace_reset)(void);
static void          (*p_text)(uint8_t *, uint32_t, uint32_t, uint32_t);

/* トラップROM足場（M2）。無いコアもあり得るので dlsym は load_core とは
 * 別枠にして、失敗しても致命的にしない。「見つからなければ従来どおり
 * 動く」を守るため、機能全体を g_trap_available で束ねる。 */
static q88h_trap_t *(*p_trap)(void);
static q88h_trap_t *(*p_trap_sub)(void);
static void         (*p_trap_reset)(void);
static bool          g_trap_available = false;

/* 順序付き I/O 記録（M4）。トラップROM足場と同じ理由で、無いコアもあり得るので
 * 失敗を許す枠で dlsym する。「見つからなければ従来どおり動く」を守る。 */
static q88h_iolog_t *(*p_iolog)(void);
static q88h_iolog_t *(*p_iolog_sub)(void);
static void          (*p_iolog_reset)(void);
static void          (*p_iolog_set_enabled)(int);
static void          (*p_iolog_set_frame)(uint32_t);
static bool           g_iolog_available = false;

/* 割り込み受理ログ（M4c）。q88h_iolog と同じ理由で失敗を許す枠で dlsym する。 */
static q88h_intlog_t *(*p_intlog)(void);
static q88h_intlog_t *(*p_intlog_sub)(void);
static void           (*p_intlog_reset)(void);
static void           (*p_intlog_set_enabled)(int);
static void           (*p_intlog_set_frame)(uint32_t);
static bool            g_intlog_available = false;

/* フォント供給源の可視化（M5下ごしらえ）。他の計測フックと同じ理由で
 * 失敗を許す枠で dlsym する。「見つからなければ従来どおり動く」を守る。 */
static q88h_fontsrc_t *(*p_fontsrc)(void);
static void            (*p_fontsrc_reset)(void);
static bool             g_fontsrc_available = false;

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

/* ---- トラップROM足場（M2） --------------------------------------------- */

static char     g_trap_map_path[1024] = { 0 };
static uint8_t  g_trap_mode        = Q88H_TRAP_RET;
static unsigned g_trap_stop_after  = 0;   /* 0 = 無制限 */
static unsigned g_trap_dump_events = 20;  /* 発生順で出す先頭件数 */

static bool parse_hex_range(const char *s, unsigned *lo, unsigned *hi)
{
    const char *dash = strchr(s, '-');
    if (!dash) return false;
    *lo = (unsigned)strtoul(s, NULL, 16);
    *hi = (unsigned)strtoul(dash + 1, NULL, 16);
    return *lo <= *hi;
}

/* trap.map を読み、main/sub それぞれの trap->map にビットを立てる。
 * 書式は make_trap_rom.py の write_trap_map と対応させてある。 */
static bool load_trap_map(const char *path, q88h_trap_t *tmain, q88h_trap_t *tsub)
{
    FILE *fp = fopen(path, "r");
    char line[256];
    if (!fp) { fprintf(stderr, "[q88measure] trap-map を開けない: %s\n", path); return false; }

    while (fgets(line, sizeof(line), fp)) {
        char who[16] = {0}, range[64] = {0};
        char *p = line;
        unsigned lo, hi, a;
        q88h_trap_t *t;

        while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == '\n' || *p == '\0') continue;
        if (sscanf(p, "%15s %63s", who, range) != 2) continue;

        if (!parse_hex_range(range, &lo, &hi)) {
            fprintf(stderr, "[q88measure] trap-map の範囲を解釈できない: %s", line);
            fclose(fp); return false;
        }
        if (!strcmp(who, "main")) t = tmain;
        else if (!strcmp(who, "sub")) t = tsub;
        else {
            fprintf(stderr, "[q88measure] trap-map の対象が不明: %s\n", who);
            fclose(fp); return false;
        }
        for (a = lo; a <= hi && a <= 0xFFFF; a++) t->map[a] = 1;
    }
    fclose(fp);
    return true;
}

/* map 上でトラップ対象になっている番地のうち、実際にヒットした
 * （実行かデータかを問わない）ものの個数。--trap-stop-after の判定に使う。 */
static unsigned count_distinct_hits(const q88h_trap_t *t)
{
    unsigned i, n = 0;
    for (i = 0; i < 0x10000; i++)
        if (t->exec_hits[i] || t->data_hits[i]) n++;
    return n;
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
    SYM(p_trace_sub,   "retro_q88h_trace_sub");
    SYM(p_trace_reset, "retro_q88h_trace_reset");
    SYM(p_text,        "retro_q88h_text");

    /* トラップROM足場は M2 で足したばかりの機能なので、古いビルドのコアには
     * 無いことがある。SYM と違ってここは失敗を許す — 見つからなければ
     * g_trap_available を立てず、既存の測定は今までどおり動く。 */
    *(void **)(&p_trap)       = dlsym(h, "retro_q88h_trap");
    *(void **)(&p_trap_sub)   = dlsym(h, "retro_q88h_trap_sub");
    *(void **)(&p_trap_reset) = dlsym(h, "retro_q88h_trap_reset");
    g_trap_available = p_trap && p_trap_sub && p_trap_reset;
    if (!g_trap_available)
        fprintf(stderr, "[q88measure] 注記: このコアにトラップROM足場が無い。"
                        "トラップ関連オプションは無効化される\n");

    /* 順序付き I/O 記録（M4）も同様に、無いコアでは黙って機能を落とす。 */
    *(void **)(&p_iolog)              = dlsym(h, "retro_q88h_iolog");
    *(void **)(&p_iolog_sub)          = dlsym(h, "retro_q88h_iolog_sub");
    *(void **)(&p_iolog_reset)        = dlsym(h, "retro_q88h_iolog_reset");
    *(void **)(&p_iolog_set_enabled)  = dlsym(h, "retro_q88h_iolog_set_enabled");
    *(void **)(&p_iolog_set_frame)    = dlsym(h, "retro_q88h_iolog_set_frame");
    g_iolog_available = p_iolog && p_iolog_sub && p_iolog_reset
                      && p_iolog_set_enabled && p_iolog_set_frame;
    if (!g_iolog_available)
        fprintf(stderr, "[q88measure] 注記: このコアに順序付きI/O記録が無い。"
                        "--io-log は無効化される\n");

    /* 割り込み受理ログ（M4c）も同様に、無いコアでは黙って機能を落とす。 */
    *(void **)(&p_intlog)             = dlsym(h, "retro_q88h_intlog");
    *(void **)(&p_intlog_sub)         = dlsym(h, "retro_q88h_intlog_sub");
    *(void **)(&p_intlog_reset)       = dlsym(h, "retro_q88h_intlog_reset");
    *(void **)(&p_intlog_set_enabled) = dlsym(h, "retro_q88h_intlog_set_enabled");
    *(void **)(&p_intlog_set_frame)   = dlsym(h, "retro_q88h_intlog_set_frame");
    g_intlog_available = p_intlog && p_intlog_sub && p_intlog_reset
                       && p_intlog_set_enabled && p_intlog_set_frame;
    if (!g_intlog_available)
        fprintf(stderr, "[q88measure] 注記: このコアに割り込み受理ログが無い。"
                        "--int-log は無効化される\n");

    /* フォント供給源の可視化（M5下ごしらえ）も同様に、無いコアでは黙って機能を落とす。 */
    *(void **)(&p_fontsrc)       = dlsym(h, "retro_q88h_fontsrc");
    *(void **)(&p_fontsrc_reset) = dlsym(h, "retro_q88h_fontsrc_reset");
    g_fontsrc_available = p_fontsrc && p_fontsrc_reset;
    if (!g_fontsrc_available)
        fprintf(stderr, "[q88measure] 注記: このコアにフォント供給源記録が無い。"
                        "--font-log は無効化される\n");
    return true;
}

/* ---- 採取結果の出力 ---------------------------------------------------- */

/* 連続する区間にまとめて出す。番地の羅列は読めないので */
static void dump_ranges(FILE *fp, const char *label,
                        const uint8_t *map, size_t n)
{
    size_t i = 0;
    unsigned count = 0;
    fprintf(fp, "%s\n", label);
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

/* CPU 1 個分の採取結果を書く */
/* who は "メインCPU" のような CPU 名。見出しは "[メインCPU 実行された番地]" になる */
static void write_cpu(FILE *fp, const char *who, const q88h_trace_t *t)
{
    char label[80];
    fprintf(fp, "[%s] 総アクセス回数: exec=%llu read=%llu write=%llu in=%llu out=%llu\n\n",
            who,
            (unsigned long long)t->n_exec,  (unsigned long long)t->n_read,
            (unsigned long long)t->n_write, (unsigned long long)t->n_in,
            (unsigned long long)t->n_out);
    snprintf(label, sizeof(label), "[%s 実行された番地 (fetch)]", who);
    dump_ranges(fp, label, t->mem_exec, Q88H_MEM_SIZE);
    snprintf(label, sizeof(label), "[%s データとして読まれた番地]", who);
    dump_ranges(fp, label, t->mem_read, Q88H_MEM_SIZE);
    snprintf(label, sizeof(label), "[%s 書き込まれた番地]", who);
    dump_ranges(fp, label, t->mem_write, Q88H_MEM_SIZE);
    snprintf(label, sizeof(label), "[%s 入力された I/O ポート]", who);
    dump_ranges(fp, label, t->io_in, Q88H_IO_SIZE);
    snprintf(label, sizeof(label), "[%s 出力された I/O ポート]", who);
    dump_ranges(fp, label, t->io_out, Q88H_IO_SIZE);
    fprintf(fp, "\n");
}

/* トラップ発火の結果を書く。1件目のイベントを「代表」として使う —
 * 同じ番地への2回目以降の呼び出しは caller/prev_fetch が違うことがあるが、
 * まず「一度でも来たときの様子」が分かれば足場としては十分なため。
 *
 * prev_fetch は直前に fetch() で要求された番地であって、CPU の PC_prev
 * ではない（PC_prev は常に 0000 のまま更新されず使えなかった。実測で
 * 判明したのでパッチ側で自前に維持する値へ置き換えた）。また
 * 「直前に実行された命令の先頭番地」でもない点に注意 — プレフィクスや
 * オペランドのフェッチも同じ fetch() を通るので、直前命令の途中を
 * 指すことがある。 */
static void write_trap_cpu(FILE *fp, const char *who, const q88h_trap_t *t)
{
    unsigned i;
    unsigned n_exec_addr = 0, n_data_addr = 0;
    /* 番地ごとの代表イベント（最初に見つかった1件）へのポインタ。無ければ NULL */
    static const q88h_trap_ev_t *rep_exec[0x10000];
    static const q88h_trap_ev_t *rep_data[0x10000];

    memset((void *)rep_exec, 0, sizeof(rep_exec));
    memset((void *)rep_data, 0, sizeof(rep_data));
    for (i = 0; i < t->n_events; i++) {
        const q88h_trap_ev_t *e = &t->ev[i];
        if (e->kind == Q88H_TRAP_EXEC) { if (!rep_exec[e->addr]) rep_exec[e->addr] = e; }
        else                            { if (!rep_data[e->addr]) rep_data[e->addr] = e; }
    }

    fprintf(fp, "[トラップ %s] 要求された入口（実行）\n", who);
    for (i = 0; i < 0x10000; i++) {
        if (!t->exec_hits[i]) continue;
        n_exec_addr++;
        if (rep_exec[i])
            fprintf(fp, "  %04X  回数=%u  caller=%04X prev_fetch=%04X"
                        " AF=%04X BC=%04X DE=%04X HL=%04X\n",
                    i, t->exec_hits[i], rep_exec[i]->caller, rep_exec[i]->prev_fetch,
                    rep_exec[i]->af, rep_exec[i]->bc, rep_exec[i]->de, rep_exec[i]->hl);
        else
            fprintf(fp, "  %04X  回数=%u  （イベント取りこぼしで詳細無し）\n",
                    i, t->exec_hits[i]);
    }
    if (!n_exec_addr) fprintf(fp, "  (なし)\n");

    fprintf(fp, "[トラップ %s] 要求された番地（データ）\n", who);
    for (i = 0; i < 0x10000; i++) {
        if (!t->data_hits[i]) continue;
        n_data_addr++;
        fprintf(fp, "  %04X  回数=%u\n", i, t->data_hits[i]);
    }
    if (!n_data_addr) fprintf(fp, "  (なし)\n");

    fprintf(fp, "[トラップ %s] 発生順（先頭%u件）\n", who, g_trap_dump_events);
    if (!t->n_events) fprintf(fp, "  (なし)\n");
    for (i = 0; i < t->n_events && i < g_trap_dump_events; i++) {
        const q88h_trap_ev_t *e = &t->ev[i];
        fprintf(fp, "  seq=%-4u %-4s addr=%04X caller=%04X prev_fetch=%04X sp=%04X"
                    " AF=%04X BC=%04X DE=%04X HL=%04X\n",
                e->seq, e->kind == Q88H_TRAP_EXEC ? "EXEC" : "DATA",
                e->addr, e->caller, e->prev_fetch, e->sp, e->af, e->bc, e->de, e->hl);
    }

    fprintf(fp, "[トラップ %s] 取りこぼし: %u件 / 総イベント数: %u件\n",
            who, t->n_dropped, t->n_events);
    fprintf(fp, "[トラップ %s] 停止: %s",
            who, t->stopped ? "した" : "していない");
    if (t->stopped) fprintf(fp, " (番地=%04X)", t->stop_addr);
    fprintf(fp, "\n\n");
}

/* ---- 順序付き I/O 記録（M4）の書き出し ---------------------------------
 *
 * PC-88 はメインCPUとサブCPUが別々のZ80として並行に走る。それぞれの
 * q88h_iolog は自分のCPUの中でだけ通し番号(seq)が意味を持ち、CPUをまたいで
 * 比較しても「実際に起きた前後関係」にはならない。1本の列に混ぜて
 * 出すと「起きた順」だと誤解されるので、CPUごとに節を分けて出す。
 * この判断の理由はコア側（q88h_iolog.h）にも書いてある。 */
static void write_iolog_cpu(FILE *fp, const char *who, const q88h_iolog_t *l)
{
    uint32_t i;
    fprintf(fp, "# %s\n", who);
    fprintf(fp, "# seq  frame  cpu   kind  port  value  pc\n");
    if (!l->n_events) fprintf(fp, "# (記録されたイベントなし)\n");
    for (i = 0; i < l->n_events; i++) {
        const q88h_iolog_ev_t *e = &l->ev[i];
        fprintf(fp, "%6u %6u  %-4s  %-4s  %04X   %02X   %04X\n",
                e->seq, e->frame, who, e->kind == Q88H_IOLOG_OUT ? "OUT" : "IN",
                e->port, e->value, e->pc);
    }
    /* 0件でも必ず出す。無言で欠けるのが一番まずい */
    fprintf(fp, "# 取りこぼし: %u件 / 総イベント数: %u件\n\n", l->n_dropped, l->n_events);
}

static void write_iolog_report(FILE *fp, const char *core, const char *romdir,
                               const char *disk, unsigned frames,
                               const q88h_iolog_t *l, const q88h_iolog_t *ls)
{
    fprintf(fp, "# PC88Behavior 順序付き I/O 記録\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# 記録しているのは OUT/IN の発生順・ポート番号・値・発行元PC(直前PC)・\n");
    fprintf(fp, "# フレーム番号のみ。ROM の内容は含まない。\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# メインCPUとサブCPUは別々のZ80として並行に走っており、互いの\n");
    fprintf(fp, "# seq/frame を比較しても実際の前後関係にはならない。そのため\n");
    fprintf(fp, "# 1本の列に混ぜず、CPUごとに節を分けて出す（メイン→サブの順）。\n");
    fprintf(fp, "# 同一CPU内の節は seq の昇順＝発生順そのもの。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    fprintf(fp, "frames    : %u\n\n", frames);

    write_iolog_cpu(fp, "main", l);
    write_iolog_cpu(fp, "sub",  ls);
}

/* ---- 割り込み受理ログ（M4c）の書き出し ----------------------------------
 * 考え方は write_iolog_* と同じ。main/sub は別々に走る Z80 なので、
 * 混ぜて出すと前後関係を誤解させる。CPUごとに節を分ける。 */
static void write_intlog_cpu(FILE *fp, const char *who, const q88h_intlog_t *l)
{
    uint32_t i;
    fprintf(fp, "# %s\n", who);
    fprintf(fp, "# seq  frame  cpu   im  level  ret_pc  handler_pc\n");
    if (!l->n_events) fprintf(fp, "# (記録されたイベントなし)\n");
    for (i = 0; i < l->n_events; i++) {
        const q88h_intlog_ev_t *e = &l->ev[i];
        fprintf(fp, "%6u %6u  %-4s  %2u   %3u   %04X    %04X\n",
                e->seq, e->frame, who, e->im, e->level, e->ret_pc, e->handler_pc);
    }
    /* 0件でも必ず出す。無言で欠けるのが一番まずい（write_iolog_cpu と同じ理由） */
    fprintf(fp, "# 取りこぼし: %u件 / 総イベント数: %u件\n\n", l->n_dropped, l->n_events);
}

static void write_intlog_report(FILE *fp, const char *core, const char *romdir,
                                const char *disk, unsigned frames,
                                const q88h_intlog_t *l, const q88h_intlog_t *ls)
{
    fprintf(fp, "# PC88Behavior 割り込み受理ログ\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# 記録しているのは Z80 が割り込みを受理した事実そのもの——\n");
    fprintf(fp, "# 受理時の割り込みモード(im)・intr_ack()が返したレベル(level)・\n");
    fprintf(fp, "# 受理直前PC(ret_pc、スタックに積まれる戻り番地)・分岐後の\n");
    fprintf(fp, "# ハンドラ入口(handler_pc)・フレーム番号のみ。ROM の内容は含まない。\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# メインCPUとサブCPUは別々のZ80として並行に走っており、互いの\n");
    fprintf(fp, "# seq/frame を比較しても実際の前後関係にはならない。そのため\n");
    fprintf(fp, "# 1本の列に混ぜず、CPUごとに節を分けて出す（メイン→サブの順）。\n");
    fprintf(fp, "# 同一CPU内の節は seq の昇順＝発生順そのもの。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    fprintf(fp, "frames    : %u\n\n", frames);

    write_intlog_cpu(fp, "main", l);
    write_intlog_cpu(fp, "sub",  ls);
}

/* ---- フォント供給源の可視化（M5下ごしらえ）の書き出し ---------------------
 * q88h_fontsrc は main/sub のようなCPU単位ではなく、font_mem 系6領域単位。
 * 出すのは領域名・供給源タグ・書き込み回数・CRC32 のみ——グリフのバイト列は
 * 一切出さない（q88h_fontsrc.h 冒頭のコメント参照）。 */
static const char *fontsrc_region_name(int region)
{
    switch (region) {
    case Q88H_FONTSRC_REGION_FONT1_ANK:   return "font_mem  ANK  (画面へ出る)";
    case Q88H_FONTSRC_REGION_FONT1_GRAPH: return "font_mem  GRAPH(画面へ出る)";
    case Q88H_FONTSRC_REGION_FONT2_ANK:   return "font_mem2 ANK  (死んだ経路)";
    case Q88H_FONTSRC_REGION_FONT2_GRAPH: return "font_mem2 GRAPH(死んだ経路)";
    case Q88H_FONTSRC_REGION_FONT3_ANK:   return "font_mem3 ANK  (死んだ経路)";
    case Q88H_FONTSRC_REGION_FONT3_GRAPH: return "font_mem3 GRAPH(死んだ経路)";
    default:                              return "?";
    }
}

static const char *fontsrc_tag_name(uint8_t src)
{
    switch (src) {
    case Q88H_FONTSRC_NONE:            return "NONE(未設定)";
    case Q88H_FONTSRC_ROM_FILE:        return "ROM_FILE(外部ファイルの内容そのまま)";
    case Q88H_FONTSRC_KANJI_DERIVED:   return "KANJI_DERIVED(漢字ROM由来)";
    case Q88H_FONTSRC_UNAVAILABLE:     return "UNAVAILABLE(代替データ無し・0埋め)";
    case Q88H_FONTSRC_BUILTIN_UNKNOWN: return "BUILTIN_UNKNOWN(出所不明の内蔵データ)";
    default:                           return "?";
    }
}

static void write_fontsrc_report(FILE *fp, const char *core, const char *romdir,
                                 const char *disk, unsigned frames,
                                 const q88h_fontsrc_t *f)
{
    int i;
    fprintf(fp, "# PC88Behavior フォント供給源記録\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# 記録しているのは font_mem/font_mem2/font_mem3 の各領域が、\n");
    fprintf(fp, "# どの供給源で・何回書き込まれたかというタグと件数、そして\n");
    fprintf(fp, "# 内容の CRC32 のみ。グリフのバイト列は一切出力しない。\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# 書き込み回数が2以上の領域は、複数の経路が同じ領域を上書きした\n");
    fprintf(fp, "# ことを示す（docs/spec/l2-font.md 3節が問題にした二重ロードの兆候）。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    fprintf(fp, "frames    : %u\n\n", frames);

    fprintf(fp, "# region                          source                                    writes  crc32\n");
    for (i = 0; i < Q88H_FONTSRC_REGION_COUNT; i++) {
        fprintf(fp, "  %-32s %-42s %6u  %08X\n",
                fontsrc_region_name(i), fontsrc_tag_name(f->region_src[i]),
                f->region_writes[i], f->region_crc32[i]);
    }
    fprintf(fp, "\n");
}

static void write_report(FILE *fp, const q88h_trace_t *t, const q88h_trace_t *ts,
                         const q88h_trap_t *tp, const q88h_trap_t *tps,
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
    write_screen(fp);

    /* PC-88 は Z80 が 2 個。サブ ROM も再実装対象なので別々に出す。 */
    write_cpu(fp, "メインCPU", t);
    write_cpu(fp, "サブCPU",   ts);

    if (g_trap_available && tp && tps) {
        write_trap_cpu(fp, "メインCPU", tp);
        write_trap_cpu(fp, "サブCPU",   tps);
    }
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
        "                   [--expect-io-out PORT]\n"
        "                   [--trap-map FILE] [--trap-mode ret|stop]\n"
        "                   [--trap-stop-after N]\n"
        "                   [--expect-trap-exec ADDR] [--expect-trap-data ADDR]\n"
        "                   [--io-log FILE] [--int-log FILE] [--font-log FILE]\n");
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
    /* --expect-trap-exec / --expect-trap-data。既存の chk[] とは形が違う
     * （見る先が map ではなく exec_hits/data_hits）ので別立てにする。 */
    unsigned expect_trap_exec[16]; int n_expect_trap_exec = 0;
    unsigned expect_trap_data[16]; int n_expect_trap_data = 0;
    const char *io_log_path = NULL;
    const char *int_log_path = NULL;
    const char *font_log_path = NULL;
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
        else if (!strcmp(argv[i], "--trap-map") && i + 1 < argc)
            snprintf(g_trap_map_path, sizeof(g_trap_map_path), "%s", argv[++i]);
        else if (!strcmp(argv[i], "--trap-mode") && i + 1 < argc) {
            const char *m = argv[++i];
            if      (!strcmp(m, "ret"))  g_trap_mode = Q88H_TRAP_RET;
            else if (!strcmp(m, "stop")) g_trap_mode = Q88H_TRAP_STOP;
            else { fprintf(stderr, "[q88measure] --trap-mode は ret か stop\n"); return 2; }
        }
        else if (!strcmp(argv[i], "--trap-stop-after") && i + 1 < argc)
            g_trap_stop_after = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--expect-trap-exec") && i + 1 < argc) {
            if (n_expect_trap_exec < 16)
                expect_trap_exec[n_expect_trap_exec++] = (unsigned)strtoul(argv[++i], NULL, 0);
            else ++i;
        }
        else if (!strcmp(argv[i], "--expect-trap-data") && i + 1 < argc) {
            if (n_expect_trap_data < 16)
                expect_trap_data[n_expect_trap_data++] = (unsigned)strtoul(argv[++i], NULL, 0);
            else ++i;
        }
        else if (!strcmp(argv[i], "--io-log") && i + 1 < argc)
            io_log_path = argv[++i];
        else if (!strcmp(argv[i], "--int-log") && i + 1 < argc)
            int_log_path = argv[++i];
        else if (!strcmp(argv[i], "--font-log") && i + 1 < argc)
            font_log_path = argv[++i];
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

    /* トラップの map/mode は load_game の後・フレームループの前に設定する。
     * retro_load_game より前に触ると、コア側の初期化でトラップ構造体が
     * 上書きされないという保証が無いため。 */
    if (g_trap_map_path[0]) {
        if (!g_trap_available) {
            fprintf(stderr, "[q88measure] 注記: --trap-map が指定されたが、"
                            "このコアにトラップROM足場が無いので無視する\n");
        } else {
            q88h_trap_t *tp = p_trap(), *tps = p_trap_sub();
            if (!load_trap_map(g_trap_map_path, tp, tps)) {
                p_deinit();
                return 1;
            }
            tp->mode  = g_trap_mode;
            tps->mode = g_trap_mode;
            fprintf(stderr, "[q88measure] トラップ有効: map=%s mode=%s\n",
                    g_trap_map_path, g_trap_mode == Q88H_TRAP_RET ? "ret" : "stop");
        }
    }

    /* 順序付き I/O 記録（M4）も trap と同じく load_game の後・
     * フレームループの前に有効化する。既定は off なので、--io-log が
     * 指定されない限り記録用の巨大バッファへは一切書かない。 */
    if (io_log_path) {
        if (!g_iolog_available) {
            fprintf(stderr, "[q88measure] 注記: --io-log が指定されたが、"
                            "このコアに順序付きI/O記録が無いので無視する\n");
        } else {
            p_iolog_reset();
            p_iolog_set_enabled(1);
            fprintf(stderr, "[q88measure] I/O記録 有効: out=%s\n", io_log_path);
        }
    }

    /* 割り込み受理ログ（M4c）も iolog と同じ位置・同じ理由で有効化する。 */
    if (int_log_path) {
        if (!g_intlog_available) {
            fprintf(stderr, "[q88measure] 注記: --int-log が指定されたが、"
                            "このコアに割り込み受理ログが無いので無視する\n");
        } else {
            p_intlog_reset();
            p_intlog_set_enabled(1);
            fprintf(stderr, "[q88measure] 割り込み受理ログ 有効: out=%s\n", int_log_path);
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
    if (g_trap_available && g_trap_map_path[0]) p_trap_reset();
    for (g_frame = 0; g_frame < frames; g_frame++) {
        /* イベントに frame を載せるため、走らせる前に必ず今のフレーム番号を
         * コア側へ渡す。有効化されていなくても呼ぶコスト自体は軽い。 */
        if (g_iolog_available) p_iolog_set_frame(g_frame);
        if (g_intlog_available) p_intlog_set_frame(g_frame);

        p_run();

        if (g_trap_available && g_trap_map_path[0]) {
            q88h_trap_t *tp = p_trap(), *tps = p_trap_sub();
            if (tp->stopped || tps->stopped) {
                fprintf(stderr, "[q88measure] トラップで停止: フレーム=%u"
                                " メイン=%s(%04X) サブ=%s(%04X)\n",
                        g_frame,
                        tp->stopped  ? "停止" : "-", tp->stop_addr,
                        tps->stopped ? "停止" : "-", tps->stop_addr);
                g_frame++;
                break;
            }
            if (g_trap_stop_after > 0 &&
                count_distinct_hits(tp) + count_distinct_hits(tps) >= g_trap_stop_after) {
                fprintf(stderr, "[q88measure] トラップ: 相異なる要求番地が %u件に達したので"
                                "フレーム=%u で打ち切り\n", g_trap_stop_after, g_frame);
                g_frame++;
                break;
            }
        }
    }

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

        {
            q88h_trap_t *tp  = (g_trap_available && g_trap_map_path[0]) ? p_trap()     : NULL;
            q88h_trap_t *tps = (g_trap_available && g_trap_map_path[0]) ? p_trap_sub() : NULL;

            write_report(stdout, t, p_trace_sub(), tp, tps, core, g_rom_dir, disk, frames);
            if (out) {
                FILE *fp = fopen(out, "w");
                if (!fp) { perror(out); return 1; }
                write_report(fp, t, p_trace_sub(), tp, tps, core, g_rom_dir, disk, frames);
                fclose(fp);
                fprintf(stderr, "[q88measure] 書き出した: %s\n", out);
            }

            /* 順序付き I/O 記録（M4）は --out の本体とは別ファイルに書く。
             * バスアクセス採取の集計結果（有無フラグ）とは性格が違うので
             * 混ぜない。 */
            if (io_log_path && g_iolog_available) {
                q88h_iolog_t *l  = p_iolog();
                q88h_iolog_t *ls = p_iolog_sub();
                FILE *fp = fopen(io_log_path, "w");
                if (!fp) { perror(io_log_path); return 1; }
                write_iolog_report(fp, core, g_rom_dir, disk, frames, l, ls);
                fclose(fp);
                fprintf(stderr, "[q88measure] I/O記録を書き出した: %s"
                                " (main: %u件/取りこぼし%u件, sub: %u件/取りこぼし%u件)\n",
                        io_log_path, l->n_events, l->n_dropped, ls->n_events, ls->n_dropped);
            }

            /* 割り込み受理ログ（M4c）も --io-log と同じく別ファイルに書く。
             * 性格が違う記録を混ぜないという方針を踏襲する。 */
            if (int_log_path && g_intlog_available) {
                q88h_intlog_t *l  = p_intlog();
                q88h_intlog_t *ls = p_intlog_sub();
                FILE *fp = fopen(int_log_path, "w");
                if (!fp) { perror(int_log_path); return 1; }
                write_intlog_report(fp, core, g_rom_dir, disk, frames, l, ls);
                fclose(fp);
                fprintf(stderr, "[q88measure] 割り込み受理ログを書き出した: %s"
                                " (main: %u件/取りこぼし%u件, sub: %u件/取りこぼし%u件)\n",
                        int_log_path, l->n_events, l->n_dropped, ls->n_events, ls->n_dropped);
            }

            /* フォント供給源の可視化（M5下ごしらえ）も同じく別ファイルに書く。
             * iolog/intlogと違い、記録はフレームループではなく retro_init() の
             * 中（フォント読み込み）で起きるので、有効化/リセットの操作は
             * 要らない——プロセス起動ごとに毎回きれいな状態から始まる。 */
            if (font_log_path && g_fontsrc_available) {
                q88h_fontsrc_t *f = p_fontsrc();
                FILE *fp = fopen(font_log_path, "w");
                if (!fp) { perror(font_log_path); return 1; }
                write_fontsrc_report(fp, core, g_rom_dir, disk, frames, f);
                fclose(fp);
                fprintf(stderr, "[q88measure] フォント供給源記録を書き出した: %s\n",
                        font_log_path);
            }

            /* --expect-trap-exec / --expect-trap-data の検査。
             * exec_hits/data_hits を見る — map に入っているだけでは
             * 「対象にした」であって「実際に要求された」ではないため。 */
            if (n_expect_trap_exec || n_expect_trap_data) {
                if (!tp || !tps) {
                    fprintf(stderr, "[q88measure] NG: --expect-trap-* が指定されたが"
                                    "トラップが有効になっていない\n");
                    failed = 1;
                } else {
                    for (i = 0; i < n_expect_trap_exec; i++) {
                        unsigned a = expect_trap_exec[i];
                        unsigned hit = (a <= 0xFFFF) ? (tp->exec_hits[a] + tps->exec_hits[a]) : 0;
                        if (hit) fprintf(stderr, "[q88measure] OK: trap-exec %04X を観測 (回数=%u)\n", a, hit);
                        else     { fprintf(stderr, "[q88measure] NG: trap-exec %04X が観測されていない\n", a); failed = 1; }
                    }
                    for (i = 0; i < n_expect_trap_data; i++) {
                        unsigned a = expect_trap_data[i];
                        unsigned hit = (a <= 0xFFFF) ? (tp->data_hits[a] + tps->data_hits[a]) : 0;
                        if (hit) fprintf(stderr, "[q88measure] OK: trap-data %04X を観測 (回数=%u)\n", a, hit);
                        else     { fprintf(stderr, "[q88measure] NG: trap-data %04X が観測されていない\n", a); failed = 1; }
                    }
                }
            }
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

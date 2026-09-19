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
 *              [--disk2 <b.d88>]
 *              [--insert-disk2 <b.d88> --insert-disk2-at FRAME]
 *              [--frames N] [--out <file>] [--expect-exec ADDR]...
 *
 *   --rom-dir      公式 ROM の置き場。PC88_REF_ROM_DIR でも指定できる
 *   --frames       走らせるフレーム数（既定 600 ≒ 10 秒）
 *   --out          採取結果の書き出し先（省略時は書かない）
 *   --expect-exec  この番地が実行されていなければ異常終了する。
 *                  フックが末端まで生きていることを検査するために使う
 *
 *   --insert-disk2 / --insert-disk2-at
 *       起動時は DRIVE_2（B:）を空のまま走らせ、指定フレームになった
 *       retro_run() 呼び出しの直前に QUASI88 本体の quasi88_disk_insert()
 *       を dlsym 経由で呼んで媒体を差し込む（m7lw: B:媒体待ち中の途中
 *       差し込みを測るための器具）。両方必須の組で、片方だけの指定や
 *       --disk2 との同時指定、--frames 以上のFRAME指定はエラーにする。
 *       挿入直前まで filename_get_disk(1) が空であること、挿入直後に
 *       指定パスを返すことをそれぞれ末端で確認する。
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <dlfcn.h>
#include <sys/stat.h>

#include "libretro.h"
#include <limits.h>

#include "q88h_trace.h"
#include "q88h_trap.h"
#include "q88h_iolog.h"
#include "q88h_memlog.h"
#include "q88h_exchange_intervention.h"
#include "q88h_sub_interrupt_intervention.h"
#include "q88h_main_interrupt_intervention.h"
#include "q88h_intlog.h"
#include "q88h_fontsrc.h"
#include "q88h_screenshot.h"

/* --vram-dump / --mem-write-log の出力先安全策（禁止事項5/7）が使う、
 * このリポジトリ自身の実体パス。コンパイル時定数にはしない——
 * disk2_selftest.sh / insert_disk2_selftest.sh のように main.c を
 * Makefile を介さず直接 cc するスクリプトが既にあり、そこに新しい
 * 定義を強制すると既存の選択肢を静かに壊す。代わりに argv[0] から
 * 実行時に求める（g_repo_root, main() 冒頭で設定）。このバイナリは
 * 常に "<repo>/tools/harness/frontend/q88measure" に置かれる約束
 * （setup_harness.sh の疎通試験、各 *_selftest.sh のいずれも
 * この相対位置を前提にしている）ので、そこから4段上がれば求まる。 */
static char g_repo_root[PATH_MAX] = { 0 };

static void set_repo_root_from_argv0(const char *argv0)
{
    char real[PATH_MAX];
    int i;
    if (!realpath(argv0, real)) return;
    /* .../<repo>/tools/harness/frontend/q88measure から4段（q88measure・
     * frontend・harness・tools）上がって <repo> にする。 */
    for (i = 0; i < 4; i++) {
        char *slash = strrchr(real, '/');
        if (!slash) return;
        *slash = 0;
    }
    strncpy(g_repo_root, real, sizeof(g_repo_root) - 1);
}

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
static bool (*p_load_game_special)(unsigned, const struct retro_game_info *, size_t);
static void (*p_unload_game)(void);
static void (*p_run)(void);
static void (*p_reset)(void);
static void (*p_get_system_av_info)(struct retro_system_av_info *);

static q88h_trace_t *(*p_trace)(void);
static q88h_trace_t *(*p_trace_sub)(void);
static void          (*p_trace_reset)(void);
static void          (*p_text)(uint8_t *, uint32_t, uint32_t, uint32_t);

/* 二本ロード時の末端検査。QUASI88 は quasi88_disk_insert() が成功した後だけ
 * filename_get_disk() の返す状態へ実パスを保存する。単にspecialへ渡した引数を
 * 見直すのではなく、DRIVE_1/2への挿入が完了した後の状態を検査する。 */
static const char *(*p_filename_get_disk)(int);

/* m7lw: 実行中のDRIVE_2（B:）差し込み器具。QUASI88本体の
 * quasi88_disk_insert(drv, filename, image, ro) をdlsymで取る。既存の
 * filename_get_disk と同じ作法（無ければ機能を落とすのではなく、
 * --insert-disk2 使用時にだけ必須にする）。DRIVE_2 の値は vendor の
 * src/initval.h の enum { DRIVE_1, DRIVE_2, ... } により 1 固定
 * （GPLの第三者実装のソースで、公式ROMとは無関係）。 */
static int (*p_quasi88_disk_insert)(int, const char *, int, int);
enum { Q88_DRIVE_2 = 1 };

/* キーマトリクス直接操作（M7段階1の器具その2）。QUASI88本体の
 * key_scan[0x10]（vendor/quasi88-libretro/src/keyboard.c、IN 00h〜0Eh。
 * [15]はジョイスティック）をdlsymで直接取る。p_quasi88_disk_insertと
 * 同じ作法——公開データシンボル（nmで確認済み: S _key_scan）であり、
 * コアへパッチを当てずに済む。押されているビットは0（KEY88_ON/OFF
 * マクロが押下でクリア・解放でセットする）。 */
static uint8_t *p_key_scan = NULL;
static bool     g_key_scan_available = false;

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

/* 範囲指定の書き込み記録（M7器具2）。iolog と同じ理由で失敗を許す枠で dlsym する。 */
static q88h_memlog_t *(*p_memlog)(void);
static void           (*p_memlog_reset)(void);
static void           (*p_memlog_set_enabled)(int);
static void           (*p_memlog_set_frame)(uint32_t);
static void           (*p_memlog_set_range)(uint32_t, uint32_t);
static bool            g_memlog_available = false;

/* 交換run介入。既存コアでも通常測定は続けられるが、オプション指定時は
 * シンボル・命中・実変更をすべて必須にして「指定したが効かなかった」を落とす。 */
static q88h_exchange_intervention_t *(*p_exchange_intervention)(void);
static void (*p_exchange_intervention_reset)(void);
static int (*p_exchange_intervention_configure)(unsigned, int32_t, uint8_t, uint8_t);
static int (*p_exchange_ready_handoff_configure)(int32_t, int32_t);
static bool g_exchange_intervention_available = false;

/* main→sub要求runの位置指定介入。既存の交換run介入とは別枠のシンボル群。 */
static q88h_request_intervention_t *(*p_request_intervention)(void);
static void (*p_request_intervention_reset)(void);
static int (*p_request_intervention_configure)(unsigned, int32_t, uint32_t, uint8_t, uint8_t);
static bool g_request_intervention_available = false;

/* sub→main応答runの位置指定介入。既存の交換run介入・要求run介入とは
 * 別枠のシンボル群。 */
static q88h_response_intervention_t *(*p_response_intervention)(void);
static void (*p_response_intervention_reset)(void);
static int (*p_response_intervention_configure)(unsigned, int32_t, uint32_t, uint8_t, uint8_t);
static bool g_response_intervention_available = false;

static q88h_sub_interrupt_intervention_t *(*p_sub_interrupt_intervention)(void);
static void (*p_sub_interrupt_intervention_reset)(void);
static int (*p_sub_interrupt_intervention_configure)(int32_t, int32_t, uint8_t);
static bool g_sub_interrupt_intervention_available = false;

/* m7lr: main側割り込み受理への介入。sub側と同じ形・同じく失敗を許す枠で dlsym する。 */
static q88h_main_interrupt_intervention_t *(*p_main_interrupt_intervention)(void);
static void (*p_main_interrupt_intervention_reset)(void);
static int (*p_main_interrupt_intervention_configure)(int32_t, int32_t, uint8_t);
static bool g_main_interrupt_intervention_available = false;

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

/* 画面ピクセルスナップショット（M5本題）。他の計測フックと同じ理由で
 * 失敗を許す枠で dlsym する。「見つからなければ従来どおり動く」を守る。 */
static q88h_screenshot_t *(*p_screenshot)(void);
static void               (*p_screenshot_capture)(void);
static bool                g_screenshot_available = false;

/* ---- 設定 -------------------------------------------------------------- */
static char g_rom_dir[1024] = { 0 };
static bool g_verbose       = false;
/* --type に打てない文字があったとき、既定では走行前に rc!=0 で止める
 * （m7hk後日: 以前は警告して黙って飛ばし、欠けた打鍵列のまま走行が正常
 * 終了していた）。意図して打てない文字を含む検査だけ --allow-untypable
 * で従来どおり警告のみに落とす。--type より前に指定すること
 * （--key-hold等と同じく、その時点の値をそれ以降の--typeが使う規則）。 */
static bool g_allow_untypable = false;
/* 既定では libretro コアが書込み差分を save directory の .srm に置く。
 * 二つの独立実行の間で「1回目がSAVEした使い捨てD88複製そのもの」を渡す
 * 測定だけは、コアの公開オプション q88_save_to_disk_image を明示的に有効に
 * する。指定しない既存測定の保存方式は変えない。 */
static bool g_save_to_disk_image = false;

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

/* テキストVRAMの写し（M7器具1）で --vram-dump/--vram-dump-at を
 * ペアとして受け付ける最大件数。usage() でも使うのでファイルスコープに置く。 */
#define VRAM_DUMP_MAX 16

/* キーマトリクス直接操作（M7段階1の器具その2）で --key-matrix を
 * 受け付ける最大件数。usage() でも使うのでファイルスコープに置く。 */
#define KEY_MATRIX_MAX 64

/* --key-matrix の実際の書き換え記録（press/release 各1件）。末端検査用に
 * frame・port・bit・書き換え前後の値だけを持つ——この器具自身が書いた値で
 * あって ROM・公式ディスクの内容ではないので、禁止事項5/7には当たらない。
 * write_report() の引数として渡すためファイルスコープの型にする。 */
typedef struct {
    unsigned frame, port, bit;
    uint8_t  before, after;
    const char *action;   /* "press" | "release" */
} kmrec_t;
#define KEY_MATRIX_RECORD_MAX (KEY_MATRIX_MAX * 2)

typedef struct { unsigned start, end; uint16_t key; int shift; } keyev_t;
static keyev_t  g_keyev[MAX_KEYSTROKES];
static int      g_n_keyev = 0;
static unsigned g_frame   = 0;
static const char *g_basic_mode = NULL;
/* q88_sub_cpu_mode: 未指定時は変更前と完全に同じ挙動（NULLを返す）にするため、
 * 明示指定があったときだけ g_sub_cpu_mode_set を立てる。requested はコアが
 * このキーを問い合わせた回数を無条件に数える（無指定でも数える）。 */
static char g_sub_cpu_mode[4]     = { 0 };
static bool g_sub_cpu_mode_set    = false;
static unsigned g_sub_cpu_mode_requested = 0;

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
 *
 * { | } ~ も同じ理由で追加した（M7）。コア(libretro.c 250〜255行付近)は
 *   for (i=0;i<64;i++) handle_key(i,i);                                 (a)
 *   for (i=0;i<6;i++)  handle_key(KEY88_BRACKETLEFT+i, RETROK_LEFTBRACKET+i);  (b)
 *   for (i=0;i<4;i++)  handle_key(KEY88_BRACELEFT+i,   RETROK_LEFTBRACE+i);    (c)
 * という3本のループでキーを受け取る。(b)は '[' '\' ']' '^' '_' '`' の6個
 * (KEY88コード91〜96)、(c)は '{' '|' '}' '~' の4個(123〜126)で、いずれも
 * RETROKの数値がASCIIと同じ(libretro.hで確認: LEFTBRACKET=91…BACKQUOTE=96,
 * LEFTBRACE=123…TILDE=126)。(a)の0-63(ASCII 0x20-0x3F)と同じ形で、コア
 * 自身はここでSHIFTを合成していない。
 *
 * それでもSHIFTが要るキーとがある。keyboard.c の keyport[] 表(KEY88コード
 * →実際のポート・ビット)を見ると:
 *   KEY88_BRACKETLEFT(91)= Port5 Bit3   KEY88_BRACELEFT (123)= Port5 Bit3
 *   KEY88_YEN(92)        = Port5 Bit4   KEY88_BAR       (124)= Port5 Bit4
 *   KEY88_BRACKETRIGHT(93)=Port5 Bit5   KEY88_BRACERIGHT(125)= Port5 Bit5
 *   KEY88_CARET(94)      = Port5 Bit6   KEY88_TILDE     (126)= Port5 Bit6
 * と、(b)と(c)の対応する4個は同じポート・ビットを指す(既存のSHIFTED[]の
 * '!'/'1'等が同じ Port6 Bit1 を共有するのとまったく同じ形)。同じビットを
 * 押すだけでは '[' と '{' はハードウェア的に区別が付かない。区別を作る
 * 手段は、その場にしか無い別のビット――SHIFTキー自身のビット
 * (KEY88_SHIFT/SHIFTL/SHIFTR はいずれも Port8 Bit6 を共有)――を同時に
 * 押すことだけなので、(c)の4個は「(b)側の土台+SHIFT」として送る。
 *
 * 一方 KEY88_UNDERSCORE(95, Port7 Bit7)にはビットを共有する対の相手が
 * keyport[]に無い(単独の物理キー)。KEY88_BACKQUOTE(96)は KEY88_AT(64,
 * Port2 Bit0)とビットを共有するが、AT はコアの libretro 経由では
 * handle_key が登録されておらず(main.c 上部のコメント/PLAN参照)、この
 * 経路からは触れない。(b)のループ自体がこの6個を「SHIFT無しでそのまま
 * 送る」対象として一括で扱っている(コアのソース上の事実。ROM/逆アセンブル
 * 由来ではない)ので、その分類にそのまま従い、_ と ` もSHIFT無しにする。
 */
static const struct { char ch; char base; } SHIFTED[] = {
    { '!', '1' }, { '"', '2' }, { '#', '3' }, { '$', '4' }, { '%', '5' },
    { '&', '6' }, { '\'', '7' }, { '(', '8' }, { ')', '9' },
    { '=', '-' }, { '+', ';' }, { '*', ':' },
    { '<', ',' }, { '>', '.' }, { '?', '/' },
    { '{', '[' }, { '|', '\\' }, { '}', ']' }, { '~', '^' },
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
        if (SHIFTED[i].ch == c) {
            char base = SHIFTED[i].base;
            /* 故障注入: '{' の土台キーをわざと誤らせる(本来は '[' 、
             * Port5 Bit3。'\' は Port5 Bit4)。key_matrix_bracesymbol_
             * selftest.sh がこの環境変数で検出力を確かめる。 */
            if (c == '{' && getenv("Q88MEASURE_FAULT_SWAP_BRACE_KEY"))
                base = '\\';
            *need_shift = 1;
            return (uint16_t)base;
        }
    }
    if ((unsigned char)c >= 32 && (unsigned char)c < 64) return (uint16_t)c;
    /* '[' '\' ']' '^' '_' '`' (0x5B-0x60)。コアの2本目のループ(b)が対象。
     * RETROKの数値はASCIIと同じなのでそのまま渡せばよい(--key-matrixの
     * key_matrix_selftest.shで既に確認済みの基礎機構の延長)。 */
    if ((unsigned char)c >= 0x5B && (unsigned char)c <= 0x60) return (uint16_t)c;
    return 0;
}

/* 打鍵列を組み立てる。hold フレーム押して gap フレーム離す。
 *
 * 打てない文字（ascii_to_retrok が0を返す文字）は、既定では走行を
 * 始める前に検出してエラー終了する（rc!=0）。以前は stderr に警告を
 * 出すだけで走行を続けており、警告を読み落とすと欠けた打鍵列のまま
 * 「正常終了」して測定が黙って壊れた。--allow-untypable 指定時、または
 * 検出力を確かめる故障注入（環境変数 Q88MEASURE_FAULT_SKIP_UNTYPABLE_CHECK）
 * のときだけ、従来どおり警告して読み飛ばす。 */
static int schedule_typing(const char *text, unsigned at,
                           unsigned hold, unsigned gap)
{
    unsigned t = at;
    unsigned idx = 0;
    for (; *text; text++) {
        uint16_t k;
        int shift = 0;
        idx++;
        if (text[0] == '\\' && text[1] == 'n') { k = RETROK_RETURN; text++; }
        else k = ascii_to_retrok(*text, &shift);

        if (!k) {
            if (g_allow_untypable ||
                getenv("Q88MEASURE_FAULT_SKIP_UNTYPABLE_CHECK")) {
                fprintf(stderr,
                        "[q88measure] 打てない文字を無視(%u文字目): 0x%02X\n",
                        idx, (unsigned char)*text);
                continue;
            }
            fprintf(stderr,
                    "[q88measure] --type に打てない文字がある(%u文字目): "
                    "0x%02X。打てるのは英字・ASCII 0x20-0x3F・SHIFT対応表"
                    "だけ。意図した文字なら --type より前に "
                    "--allow-untypable を指定すること\n",
                    idx, (unsigned char)*text);
            return 0;
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
        if (g_basic_mode && !strcmp(((struct retro_variable *)data)->key,
                                    "q88_basic_mode")) {
            ((struct retro_variable *)data)->value = g_basic_mode;
            return true;
        }
        if (g_save_to_disk_image &&
            !strcmp(((struct retro_variable *)data)->key,
                    "q88_save_to_disk_image")) {
            ((struct retro_variable *)data)->value = "enabled";
            return true;
        }
        if (!strcmp(((struct retro_variable *)data)->key, "q88_sub_cpu_mode")) {
            g_sub_cpu_mode_requested++;
            if (g_sub_cpu_mode_set) {
                ((struct retro_variable *)data)->value = g_sub_cpu_mode;
                return true;
            }
            ((struct retro_variable *)data)->value = NULL;  /* 既定値を使わせる */
            return false;
        }
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
    SYM(p_reset,                  "retro_reset");
    SYM(p_get_system_av_info,     "retro_get_system_av_info");

    /* 一枚だけの既存経路では要求しない。古いコアでも従来測定を変えないため、
     * 二本時にだけ呼出側で存在を必須にする。 */
    *(void **)(&p_load_game_special) = dlsym(h, "retro_load_game_special");
    *(void **)(&p_filename_get_disk) = dlsym(h, "filename_get_disk");
    *(void **)(&p_quasi88_disk_insert) = dlsym(h, "quasi88_disk_insert");

    /* キーマトリクス直接操作（M7段階1の器具その2）。無いコアもあり得るので
     * 他の計測フックと同じ理由で失敗を許す枠で dlsym する。
     * 「見つからなければ従来どおり動く（--key-matrix は無効化）」。 */
    *(void **)(&p_key_scan) = dlsym(h, "key_scan");
    g_key_scan_available = p_key_scan != NULL;
    if (!g_key_scan_available)
        fprintf(stderr, "[q88measure] 注記: このコアに key_scan シンボルが無い。"
                        "--key-matrix は無効化される\n");

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

    /* 範囲指定の書き込み記録（M7器具2）も同様に、無いコアでは黙って機能を落とす。 */
    *(void **)(&p_memlog)             = dlsym(h, "retro_q88h_memlog");
    *(void **)(&p_memlog_reset)       = dlsym(h, "retro_q88h_memlog_reset");
    *(void **)(&p_memlog_set_enabled) = dlsym(h, "retro_q88h_memlog_set_enabled");
    *(void **)(&p_memlog_set_frame)   = dlsym(h, "retro_q88h_memlog_set_frame");
    *(void **)(&p_memlog_set_range)   = dlsym(h, "retro_q88h_memlog_set_range");
    g_memlog_available = p_memlog && p_memlog_reset && p_memlog_set_enabled
                       && p_memlog_set_frame && p_memlog_set_range;
    if (!g_memlog_available)
        fprintf(stderr, "[q88measure] 注記: このコアに範囲指定の書き込み記録が無い。"
                        "--mem-write-log は無効化される\n");

    *(void **)(&p_exchange_intervention) = dlsym(h, "retro_q88h_exchange_intervention");
    *(void **)(&p_exchange_intervention_reset) = dlsym(h, "retro_q88h_exchange_intervention_reset");
    *(void **)(&p_exchange_intervention_configure) = dlsym(h, "retro_q88h_exchange_intervention_configure");
    *(void **)(&p_exchange_ready_handoff_configure) =
        dlsym(h, "retro_q88h_exchange_ready_handoff_configure");
    g_exchange_intervention_available = p_exchange_intervention
                                      && p_exchange_intervention_reset
                                      && p_exchange_intervention_configure
                                      && p_exchange_ready_handoff_configure;

    *(void **)(&p_request_intervention) = dlsym(h, "retro_q88h_request_intervention");
    *(void **)(&p_request_intervention_reset) =
        dlsym(h, "retro_q88h_request_intervention_reset");
    *(void **)(&p_request_intervention_configure) =
        dlsym(h, "retro_q88h_request_intervention_configure");
    g_request_intervention_available = p_request_intervention
                                     && p_request_intervention_reset
                                     && p_request_intervention_configure;

    *(void **)(&p_response_intervention) = dlsym(h, "retro_q88h_response_intervention");
    *(void **)(&p_response_intervention_reset) =
        dlsym(h, "retro_q88h_response_intervention_reset");
    *(void **)(&p_response_intervention_configure) =
        dlsym(h, "retro_q88h_response_intervention_configure");
    g_response_intervention_available = p_response_intervention
                                      && p_response_intervention_reset
                                      && p_response_intervention_configure;

    *(void **)(&p_sub_interrupt_intervention) =
        dlsym(h, "retro_q88h_sub_interrupt_intervention");
    *(void **)(&p_sub_interrupt_intervention_reset) =
        dlsym(h, "retro_q88h_sub_interrupt_intervention_reset");
    *(void **)(&p_sub_interrupt_intervention_configure) =
        dlsym(h, "retro_q88h_sub_interrupt_intervention_configure");
    g_sub_interrupt_intervention_available = p_sub_interrupt_intervention
                                           && p_sub_interrupt_intervention_reset
                                           && p_sub_interrupt_intervention_configure;

    *(void **)(&p_main_interrupt_intervention) =
        dlsym(h, "retro_q88h_main_interrupt_intervention");
    *(void **)(&p_main_interrupt_intervention_reset) =
        dlsym(h, "retro_q88h_main_interrupt_intervention_reset");
    *(void **)(&p_main_interrupt_intervention_configure) =
        dlsym(h, "retro_q88h_main_interrupt_intervention_configure");
    g_main_interrupt_intervention_available = p_main_interrupt_intervention
                                            && p_main_interrupt_intervention_reset
                                            && p_main_interrupt_intervention_configure;

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

    /* 画面ピクセルスナップショット（M5本題）も同様に、無いコアでは黙って機能を落とす。 */
    *(void **)(&p_screenshot)         = dlsym(h, "retro_q88h_screenshot");
    *(void **)(&p_screenshot_capture) = dlsym(h, "retro_q88h_screenshot_capture");
    g_screenshot_available = p_screenshot && p_screenshot_capture;
    if (!g_screenshot_available)
        fprintf(stderr, "[q88measure] 注記: このコアに画面スナップショットが無い。"
                        "--screenshot は無効化される\n");
    return true;
}

/* ---- 出力先の安全策（禁止事項5/7） --------------------------------------
 *
 * --vram-dump が書く生バイナリにはテキストVRAMの文字コード（＝画面本文）が
 * そのまま入り、--mem-write-log が書く記録も対象範囲をテキストVRAMに
 * 取ったときは同じく文字コードの値列を含む。どちらも公式ROM上で走らせて
 * 使う想定の器具なので、CLAUDE.md 禁止事項5「測定ログをコミットする前に
 * データポートの値列を伏せる」・7「画面本文を書かない」と同じ実害がある。
 *
 * このリポジトリ内（ただし tmp/ 配下は git 管理外の作業領域として除く）へ
 * 直接書かせると、うっかりコミット対象へ紛れ込む経路になるため、
 * 出力先をここで機械的に拒否する。判定は realpath ベース——シンボリック
 * リンクや `..` で見かけ上リポジトリ外に見せかけても実体で弾く。 */

/* path の実体が「このリポジトリの内側」かどうかを判定する。
 * tmp/ 配下（実体で判定）は例外として false を返す。
 * path がまだ存在しないファイルでもよい（親ディレクトリまでを解決する）。
 * 判定不能（親ディレクトリも無い等）なら安全側に倒して false
 * ——実際の書き込みは後続の fopen が同じ理由で失敗して検出される。 */
static bool path_is_inside_repo_but_not_tmp(const char *path)
{
    char repo_real[PATH_MAX];
    char resolved[PATH_MAX];
    char tmp_prefix[PATH_MAX];
    size_t rlen;

    if (!g_repo_root[0]) return false;   /* 実体パスが求まらなければ判定不能→安全側(不拒否) */
    if (!realpath(g_repo_root, repo_real)) return false;

    if (!realpath(path, resolved)) {
        /* ファイル自体は無くてよいが、親ディレクトリは実在する必要がある */
        char dirbuf[PATH_MAX];
        char parent[PATH_MAX];
        const char *base;
        const char *slash = strrchr(path, '/');
        char parent_real[PATH_MAX];

        if (slash) {
            size_t dlen = (size_t)(slash - path);
            if (dlen == 0) dlen = 1; /* "/foo" のときは "/" を親にする */
            if (dlen >= sizeof(parent)) return false;
            memcpy(parent, path, dlen);
            parent[dlen] = 0;
            base = slash + 1;
        } else {
            strcpy(parent, ".");
            base = path;
        }
        if (!realpath(parent, parent_real)) return false;
        if (snprintf(dirbuf, sizeof(dirbuf), "%s/%s", parent_real, base) >= (int)sizeof(dirbuf))
            return false;
        strncpy(resolved, dirbuf, sizeof(resolved) - 1);
        resolved[sizeof(resolved) - 1] = 0;
    }

    rlen = strlen(repo_real);
    if (strncmp(resolved, repo_real, rlen) != 0) return false;          /* リポジトリ外 */
    if (resolved[rlen] != '/' && resolved[rlen] != '\0') return false;  /* 前方一致の別ディレクトリ */

    if (snprintf(tmp_prefix, sizeof(tmp_prefix), "%s/tmp/", repo_real) >= (int)sizeof(tmp_prefix))
        return true; /* 作れないなら安全側（拒否）に倒す */
    if (strncmp(resolved, tmp_prefix, strlen(tmp_prefix)) == 0) return false; /* tmp/配下は許可 */

    return true;
}

/* 呼び出し側の共通エラー処理。だめなら NULL は返さずここで終了させたいので、
 * 呼び出し元で「拒否なら return 1」の1行にまとめられるよう bool を返す。 */
static bool reject_if_unsafe_output_path(const char *opt, const char *path)
{
    if (path_is_inside_repo_but_not_tmp(path)) {
        fprintf(stderr,
            "[q88measure] NG: %s の出力先がリポジトリ内 (tmp/ 以外) を指している: %s\n"
            "  画面本文/データポート値列を含みうる出力はリポジトリ内へ直接書かせない"
            "（CLAUDE.md 禁止事項5/7）。tmp/ 配下かリポジトリ外へ書くこと。\n",
            opt, path);
        return true;
    }
    return false;
}

/* ---- テキストVRAMの写し（M7器具1） --------------------------------------
 *
 * 複数フレームぶん指定されたときにファイルが衝突しないよう、件数が2以上の
 * ときだけファイル名へフレーム番号を差し込む規則にする（1件だけの素朴な
 * 使い方では、指定したパスがそのまま出てほしいため）。挿入位置は最後の
 * '.' の直前（拡張子が無ければ末尾に付け足す）。 */
static void vram_dump_path_for(char *out, size_t outsz, const char *path,
                               unsigned frame, bool need_suffix)
{
    const char *dot, *slash;
    if (!need_suffix) { snprintf(out, outsz, "%s", path); return; }

    slash = strrchr(path, '/');
    dot   = strrchr(path, '.');
    if (dot && (!slash || dot > slash)) {
        snprintf(out, outsz, "%.*s.f%06u%s", (int)(dot - path), path, frame, dot);
    } else {
        snprintf(out, outsz, "%s.f%06u", path, frame);
    }
}

/* main RAM の F3C8〜FF7F（文字コード+属性、両端含む、3000バイト）を
 * 生バイナリで1枚書く。既存の retro_q88h_text() は「1行80文字」を
 * cols==stride より小さく指定して呼ぶことで属性を読み飛ばす使われ方が
 * 通例だったが、ここでは cols=stride=Q88H_TEXT_STRIDE を渡す——そうすると
 * dst[r*cols+c] = main_ram[BASE + r*stride + c] が c を stride 全域まで
 * 埋めるので、結果的に F3C8 からの 3000 バイトを1バイトも飛ばさず
 * 連続コピーしたのと同じになる。新しいコア側フックを増やさずに済む。 */
static int write_vram_dump(const char *path, unsigned frame,
                           void (*text_fn)(uint8_t *, uint32_t, uint32_t, uint32_t))
{
    static uint8_t buf[Q88H_TEXT_ROWS * Q88H_TEXT_STRIDE];
    char infopath[PATH_MAX + 16];
    FILE *fp, *ip;

    text_fn(buf, Q88H_TEXT_ROWS, Q88H_TEXT_STRIDE, Q88H_TEXT_STRIDE);

    /* vram_dump_selftest.sh 専用の故障注入。既定では環境変数が無いので
     * 何もしない。1バイトだけ化けさせて、期待値と比較する側の検査が
     * 実際に NG になることを確かめるための対照。 */
    if (getenv("Q88MEASURE_FAULT_CORRUPT_VRAM_DUMP")) buf[0] ^= 0xFF;

    fp = fopen(path, "wb");
    if (!fp) { perror(path); return 0; }
    fwrite(buf, 1, sizeof(buf), fp);
    fclose(fp);

    /* 見出し（フレーム・範囲）は生バイナリに混ぜず、隣に小さなテキストで置く。
     * 中身はバイト列そのものではなく採取条件だけなので、禁止事項7には当たらない。 */
    snprintf(infopath, sizeof(infopath), "%s.info.txt", path);
    ip = fopen(infopath, "w");
    if (ip) {
        fprintf(ip, "frame: %u\n", frame);
        fprintf(ip, "timing: retro_run() 呼び出しの直前\n");
        fprintf(ip, "range: %04X-%04X (両端含む, %zuバイト = 80文字+40属性 x %u行)\n",
                Q88H_TEXT_BASE, Q88H_TEXT_BASE + (unsigned)sizeof(buf) - 1,
                sizeof(buf), (unsigned)Q88H_TEXT_ROWS);
        fclose(ip);
    }
    return 1;
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
 * 眺めるのが一番危ない（実際に一度やった）。
 *
 * 呼び出し先は必ず「ファイルへ書く」経路（--out の書き出し）に限る。
 * 標準出力・標準エラーは対話実行だと素通しで作業端末に出る＝人の目に
 * 触れうる経路なので、そちらには絶対に呼ばない
 * （write_report_screen_section() / --dump-text 参照。
 * 経緯: docs/notes/m7hk-screen-content-leak-path-closed.md、
 * disclosure-2026-09-19.md）。 */
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

/* write_screen() の代わりに、画面本文を出さない旨の1行だけを書く。
 * 呼び先が作業端末（標準出力・標準エラー）のときに使う。
 * write_screen() が出す見出し行 "[測定終了時のテキスト画面]" 自体も
 * 出さない（画面節の見出しが出ること自体を「画面を覗いてよい経路」と
 * 誤解させないため）。--out のファイル側（write_screen() 本体）の
 * 書式はこの関数では一切変えない。 */
static void write_screen_redacted_notice(FILE *fp)
{
    fprintf(fp, "(このコマンドの標準出力・標準エラーには、q88h_text が返す"
                "テキスト画面の内容を書かない設計。"
                "--out で指定したファイルにのみ書くので、"
                "そのファイルを直接 cat/grep 等で開かず、"
                "tools/check_l3_screen_output.py や tools/check_l3_entry_screen.py "
                "で扱うこと。PC88Behavior/CLAUDE.md 禁止事項7。)\n\n");
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
    /* fetch の内訳。番地だけでは ROM 像を実行したのか、port $31 等で
     * 差し替えられた RAM を実行したのかが分からない（PC-88 は 0000-7FFF
     * を RAM に差し替えられる）ので、コアの実メモリマップを見て振り分けた
     * ものを追加セクションとして出す。既存の [fetch] セクションは変えない。 */
    snprintf(label, sizeof(label), "[%s 実行された番地 (fetch, ROM)]", who);
    dump_ranges(fp, label, t->mem_exec_rom, Q88H_MEM_SIZE);
    snprintf(label, sizeof(label), "[%s 実行された番地 (fetch, RAM)]", who);
    dump_ranges(fp, label, t->mem_exec_ram, Q88H_MEM_SIZE);
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
    fprintf(fp, "# seq    clock   frame  cpu   kind  port  value  pc\n");
    if (!l->n_events) fprintf(fp, "# (記録されたイベントなし)\n");
    for (i = 0; i < l->n_events; i++) {
        const q88h_iolog_ev_t *e = &l->ev[i];
        fprintf(fp, "%6u %7u %6u  %-4s  %-4s  %04X   %02X   %04X\n",
                e->seq, e->clock, e->frame, who,
                e->kind == Q88H_IOLOG_OUT ? "OUT" : "IN",
                e->port, e->value, e->pc);
    }
    /* 0件でも必ず出す。無言で欠けるのが一番まずい */
    fprintf(fp, "# 取りこぼし: %u件 / 総イベント数: %u件\n\n", l->n_dropped, l->n_events);
}

static void write_iolog_report(FILE *fp, const char *core, const char *romdir,
                               const char *disk, const char *disk2, unsigned frames,
                               unsigned from_frame,
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
    fprintf(fp, "# 同一CPU内の節は seq の昇順＝発生順そのもの。\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# clock 列（M6c）は main/sub・iolog/intlog を横断する共通の\n");
    fprintf(fp, "# 単調増加通し番号。frame と違い、これは他CPUの clock 値・\n");
    fprintf(fp, "# 他ログ種別の clock 値と比較して真の前後関係を判定してよい\n");
    fprintf(fp, "# （小さいほうが先に起きた）。詳細は q88h_clock.h を参照。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    if (disk2) fprintf(fp, "disk2     : %s\n", disk2);
    fprintf(fp, "frames    : %u\n\n", frames);
    fprintf(fp, "io-log-from-frame: %u\n\n", from_frame);

    write_iolog_cpu(fp, "main", l);
    write_iolog_cpu(fp, "sub",  ls);
}

/* ---- 範囲指定の書き込み記録（M7器具2）の書き出し ------------------------
 *
 * write_iolog_cpu と同じ形。対象は main CPU のみ（M7段階1はテキストVRAMを
 * 含む main側の測定が目的のため、q88h_memlog.h 参照）。value 列には
 * 対象範囲の実データがそのまま入るので、このファイル自体の出力先も
 * reject_if_unsafe_output_path で制限している。 */
static void write_memlog_report(FILE *fp, const char *core, const char *romdir,
                                const char *disk, const char *disk2, unsigned frames,
                                unsigned from_frame, const q88h_memlog_t *m)
{
    uint32_t i;
    fprintf(fp, "# PC88Behavior 範囲指定メモリ書き込み記録\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# 記録しているのは指定範囲内への書き込みの発生順・番地・値・\n");
    fprintf(fp, "# 発行元PC(その書き込みを行った命令の先頭番地)・フレーム番号のみ。\n");
    fprintf(fp, "# 対象は main CPU のみ。\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# 発行元PCは q88h_iolog の「PC.W-2」方式ではなく、fetch()の\n");
    fprintf(fp, "# 呼び出し列からオペコード/プレフィクスバイトだけを辿って求めた\n");
    fprintf(fp, "# 「命令の先頭番地」——メモリ書き込み命令は1〜4バイトと長さが\n");
    fprintf(fp, "# まちまちで PC からの引き算では出せないため。詳細は\n");
    fprintf(fp, "# tools/patches/0014-mem-write-log.patch の pc88main.c 側コメント参照。\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# LDIR 等のブロック転送も1バイトずつ q88h_mem_write を通るため、\n");
    fprintf(fp, "# その分だけ複数件として記録される（同じPCの反復として見える）。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    if (disk2) fprintf(fp, "disk2     : %s\n", disk2);
    fprintf(fp, "frames    : %u\n", frames);
    fprintf(fp, "range     : %04X-%04X\n", m->range_lo, m->range_hi);
    fprintf(fp, "from-frame: %u\n", from_frame);
    fprintf(fp, "capacity  : %u件\n\n", (unsigned)Q88H_MEMLOG_MAX_EVENTS);

    fprintf(fp, "# seq    frame    pc   addr  value\n");
    if (!m->n_events) fprintf(fp, "# (記録されたイベントなし)\n");
    for (i = 0; i < m->n_events; i++) {
        const q88h_memlog_ev_t *e = &m->ev[i];
        fprintf(fp, "%6u %7u  %04X  %04X   %02X\n",
                e->seq, e->frame, e->pc, e->addr, e->value);
    }
    fprintf(fp, "# 取りこぼし: %u件 / 総イベント数: %u件\n", m->n_dropped, m->n_events);
}

/* ---- 割り込み受理ログ（M4c）の書き出し ----------------------------------
 * 考え方は write_iolog_* と同じ。main/sub は別々に走る Z80 なので、
 * 混ぜて出すと前後関係を誤解させる。CPUごとに節を分ける。 */
static void write_intlog_cpu(FILE *fp, const char *who, const q88h_intlog_t *l)
{
    uint32_t i;
    fprintf(fp, "# %s\n", who);
    fprintf(fp, "# seq    clock   frame  cpu   im  level  ret_pc  handler_pc\n");
    if (!l->n_events) fprintf(fp, "# (記録されたイベントなし)\n");
    for (i = 0; i < l->n_events; i++) {
        const q88h_intlog_ev_t *e = &l->ev[i];
        fprintf(fp, "%6u %7u %6u  %-4s  %2u   %3u   %04X    %04X\n",
                e->seq, e->clock, e->frame, who, e->im, e->level,
                e->ret_pc, e->handler_pc);
    }
    /* 0件でも必ず出す。無言で欠けるのが一番まずい（write_iolog_cpu と同じ理由） */
    fprintf(fp, "# 取りこぼし: %u件 / 総イベント数: %u件\n\n", l->n_dropped, l->n_events);
}

static void write_intlog_report(FILE *fp, const char *core, const char *romdir,
                                const char *disk, const char *disk2, unsigned frames,
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
    fprintf(fp, "# 同一CPU内の節は seq の昇順＝発生順そのもの。\n");
    fprintf(fp, "#\n");
    fprintf(fp, "# clock 列（M6c）は main/sub・iolog/intlog を横断する共通の\n");
    fprintf(fp, "# 単調増加通し番号。iolog の clock 列と同じ番号空間を共有して\n");
    fprintf(fp, "# いるので、割り込み受理と I/O イベントの前後関係も判定できる\n");
    fprintf(fp, "# （小さいほうが先に起きた）。詳細は q88h_clock.h を参照。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    if (disk2) fprintf(fp, "disk2     : %s\n", disk2);
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
                                 const char *disk, const char *disk2, unsigned frames,
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
    if (disk2) fprintf(fp, "disk2     : %s\n", disk2);
    fprintf(fp, "frames    : %u\n\n", frames);

    fprintf(fp, "# region                          source                                    writes  crc32\n");
    for (i = 0; i < Q88H_FONTSRC_REGION_COUNT; i++) {
        fprintf(fp, "  %-32s %-42s %6u  %08X\n",
                fontsrc_region_name(i), fontsrc_tag_name(f->region_src[i]),
                f->region_writes[i], f->region_crc32[i]);
    }
    fprintf(fp, "\n");
}

/* ---- 画面ピクセルスナップショット（M5本題）の書き出し --------------------
 * q88h_screenshot は「バッファに届いた」ではなく「実際に描画されたピクセル」
 * を持つ唯一のフック——font_mem までの到達確認（--font-log）とは見ている
 * 末端が違う。PPM(P6, バイナリ)で書く。外部ライブラリを増やさない形式を
 * 選んだ理由はここ。640x400・R,G,Bインターリーブはコア側
 * （q88h_screenshot.h）の約束どおり。 */
static int write_screenshot_ppm(const char *path, const q88h_screenshot_t *s)
{
    FILE *fp = fopen(path, "wb");
    if (!fp) { perror(path); return 0; }
    fprintf(fp, "P6\n%u %u\n255\n", (unsigned)Q88H_SCREENSHOT_W, (unsigned)Q88H_SCREENSHOT_H);
    fwrite(s->rgb, 1, sizeof(s->rgb), fp);
    fclose(fp);
    return 1;
}

/* show_screen: false のときは write_screen() を呼ばず、
 * write_screen_redacted_notice() で済ませる。
 * fp が作業端末（標準出力・標準エラー）になりうる呼び出しでは
 * 必ず false を渡すこと。--out のファイルへ書く呼び出しだけ true。 */
static void write_report(FILE *fp, const q88h_trace_t *t, const q88h_trace_t *ts,
                         const q88h_trap_t *tp, const q88h_trap_t *tps,
                         const char *core, const char *romdir,
                         const char *disk, const char *disk2, unsigned frames,
                         bool insert2_done, unsigned insert2_frame,
                         int insert2_rc, const char *insert2_actual,
                         const kmrec_t *kmrec, int n_kmrec, bool show_screen)
{
    int i;
    fprintf(fp, "# PC88Behavior バスアクセス採取結果\n");
    fprintf(fp, "# 記録しているのはアドレスとアクセス種別のみ。ROM の内容は含まない。\n\n");
    fprintf(fp, "core      : %s\n", core);
    fprintf(fp, "rom-dir   : %s\n", romdir);
    fprintf(fp, "disk      : %s\n", disk ? disk : "(なし)");
    if (disk2) fprintf(fp, "disk2     : %s\n", disk2);
    if (insert2_done)
        fprintf(fp, "insert2   : frame=%u rc=%d actual=%s\n",
                insert2_frame, insert2_rc, insert2_actual ? insert2_actual : "(なし)");
    fprintf(fp, "frames    : %u\n", frames);
    fprintf(fp, "type      : %s\n\n", g_typed ? g_typed : "(なし)");
    if (show_screen) write_screen(fp); else write_screen_redacted_notice(fp);

    /* PC-88 は Z80 が 2 個。サブ ROM も再実装対象なので別々に出す。 */
    write_cpu(fp, "メインCPU", t);
    write_cpu(fp, "サブCPU",   ts);

    if (g_trap_available && tp && tps) {
        write_trap_cpu(fp, "メインCPU", tp);
        write_trap_cpu(fp, "サブCPU",   tps);
    }

    /* キーマトリクス直接操作（M7段階1の器具その2）の実書き換え記録。
     * この器具自身が書いた値（frame・port・bit・書き換え前後の値）だけで、
     * ROM・公式ディスクの内容は含まない。 */
    fprintf(fp, "[キーマトリクス書き換え]\n");
    if (!n_kmrec) fprintf(fp, "  (なし)\n");
    for (i = 0; i < n_kmrec; i++) {
        fprintf(fp, "  frame=%-6u port=%02X bit=%u  %-7s  key_scan[%02X]: %02X -> %02X\n",
                kmrec[i].frame, kmrec[i].port, kmrec[i].bit, kmrec[i].action,
                kmrec[i].port, kmrec[i].before, kmrec[i].after);
    }
    fprintf(fp, "\n");
}

/* ---- main -------------------------------------------------------------- */

static void usage(void)
{
    fprintf(stderr,
        "使い方: q88measure --core <path> [--rom-dir <dir>] [--disk <path>]\n"
        "                   [--disk2 <path>] [--expect-disk2-empty]\n"
        "                   [--insert-disk2 <path> --insert-disk2-at FRAME]\n"
        "                   [--frames N] [--out <file>] [--verbose]\n"
        "                   [--reset-at FRAME]\n"
        "                   [--basic-mode 'N88 V2|N88 V1H|N88 V1S|N']\n"
        "                   [--save-to-disk-image]\n"
        "                   [--type \"TEXT\"] [--type-at FRAME]\n"
        "                   [--allow-untypable] (--typeより前に指定。既定は\n"
        "                    打てない文字があれば走行前にrc!=0で止まる)\n"
        "                   [--key-hold N] [--key-gap N]\n"
        "                   [--expect-exec ADDR] [--expect-read ADDR]\n"
        "                   [--expect-write ADDR] [--expect-io-in PORT]\n"
        "                   [--expect-io-out PORT]\n"
        "                   [--trap-map FILE] [--trap-mode ret|stop]\n"
        "                   [--trap-stop-after N]\n"
        "                   [--expect-trap-exec ADDR] [--expect-trap-data ADDR]\n"
        "                   [--io-log FILE] [--io-log-from-frame FRAME]\n"
        "                   [--exchange-intervention RUN:MODE:VALUE] (最大64個)\n"
        "                   [--request-intervention RUN:POS:MODE:VALUE] (最大64個)\n"
        "                   [--response-intervention RUN:POS:MODE:VALUE] (最大64個)\n"
        "                   [--response-ready-handoff RUN:MODE] (now|defer-once)\n"
        "                   [--sub-interrupt-intervention FIRST:LAST:MODE]\n"
        "                   [--main-interrupt-intervention FIRST:LAST:MODE]\n"
        "                   [--sub-cpu-mode 0|1|2]\n"
        "                   [--int-log FILE] [--font-log FILE]\n"
        "                   [--screenshot FILE.ppm]\n"
        "                   [--mem-write-log FILE --mem-write-range LO-HI\n"
        "                    [--mem-write-from-frame N]]\n"
        "                   [--vram-dump PATH --vram-dump-at FRAME] (最大%d組)\n"
        "                   [--key-matrix PORT:BIT:FRAME[:HOLD]] (最大%d個,\n"
        "                    PORTは0x00-0x0E, BITは0-7。--typeとは同時指定不可)\n",
        VRAM_DUMP_MAX, KEY_MATRIX_MAX);
}

int main(int argc, char **argv)
{
    const char *core = NULL, *disk = NULL, *disk2 = NULL, *out = NULL;
    unsigned frames = 600, next_at = 180, key_hold = 4, key_gap = 4;
    unsigned reset_at = UINT32_MAX;
    unsigned io_log_from_frame = 0;
    static char typed[1024]; size_t typed_len = 0;
    bool dump_text = false;
    bool expect_disk2_empty = false;
    const char *insert_disk2 = NULL;
    unsigned insert_disk2_at = 0;
    bool insert_disk2_at_set = false;
    bool insert2_done = false;
    int insert2_rc = 0;
    const char *insert2_actual = NULL;
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
    const char *screenshot_path = NULL;
    /* 範囲指定の書き込み記録（M7器具2）。--mem-write-range は必須
     * （範囲を指定しないと何も記録しない設計 — q88h_memlog.h 参照）。 */
    const char *mem_write_log_path = NULL;
    unsigned    mem_write_range_lo = 0, mem_write_range_hi = 0;
    bool        mem_write_range_set = false;
    unsigned    mem_write_from_frame = 0;
    /* テキストVRAMの写し（M7器具1）。PATH と FRAME をペアとして複数回
     * 指定できる。件数が2以上のときだけファイル名にフレーム番号を差し込む
     * （1件だけなら指定パスそのものを使う——この規則は vram_dump_path_for
     * のコメントに書く）。 */
    struct { const char *path; unsigned frame; bool done; } vram_dump[VRAM_DUMP_MAX];
    int         n_vram_dump = 0;
    const char *vram_dump_pending_path = NULL;
    /* キーマトリクス直接操作（M7段階1の器具その2）。HOLD省略時は
     * その時点の --key-hold の値を使う（--type の hold と同じ、指定順に
     * 依存する規則）。apply/release はフレームループ内で1回ずつだけ行う
     * ので done_press/done_release で管理する。 */
    struct {
        unsigned port, bit, frame, hold;
        bool     done_press, done_release;
    } keymatrix[KEY_MATRIX_MAX];
    int n_keymatrix = 0;
    kmrec_t kmrec[KEY_MATRIX_RECORD_MAX];
    int n_kmrec = 0;
    struct { int32_t run; uint8_t mode, value; } xi[Q88H_EXCHANGE_INTERVENTION_SLOTS];
    int n_xi = 0;
    struct { int32_t run; uint32_t position; uint8_t mode, value; }
        rxi[Q88H_REQUEST_INTERVENTION_SLOTS];
    int n_rxi = 0;
    struct { int32_t run; uint32_t position; uint8_t mode, value; }
        rsi[Q88H_RESPONSE_INTERVENTION_SLOTS];
    int n_rsi = 0;
    int32_t ready_handoff_run = -1, ready_handoff_mode = Q88H_READY_HANDOFF_NONE;
    int32_t sii_first = -1, sii_last = -1;
    uint8_t sii_mode = Q88H_SII_NONE;
    int32_t mii_first = -1, mii_last = -1;
    uint8_t mii_mode = Q88H_MII_NONE;
    const char *env;
    int i, k;

    set_repo_root_from_argv0(argv[0]);

    if ((env = getenv("PC88_REF_ROM_DIR")))
        snprintf(g_rom_dir, sizeof(g_rom_dir), "%s", env);

    for (i = 1; i < argc; i++) {
        if      (!strcmp(argv[i], "--core")    && i + 1 < argc) core = argv[++i];
        else if (!strcmp(argv[i], "--disk")    && i + 1 < argc) disk = argv[++i];
        else if (!strcmp(argv[i], "--disk2")   && i + 1 < argc) disk2 = argv[++i];
        else if (!strcmp(argv[i], "--expect-disk2-empty")) expect_disk2_empty = true;
        else if (!strcmp(argv[i], "--insert-disk2") && i + 1 < argc) insert_disk2 = argv[++i];
        else if (!strcmp(argv[i], "--insert-disk2-at") && i + 1 < argc) {
            insert_disk2_at = (unsigned)strtoul(argv[++i], NULL, 0);
            insert_disk2_at_set = true;
        }
        else if (!strcmp(argv[i], "--out")     && i + 1 < argc) out  = argv[++i];
        else if (!strcmp(argv[i], "--frames")  && i + 1 < argc) frames = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--reset-at") && i + 1 < argc) reset_at = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--basic-mode") && i + 1 < argc) g_basic_mode = argv[++i];
        else if (!strcmp(argv[i], "--save-to-disk-image")) g_save_to_disk_image = true;
        else if (!strcmp(argv[i], "--sub-cpu-mode") && i + 1 < argc) {
            const char *v = argv[++i];
            if (strlen(v) != 1 || v[0] < '0' || v[0] > '2') {
                fprintf(stderr, "[q88measure] --sub-cpu-mode は 0/1/2\n");
                return 2;
            }
            g_sub_cpu_mode[0] = v[0];
            g_sub_cpu_mode[1] = '\0';
            g_sub_cpu_mode_set = true;
        }
        else if (!strcmp(argv[i], "--rom-dir") && i + 1 < argc)
            snprintf(g_rom_dir, sizeof(g_rom_dir), "%s", argv[++i]);
        /* --type-at で打ち始めるフレームを決め、--type で打つ。
         * 何度でも繰り返せる。起動時の "How many files" のような
         * 途中のプロンプトを挟む場合に要る（実際に必要だった）。 */
        else if (!strcmp(argv[i], "--type-at")   && i + 1 < argc) next_at = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--allow-untypable")) g_allow_untypable = true;
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
        else if (!strcmp(argv[i], "--io-log-from-frame") && i + 1 < argc)
            io_log_from_frame = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--exchange-intervention") && i + 1 < argc) {
            char *end;
            const char *spec = argv[++i], *mode, *value;
            long run;
            size_t mode_len;
            if (n_xi >= Q88H_EXCHANGE_INTERVENTION_SLOTS) {
                fprintf(stderr, "[q88measure] --exchange-intervention は最大%d個\n",
                        Q88H_EXCHANGE_INTERVENTION_SLOTS);
                return 2;
            }
            run = strtol(spec, &end, 0);
            if (end == spec || *end != ':' || run < 0 || run > INT32_MAX) {
                fprintf(stderr, "[q88measure] 介入書式は RUN:MODE:VALUE\n"); return 2;
            }
            mode = end + 1; value = strchr(mode, ':');
            if (!value) { fprintf(stderr, "[q88measure] 介入書式は RUN:MODE:VALUE\n"); return 2; }
            mode_len = (size_t)(value - mode); value++;
#define XI_MODE(name, code) (mode_len == strlen(name) && !strncmp(mode, name, mode_len)) ? code
            xi[n_xi].mode = XI_MODE("xor-all", Q88H_XI_XOR_ALL) :
                            XI_MODE("xor-first", Q88H_XI_XOR_FIRST) :
                            XI_MODE("xor-tail", Q88H_XI_XOR_TAIL) :
                            XI_MODE("replace-all", Q88H_XI_REPLACE_ALL) :
                            XI_MODE("replace-first", Q88H_XI_REPLACE_FIRST) : Q88H_XI_NONE;
#undef XI_MODE
            if (xi[n_xi].mode == Q88H_XI_NONE) {
                fprintf(stderr, "[q88measure] 未知の介入MODE\n"); return 2;
            }
            xi[n_xi].value = (uint8_t)strtoul(value, &end, 0);
            if (*value == '\0' || *end != '\0' || strtoul(value, NULL, 0) > 255) {
                fprintf(stderr, "[q88measure] 介入VALUEは0〜255\n"); return 2;
            }
            xi[n_xi].run = (int32_t)run;
            n_xi++;
        }
        else if (!strcmp(argv[i], "--request-intervention") && i + 1 < argc) {
            char *end;
            const char *spec = argv[++i], *pos_s, *mode, *value;
            long run, pos;
            size_t mode_len;
            if (n_rxi >= Q88H_REQUEST_INTERVENTION_SLOTS) {
                fprintf(stderr, "[q88measure] --request-intervention は最大%d個\n",
                        Q88H_REQUEST_INTERVENTION_SLOTS);
                return 2;
            }
            run = strtol(spec, &end, 0);
            if (end == spec || *end != ':' || run < 0 || run > INT32_MAX) {
                fprintf(stderr, "[q88measure] 介入書式は RUN:POS:MODE:VALUE\n"); return 2;
            }
            pos_s = end + 1;
            pos = strtol(pos_s, &end, 0);
            if (end == pos_s || *end != ':' || pos < 0) {
                fprintf(stderr, "[q88measure] 介入書式は RUN:POS:MODE:VALUE\n"); return 2;
            }
            mode = end + 1; value = strchr(mode, ':');
            if (!value) { fprintf(stderr, "[q88measure] 介入書式は RUN:POS:MODE:VALUE\n"); return 2; }
            mode_len = (size_t)(value - mode); value++;
#define RXI_MODE(name, code) (mode_len == strlen(name) && !strncmp(mode, name, mode_len)) ? code
            rxi[n_rxi].mode = RXI_MODE("xor", Q88H_RXI_XOR) :
                              RXI_MODE("replace", Q88H_RXI_REPLACE) : Q88H_RXI_NONE;
#undef RXI_MODE
            if (rxi[n_rxi].mode == Q88H_RXI_NONE) {
                fprintf(stderr, "[q88measure] 未知の介入MODE\n"); return 2;
            }
            rxi[n_rxi].value = (uint8_t)strtoul(value, &end, 0);
            if (*value == '\0' || *end != '\0' || strtoul(value, NULL, 0) > 255) {
                fprintf(stderr, "[q88measure] 介入VALUEは0〜255\n"); return 2;
            }
            rxi[n_rxi].run = (int32_t)run;
            rxi[n_rxi].position = (uint32_t)pos;
            n_rxi++;
        }
        else if (!strcmp(argv[i], "--response-intervention") && i + 1 < argc) {
            char *end;
            const char *spec = argv[++i], *pos_s, *mode, *value;
            long run, pos;
            size_t mode_len;
            if (n_rsi >= Q88H_RESPONSE_INTERVENTION_SLOTS) {
                fprintf(stderr, "[q88measure] --response-intervention は最大%d個\n",
                        Q88H_RESPONSE_INTERVENTION_SLOTS);
                return 2;
            }
            run = strtol(spec, &end, 0);
            if (end == spec || *end != ':' || run < 0 || run > INT32_MAX) {
                fprintf(stderr, "[q88measure] 介入書式は RUN:POS:MODE:VALUE\n"); return 2;
            }
            pos_s = end + 1;
            pos = strtol(pos_s, &end, 0);
            if (end == pos_s || *end != ':' || pos < 0) {
                fprintf(stderr, "[q88measure] 介入書式は RUN:POS:MODE:VALUE\n"); return 2;
            }
            mode = end + 1; value = strchr(mode, ':');
            if (!value) { fprintf(stderr, "[q88measure] 介入書式は RUN:POS:MODE:VALUE\n"); return 2; }
            mode_len = (size_t)(value - mode); value++;
#define RSI_MODE(name, code) (mode_len == strlen(name) && !strncmp(mode, name, mode_len)) ? code
            rsi[n_rsi].mode = RSI_MODE("xor", Q88H_RSI_XOR) :
                              RSI_MODE("replace", Q88H_RSI_REPLACE) : Q88H_RSI_NONE;
#undef RSI_MODE
            if (rsi[n_rsi].mode == Q88H_RSI_NONE) {
                fprintf(stderr, "[q88measure] 未知の介入MODE\n"); return 2;
            }
            rsi[n_rsi].value = (uint8_t)strtoul(value, &end, 0);
            if (*value == '\0' || *end != '\0' || strtoul(value, NULL, 0) > 255) {
                fprintf(stderr, "[q88measure] 介入VALUEは0〜255\n"); return 2;
            }
            rsi[n_rsi].run = (int32_t)run;
            rsi[n_rsi].position = (uint32_t)pos;
            n_rsi++;
        }
        else if (!strcmp(argv[i], "--response-ready-handoff") && i + 1 < argc) {
            char *end;
            const char *spec = argv[++i], *mode_text;
            long run_value;
            run_value = strtol(spec, &end, 0);
            if (end == spec || *end != ':' || run_value < 1 || run_value > INT32_MAX) {
                fprintf(stderr, "[q88measure] 応答準備handoff介入書式は RUN:MODE\n"); return 2;
            }
            mode_text = end + 1;
            if (!strcmp(mode_text, "now"))
                ready_handoff_mode = Q88H_READY_HANDOFF_NOW;
            else if (!strcmp(mode_text, "defer-once"))
                ready_handoff_mode = Q88H_READY_HANDOFF_DEFER_ONCE;
            else {
                fprintf(stderr, "[q88measure] MODEはnowまたはdefer-once\n"); return 2;
            }
            ready_handoff_run = (int32_t)run_value;
        }
        else if (!strcmp(argv[i], "--sub-interrupt-intervention") && i + 1 < argc) {
            char *end;
            const char *spec = argv[++i], *last, *mode;
            long first_value, last_value;
            first_value = strtol(spec, &end, 0);
            if (end == spec || *end != ':' || first_value < 0 || first_value > INT32_MAX) {
                fprintf(stderr, "[q88measure] sub割り込み介入書式は FIRST:LAST:MODE\n"); return 2;
            }
            last = end + 1;
            last_value = strtol(last, &end, 0);
            if (end == last || *end != ':' || last_value < first_value || last_value > INT32_MAX) {
                fprintf(stderr, "[q88measure] sub割り込み介入のrun範囲が不正\n"); return 2;
            }
            mode = end + 1;
            if (!strcmp(mode, "suppress")) sii_mode = Q88H_SII_SUPPRESS;
            else if (!strcmp(mode, "delay-one")) sii_mode = Q88H_SII_DELAY_ONE;
            else { fprintf(stderr, "[q88measure] 未知のsub割り込み介入MODE\n"); return 2; }
            sii_first = (int32_t)first_value;
            sii_last = (int32_t)last_value;
        }
        else if (!strcmp(argv[i], "--main-interrupt-intervention") && i + 1 < argc) {
            char *end;
            const char *spec = argv[++i], *last, *mode;
            long first_value, last_value;
            first_value = strtol(spec, &end, 0);
            if (end == spec || *end != ':' || first_value < 0 || first_value > INT32_MAX) {
                fprintf(stderr, "[q88measure] main割り込み介入書式は FIRST:LAST:MODE\n"); return 2;
            }
            last = end + 1;
            last_value = strtol(last, &end, 0);
            if (end == last || *end != ':' || last_value < first_value || last_value > INT32_MAX) {
                fprintf(stderr, "[q88measure] main割り込み介入のrun範囲が不正\n"); return 2;
            }
            mode = end + 1;
            if (!strcmp(mode, "suppress")) mii_mode = Q88H_MII_SUPPRESS;
            else if (!strcmp(mode, "delay-one")) mii_mode = Q88H_MII_DELAY_ONE;
            else { fprintf(stderr, "[q88measure] 未知のmain割り込み介入MODE\n"); return 2; }
            mii_first = (int32_t)first_value;
            mii_last = (int32_t)last_value;
        }
        else if (!strcmp(argv[i], "--int-log") && i + 1 < argc)
            int_log_path = argv[++i];
        else if (!strcmp(argv[i], "--font-log") && i + 1 < argc)
            font_log_path = argv[++i];
        else if (!strcmp(argv[i], "--screenshot") && i + 1 < argc)
            screenshot_path = argv[++i];
        else if (!strcmp(argv[i], "--mem-write-log") && i + 1 < argc)
            mem_write_log_path = argv[++i];
        else if (!strcmp(argv[i], "--mem-write-range") && i + 1 < argc) {
            unsigned lo, hi;
            if (!parse_hex_range(argv[++i], &lo, &hi)) {
                fprintf(stderr, "[q88measure] --mem-write-range は LO-HI (16進, LO<=HI)\n");
                return 2;
            }
            mem_write_range_lo = lo; mem_write_range_hi = hi;
            mem_write_range_set = true;
        } else if (!strcmp(argv[i], "--mem-write-from-frame") && i + 1 < argc)
            mem_write_from_frame = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--vram-dump") && i + 1 < argc) {
            if (vram_dump_pending_path) {
                fprintf(stderr, "[q88measure] --vram-dump は直前の --vram-dump に"
                                "対応する --vram-dump-at が無いまま次を指定された: %s\n",
                        vram_dump_pending_path);
                return 2;
            }
            vram_dump_pending_path = argv[++i];
        } else if (!strcmp(argv[i], "--vram-dump-at") && i + 1 < argc) {
            if (!vram_dump_pending_path) {
                fprintf(stderr, "[q88measure] --vram-dump-at の前に --vram-dump PATH が要る\n");
                return 2;
            }
            if (n_vram_dump >= VRAM_DUMP_MAX) {
                fprintf(stderr, "[q88measure] --vram-dump は最大%d個\n", VRAM_DUMP_MAX);
                return 2;
            }
            vram_dump[n_vram_dump].path  = vram_dump_pending_path;
            vram_dump[n_vram_dump].frame = (unsigned)strtoul(argv[++i], NULL, 0);
            vram_dump[n_vram_dump].done  = false;
            n_vram_dump++;
            vram_dump_pending_path = NULL;
        }
        else if (!strcmp(argv[i], "--key-matrix") && i + 1 < argc) {
            const char *spec = argv[++i];
            int port_i, bit_i, frame_i, hold_i = -1;
            int n = sscanf(spec, "%i:%i:%i:%i", &port_i, &bit_i, &frame_i, &hold_i);
            if (n != 3 && n != 4) {
                fprintf(stderr, "[q88measure] --key-matrix書式は"
                                " PORT:BIT:FRAME[:HOLD] (10進/16進(0x..)): %s\n", spec);
                return 2;
            }
            if (port_i < 0x00 || port_i > 0x0E) {
                fprintf(stderr, "[q88measure] --key-matrix PORT は0x00-0x0Eの範囲外: %s\n", spec);
                return 2;
            }
            if (bit_i < 0 || bit_i > 7) {
                fprintf(stderr, "[q88measure] --key-matrix BIT は0-7の範囲外: %s\n", spec);
                return 2;
            }
            if (frame_i < 0) {
                fprintf(stderr, "[q88measure] --key-matrix FRAME は0以上: %s\n", spec);
                return 2;
            }
            if (hold_i == 0 || (n == 4 && hold_i < 0)) {
                fprintf(stderr, "[q88measure] --key-matrix HOLD は1以上: %s\n", spec);
                return 2;
            }
            if (n_keymatrix >= KEY_MATRIX_MAX) {
                fprintf(stderr, "[q88measure] --key-matrix は最大%d個\n", KEY_MATRIX_MAX);
                return 2;
            }
            keymatrix[n_keymatrix].port         = (unsigned)port_i;
            keymatrix[n_keymatrix].bit           = (unsigned)bit_i;
            keymatrix[n_keymatrix].frame         = (unsigned)frame_i;
            /* HOLD省略時は現時点の --key-hold の値を使う。--type の
             * schedule_typing と同じく指定順に依存する（usageにも明記）。 */
            keymatrix[n_keymatrix].hold          = (n == 4) ? (unsigned)hold_i : key_hold;
            keymatrix[n_keymatrix].done_press    = false;
            keymatrix[n_keymatrix].done_release  = false;
            n_keymatrix++;
        }
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
    if (disk2 && !disk) {
        fprintf(stderr, "[q88measure] --disk2 には --disk が要る\n");
        return 2;
    }
    if (disk2 && expect_disk2_empty) {
        fprintf(stderr, "[q88measure] --disk2 と --expect-disk2-empty は同時指定できない\n");
        return 2;
    }
    if (disk2) {
        struct stat st;
        if (stat(disk2, &st) != 0 || !S_ISREG(st.st_mode)) {
            fprintf(stderr, "[q88measure] --disk2 の通常ファイルを読めない: %s\n", disk2);
            return 2;
        }
    }
    if ((insert_disk2 != NULL) != insert_disk2_at_set) {
        fprintf(stderr, "[q88measure] --insert-disk2 と --insert-disk2-at は両方必須\n");
        return 2;
    }
    if (insert_disk2 && disk2) {
        fprintf(stderr, "[q88measure] --insert-disk2 と --disk2 は同時指定できない\n");
        return 2;
    }
    if (insert_disk2 && insert_disk2_at >= frames) {
        fprintf(stderr, "[q88measure] --insert-disk2-at は --frames 未満で指定すること\n");
        return 2;
    }
    if (insert_disk2) {
        struct stat st;
        if (stat(insert_disk2, &st) != 0 || !S_ISREG(st.st_mode)) {
            fprintf(stderr, "[q88measure] --insert-disk2 の通常ファイルを読めない: %s\n",
                    insert_disk2);
            return 2;
        }
    }
    if (io_log_path && io_log_from_frame >= frames) {
        fprintf(stderr, "[q88measure] --io-log-from-frame は --frames 未満で指定すること\n");
        return 2;
    }
    if (vram_dump_pending_path) {
        fprintf(stderr, "[q88measure] --vram-dump %s に対応する --vram-dump-at が無い\n",
                vram_dump_pending_path);
        return 2;
    }
    if (mem_write_log_path && !mem_write_range_set) {
        fprintf(stderr, "[q88measure] --mem-write-log には --mem-write-range が要る\n");
        return 2;
    }
    if (mem_write_log_path && mem_write_from_frame >= frames) {
        fprintf(stderr, "[q88measure] --mem-write-from-frame は --frames 未満で指定すること\n");
        return 2;
    }
    /* --key-matrix と --type の併用は禁止する。--type はコアの入力処理
     * （input_state_cb 経由の handle_key）が同じ key_scan を書き換えるので、
     * 同じフレームで両方使うと「どちらが最後に勝つか」がコア内部の処理順に
     * 依存してしまい、末端検査が不安定になる。安全側に倒して同時指定を
     * 引数エラーにする（優先順位を決めて黙って共存させる案は採らない）。 */
    if (n_keymatrix > 0 && g_n_keyev > 0) {
        fprintf(stderr, "[q88measure] --key-matrix と --type は同時指定できない"
                        "（どちらもkey_scanを書き換えるため、コア側の処理順に依存し"
                        "末端検査が不安定になる）\n");
        return 2;
    }
    for (k = 0; k < n_keymatrix; k++) {
        if (keymatrix[k].frame + keymatrix[k].hold > frames)
            fprintf(stderr, "[q88measure] 警告: --key-matrix %u:%u:%u:%u の解放"
                            "(frame %u)が --frames %u 以上なので届かない\n",
                    keymatrix[k].port, keymatrix[k].bit, keymatrix[k].frame,
                    keymatrix[k].hold, keymatrix[k].frame + keymatrix[k].hold, frames);
    }
    /* 出力先の安全策（禁止事項5/7）。走らせる前、コアの読み込みより先に
     * 検査する——「走らせたのに書けなかった」という遅い失敗より分かりやすい。 */
    if (mem_write_log_path && reject_if_unsafe_output_path("--mem-write-log", mem_write_log_path))
        return 1;
    for (k = 0; k < n_vram_dump; k++) {
        if (reject_if_unsafe_output_path("--vram-dump", vram_dump[k].path))
            return 1;
    }

    /* 何を測ったのかが後から辿れるように、必ず出す。
     * ここが取り違えられていると測定結果そのものが無意味になる。 */
    fprintf(stderr, "[q88measure] core    = %s\n", core);
    fprintf(stderr, "[q88measure] rom-dir = %s\n", g_rom_dir);
    fprintf(stderr, "[q88measure] disk    = %s\n", disk ? disk : "(なし)");
    if (disk2) fprintf(stderr, "[q88measure] disk2   = %s\n", disk2);
    if (insert_disk2)
        fprintf(stderr, "[q88measure] insert-disk2 = %s (at frame %u)\n",
                insert_disk2, insert_disk2_at);

    if (!load_core(core)) return 1;
    if ((disk2 || expect_disk2_empty || insert_disk2) && !p_filename_get_disk) {
        fprintf(stderr, "[q88measure] DRIVE_2末端状態を検査できないコア\n");
        return 2;
    }
    if (disk2 && !p_load_game_special) {
        fprintf(stderr, "[q88measure] retro_load_game_specialを持たないコア\n");
        return 2;
    }
    if (insert_disk2 && !p_quasi88_disk_insert) {
        fprintf(stderr, "[q88measure] quasi88_disk_insertを持たないコア\n");
        return 2;
    }
    if ((n_xi || ready_handoff_mode) && !g_exchange_intervention_available) {
        fprintf(stderr, "[q88measure] 交換run介入を持たないコア\n"); return 2;
    }
    if (n_rxi && !g_request_intervention_available) {
        fprintf(stderr, "[q88measure] 要求run介入を持たないコア\n"); return 2;
    }
    if (n_rsi && !g_response_intervention_available) {
        fprintf(stderr, "[q88measure] 応答run介入を持たないコア\n"); return 2;
    }
    if (sii_mode != Q88H_SII_NONE &&
        (!g_exchange_intervention_available || !g_sub_interrupt_intervention_available)) {
        fprintf(stderr, "[q88measure] sub割り込み介入を持たないコア\n"); return 2;
    }
    if (mii_mode != Q88H_MII_NONE &&
        (!g_exchange_intervention_available || !g_main_interrupt_intervention_available)) {
        fprintf(stderr, "[q88measure] main割り込み介入を持たないコア\n"); return 2;
    }

    p_set_environment(environment_cb);
    p_set_video_refresh(video_cb);
    p_set_audio_sample(audio_cb);
    p_set_audio_sample_batch(audio_batch_cb);
    p_set_input_poll(input_poll_cb);
    p_set_input_state(input_state_cb);

    p_init();

    if (disk2) {
        enum { Q88_SUBSYSTEM_2_DISK = 0x0101 };
        struct retro_game_info info[2];
        const char *actual1, *actual2;
        memset(info, 0, sizeof(info));
        info[0].path = disk;
        info[1].path = disk2;
#ifdef Q88MEASURE_FAULT_SWAP_DISKS
        /* disk2_selftest.shだけが別成果物へ有効化する故障注入。通常ビルドには入らない。 */
        info[0].path = disk2;
        info[1].path = disk;
#endif
        if (!p_load_game_special(Q88_SUBSYSTEM_2_DISK, info, 2)) {
            fprintf(stderr, "[q88measure] 二本のディスクで起動に失敗した\n");
            p_deinit();
            return 1;
        }
        actual1 = p_filename_get_disk(0);
        actual2 = p_filename_get_disk(1);
        if (!actual1 || !actual2 || strcmp(actual1, disk) || strcmp(actual2, disk2)) {
            fprintf(stderr, "[q88measure] NG: 二本のディスクがDRIVE_1/2へ指定順に入っていない\n");
            p_unload_game();
            p_deinit();
            return 1;
        }
        fprintf(stderr, "[q88measure] OK: 二本目のDRIVE_2挿入をコア末端状態で確認\n");
    } else {
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
    if (expect_disk2_empty) {
        if (p_filename_get_disk(1)) {
            fprintf(stderr, "[q88measure] NG: --disk2未指定なのにDRIVE_2へ媒体が入っている\n");
            p_unload_game();
            p_deinit();
            return 1;
        }
        fprintf(stderr, "[q88measure] OK: --disk2未指定時のDRIVE_2空状態をコア末端で確認\n");
    }
    if (insert_disk2) {
        /* 差し込み(--insert-disk2-at)より前は、--expect-disk2-emptyと同じ
         * 考え方でDRIVE_2が空であることを末端で確認する。ここで確認して
         * おけば、差し込み直後の「actualが指定パスに変わった」との対比が
         * 意味を持つ。 */
        if (p_filename_get_disk(1)) {
            fprintf(stderr, "[q88measure] NG: --insert-disk2指定なのに起動直後から"
                            "DRIVE_2へ媒体が入っている\n");
            p_unload_game();
            p_deinit();
            return 1;
        }
        fprintf(stderr, "[q88measure] OK: 差し込み前のDRIVE_2空状態をコア末端で確認\n");
    }

    if (g_exchange_intervention_available) {
        p_exchange_intervention_reset();
        for (i = 0; i < n_xi; i++) {
            if (!p_exchange_intervention_configure((unsigned)i, xi[i].run,
                                                   xi[i].mode, xi[i].value)) {
                fprintf(stderr, "[q88measure] 交換run介入の設定に失敗\n");
                p_deinit(); return 2;
            }
        }
        if (ready_handoff_mode && !p_exchange_ready_handoff_configure(
                ready_handoff_run, ready_handoff_mode)) {
            fprintf(stderr, "[q88measure] 応答準備handoff介入の設定に失敗\n");
            p_deinit(); return 2;
        }
    }
    if (g_request_intervention_available) {
        p_request_intervention_reset();
        for (i = 0; i < n_rxi; i++) {
            if (!p_request_intervention_configure((unsigned)i, rxi[i].run,
                                                  rxi[i].position, rxi[i].mode,
                                                  rxi[i].value)) {
                fprintf(stderr, "[q88measure] 要求run介入の設定に失敗\n");
                p_deinit(); return 2;
            }
        }
    }
    if (g_response_intervention_available) {
        p_response_intervention_reset();
        for (i = 0; i < n_rsi; i++) {
            if (!p_response_intervention_configure((unsigned)i, rsi[i].run,
                                                   rsi[i].position, rsi[i].mode,
                                                   rsi[i].value)) {
                fprintf(stderr, "[q88measure] 応答run介入の設定に失敗\n");
                p_deinit(); return 2;
            }
        }
    }
    if (g_sub_interrupt_intervention_available) {
        p_sub_interrupt_intervention_reset();
        if (sii_mode != Q88H_SII_NONE &&
            !p_sub_interrupt_intervention_configure(sii_first, sii_last, sii_mode)) {
            fprintf(stderr, "[q88measure] sub割り込み介入の設定に失敗\n");
            p_deinit(); return 2;
        }
    }
    if (g_main_interrupt_intervention_available) {
        p_main_interrupt_intervention_reset();
        if (mii_mode != Q88H_MII_NONE &&
            !p_main_interrupt_intervention_configure(mii_first, mii_last, mii_mode)) {
            fprintf(stderr, "[q88measure] main割り込み介入の設定に失敗\n");
            p_deinit(); return 2;
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
            p_iolog_set_enabled(io_log_from_frame == 0);
            fprintf(stderr, "[q88measure] I/O記録: out=%s, frame %u から有効\n",
                    io_log_path, io_log_from_frame);
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

    /* 範囲指定の書き込み記録（M7器具2）も iolog と同じ位置・同じ理由で
     * 有効化する。出力先の安全策はここ、load_game より前で検査済み
     * （下の入力検査ブロック参照）——コアを走らせる前に弾いたほうが、
     * 「走らせたのに書けなかった」より分かりやすい失敗になる。 */
    if (mem_write_log_path) {
        if (!g_memlog_available) {
            fprintf(stderr, "[q88measure] 注記: --mem-write-log が指定されたが、"
                            "このコアに範囲指定の書き込み記録が無いので無視する\n");
        } else {
            p_memlog_reset();
            p_memlog_set_range(mem_write_range_lo, mem_write_range_hi);
            p_memlog_set_enabled(mem_write_from_frame == 0);
            fprintf(stderr, "[q88measure] 書き込み記録: out=%s, range=%04X-%04X,"
                            " frame %u から有効\n",
                    mem_write_log_path, mem_write_range_lo, mem_write_range_hi,
                    mem_write_from_frame);
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

    for (k = 0; k < n_vram_dump; k++) {
        if (vram_dump[k].frame >= frames)
            fprintf(stderr, "[q88measure] 警告: --vram-dump-at %u は --frames %u"
                            " 以上なので届かない: %s\n",
                    vram_dump[k].frame, frames, vram_dump[k].path);
    }

    /* 測定区間はここから。ロード中のアクセスは数えない */
    p_trace_reset();
    if (g_trap_available && g_trap_map_path[0]) p_trap_reset();
    for (g_frame = 0; g_frame < frames; g_frame++) {
        /* イベントに frame を載せるため、走らせる前に必ず今のフレーム番号を
         * コア側へ渡す。有効化されていなくても呼ぶコスト自体は軽い。 */
        if (g_iolog_available) p_iolog_set_frame(g_frame);
        if (g_intlog_available) p_intlog_set_frame(g_frame);
        if (io_log_path && g_iolog_available && g_frame == io_log_from_frame)
            p_iolog_set_enabled(1);
        if (g_memlog_available) p_memlog_set_frame(g_frame);
        if (mem_write_log_path && g_memlog_available && g_frame == mem_write_from_frame)
            p_memlog_set_enabled(1);

        /* テキストVRAMの写し（M7器具1）。「g_frame==FRAME になったフレームの
         * retro_run()呼び出しの直前」——m7lw(--insert-disk2-at)と同じ定義に
         * 揃える。1回きりの寄与にするため done で管理する。 */
        for (k = 0; k < n_vram_dump; k++) {
            if (!vram_dump[k].done && g_frame == vram_dump[k].frame) {
                char outpath[PATH_MAX];
                vram_dump_path_for(outpath, sizeof(outpath), vram_dump[k].path,
                                   vram_dump[k].frame, n_vram_dump > 1);
                if (reject_if_unsafe_output_path("--vram-dump", outpath)) {
                    p_unload_game();
                    p_deinit();
                    return 1;
                }
                if (write_vram_dump(outpath, g_frame, p_text))
                    fprintf(stderr, "[q88measure] VRAM写しを書き出した: %s (frame=%u)\n",
                            outpath, g_frame);
                vram_dump[k].done = true;
            }
        }

        /* キーマトリクス直接操作（M7段階1の器具その2）。「g_frame==FRAME
         * になったフレームのretro_run()呼び出しの直前」——vram-dump/
         * insert-disk2-atと同じ定義に揃える。押す/離すをそれぞれ1回きり
         * done_press/done_releaseで管理する。故障注入は書き換えそのものを
         * 黙って飛ばす（記録も残さない——「効いたことにする」ではなく
         * 「効かなかったことがそのまま見える」ようにするため）。 */
        if (n_keymatrix > 0 && g_key_scan_available &&
            !getenv("Q88MEASURE_FAULT_SKIP_KEY_MATRIX")) {
            for (k = 0; k < n_keymatrix; k++) {
                unsigned port = keymatrix[k].port, bit = keymatrix[k].bit;
                if (!keymatrix[k].done_press && g_frame == keymatrix[k].frame) {
                    uint8_t before = p_key_scan[port];
                    p_key_scan[port] = (uint8_t)(before & ~(1u << bit));
                    if (n_kmrec < KEY_MATRIX_RECORD_MAX) {
                        kmrec[n_kmrec].frame  = g_frame;
                        kmrec[n_kmrec].port   = port;
                        kmrec[n_kmrec].bit    = bit;
                        kmrec[n_kmrec].before = before;
                        kmrec[n_kmrec].after  = p_key_scan[port];
                        kmrec[n_kmrec].action = "press";
                        n_kmrec++;
                    }
                    fprintf(stderr, "[q88measure] キーマトリクス押下: frame=%u port=%02X"
                                    " bit=%u key_scan[%02X]: %02X -> %02X\n",
                            g_frame, port, bit, port, before, p_key_scan[port]);
                    keymatrix[k].done_press = true;
                }
                if (keymatrix[k].done_press && !keymatrix[k].done_release &&
                    g_frame == keymatrix[k].frame + keymatrix[k].hold) {
                    uint8_t before = p_key_scan[port];
                    p_key_scan[port] = (uint8_t)(before | (1u << bit));
                    if (n_kmrec < KEY_MATRIX_RECORD_MAX) {
                        kmrec[n_kmrec].frame  = g_frame;
                        kmrec[n_kmrec].port   = port;
                        kmrec[n_kmrec].bit    = bit;
                        kmrec[n_kmrec].before = before;
                        kmrec[n_kmrec].after  = p_key_scan[port];
                        kmrec[n_kmrec].action = "release";
                        n_kmrec++;
                    }
                    fprintf(stderr, "[q88measure] キーマトリクス解放: frame=%u port=%02X"
                                    " bit=%u key_scan[%02X]: %02X -> %02X\n",
                            g_frame, port, bit, port, before, p_key_scan[port]);
                    keymatrix[k].done_release = true;
                }
            }
        }

        if (g_frame == reset_at) {
            p_reset();
            fprintf(stderr, "[q88measure] ハードウェアリセット: frame %u\n", g_frame);
        }

        /* m7lw: 「g_frame==FRAME になったフレームのretro_run()呼び出しの
         * 直前」と定義する。挿入は1回きり（この分岐にg_frame==FRAMEで
         * 一度だけ到達する）。 */
        if (insert_disk2 && !insert2_done && g_frame == insert_disk2_at) {
#ifdef Q88MEASURE_FAULT_SKIP_INSERT_DISK2
            /* insert_disk2_selftest.sh だけが別成果物へ有効化する故障注入。
             * quasi88_disk_insert を実際には呼ばず「呼んだふり」だけする。
             * 通常ビルドには入らない。 */
            insert2_rc = 1;
#else
            insert2_rc = p_quasi88_disk_insert(Q88_DRIVE_2, insert_disk2, 0, 0);
#endif
            insert2_actual = p_filename_get_disk(1);
            insert2_done = true;
            if (!insert2_rc || !insert2_actual || strcmp(insert2_actual, insert_disk2)) {
                fprintf(stderr, "[q88measure] NG: DRIVE_2への実行中差し込みが末端で"
                                "確認できない (frame=%u rc=%d)\n", g_frame, insert2_rc);
                p_unload_game();
                p_deinit();
                return 1;
            }
            fprintf(stderr, "[q88measure] OK: DRIVE_2への実行中差し込みをコア末端状態で確認"
                            " (frame=%u)\n", g_frame);
        }

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
        /* --dump-text は元々「画面が意図どおりか作業端末で目視確認する」
         * ためのフラグだが、標準エラーは作業端末へ素通しになりうる経路
         * （禁止事項7）。既存の tools 配下のシェル・Python スクリプトの
         * いずれもこのフラグを使っていない（grep 済み、docs/notes 内の手打ちコマンド
         * 例に残るのみ）ので、目視確認の需要そのものが無い。よって
         * 画面本文は出さず、通知だけ出す。 */
        if (dump_text) write_screen_redacted_notice(stderr);

        {
            q88h_trap_t *tp  = (g_trap_available && g_trap_map_path[0]) ? p_trap()     : NULL;
            q88h_trap_t *tps = (g_trap_available && g_trap_map_path[0]) ? p_trap_sub() : NULL;

            /* 標準出力は --out の有無に関係なく作業端末へ素通しになりうる
             * 経路なので、show_screen は常に false。画面本文が要る側は
             * 必ず --out のファイルを経由し、check_l3_screen_output.py 等
             * の署名化ヘルパで扱う（write_screen_redacted_notice 参照）。
             *
             * Q88MEASURE_FAULT_SHOW_SCREEN_ON_STDOUT は自己検査専用の
             * 故障注入（既存の Q88MEASURE_FAULT_* と同じ作法）。
             * 修正前の「標準出力にも画面本文が出る」挙動をわざと再現し、
             * tools/screen_content_leak_selftest.sh の陰性対照が
             * 検出力を持つことを確かめるためだけに使う。通常運用では
             * 設定しない。 */
            write_report(stdout, t, p_trace_sub(), tp, tps, core, g_rom_dir,
                         disk, disk2, frames,
                         insert2_done, insert_disk2_at, insert2_rc, insert2_actual,
                         kmrec, n_kmrec,
                         getenv("Q88MEASURE_FAULT_SHOW_SCREEN_ON_STDOUT") != NULL);
            if (out) {
                FILE *fp = fopen(out, "w");
                if (!fp) { perror(out); return 1; }
                /* --out のファイルは既存ツール（check_l3_screen_output.py・
                 * check_l3_entry_screen.py）が読む前提の書式なので、
                 * show_screen は true のまま変えない。 */
                write_report(fp, t, p_trace_sub(), tp, tps, core, g_rom_dir,
                             disk, disk2, frames,
                             insert2_done, insert_disk2_at, insert2_rc, insert2_actual,
                             kmrec, n_kmrec, true);
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
                write_iolog_report(fp, core, g_rom_dir, disk, disk2, frames,
                                   io_log_from_frame, l, ls);
                fclose(fp);
                fprintf(stderr, "[q88measure] I/O記録を書き出した: %s"
                                " (main: %u件/取りこぼし%u件, sub: %u件/取りこぼし%u件)\n",
                        io_log_path, l->n_events, l->n_dropped, ls->n_events, ls->n_dropped);
            }

            /* 範囲指定の書き込み記録（M7器具2）も --io-log と同じく別ファイルに書く。
             * 出力先の安全策は起動直後に検査済みだが、値そのものが対象範囲の
             * 実データなので、ここでも念のため同じ検査を通す
             * （検査から書き出しまでの間に symlink 差し替え等が起きても弾ける）。 */
            if (mem_write_log_path && g_memlog_available) {
                q88h_memlog_t *m = p_memlog();
                FILE *fp;

                /* mem_write_log_selftest.sh 専用の故障注入。既定では環境変数が
                 * 無いので何もしない。「取りこぼし数(n_dropped)を増やさずに
                 * 1件を黙って落とす」経路を模して、末尾から1件だけ配列上で
                 * 消す（seqの欠番として現れる——取りこぼし数だけを見ていた
                 * 検査ではここを見逃す）。実際の記録経路（q88h_memlog_record）
                 * 自体はいじらず、書き出す直前の値を壊すだけ。 */
                if (getenv("Q88MEASURE_FAULT_DROP_MEMLOG_EVENT") && m->n_events > 0)
                    m->n_events--;

                if (reject_if_unsafe_output_path("--mem-write-log", mem_write_log_path))
                    return 1;
                fp = fopen(mem_write_log_path, "w");
                if (!fp) { perror(mem_write_log_path); return 1; }
                write_memlog_report(fp, core, g_rom_dir, disk, disk2, frames,
                                    mem_write_from_frame, m);
                fclose(fp);
                fprintf(stderr, "[q88measure] 書き込み記録を書き出した: %s"
                                " (%u件/取りこぼし%u件)\n",
                        mem_write_log_path, m->n_events, m->n_dropped);
            }

            /* 割り込み受理ログ（M4c）も --io-log と同じく別ファイルに書く。
             * 性格が違う記録を混ぜないという方針を踏襲する。 */
            if (int_log_path && g_intlog_available) {
                q88h_intlog_t *l  = p_intlog();
                q88h_intlog_t *ls = p_intlog_sub();
                FILE *fp = fopen(int_log_path, "w");
                if (!fp) { perror(int_log_path); return 1; }
                write_intlog_report(fp, core, g_rom_dir, disk, disk2, frames, l, ls);
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
                write_fontsrc_report(fp, core, g_rom_dir, disk, disk2, frames, f);
                fclose(fp);
                fprintf(stderr, "[q88measure] フォント供給源記録を書き出した: %s\n",
                        font_log_path);
            }

            /* 画面ピクセルスナップショット（M5本題）。フレームループが終わった
             * 今の状態（＝最後に走ったフレームの結果）を1枚キャプチャする。
             * font_mem に届いた、ではなく実際に描画されたピクセルを見るための
             * フックなので、他のログとは見ている末端が違う。 */
            if (screenshot_path) {
                if (!g_screenshot_available) {
                    fprintf(stderr, "[q88measure] 注記: --screenshot が指定されたが、"
                                    "このコアに画面スナップショットが無いので無視する\n");
                } else {
                    q88h_screenshot_t *s = p_screenshot();
                    p_screenshot_capture();
                    if (s->magic != Q88H_SCREENSHOT_MAGIC || !s->captured) {
                        fprintf(stderr, "[q88measure] NG: 画面スナップショットの採取に失敗した\n");
                        failed = 1;
                    } else if (!write_screenshot_ppm(screenshot_path, s)) {
                        failed = 1;
                    } else {
                        fprintf(stderr, "[q88measure] スクリーンショットを書き出した: %s"
                                        " (%ux%u, PPM/P6)\n",
                                screenshot_path,
                                (unsigned)Q88H_SCREENSHOT_W, (unsigned)Q88H_SCREENSHOT_H);
                    }
                }
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


        if (n_xi) {
            q88h_exchange_intervention_t *state = p_exchange_intervention();
            for (i = 0; i < n_xi; i++) {
                q88h_exchange_intervention_slot_t *slot = &state->slot[i];
                int xor_mode = slot->mode == Q88H_XI_XOR_ALL ||
                               slot->mode == Q88H_XI_XOR_FIRST ||
                               slot->mode == Q88H_XI_XOR_TAIL;
                fprintf(stderr, "[q88measure] 交換介入slot%d run=%d matched=%u applied=%u changed=%u\n",
                        i, (int)slot->run_index, slot->matched_events,
                        slot->applied_events, slot->changed_events);
                if (!slot->matched_run || slot->matched_events == 0 ||
                    slot->applied_events == 0 || (xor_mode && slot->changed_events == 0)) {
                    fprintf(stderr, "[q88measure] NG: 交換介入slot%dが実際には効いていない\n", i);
                    failed = 1;
                }
            }
        }
        if (n_rxi) {
            q88h_request_intervention_t *state = p_request_intervention();
            for (i = 0; i < n_rxi; i++) {
                q88h_request_intervention_slot_t *slot = &state->slot[i];
                fprintf(stderr, "[q88measure] 要求介入slot%d run=%d pos=%u"
                                " matched=%u applied=%u changed=%u\n",
                        i, (int)slot->run_index, slot->position,
                        slot->matched_events, slot->applied_events,
                        slot->changed_events);
            }
        }
        if (n_rsi) {
            q88h_response_intervention_t *state = p_response_intervention();
            for (i = 0; i < n_rsi; i++) {
                q88h_response_intervention_slot_t *slot = &state->slot[i];
                fprintf(stderr, "[q88measure] 応答介入slot%d run=%d pos=%u"
                                " matched=%u applied=%u changed=%u\n",
                        i, (int)slot->run_index, slot->position,
                        slot->matched_events, slot->applied_events,
                        slot->changed_events);
            }
        }
        if (ready_handoff_mode) {
            q88h_exchange_intervention_t *state = p_exchange_intervention();
            fprintf(stderr, "[q88measure] 応答準備handoff介入 run=%d mode=%d action=%d matched=%u count=%u\n",
                    (int)state->ready_handoff_run, (int)state->ready_handoff_mode,
                    (int)state->ready_handoff_action,
                    state->ready_handoff_matched_waits,
                    state->ready_handoff_action_count);
            if (!state->ready_handoff_armed ||
                state->ready_handoff_action_count != 1 ||
                state->ready_handoff_mode != ready_handoff_mode) {
                fprintf(stderr, "[q88measure] NG: 応答準備handoff介入が作用点へ届いていない\n");
                failed = 1;
            }
        }

        if (sii_mode != Q88H_SII_NONE) {
            q88h_sub_interrupt_intervention_t *state = p_sub_interrupt_intervention();
            fprintf(stderr, "[q88measure] sub割り込み介入 first=%d last=%d mode=%u matched=%u suppressed=%u accepted=%u\n",
                    (int)state->first_run, (int)state->last_run, state->mode,
                    state->matched_checks, state->suppressed_checks,
                    state->accepted_in_window);
            if (!state->configured || state->matched_checks == 0 ||
                state->suppressed_checks == 0) {
                fprintf(stderr, "[q88measure] NG: sub割り込み介入が実際には届いていない\n");
                failed = 1;
            }
        }

        if (mii_mode != Q88H_MII_NONE) {
            q88h_main_interrupt_intervention_t *state = p_main_interrupt_intervention();
            fprintf(stderr, "[q88measure] main割り込み介入 first=%d last=%d mode=%u matched=%u suppressed=%u accepted=%u\n",
                    (int)state->first_run, (int)state->last_run, state->mode,
                    state->matched_checks, state->suppressed_checks,
                    state->accepted_in_window);
            if (!state->configured || state->matched_checks == 0 ||
                state->suppressed_checks == 0) {
                fprintf(stderr, "[q88measure] NG: main割り込み介入が実際には届いていない\n");
                failed = 1;
            }
        }

        fprintf(stderr, "q88h: core_option q88_sub_cpu_mode requested=%u returned=%s\n",
                g_sub_cpu_mode_requested,
                g_sub_cpu_mode_set ? g_sub_cpu_mode : "none");

        p_unload_game();
        p_deinit();
        return failed;
    }
}

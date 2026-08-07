/*
 * q88h_trace.h — PC88Behavior 計測ハーネス / バスアクセス採取
 *
 * QUASI88 のコアに組み込み、Z80 が触れたアドレスを記録する。
 * 記録するのは「どこに、どの種類のアクセスがあったか」だけで、
 * 読んだ内容（バイト列）は一切保持しない。採るのは事実であって表現ではない。
 *
 * 実行アクセス (fetch) とデータアクセス (mem_read) を分けて数えるのが要点。
 * docs/PLAN.md 開発ループ ① が要求する区別がこれにあたる。
 *
 * シンボル名を retro_ で始めているのは、上流の link.T が
 * `global: retro_*; local: *;` でエクスポートを絞っているため。
 * こうしないと Linux ビルドでフロントエンドから見えなくなる。
 */
#ifndef Q88H_TRACE_H_INCLUDED
#define Q88H_TRACE_H_INCLUDED

#include <stdint.h>

#define Q88H_TRACE_MAGIC   0x54423838u   /* "88BT" (LE) */
#define Q88H_TRACE_VERSION 1u

#define Q88H_MEM_SIZE 0x10000
#define Q88H_IO_SIZE  0x100

typedef struct {
    uint32_t magic;
    uint32_t version;

    /* アドレスごとのアクセス有無。0 = 触れていない, 1 = 触れた */
    uint8_t mem_exec [Q88H_MEM_SIZE];   /* 命令フェッチ = 実行された */
    uint8_t mem_read [Q88H_MEM_SIZE];   /* データとして読まれた */
    uint8_t mem_write[Q88H_MEM_SIZE];
    uint8_t io_in    [Q88H_IO_SIZE];
    uint8_t io_out   [Q88H_IO_SIZE];

    /* 総アクセス回数（アドレス別ではなく合計）。フックが生きているかの確認用 */
    uint64_t n_exec, n_read, n_write, n_in, n_out;
} q88h_trace_t;

/* テキスト画面（既定のレイアウト） */
#define Q88H_TEXT_BASE   0xF3C8
#define Q88H_TEXT_ROWS   25
#define Q88H_TEXT_COLS   80
#define Q88H_TEXT_STRIDE 120

#ifdef __cplusplus
extern "C" {
#endif

/* 採取バッファへのポインタ。コア内からもフロントエンドからも同じ物を見る。
 *
 * PC-88 は Z80 を 2 個持つ。メイン CPU が N88-BASIC を、
 * サブ CPU がディスク側（DISK.ROM）を動かす。
 * サブ ROM も再実装の対象なので、別のバッファに分けて採る。 */
q88h_trace_t *retro_q88h_trace(void);
q88h_trace_t *retro_q88h_trace_sub(void);

/* 採取内容を全消去する。測定区間を切りたいときに呼ぶ */
void retro_q88h_trace_reset(void);

/* テキスト画面を読み出す。打鍵やコマンドが実際に効いたかの確認用。
 * 画面に出た文字は ROM の実行結果であって ROM のバイト列ではない。 */
void retro_q88h_text(uint8_t *dst, uint32_t rows, uint32_t cols, uint32_t stride);

#ifdef __cplusplus
}
#endif

#endif /* Q88H_TRACE_H_INCLUDED */

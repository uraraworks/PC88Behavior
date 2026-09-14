/*
 * q88h_memlog.h — PC88Behavior 計測ハーネス / 範囲指定メモリ書き込み記録
 *
 * q88h_trace.h の mem_write は「触れたか触れていないか」の有無フラグと
 * 総回数しか採らない。M7 段階1（main側L3の測定）でテキストVRAMへの
 * 書き込み順序・値・発行元PCを見るには、q88h_iolog.h と同じ形の
 * 順序付き記録が要る。
 *
 * q88h_iolog.h との違いは以下の2点:
 *   - 対象が I/O ポートではなく、指定した1本のメモリ範囲 [range_lo, range_hi]
 *     （フロントエンドが起動時に一度だけ設定する）
 *   - 発行元PCが「OUT/IN命令の先頭番地」ではなく「その書き込みを行った
 *     命令の先頭番地」。メモリ書き込み命令は1〜4バイトと長さがまちまちで
 *     （IN/OUT のように毎回2バイトとは限らない）、PC.W からの引き算では
 *     求められない。そこで pc88main.c 側に「現在実行中の命令の先頭番地」
 *     を fetch() のたびに追跡する仕組み（q88h_instr_pc）を足し、
 *     そこから渡す。詳細は tools/patches/0014-mem-write-log.patch の
 *     pc88main.c 側コメント参照。
 *
 * 記録する値はすべて「実行の結果として外部から観測できるもの」
 * （番地・書いた値・発行元PC・フレーム番号）であって、ROM のバイト列
 * そのものではない（docs/PLAN.md 第5節）。ただし対象範囲をテキストVRAM
 * にすると値そのものが画面本文（文字コード）になりうるので、これを
 * ファイルへ書き出す側（q88measure）は禁止事項5/7と同じ扱いで
 * 出力先を制限する。
 *
 * シンボル名を retro_ で始めているのは q88h_trace.h / q88h_iolog.h と
 * 同じ理由（上流の link.T が `global: retro_*; local: *;` でエクスポートを
 * 絞っているため）。
 */
#ifndef Q88H_MEMLOG_H_INCLUDED
#define Q88H_MEMLOG_H_INCLUDED

#include <stdint.h>

#define Q88H_MEMLOG_MAGIC   0x4D423838u   /* "88BM" (LE) */
#define Q88H_MEMLOG_VERSION 1u

/* 容量。selftest では小さい容量へ上書きして「容量内の記録内容が容量値に
 * 依存しない」「取りこぼし数が正しく増える」ことを照合する
 * （q88h_iolog.h の Q88H_IOLOG_MAX_EVENTS と同じ作法）。 */
#ifndef Q88H_MEMLOG_MAX_EVENTS
#define Q88H_MEMLOG_MAX_EVENTS (1u << 20)
#endif

typedef struct {
    uint32_t seq;    /* 1始まりの通し番号（記録できたイベントの中での順） */
    uint32_t frame;  /* フロントエンドが毎フレーム設定した値のスナップショット */
    uint16_t pc;     /* 発行元＝その書き込みを行った命令の先頭番地 */
    uint16_t addr;   /* 書き込み先番地 */
    uint8_t  value;  /* 書いた値 */
    uint8_t  pad[3];
} q88h_memlog_ev_t;

typedef struct {
    uint32_t magic, version;

    uint8_t  enabled;   /* フロントエンドが on/off を切る。既定 off。
                          * q88h_iolog_t.enabled と同じ理由 —
                          * 明示的に有効化しない限り記録しない。 */
    uint8_t  pad[3];

    uint32_t frame;     /* 現在のフレーム番号。フロントエンドが毎フレーム設定する */

    /* 記録対象の範囲 [range_lo, range_hi]（両端含む）。フロントエンドが
     * 起動時に一度だけ設定する。range_lo > range_hi のときは「範囲未設定」
     * として扱い、コア側は何も記録しない（すべて弾く）。 */
    uint32_t range_lo, range_hi;

    uint32_t n_events, n_dropped;
    q88h_memlog_ev_t ev[Q88H_MEMLOG_MAX_EVENTS];
} q88h_memlog_t;

#ifdef __cplusplus
extern "C" {
#endif

/* main CPU 用。ディスク側（サブCPU）は今回の対象外
 * （M7段階1はテキストVRAMを含む main側の測定が目的で、範囲もテキストVRAM
 * 付近を想定しているため）。 */
q88h_memlog_t *retro_q88h_memlog(void);

/* 採取内容（イベント・件数）を全消去する。enabled・range は変えない。
 * q88h_iolog_reset と同じ理由 — reset のたびに設定まで落ちると
 * 「reset したら記録が止まっていた」という無言の劣化になる。 */
void retro_q88h_memlog_reset(void);

/* 記録の on/off をフロントエンドから切る。既定 off。 */
void retro_q88h_memlog_set_enabled(int enabled);

/* 現在のフレーム番号を渡す。フロントエンドが毎フレーム呼ぶ。 */
void retro_q88h_memlog_set_frame(uint32_t frame);

/* 記録対象の範囲を設定する。フロントエンドが起動時に一度だけ呼ぶ。 */
void retro_q88h_memlog_set_range(uint32_t lo, uint32_t hi);

/* 書き込みイベントの記録。パッチ側の q88h_mem_write から呼ぶ。
 * enabled かどうか・範囲内かどうかの判定は呼び手（パッチ側）の責任。
 * ここでは記録だけを行う（q88h_iolog_record と同じ役割分担）。
 * バッファが満杯なら n_dropped を増やすだけで上書きはしない。 */
void q88h_memlog_record( q88h_memlog_t *l, uint16_t addr, uint8_t value, uint16_t pc );

#ifdef __cplusplus
}
#endif

#endif /* Q88H_MEMLOG_H_INCLUDED */

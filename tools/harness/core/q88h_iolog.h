/*
 * q88h_iolog.h — PC88Behavior 計測ハーネス / 順序付き I/O 記録
 *
 * q88h_trace.h は「触れたポートの集合（有無フラグ）」しか採らない。
 * M4（L1 IPL のクリーンルーム実装）の完了条件は「自作 IPL が公式版と
 * 同じ I/O 書き込み"列"を出す」ことなので、有無フラグでは判定できない。
 * このファイルは順序・値・発行元 PC を1件ずつ記録する。
 *
 * 記録する値はすべて「実行の結果として外部から観測できるもの」
 * （ポート番号・書いた値/読めた値・発行元PC・フレーム番号）であって、
 * ROM のバイト列そのものではない（docs/PLAN.md 第5節）。
 *
 * シンボル名を retro_ で始めているのは q88h_trace.h / q88h_trap.h と同じ理由。
 * 上流の link.T が `global: retro_*; local: *;` でエクスポートを絞っているため。
 */
#ifndef Q88H_IOLOG_H_INCLUDED
#define Q88H_IOLOG_H_INCLUDED

#include <stdint.h>

#define Q88H_IOLOG_MAGIC   0x4C423838u   /* "88BL" (LE) */
#define Q88H_IOLOG_VERSION 2u   /* v2 (M6c): q88h_iolog_ev_t に clock を追加 */

/* 反復区間を短縮せず採るため、1CPUあたり 1<<23 件を確保する。
 * 旧容量(1<<20)では高密度なSENSE反復100Fを保持できなかった。
 * selftestでは小さい2種類の代表容量へ上書きし、容量内の記録内容が容量値に
 * 依存しないことも照合する。 */
#ifndef Q88H_IOLOG_MAX_EVENTS
#define Q88H_IOLOG_MAX_EVENTS (1u << 23)
#endif

/* kind: イベントの種別 */
enum { Q88H_IOLOG_OUT = 0, Q88H_IOLOG_IN = 1 };

typedef struct {
    uint32_t seq;      /* 1始まりの通し番号（記録できたイベントの中での順） */
    uint32_t clock;    /* M6c: main/sub・iolog/intlog を横断する共通の
                          * 単調増加通し番号（q88h_clock.h）。frame は
                          * 1フレームに数千件のイベントが起きるため
                          * main/sub の真の前後関係を表せないが、これは
                          * 表す——q88h_clock.h の説明参照。 */
    uint32_t frame;    /* フロントエンドが毎フレーム設定した値のスナップショット */
    uint16_t pc;        /* 発行元（OUT/IN 命令の先頭番地）。
                          * z80.h の PC_prev は「モニタ用のダミー」で
                          * CPU セットアップ時に一度きり設定されるだけと判明した
                          * （実測で常に 0000 だった）ため、パッチ側では
                          * PC.W - 2 から逆算している。詳細は
                          * pc88main.c の q88h_io_in のコメント参照。 */
    uint8_t  kind;      /* Q88H_IOLOG_OUT / Q88H_IOLOG_IN */
    uint8_t  port;
    uint8_t  value;     /* OUT は書いた値、IN は読めた値 */
    uint8_t  pad;
} q88h_iolog_ev_t;

typedef struct {
    uint32_t magic, version;

    uint8_t  enabled;   /* フロントエンドが on/off を切る。既定 off。
                          * 常時 8MB 級のバッファへ書き続けると既存の
                          * 170 条件スイートが遅くなるため、明示的に
                          * 有効化しない限り記録しない。 */
    uint8_t  pad[3];

    uint32_t frame;     /* 現在のフレーム番号。フロントエンドが毎フレーム設定する */

    uint32_t n_events, n_dropped;
    q88h_iolog_ev_t ev[Q88H_IOLOG_MAX_EVENTS];
} q88h_iolog_t;

#ifdef __cplusplus
extern "C" {
#endif

/* PC-88 は Z80 を2個持つ。メインCPU用・サブCPU用を別バッファで持つのは
 * q88h_trace.h / q88h_trap.h と同じ理由。2つの CPU は別々に走るため、
 * seq は CPU をまたいで前後関係を表さない（frontend 側で節を分けて出す）。 */
q88h_iolog_t *retro_q88h_iolog(void);
q88h_iolog_t *retro_q88h_iolog_sub(void);

/* 採取内容（イベント・件数）を全消去する。enabled は変えない。
 * q88h_trap.c の retro_q88h_trap_reset と同じ理由 —
 * reset のたびに enabled まで落ちると「reset したら記録が止まっていた」
 * という無言の劣化になる。 */
void retro_q88h_iolog_reset(void);

/* 記録の on/off をフロントエンドから切る。既定 off。main/sub 両方に効く
 * ——フロントエンドは「このCPUだけ記録する」という使い方をしないため、
 * ここで一括にして呼び出し側の取り違えを防ぐ。 */
void retro_q88h_iolog_set_enabled(int enabled);

/* 現在のフレーム番号を渡す。フロントエンドが毎フレーム呼ぶ。
 * main/sub 両方の frame に同じ値が入る（同じフレームの中で両CPUが走るため）。 */
void retro_q88h_iolog_set_frame(uint32_t frame);

/* I/O イベントの記録。パッチ側の q88h_io_in / q88h_io_out から呼ぶ。
 * enabled のチェックは呼び手（パッチ側）の責任。ここでは記録だけを行う
 * （q88h_trap_record と同じ役割分担）。
 * バッファが満杯なら n_dropped を増やすだけで上書きはしない
 * ——起動の先頭こそが知りたいものなので、古いイベントを消して
 * 新しいイベントで上書きする設計にはしない。 */
void q88h_iolog_record(q88h_iolog_t *l, uint8_t kind, uint8_t port,
                        uint8_t value, uint16_t pc);

#ifdef __cplusplus
}
#endif

#endif /* Q88H_IOLOG_H_INCLUDED */

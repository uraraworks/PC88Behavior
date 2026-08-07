/*
 * q88h_intlog.h — PC88Behavior 計測ハーネス / 割り込み受理ログ
 *
 * q88h_iolog.h は「Z80 が OUT/IN した」という事実を記録する。
 * このファイルは一段手前、「Z80 が割り込みそのものを受理した」という
 * 事実を記録する。M4c の目的は docs/spec/l1-ipl.md 第8節の未解決点
 * 「定常状態が1フレームに1回である理由。割り込み駆動か、そうでないか」
 * を、PC が RAM(E7Fx) にあるという状況証拠ではなく、Z80 が実際に
 * 割り込みを受理した事実そのもので確定させることにある。
 *
 * 記録する値はすべて「実行の結果として外部から観測できるもの」
 * （割り込みモード・レベル・受理直前PC・分岐後PC・フレーム番号）で
 * あって、ROM のバイト列そのものではない（docs/PLAN.md 第5節）。
 *
 * シンボル名を retro_ で始めているのは q88h_iolog.h / q88h_trace.h /
 * q88h_trap.h と同じ理由。上流の link.T が
 * `global: retro_*; local: *;` でエクスポートを絞っているため。
 */
#ifndef Q88H_INTLOG_H_INCLUDED
#define Q88H_INTLOG_H_INCLUDED

#include <stdint.h>

#define Q88H_INTLOG_MAGIC   0x4C423838u   /* "88BL" (LE)。q88h_iolog と同じ値でよい
                                            * ——バッファの取り違え検出用の合言葉であって、
                                            * ファイル種別の判別には使っていないため。 */
#define Q88H_INTLOG_VERSION 1u

/* 起動シーケンスで何件出るか事前に分からないので、まず取りこぼさないことを
 * 優先して大きめに取る。1CPUあたり 1<<16 件
 * ——割り込み受理は OUT/IN ほど頻発しないので q88h_iolog より小さくてよい。 */
#define Q88H_INTLOG_MAX_EVENTS (1u << 16)

typedef struct {
    uint32_t seq;        /* 1始まりの通し番号（記録できたイベントの中での順） */
    uint32_t frame;      /* フロントエンドが毎フレーム設定した値のスナップショット */
    uint16_t ret_pc;     /* 受理直前のPC（＝スタックに積まれる戻り番地）。
                           * HALT 中に受理した場合は HALT 解除で PC が +1 された
                           * "あと" の値になる（実機の Z80 も同じ——HALT の再実行を
                           * 戻り先にしない）。詳細はパッチ側 z80.c のコメント参照。 */
    uint16_t handler_pc; /* 分岐後のPC（ハンドラ入口）。IM1 なら常に 0x0038。 */
    uint8_t  im;         /* 受理時の割り込みモード（z80->IM） */
    uint8_t  level;      /* intr_ack() が返したレベル */
    uint8_t  pad[2];
} q88h_intlog_ev_t;

typedef struct {
    uint32_t magic, version;

    uint8_t  enabled;   /* フロントエンドが on/off を切る。既定 off。
                          * 常時大きなバッファへ書き続けると既存の測定が
                          * 遅くなるため、明示的に有効化しない限り記録しない。 */
    uint8_t  pad[3];

    uint32_t frame;     /* 現在のフレーム番号。フロントエンドが毎フレーム設定する */

    uint32_t n_events, n_dropped;
    q88h_intlog_ev_t ev[Q88H_INTLOG_MAX_EVENTS];
} q88h_intlog_t;

#ifdef __cplusplus
extern "C" {
#endif

/* PC-88 は Z80 を2個持つ。メインCPU用・サブCPU用を別バッファで持つのは
 * q88h_iolog.h と同じ理由。2つの CPU は別々に走るため、seq は CPU を
 * またいで前後関係を表さない（frontend 側で節を分けて出す）。 */
q88h_intlog_t *retro_q88h_intlog(void);
q88h_intlog_t *retro_q88h_intlog_sub(void);

/* 採取内容（イベント・件数）を全消去する。enabled は変えない。
 * q88h_iolog.c の retro_q88h_iolog_reset と同じ理由。 */
void retro_q88h_intlog_reset(void);

/* 記録の on/off をフロントエンドから切る。既定 off。main/sub 両方に効く
 * ——q88h_iolog.c と同じ理由。 */
void retro_q88h_intlog_set_enabled(int enabled);

/* 現在のフレーム番号を渡す。フロントエンドが毎フレーム呼ぶ。
 * main/sub 両方の frame に同じ値が入る（同じフレームの中で両CPUが走るため）。 */
void retro_q88h_intlog_set_frame(uint32_t frame);

/* 割り込み受理イベントの記録。パッチ側の z80.c の z80_interrupt から呼ぶ。
 * enabled のチェックは呼び手（パッチ側）の責任。ここでは記録だけを行う
 * （q88h_iolog_record と同じ役割分担）。
 * バッファが満杯なら n_dropped を増やすだけで上書きはしない
 * ——起動の先頭こそが知りたいものなので、古いイベントを消して
 * 新しいイベントで上書きする設計にはしない。 */
void q88h_intlog_record(q88h_intlog_t *l, uint8_t im, uint8_t level,
                         uint16_t ret_pc, uint16_t handler_pc);

/* main/sub の判別について: 当初は z80.c から z80main_cpu/z80sub_cpu が
 * 見えない前提で「pc88main_init からポインタを登録してもらう」設計を
 * 検討したが、実際には pc88cpu.h は z80.h しか要求しない薄いヘッダだと
 * 確認できたため、パッチ側（z80.c）で直接 #include "pc88cpu.h" して
 * `z80 == &z80main_cpu` で比較する方式にした（registration の類は
 * 導入していない）。詳細はパッチ 0006-int-log.patch の z80.c 側コメント参照。 */

#ifdef __cplusplus
}
#endif

#endif /* Q88H_INTLOG_H_INCLUDED */

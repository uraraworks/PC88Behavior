/*
 * q88h_trap.h — PC88Behavior 計測ハーネス / トラップROM足場
 *
 * q88h_trace.h が「触れた番地の集合」を採るのに対し、こちらは
 * 「その番地が要求されたときの入口の状態」を1件ずつ記録する。
 * ROM 未実装の状態でも、CALL/JP されたら何かを返して先に進める
 * （RET モード）か、その場で止めて実測に使う（STOP モード）かを選べる。
 *
 * 記録する値は全部「実行の結果として外部から観測できるもの」
 * （要求番地・戻り番地・直前PC・入口のレジスタ）であって、
 * ROM のバイト列そのものではない。
 *
 * シンボル名を retro_ で始めているのは q88h_trace.h と同じ理由。
 * 上流の link.T が `global: retro_*; local: *;` でエクスポートを絞っているため。
 */
#ifndef Q88H_TRAP_H_INCLUDED
#define Q88H_TRAP_H_INCLUDED

#include <stdint.h>

#define Q88H_TRAP_MAGIC   0x50423838u   /* "88BP" (LE) */
#define Q88H_TRAP_VERSION 1u

#define Q88H_TRAP_MAX_EVENTS 4096

/* mode: フロントエンドが起動前に設定する動作モード */
enum { Q88H_TRAP_OFF = 0, Q88H_TRAP_RET = 1, Q88H_TRAP_STOP = 2 };

/* kind: イベントの種別 */
enum { Q88H_TRAP_EXEC = 0, Q88H_TRAP_DATA = 1 };

typedef struct {
    uint32_t seq;        /* 発生順（記録できたイベントの中での通し番号、1始まり） */
    uint16_t addr;        /* 要求された番地 */
    uint16_t caller;      /* スタック先頭から読んだ戻り番地（CALLで来た場合の呼び元の次） */
    uint16_t prev_fetch;  /* 直前に fetch() で要求された番地（＝直前の命令バイトの取得元）。
                            * パッチ側が自前で維持する値であって Z80 コアの PC_prev では
                            * ない（PC_prev は z80.h のコメントどおり「モニタ用のダミー」で、
                            * 通常実行では常に 0000 のまま更新されず使い物にならないと実測で
                            * 判明した）。
                            * 「直前に実行された命令の先頭番地」ではない点にも注意：
                            * CB/ED/DD/FD 等のプレフィクスやオペランドのフェッチも同じ
                            * fetch() を通るので、直前命令の途中（プレフィクスやオペランド
                            * の一部）を指すことがある。JP/JR で来た場合の手掛かりとして
                            * 使うときは、この限界を踏まえて読むこと。 */
    uint16_t sp;
    uint16_t af, bc, de, hl;   /* 入口のレジスタ = 引数の観測 */
    uint8_t  kind;        /* Q88H_TRAP_EXEC / Q88H_TRAP_DATA */
    uint8_t  pad;
} q88h_trap_ev_t;

typedef struct {
    uint32_t magic, version;

    uint8_t  mode;              /* フロントエンドが設定する動作モード */
    uint8_t  stopped;           /* STOPモードで発火したら1 */
    uint16_t stop_addr;

    uint8_t  map[0x10000];      /* 1 = トラップ対象。フロントエンドが設定する */

    uint32_t exec_hits[0x10000];
    uint32_t data_hits[0x10000];

    uint32_t n_events, n_dropped;
    q88h_trap_ev_t ev[Q88H_TRAP_MAX_EVENTS];
} q88h_trap_t;

#ifdef __cplusplus
extern "C" {
#endif

/* PC-88 は Z80 を2個持つ。メインCPU用・サブCPU用を別バッファで持つのは
 * q88h_trace.h と同じ理由（サブROMも再実装対象なので独立に観測したい）。 */
q88h_trap_t *retro_q88h_trap(void);
q88h_trap_t *retro_q88h_trap_sub(void);

/* 採取内容（イベント・ヒット数・stopped）を全消去する。map/mode は変えない。
 * 測定区間を切りたいときに呼ぶ。map/mode はフロントエンドが毎回明示的に
 * 設定し直すものなので、ここでは触らない。 */
void retro_q88h_trap_reset(void);

/* トラップ発火時のイベント記録。パッチ側の q88h_fetch / q88h_mem_read から呼ぶ。
 * exec_hits/data_hits の加算とイベントバッファへの追記をここに集約し、
 * パッチのコード自体は「どの値を渡すか」だけに専念できるようにする。
 * バッファが満杯なら n_dropped を増やすだけで上書きはしない。 */
void q88h_trap_record(q88h_trap_t *t, uint16_t addr, uint8_t kind,
                       uint16_t caller, uint16_t prev_fetch, uint16_t sp,
                       uint16_t af, uint16_t bc, uint16_t de, uint16_t hl);

#ifdef __cplusplus
}
#endif

#endif /* Q88H_TRAP_H_INCLUDED */

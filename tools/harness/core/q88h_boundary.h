/*
 * q88h_boundary.h — PC88Behavior 計測ハーネス / ROM 境界の横断記録
 *
 * ゴール B の需要測定（docs/notes/goal-b-policy-2026-10-24.md 第3節1〜3）の器具。
 * 「ROM 以外から ROM への制御の移動」を、番地と回数だけで記録する。
 * 対象は main CPU のみ（サブ CPU は範囲外）。
 *
 * 記録するのは次の3種だけ。
 *   a. 横断: 直前の命令が RAM 由来で、今の命令が ROM 由来になった瞬間の
 *      飛び先番地。番地ごとに回数、呼び出し型 / 飛び込み型の内訳、
 *      割り込み受理直後だった回数、RAM 側の期待した戻り番地へ戻ってきた回数。
 *   b. ROM のデータ読み: RAM 由来の命令が、ROM 由来の番地をデータとして
 *      読んだ番地。番地ごとの回数のみ。
 *   c. 共有 RAM 番地: RAM 由来の番地を「ROM 由来の命令が読んだ/書いた」
 *      「RAM 由来の命令が読んだ/書いた」を別々に数え、両方から触られた番地。
 *
 * **レジスタの値・メモリの値・ROM から読んだ値は記録しない**（方針ノート第4節）。
 * コアはスタック先頭の1語を「呼び出し型か」の判定に一瞬だけ使うが、判定が済めば
 * 捨てる。戻り番地の対応づけに使う期待戻り番地(rs[])は番地であって、
 * 出力には出さない。出力ファイルに値が出ないことは boundary_selftest.sh が
 * 目印の値の不在で検査する（故障注入で、値を出す壊れ版がその検査に落ちることも確認する）。
 *
 * 「どこ由来か」は番地の固定範囲ではなく、上流がバンク切替のたびに更新する
 * read_mem_* ポインタが指す配列で決める（pc88main.c の q88h_addr_class）。
 * 配列が main_rom / main_rom_n / main_rom_ext / jisho_rom なら ROM、
 * dummy_rom なら「未割り当て」、それ以外は RAM。
 *
 * 既定は off。off のときコアの挙動も既存の測定出力も変えない。
 *
 * シンボル名を retro_ で始めているのは q88h_trace.h と同じ理由
 * （上流の link.T が `global: retro_*; local: *;` でエクスポートを絞っている）。
 */
#ifndef Q88H_BOUNDARY_H_INCLUDED
#define Q88H_BOUNDARY_H_INCLUDED

#include <stdint.h>

#define Q88H_BOUNDARY_MAGIC   0x48423838u   /* "88BH" (LE) */
#define Q88H_BOUNDARY_VERSION 1u

/* 由来の分類 */
enum { Q88H_BND_RAM = 0, Q88H_BND_ROM = 1, Q88H_BND_NONE = 2 };

/* 故障注入（自己検査専用。frontend が Q88MEASURE_FAULT_BOUNDARY から設定する） */
enum {
    Q88H_BND_FAULT_NONE      = 0,
    Q88H_BND_FAULT_CLASS_RAM = 1,  /* 分類を常に RAM にする */
    Q88H_BND_FAULT_NO_RETURN = 2,  /* 戻りの対応づけを切る */
    Q88H_BND_FAULT_LEAK_REG  = 3   /* 最初の横断で HL を leak_value に控え、出力に混ぜさせる */
};

/* c の4つの別々のカウンタの添字 */
enum {
    Q88H_BND_ROM_READ = 0, Q88H_BND_ROM_WRITE = 1,
    Q88H_BND_RAM_READ = 2, Q88H_BND_RAM_WRITE = 3
};

/* 期待戻り番地スタックの深さ。溢れたら最古を捨てる（rs_dropped を数える） */
#define Q88H_BND_RS_DEPTH 32

typedef struct {
    uint16_t ret;        /* 期待した戻り番地（RAM 側） */
    uint16_t sp_after;   /* 横断直後の SP。戻ったときは sp_after+2 のはず */
    uint16_t target;     /* 横断先（ROM 側の番地） */
} q88h_bnd_rs_t;

typedef struct {
    uint32_t magic, version;

    uint8_t  enabled;    /* 既定 off */
    uint8_t  fault;      /* 故障注入の種別（Q88H_BND_FAULT_*） */
    uint8_t  pad0[2];

    /* ---- 追跡状態（命令単位） ---- */
    uint8_t  last_class;     /* 直前の命令（先頭 fetch）の由来 */
    uint8_t  cur_class;      /* 実行中の命令の由来（データアクセスの帰属先） */
    uint8_t  in_int;         /* 割り込み受理処理中（この間のアクセスは記録しない） */
    uint8_t  int_pending;    /* 割り込みを受理してから、まだ次の命令先頭 fetch が来ていない */
    uint16_t last_pc;        /* 直前の命令の先頭番地 */
    uint16_t last_sp;        /* 直前の命令の開始時の SP */
    uint16_t int_sp;         /* 割り込み受理直前の SP */
    uint16_t pad1;

    /* ---- a. 横断 ---- */
    uint32_t x_total[0x10000];  /* 飛び先ごとの横断回数 */
    uint32_t x_call[0x10000];   /* うち呼び出し型（SP が2減り、スタック先頭が直前の RAM 番地の近く） */
    uint32_t x_jump[0x10000];   /* うち飛び込み型（それ以外） */
    uint32_t x_int[0x10000];    /* うち割り込み受理直後（呼び出し型の一種として数える） */
    uint32_t x_ret[0x10000];    /* その呼び出しに対応して期待した戻り番地へ戻ってきた回数 */
    q88h_bnd_rs_t rs[Q88H_BND_RS_DEPTH];
    uint32_t rs_n, rs_dropped;

    /* ---- b. ROM のデータ読み ---- */
    uint32_t rom_read[0x10000];

    /* ---- c. 共有 RAM 番地 ---- */
    uint32_t shared[4][0x10000];

    /* ---- 命令先頭 fetch の由来別総数（走ったことの確認用） ---- */
    uint32_t n_instr[3];

    /* ---- 故障注入 LEAK_REG 専用。通常の走りでは常に 0 ---- */
    uint8_t  leak_valid;
    uint8_t  pad2;
    uint16_t leak_value;
} q88h_boundary_t;

#ifdef __cplusplus
extern "C" {
#endif

q88h_boundary_t *retro_q88h_boundary(void);

/* 採取内容を全消去する。enabled / fault は変えない（q88h_memlog と同じ理由） */
void retro_q88h_boundary_reset(void);
void retro_q88h_boundary_set_enabled(int enabled);
void retro_q88h_boundary_set_fault(int fault);

/* 以下はパッチ側（pc88main.c / z80.c）から呼ぶ。enabled の判定は呼び手の責任。 */

/* 故障注入 CLASS_RAM のとき分類を RAM に潰す。通常は素通し。 */
int  q88h_boundary_class_filter(const q88h_boundary_t *b, int cls);

/* 命令の先頭 fetch。sp = その時点の SP、top = スタック先頭の1語
 * （cls==ROM かつ直前が RAM のときだけ呼び手が読んで渡す。それ以外は 0）。
 * fault_reg は故障注入 LEAK_REG のためだけに渡すレジスタ値で、通常の走りでは
 * 参照しない（コアは fault 以外で読まない）。 */
void q88h_boundary_on_instr(q88h_boundary_t *b, uint16_t addr, int cls,
                            uint16_t sp, uint16_t top, uint16_t fault_reg);

/* 割り込み受理の前後（z80.c から）。受理処理中のスタック操作等は記録しない。 */
void q88h_boundary_int_begin(q88h_boundary_t *b, uint16_t sp);
void q88h_boundary_int_end(q88h_boundary_t *b);

/* データ読み / 書き。addr_cls は「その番地が今どこ由来か」
 * （書き込みは常に RAM へ落ちるので呼び手が RAM を渡す）。 */
void q88h_boundary_on_read(q88h_boundary_t *b, uint16_t addr, int addr_cls);
void q88h_boundary_on_write(q88h_boundary_t *b, uint16_t addr);

#ifdef __cplusplus
}
#endif

#endif /* Q88H_BOUNDARY_H_INCLUDED */

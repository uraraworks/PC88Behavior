/*
 * q88h_clock.h — PC88Behavior 計測ハーネス / 両CPU共通の単調増加クロック
 *
 * 経緯（M6c）: q88h_iolog / q88h_intlog は main/sub を別バッファに持ち、
 * イベントに付く時刻情報は frame 番号しか無かった。1フレームに数千件の
 * イベントが起きるため、frame だけでは main と sub の真の前後関係を
 * 復元できない。これが `docs/notes/m6-sub-proto.md` の対応付け精度が
 * 20% で頭打ちになった原因と診断した（対応付けアルゴリズムの改善では
 * 動かなかった数字が、観測系の分解能不足では説明がつく）。
 *
 * ここでは記録イベント1件ごとにインクリメントするグローバルな通し番号を
 * 1本だけ用意する。QUASI88 は main/sub の Z80 を時分割で（1回の
 * z80_exec 呼び出しで一方だけを連続実行してから切り替える形で）走らせる
 * ため、フックが実際に発火する順序＝真の実行順序そのものであり、
 * その発火順にただ番号を振るだけで、frame より遥かに細かい粒度で
 * main/sub 間の前後関係を復元できる（emu.c の z80_exec 呼び出し方が
 * その根拠——detail は `tools/patches/0010-shared-clock.patch` の
 * 説明、および本パッチが変更しない emu.c 自体を参照）。
 *
 * Z80 の実行サイクル数（T-state 累積）そのものを刻めればより物理的だが、
 * emu.c の main_state/sub_state はスケジューラ内部の按分値であり
 * CPU 側から見える値ではない。まずは「真の発生順」を保証する通し番号
 * (呼び出し順カウンタ) を導入し、サイクル数ベース化は次のスコープとする。
 *
 * この値も「実行の結果として外部から観測できるもの」の一種であり、
 * ROM のバイト列そのものではない（docs/PLAN.md 第5節）。
 *
 * シンボル名を retro_ で始めているのは他の q88h_*.h と同じ理由。
 * 上流の link.T が `global: retro_*; local: *;` でエクスポートを絞っているため。
 */
#ifndef Q88H_CLOCK_H_INCLUDED
#define Q88H_CLOCK_H_INCLUDED

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 次のクロック値を発行する。呼ぶたびに単調増加し、同じ値は二度と返らない。
 * q88h_iolog_record / q88h_intlog_record の内部から、main/sub・
 * io/int の区別なく呼ぶ。呼び出し順＝記録順＝実発生順（このファイル冒頭の
 * コメント参照）なので、返り値は両CPU・両ログ種別を横断して比較してよい。
 * 0 は「まだ一度も打刻していない」を表す番兵として予約し、実際の値は
 * 1 から始める（q88h_iolog / q88h_intlog の既存の seq と同じ流儀）。 */
uint32_t q88h_clock_tick(void);

/* 通し番号を 0 に戻す。enabled のようなフラグは持たないので on/off の
 * 概念は無い——q88h_iolog_reset / q88h_intlog_reset の両方から呼ばれる
 * 想定（どちらから先に呼ばれても、まだイベントが記録されていない
 * タイミングで呼ばれる限り安全）。 */
void retro_q88h_clock_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* Q88H_CLOCK_H_INCLUDED */

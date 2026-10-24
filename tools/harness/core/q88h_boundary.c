/*
 * q88h_boundary.c — PC88Behavior 計測ハーネス / ROM 境界の横断記録
 * 詳細は q88h_boundary.h を参照。
 */

#include <string.h>
#include "q88h_boundary.h"

static q88h_boundary_t g_boundary;

static q88h_boundary_t *ensure( q88h_boundary_t *b )
{
  if( b->magic != Q88H_BOUNDARY_MAGIC ){
    memset( b, 0, sizeof(*b) );
    b->magic      = Q88H_BOUNDARY_MAGIC;
    b->version    = Q88H_BOUNDARY_VERSION;
    b->last_class = Q88H_BND_NONE;   /* 起動直後は「どこ由来でもない」 */
    b->cur_class  = Q88H_BND_NONE;
  }
  return b;
}

q88h_boundary_t *retro_q88h_boundary( void ) { return ensure( &g_boundary ); }

void retro_q88h_boundary_reset( void )
{
  uint8_t enabled = g_boundary.magic == Q88H_BOUNDARY_MAGIC ? g_boundary.enabled : 0;
  uint8_t fault   = g_boundary.magic == Q88H_BOUNDARY_MAGIC ? g_boundary.fault   : 0;

  memset( &g_boundary, 0, sizeof(g_boundary) );
  ensure( &g_boundary );
  g_boundary.enabled = enabled;
  g_boundary.fault   = fault;
}

void retro_q88h_boundary_set_enabled( int enabled )
{
  ensure( &g_boundary )->enabled = enabled ? 1 : 0;
}

void retro_q88h_boundary_set_fault( int fault )
{
  ensure( &g_boundary )->fault = (uint8_t)fault;
}

int q88h_boundary_class_filter( const q88h_boundary_t *b, int cls )
{
  if( b->fault == Q88H_BND_FAULT_CLASS_RAM ) return Q88H_BND_RAM;
  return cls;
}

/* 期待戻り番地を積む。溢れたら最古を捨てて数える。 */
static void rs_push( q88h_boundary_t *b, uint16_t ret, uint16_t sp_after,
                     uint16_t target )
{
  if( b->rs_n >= Q88H_BND_RS_DEPTH ){
    memmove( &b->rs[0], &b->rs[1], sizeof(b->rs[0]) * (Q88H_BND_RS_DEPTH - 1) );
    b->rs_n = Q88H_BND_RS_DEPTH - 1;
    b->rs_dropped++;
  }
  b->rs[ b->rs_n ].ret      = ret;
  b->rs[ b->rs_n ].sp_after = sp_after;
  b->rs[ b->rs_n ].target   = target;
  b->rs_n++;
}

void q88h_boundary_on_instr( q88h_boundary_t *b, uint16_t addr, int cls,
                             uint16_t sp, uint16_t top, uint16_t fault_reg )
{
  int was_int = b->int_pending;

  b->n_instr[cls]++;
  b->int_pending = 0;

  if( cls == Q88H_BND_ROM && b->last_class == Q88H_BND_RAM ){
    /* RAM → ROM の横断。 */
    int is_call;

    b->x_total[addr]++;
    if( was_int ){
      /* 割り込み受理直後。受理は SP を2減らして戻り番地を積む（呼び出し型の一種）。
       * 戻り番地は積まれた語そのもの（割り込まれた命令の次の番地で、
       * 直前の RAM 命令の「近く」とは限らない）。 */
      is_call = ( sp == (uint16_t)(b->int_sp - 2) );
      if( is_call ) b->x_int[addr]++;
    }else{
      /* 呼び出し型: SP がちょうど2減り、スタック先頭が直前の命令の
       * 直後（CALL nn / RST の次の番地 = 先頭+1〜+4）を指す。 */
      is_call = ( sp == (uint16_t)(b->last_sp - 2)
                  && (uint16_t)(top - b->last_pc) >= 1
                  && (uint16_t)(top - b->last_pc) <= 4 );
    }
    if( is_call ){
      b->x_call[addr]++;
      rs_push( b, top, sp, addr );
    }else{
      b->x_jump[addr]++;
    }
    if( b->fault == Q88H_BND_FAULT_LEAK_REG && !b->leak_valid ){
      /* 故障注入: レジスタ値を1つ控え、出力に混ぜさせる（検出力の確認用） */
      b->leak_value = fault_reg;
      b->leak_valid = 1;
    }
  }else if( cls == Q88H_BND_RAM && b->last_class == Q88H_BND_ROM
            && b->fault != Q88H_BND_FAULT_NO_RETURN ){
    /* ROM → RAM。期待した戻り番地・SP へ戻ってきたか。
     * 上から探し、見つかった段より上（戻らなかった呼び出し）は捨てる。 */
    uint32_t i = b->rs_n;
    while( i > 0 ){
      i--;
      if( b->rs[i].ret == addr && (uint16_t)(b->rs[i].sp_after + 2) == sp ){
        b->x_ret[ b->rs[i].target ]++;
        b->rs_n = i;
        break;
      }
    }
  }

  b->cur_class  = (uint8_t)cls;
  b->last_class = (uint8_t)cls;
  b->last_pc    = addr;
  b->last_sp    = sp;
}

void q88h_boundary_int_begin( q88h_boundary_t *b, uint16_t sp )
{
  b->in_int      = 1;
  b->int_pending = 1;
  b->int_sp      = sp;
}

void q88h_boundary_int_end( q88h_boundary_t *b )
{
  b->in_int = 0;
}

void q88h_boundary_on_read( q88h_boundary_t *b, uint16_t addr, int addr_cls )
{
  if( b->in_int ) return;
  if( addr_cls == Q88H_BND_ROM ){
    /* b. RAM 由来の命令が ROM 由来の番地をデータとして読んだ */
    if( b->cur_class == Q88H_BND_RAM ) b->rom_read[addr]++;
  }else if( addr_cls == Q88H_BND_RAM ){
    /* 実行中の命令の先頭 +1〜+3 の読みは、命令のオペランド(即値・番地・変位)。
     * 命令長は接頭つきで最大4バイト(DD CB d op)で、先頭〜+0 は fetch が読むので
     * mem_read に来るのは +1〜+3 まで。データではないので c に数えない
     * (数えると ROM が写したコード領域全体が「共有」になる)。 */
    if( (uint16_t)(addr - b->last_pc) >= 1 && (uint16_t)(addr - b->last_pc) <= 3 ) return;
    /* c. RAM 番地の読み */
    if( b->cur_class == Q88H_BND_ROM )      b->shared[Q88H_BND_ROM_READ][addr]++;
    else if( b->cur_class == Q88H_BND_RAM ) b->shared[Q88H_BND_RAM_READ][addr]++;
  }
}

void q88h_boundary_on_write( q88h_boundary_t *b, uint16_t addr )
{
  if( b->in_int ) return;
  if( b->cur_class == Q88H_BND_ROM )      b->shared[Q88H_BND_ROM_WRITE][addr]++;
  else if( b->cur_class == Q88H_BND_RAM ) b->shared[Q88H_BND_RAM_WRITE][addr]++;
}

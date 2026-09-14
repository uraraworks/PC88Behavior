/*
 * q88h_memlog.c — PC88Behavior 計測ハーネス / 範囲指定メモリ書き込み記録
 * 詳細は q88h_memlog.h を参照。q88h_iolog.c と同じ形。
 */

#include <string.h>
#include "q88h_memlog.h"

static q88h_memlog_t g_memlog;

static q88h_memlog_t *ensure( q88h_memlog_t *l )
{
  if( l->magic != Q88H_MEMLOG_MAGIC ){
    memset( l, 0, sizeof(*l) );
    l->magic     = Q88H_MEMLOG_MAGIC;
    l->version   = Q88H_MEMLOG_VERSION;
    l->range_lo  = 1;   /* range_lo > range_hi = 未設定（何も記録しない） */
    l->range_hi  = 0;
  }
  return l;
}

q88h_memlog_t *retro_q88h_memlog( void ) { return ensure( &g_memlog ); }

void retro_q88h_memlog_reset( void )
{
  uint8_t  enabled  = g_memlog.magic == Q88H_MEMLOG_MAGIC ? g_memlog.enabled   : 0;
  uint32_t range_lo = g_memlog.magic == Q88H_MEMLOG_MAGIC ? g_memlog.range_lo  : 1;
  uint32_t range_hi = g_memlog.magic == Q88H_MEMLOG_MAGIC ? g_memlog.range_hi  : 0;

  memset( &g_memlog, 0, sizeof(g_memlog) );
  ensure( &g_memlog );
  g_memlog.enabled  = enabled;
  g_memlog.range_lo = range_lo;
  g_memlog.range_hi = range_hi;
}

void retro_q88h_memlog_set_enabled( int enabled )
{
  ensure( &g_memlog )->enabled = enabled ? 1 : 0;
}

void retro_q88h_memlog_set_frame( uint32_t frame )
{
  ensure( &g_memlog )->frame = frame;
}

void retro_q88h_memlog_set_range( uint32_t lo, uint32_t hi )
{
  q88h_memlog_t *l = ensure( &g_memlog );
  l->range_lo = lo;
  l->range_hi = hi;
}

void q88h_memlog_record( q88h_memlog_t *l, uint16_t addr, uint8_t value, uint16_t pc )
{
  if( l->n_events >= Q88H_MEMLOG_MAX_EVENTS ){
    l->n_dropped++;
    return;
  }
  {
    q88h_memlog_ev_t *e = &l->ev[ l->n_events ];
    e->seq   = l->n_events + 1;
    e->frame = l->frame;
    e->pc    = pc;
    e->addr  = addr;
    e->value = value;
    e->pad[0] = e->pad[1] = e->pad[2] = 0;
    l->n_events++;
  }
}

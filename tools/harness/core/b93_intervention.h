/* B93: 値を受け取らない見出し記録と、帰還直後の一回限りの R 介入。 */
#ifndef B93_INTERVENTION_H
#define B93_INTERVENTION_H
#include "q88h_boundary.h"
int retro_q88h_b93_version(void);
int retro_q88h_b93_open(const char *, unsigned, int, unsigned);
void retro_q88h_b93_frame(uint32_t);
int retro_q88h_b93_close(void);
int q88h_b93_instr(const q88h_boundary_t *, unsigned, int, int, unsigned, unsigned);
unsigned q88h_b93_value(void);
void q88h_b93_fetch(unsigned cpu, unsigned pc, int cls);
void q88h_b93_boundary(void);
void q88h_b93_io(unsigned cpu, unsigned kind, unsigned port, unsigned pc);
#endif

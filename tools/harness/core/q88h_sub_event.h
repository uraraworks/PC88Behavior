#ifndef Q88H_SUB_EVENT_H
#define Q88H_SUB_EVENT_H
#include <stdint.h>
int retro_q88h_sub_event_open(const char *path);
int retro_q88h_sub_event_close(void);
int q88h_sub_event_enabled(void);
void q88h_sub_event_instr(uint16_t pc);
void q88h_sub_event_suppress(int on);
void q88h_sub_event_fc(void);
void q88h_sub_event_record(char kind, uint16_t addr, uint8_t value);
#endif

#ifndef Q88H_MAIN_EVENT_H
#define Q88H_MAIN_EVENT_H
#include <stdint.h>
int retro_q88h_main_event_open(const char *path);
int retro_q88h_main_event_close(void);
void retro_q88h_main_event_set_frame(uint32_t frame);
int q88h_main_event_enabled(void);
void q88h_main_event_instr(uint16_t pc, int ram);
void q88h_main_event_suppress(int on);
void q88h_main_event_record(char kind, uint16_t addr, uint8_t value);
#endif

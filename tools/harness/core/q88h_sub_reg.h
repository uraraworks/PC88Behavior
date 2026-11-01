#ifndef Q88H_SUB_REG_H
#define Q88H_SUB_REG_H
#include <stdint.h>
#include <stdio.h>
int retro_q88h_sub_reg_open(const char *path);
int retro_q88h_sub_reg_close(void);
int q88h_sub_reg_enabled(void);
void q88h_sub_reg_instr(uint16_t pc);
void q88h_sub_reg_fc(void);
void q88h_sub_reg_opcode(int opcode);
void q88h_sub_reg_capture(char kind, uint16_t pc);
#endif

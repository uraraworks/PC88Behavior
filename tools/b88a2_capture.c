/* B88追補2。ROM命令・内部PCを読出し／保存せず、境界とI/Oだけを縮約する。 */
#include "drive.h"
#define retro_b88_instr b88_base_instr
#define retro_b88_finish b88_base_finish
#define b88_port b88_base_port
#define b88_write b88_base_write
#include "b88_capture.c"
#undef retro_b88_instr
#undef retro_b88_finish
#undef b88_port
#undef b88_write

#define A2_MAX 280
#define A2_CAND 16
typedef struct { unsigned value, kind, index, n, overflow, addr[A2_CAND], valid[A2_CAND]; } a2_event;
static a2_event a2_events[A2_MAX];
static unsigned a2_n, a2_overflow, a2_current, a2_have_current;
static unsigned a2_configured, a2_media, a2_media_ok, a2_prepare, a2_prepared;
static unsigned a2_entered, a2_pending, a2_read, a2_msr, a2_window;
static unsigned a2_target, a2_prepare_pc, a2_prepared_pc, a2_start_pc, a2_return_pc, a2_sent_pc;
static unsigned a2_step_pc[11], a2_done_pc[11], a2_steps[11], a2_done[11];
static unsigned a2_sent, a2_recv, a2_data, a2_result, a2_command, a2_command_match=1;
static unsigned a2_ei_delay;
static unsigned a2_irq_before, a2_irq_inside, a2_irq_prepare;
static unsigned a2_states[3][3], a2_seen[3], a2_sent_values[2], a2_sent_n;
static unsigned a2_recv_match[2], a2_data_match=1;
static const unsigned a2_command_values[9] = {6,0,0,0,4,1,4,27,255};
static unsigned a2_env(const char *name) {
    const char *s=getenv(name); return s ? strtoul(s,NULL,16) : 0;
}
static unsigned a2_pattern(unsigned i) {
    if (i < 4) { static const unsigned p[4]={0x42,0,0,4}; return p[i]; }
    return (0x42*131 + 4*57 + i*7 + 13) & 255;
}
static void a2_state(unsigned which) {
    a2_seen[which]=1;
    a2_states[which][0]=z80sub_cpu.IFF;
    a2_states[which][1]=z80sub_cpu.IFF2;
    a2_states[which][2]=z80sub_cpu.IM;
}
void retro_b88a2_ei_delay(unsigned pc) {
    if (a2_configured && pc==a2_start_pc && !b88_starts) ++a2_ei_delay;
}
void retro_b88a2_interrupt(void) {
    if (!a2_window) return;
    if(getenv("B88A2_TEST_IRQ")) FDC_flag=FALSE;
    if (!b88_starts) ++a2_irq_prepare;
    else if (!a2_entered) ++a2_irq_before;
    else if (b88_active) ++a2_irq_inside;
}
static void a2_configure(void) {
    unsigned i; const char *s; char *end;
    a2_configured=1;
    a2_prepare_pc=a2_env("B88A2_PREPARE"); a2_prepared_pc=a2_env("B88A2_PREPARED");
    a2_start_pc=a2_env("B88_START"); a2_return_pc=a2_env("B88_RETURN");
    a2_target=a2_env("B88A2_TARGET"); a2_sent_pc=a2_env("B88A2_COOP_SENT");
    a2_read=a2_env("B88A2_READ");
    s=getenv("B88A2_STEPS");
    for (i=0; s && *s && i<11; ++i) {
        a2_step_pc[i]=strtoul(s,&end,16); s=end+1;
        a2_done_pc[i]=strtoul(s,&end,16); s=(*end ? end+1 : end);
    }
    s=getenv("B88A2_SENT");
    while(s && *s && a2_sent_n<2) {
        a2_sent_values[a2_sent_n++]=strtoul(s,&end,10); s=(*end ? end+1 : end);
    }
}
void retro_b88_instr(int main_cpu, unsigned pc) {
    unsigned i;
    if (!a2_configured) a2_configure();
    if (main_cpu) {
        if (pc==a2_sent_pc && a2_entered && !b88_restarts) ++a2_sent;
    } else {
        if (pc==0x7800 && !a2_media) {
            const char *fixture=getenv("B88A2_FIXTURE");
            if(fixture) {
                unsigned char h[4], code[0x2000]; unsigned address,n; FILE *patch;
                if(getenv("PC88_REF_ROM_DIR")) abort();
                patch=fopen(fixture,"rb"); if(!patch) abort();
                while(fread(h,1,4,patch)==4) {
                    address=h[0]+256*h[1]; n=h[2]+256*h[3];
                    if(!n || address+n>0x2000 || fread(code,1,n,patch)!=n) abort();
                    memcpy(sub_romram+address,code,n);
                }
                fclose(patch);
            }
            if(getenv("B88A2_TEST_IFF2")) {
                if(getenv("PC88_REF_ROM_DIR")) abort();
                z80sub_cpu.IFF2=a2_env("B88A2_TEST_IFF2");
            }
            a2_media=1;
            disk_eject(0);
            disk_insert(0,getenv("B88A2_MEDIA"),0,1);
            disk_eject(1);
            a2_media_ok=!!disk_image_exist(0) && !disk_image_exist(1);
        }
        if (pc==a2_start_pc-1 && getenv("B88A2_TEST_IRQ") && !b88_starts) {
            if(getenv("PC88_REF_ROM_DIR")) abort();
            FDC_flag=TRUE; z80sub_cpu.INT_active=TRUE;
        }
        if (pc==a2_prepare_pc && !a2_prepare) { ++a2_prepare; a2_window=1; }
        if (pc==a2_prepared_pc && !a2_prepared) ++a2_prepared;
        if (a2_read && a2_window && !b88_starts) {
            for (i=0;i<11;++i) {
                if(pc==a2_step_pc[i] && !a2_steps[i]) ++a2_steps[i];
                if(pc==a2_done_pc[i] && !a2_done[i]) ++a2_done[i];
            }
        }
        if (a2_pending && pc==a2_target && b88_active && !a2_entered) {
            ++a2_entered; a2_pending=0; a2_state(1); main_ram[0xcffe]=1;
        }
        if (pc==a2_start_pc && !b88_starts) { a2_state(0); a2_pending=1; }
        if (pc==a2_return_pc && b88_active) {
            a2_state(2); a2_window=0; a2_have_current=0; main_ram[0xcfff]=1;
        }
    }
    b88_base_instr(main_cpu,pc);
    if (b88_restarts) { a2_window=0; a2_have_current=0; }
}
static void b88a2_before_in(unsigned port) {
    if ((port&255)==0xfb) a2_msr=fdc_status();
}
static void a2_event_add(unsigned kind, unsigned index, unsigned data) {
    if (a2_n>=A2_MAX) { a2_overflow=1; a2_have_current=0; return; }
    a2_current=a2_n++; a2_have_current=1;
    a2_events[a2_current].kind=kind;
    a2_events[a2_current].index=index;
    a2_events[a2_current].value=data;
}
static void b88_port(int output, unsigned port, unsigned data) {
    unsigned i; port &= 255;
    if (a2_window) {
        if (a2_read && output && port==0xfb && (fdc_status()&0xc0)==0x80) {
            if (a2_command>=9 || data!=a2_command_values[a2_command]) a2_command_match=0;
            ++a2_command;
        }
        if (a2_read && !output && port==0xfb && (a2_msr&0xc0)==0xc0) {
            if (a2_msr&0x20) {
                if(a2_data>=256 || data!=a2_pattern(a2_data)) a2_data_match=0;
                a2_event_add(0,a2_data++,data);
            } else a2_event_add(1,a2_result++,data);
        }
        if (!output && port==0xfc && a2_entered && b88_active) {
            for(i=0;i<a2_sent_n;++i) a2_recv_match[i]+=(data==a2_sent_values[i]);
            a2_event_add(2,a2_recv++,data);
        }
    }
    b88_base_port(output,port,data);
}
static void b88_write(unsigned addr, unsigned data) {
    unsigned i,j; a2_event *e;
    if (a2_window && (addr&0x4000)) {
        addr &= 0x7fff;
        /* 途中の上書きを検出。読出しごとの区間に複数候補があれば未確定。 */
        for(i=0;i<a2_n;++i) for(j=0;j<a2_events[i].n;++j)
            if(a2_events[i].addr[j]==addr) a2_events[i].valid[j]=0;
        if(a2_have_current) {
            e=&a2_events[a2_current];
            if(data==e->value) {
                if(e->n==A2_CAND) e->overflow=1;
                else { e->addr[e->n]=addr; e->valid[e->n++]=1; }
            }
        }
    }
    b88_base_write(addr,data);
}
static void a2_print_state(FILE *f,unsigned n) {
    if(!a2_seen[n]) fprintf(f,"null");
    else fprintf(f,"[%u,%u,%u]",a2_states[n][0],a2_states[n][1],a2_states[n][2]);
}
int retro_b88_finish(void) {
    unsigned i,j,ok; FILE *f;
    if(!b88_base_finish()) return 0;
    f=fopen(getenv("B88A2_CAPTURE"),"w"); if(!f) return 0;
    fprintf(f,"{\"media\":%u,\"media_ok\":%u,\"prepare\":%u,\"prepared\":%u,\"entered\":%u,",
            a2_media,a2_media_ok,a2_prepare,a2_prepared,a2_entered);
    fprintf(f,"\"ei_delay\":%u,",a2_ei_delay);
    fprintf(f,"\"states\":["); for(i=0;i<3;++i) {if(i)fprintf(f,",");a2_print_state(f,i);} fprintf(f,"],");
    fprintf(f,"\"irq\":[%u,%u,%u],\"steps\":[",a2_irq_prepare,a2_irq_before,a2_irq_inside);
    for(i=0;i<11;++i) fprintf(f,"%s[%u,%u]",i?",":"",a2_steps[i],a2_done[i]);
    fprintf(f,"],\"sent\":%u,\"recv\":%u,\"recv_match\":[%u,%u],",a2_sent,a2_recv,a2_recv_match[0],a2_recv_match[1]);
    fprintf(f,"\"command\":%u,\"command_match\":%u,\"data\":%u,\"data_match\":%u,\"result\":%u,\"overflow\":%u,\"events\":[",
            a2_command,a2_command_match,a2_data,a2_data_match,a2_result,a2_overflow);
    for(i=0;i<a2_n;++i) {
        a2_event *e=&a2_events[i];
        fprintf(f,"%s{\"kind\":%u,\"index\":%u,\"overflow\":%u,\"candidates\":[",i?",":"",e->kind,e->index,e->overflow);
        for(j=0;j<e->n;++j) fprintf(f,"%s[%u,%u]",j?",":"",e->addr[j],e->valid[j] && sub_romram[e->addr[j]]==e->value);
        fprintf(f,"]");
        if(e->kind==2) fprintf(f,",\"sent_match\":[%u,%u]",
            a2_sent_n>0 && e->value==a2_sent_values[0], a2_sent_n>1 && e->value==a2_sent_values[1]);
        /* 唯一の値列の例外: 自作媒体に対するエミュレータFDCの結果フェーズ。 */
        if(e->kind==1 && a2_command==9 && a2_command_match && a2_result==7 && a2_media_ok)
            fprintf(f,",\"fdc_result\":%u",e->value);
        fprintf(f,"}");
    }
    fprintf(f,"]}\n"); ok=!ferror(f); if(fclose(f))ok=0; return ok;
}

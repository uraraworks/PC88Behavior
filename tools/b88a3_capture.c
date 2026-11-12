/* 追補3。入口・帰還・自作ラベル以外のPCとROM命令は記録しない。 */
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

#define A3_MAX 128
static unsigned configured, media, media_ok, prepare, prepared, entered, landing, pre_read;
static unsigned target, prepare_pc, prepared_pc, media_pc, landing_pc, preread_pc;
static unsigned start_pc, return_pc, sent_pc, pair_pc, byte_pc, byte2_pc, reply_pc;
static unsigned step_pc[9], done_pc[9], steps[9], dones[9];
static unsigned states[3][3], seen[3], irq[3], ei_delay, window, pending;
static unsigned sent, received, replies, reply_done, stream[300], stream_n, stream_ok=1;
static unsigned msr, entry_msr, ready_msr, data_count, overflow, result_kind;
static unsigned result_match[7], result_seen;
static unsigned motors[A3_MAX], motor_n;
typedef struct { unsigned scope, n, bytes[9], nr, result[7], data_in, data_out; } transaction;
static transaction commands[A3_MAX];
static unsigned command_n;
static unsigned envhex(const char *name) {
    const char *s=getenv(name); return s ? strtoul(s,NULL,16) : 0;
}
static void state(unsigned n) {
    seen[n]=1; states[n][0]=z80sub_cpu.IFF; states[n][1]=z80sub_cpu.IFF2; states[n][2]=z80sub_cpu.IM;
}
static void configure(void) {
    unsigned i; const char *s; char *end;
    configured=1;
    target=envhex("B88A3_TARGET"); prepare_pc=envhex("B88A3_PREPARE"); prepared_pc=envhex("B88A3_PREPARED");
    start_pc=envhex("B88_START"); return_pc=envhex("B88_RETURN");
    media_pc=envhex("B88A3_MEDIA_PC"); landing_pc=envhex("B88A3_LANDING"); preread_pc=envhex("B88A3_PREREAD");
    sent_pc=envhex("B88A3_COOP_SENT"); pair_pc=envhex("B88A3_COOP_PAIR");
    byte_pc=envhex("B88A3_COOP_BYTE"); byte2_pc=envhex("B88A3_COOP_BYTE2"); reply_pc=envhex("B88A3_REPLY_DONE");
    result_kind=envhex("B88A3_READ");
    s=getenv("B88A3_STEPS");
    for(i=0;s && *s && i<9;++i) {
        step_pc[i]=strtoul(s,&end,16); s=end+1;
        done_pc[i]=strtoul(s,&end,16); s=*end?end+1:end;
    }
    s=getenv("B88A3_SENT");
    while(s && *s && stream_n<300) { stream[stream_n++]=strtoul(s,&end,10); s=*end?end+1:end; }
}
void retro_b88a3_ei_delay(unsigned pc) {
    if(configured && pc==start_pc && !b88_starts) ++ei_delay;
}
void retro_b88a3_interrupt(void) {
    if(window) ++irq[!b88_starts ? 0 : !entered ? 1 : 2];
}
static void exchange_media(void) {
    unsigned i; const char *paths[2]={getenv("B88A3_MEDIA"),getenv("B88A3_MEDIA2")};
    unsigned wanted[2]={envhex("B88A3_DISK1"),envhex("B88A3_DISK2")};
    media=1; media_ok=1;
    for(i=0;i<2;++i) {
        disk_eject(i);
        if(wanted[i]) disk_insert(i,paths[i],0,0);
        if(!!disk_image_exist(i)!=!!wanted[i]) media_ok=0;
    }
}
void retro_b88_instr(int main_cpu, unsigned pc) {
    unsigned i;
    if(!configured) configure();
    if(main_cpu) {
        if(pc==media_pc && !media) {
            exchange_media();
            if(preread_pc!=0xffff) window=1;
        }
        if(pc==preread_pc && media && command_n && !overflow) {
            transaction *t=&commands[command_n-1];
            pre_read=(data_count==256 && (t->bytes[0]&31)==6 && t->nr==7 && !(t->result[0]&0xc0));
        }
        if(entered && !b88_restarts) {
            if(pc==sent_pc) ++sent;
            if(pc==pair_pc) sent+=2;
            if(pc==byte_pc || pc==byte2_pc) ++replies;
            if(pc==reply_pc) ++reply_done;
        }
    } else {
        if(pc==0x7800 && !prepare) {
            const char *name=getenv("B88A3_FIXTURE");
            if(name) {
                FILE *f; unsigned char h[4], code[0x2000]; unsigned a,n;
                if(getenv("PC88_REF_ROM_DIR")) abort();
                f=fopen(name,"rb"); if(!f) abort();
                while(fread(h,1,4,f)==4) {
                    a=h[0]+256*h[1]; n=h[2]+256*h[3];
                    if(!n || a+n>0x2000 || fread(code,1,n,f)!=n) abort();
                    memcpy(sub_romram+a,code,n);
                }
                fclose(f);
            }
            if(getenv("B88A3_TEST_IFF2")) {
                if(getenv("PC88_REF_ROM_DIR")) abort();
                z80sub_cpu.IFF2=envhex("B88A3_TEST_IFF2");
            }
        }
        if(pc==prepare_pc && !prepare) { prepare=1; window=1; }
        if(pc==prepared_pc && !prepared) { prepared=1; ready_msr=fdc_status(); }
        if(result_kind && window && !b88_starts) for(i=0;i<9;++i) {
            if(pc==step_pc[i] && !steps[i]) ++steps[i];
            if(pc==done_pc[i] && !dones[i]) ++dones[i];
        }
        if(pc==start_pc && !b88_starts) { state(0); pending=1; }
        if(pending && pc==target && b88_active && !entered) {
            entered=1; pending=0; state(1); entry_msr=fdc_status(); main_ram[0xcffe]=1;
        }
        if(pc==landing_pc && entered && b88_active) ++landing;
        if(pc==return_pc && b88_active) {
            state(2); window=0; main_ram[0xcfff]=1;
            if(result_kind && command_n) {
                transaction *t=&commands[command_n-1];
                if(t->nr==7 && (t->bytes[0]&31)==6) {
                    result_seen=1;
                    for(i=0;i<7;++i) result_match[i]=(sub_romram[0x7f0d+i]==t->result[i]);
                }
            }
        }
    }
    b88_base_instr(main_cpu,pc);
    if(b88_restarts) window=0;
}
static void b88a3_before_in(unsigned port) {
    if((port&255)==0xfb) msr=fdc_status();
}
static void b88_port(int output, unsigned port, unsigned data) {
    transaction *t; unsigned status;
    port &=255;
    if(window) {
        if(output && port==0xf8 && entered) {
            if(motor_n==A3_MAX) overflow=1; else motors[motor_n++]=data;
        }
        if(!output && port==0xfc && entered) {
            if(received>=stream_n || data!=stream[received]) stream_ok=0;
            ++received;
        }
        if(port==0xfb) {
            status=output ? fdc_status() : msr;
            if(output && (status&0xd0)==0x80) {
                if(command_n==A3_MAX) overflow=1;
                else { t=&commands[command_n++]; t->scope=entered; t->bytes[t->n++]=data; }
            } else if(command_n && !overflow) {
                t=&commands[command_n-1];
                if(status&0x20) {
                    if(output) ++t->data_out;
                    else { ++t->data_in; ++data_count; }
                } else if(output && (status&0xc0)==0x80) {
                    if(t->n==9) overflow=1; else t->bytes[t->n++]=data;
                } else if(!output && (status&0xc0)==0xc0) {
                    if(t->nr==7) overflow=1; else t->result[t->nr++]=data;
                }
            }
        }
    }
    b88_base_port(output,port,data);
}
static void b88_write(unsigned addr, unsigned data) { b88_base_write(addr,data); }
int retro_b88_finish(void) {
    unsigned i,j,ok; FILE *f;
    if(!b88_base_finish()) return 0;
    f=fopen(getenv("B88A3_CAPTURE"),"w"); if(!f) return 0;
    fprintf(f,"{\"media\":%u,\"media_ok\":%u,\"prepare\":%u,\"prepared\":%u,\"entered\":%u,\"landing\":%u,\"pre_read\":%u,",
        media,media_ok,prepare,prepared,entered,landing,pre_read);
    fprintf(f,"\"sent\":%u,\"received\":%u,\"replies\":%u,\"reply_done\":%u,\"stream_ok\":%u,\"data_count\":%u,\"overflow\":%u,\"ei_delay\":%u,",
        sent,received,replies,reply_done,stream_ok,data_count,overflow,ei_delay);
    fprintf(f,"\"ready_msr\":%u,\"entry_msr\":%u,\"states\":[",ready_msr,entry_msr);
    for(i=0;i<3;++i) {
        if(i) fprintf(f,",");
        if(seen[i]) fprintf(f,"[%u,%u,%u]",states[i][0],states[i][1],states[i][2]); else fprintf(f,"null");
    }
    fprintf(f,"],\"irq\":[%u,%u,%u],\"steps\":[",irq[0],irq[1],irq[2]);
    for(i=0;i<9;++i) fprintf(f,"%s[%u,%u]",i?",":"",steps[i],dones[i]);
    fprintf(f,"],\"result_match\":[");
    if(result_seen) for(i=0;i<7;++i) fprintf(f,"%s%u",i?",":"",result_match[i]);
    fprintf(f,"],\"motors\":[");
    if(media_ok) for(i=0;i<motor_n;++i) fprintf(f,"%s%u",i?",":"",motors[i]);
    fprintf(f,"],\"commands\":[");
    /* この記録はリポジトリ外の生データ。コマンドと引数は公開集計で関係へ縮約する。 */
    if(media_ok) for(i=0;i<command_n;++i) {
        transaction *t=&commands[i];
        fprintf(f,"%s{\"scope\":%u,\"bytes\":[",i?",":"",t->scope);
        for(j=0;j<t->n;++j) fprintf(f,"%s%u",j?",":"",t->bytes[j]);
        fprintf(f,"],\"result\":[");
        for(j=0;j<t->nr;++j) fprintf(f,"%s%u",j?",":"",t->result[j]);
        fprintf(f,"],\"data_in\":%u,\"data_out\":%u}",t->data_in,t->data_out);
    }
    fprintf(f,"]}\n"); ok=!ferror(f); if(fclose(f))ok=0; return ok;
}

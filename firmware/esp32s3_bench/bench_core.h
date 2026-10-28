#ifndef SABZ_BENCH_CORE_H
#define SABZ_BENCH_CORE_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

namespace sabz {
enum Stage { ALL_RED=0, GREEN=1, YELLOW=2 };
enum Fault { OK=0, BAD_FRAME=1, BAD_SESSION=2, REPLAY=3, LEASE_LOST=4, ILLEGAL_CHANGE=5, MANUAL_STOP=6, OUTPUT_MISMATCH=7 };
struct Timings { uint32_t minimum,maximum,yellow,clearance; };
inline uint32_t crc32(const char* data,size_t size) {
    uint32_t crc=0xffffffffu;
    for(size_t i=0;i<size;++i){crc^=(uint8_t)data[i];for(int b=0;b<8;++b)crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));}
    return ~crc;
}
inline bool digits(const char* s,uint32_t &out) {
    if(!s || !*s)return false;
    uint64_t value=0;
    for(;*s;++s){if(*s<'0'||*s>'9')return false;value=value*10+(*s-'0');if(value>0xffffffffull)return false;}
    out=(uint32_t)value;return true;
}
inline bool hex(const char* s,size_t count,uint64_t &out) {
    if(strlen(s)!=count)return false;
    out=0;
    for(size_t i=0;i<count;++i){char c=s[i];uint8_t d;if(c>='0'&&c<='9')d=c-'0';else if(c>='a'&&c<='f')d=c-'a'+10;else return false;out=(out<<4)|d;}
    return true;
}
// No dynamic allocation or arbitrary per-lamp commands. Bench through phases only.
class Controller {
public:
    Timings timing; uint64_t boot; uint32_t entered,lastCommand,sequence,lease;
    Stage stage;uint8_t phase;Fault fault;bool hasCommand,clear;
    Controller(uint64_t session,uint32_t now,Timings t={8000,60000,3000,2000}):timing(t),boot(session),entered(now),lastCommand(now),sequence(0),lease(0),stage(ALL_RED),phase(0),fault(OK),hasCommand(false),clear(false){}
    void trip(Fault reason,uint32_t now){if(fault==OK)fault=reason;if(stage==GREEN){stage=YELLOW;entered=now;}}
    void advance(uint32_t now,bool conflictClear,bool stopHealthy){
        clear=conflictClear;
        if(!stopHealthy)trip(MANUAL_STOP,now);
        if(hasCommand && (uint32_t)(now-lastCommand)>=lease)trip(LEASE_LOST,now);
        if(stage==GREEN && (uint32_t)(now-entered)>=timing.maximum){stage=YELLOW;entered=now;}
        else if(stage==YELLOW && (uint32_t)(now-entered)>=timing.yellow){stage=ALL_RED;entered=now;phase^=1;}
    }
    uint8_t outputs()const {
        // bit order: NS red/amber/green, EW red/amber/green.
        if(stage==ALL_RED)return 1u|8u;
        return phase==0 ? (uint8_t)((stage==GREEN?4u:2u)|8u) : (uint8_t)(1u|(stage==GREEN?32u:16u));
    }
    bool receive(const char* frame,uint32_t now){
        size_t n=strlen(frame);if(n<11||n>126){trip(BAD_FRAME,now);return false;}
        const char* star=strchr(frame,'*');uint64_t sum;
        if(!star||!hex(star+1,8,sum)||crc32(frame,(size_t)(star-frame))!=(uint32_t)sum){trip(BAD_FRAME,now);return false;}
        char payload[128];size_t length=(size_t)(star-frame);memcpy(payload,frame,length);payload[length]=0;
        char* fields[8];size_t count=0;char* cursor=payload;
        fields[count++]=cursor;
        for(;*cursor;++cursor)if(*cursor==','){*cursor=0;if(count>=8){trip(BAD_FRAME,now);return false;}fields[count++]=cursor+1;}
        uint64_t session;
        if(count<2||!hex(fields[1],16,session)){trip(BAD_FRAME,now);return false;}
        if(session!=boot){trip(BAD_SESSION,now);return false;}
        if(count==2 && strcmp(fields[0],"Q")==0)return true; // Query never renews lease.
        uint32_t seq,requested,p,f,ms;
        if(count!=7||strcmp(fields[0],"C")||!digits(fields[2],seq)||!digits(fields[3],requested)||!digits(fields[4],p)||!digits(fields[5],f)||!digits(fields[6],ms)||requested>2||p>1||f>1||ms<100||ms>500){trip(BAD_FRAME,now);return false;}
        if(seq==0 || (hasCommand && seq<=sequence)){trip(REPLAY,now);return false;}
        sequence=seq;lastCommand=now;lease=ms;hasCommand=true;
        if(fault!=OK)return false;
        uint32_t elapsed=now-entered;
        if(stage==GREEN){
            if(requested==GREEN && p!=phase){trip(ILLEGAL_CHANGE,now);return false;}
            if(requested!=GREEN && (elapsed>=timing.minimum||f)){stage=YELLOW;entered=now;}
        }else if(stage==ALL_RED && requested==GREEN && clear && elapsed>=timing.clearance){stage=GREEN;phase=(uint8_t)p;entered=now;}
        return true;
    }
    void reply(char* out,size_t capacity,uint32_t now,uint8_t observed=255)const {
        char body[112];snprintf(body,sizeof(body),"R,%08lx%08lx,%lu,%u,%u,%u,%u,%lu",(unsigned long)(boot>>32),(unsigned long)(uint32_t)boot,(unsigned long)sequence,(unsigned)stage,(unsigned)phase,(unsigned)fault,(unsigned)(observed==255?outputs():observed),(unsigned long)now);
        snprintf(out,capacity,"%s*%08lx\n",body,(unsigned long)crc32(body,strlen(body)));
    }
};
}
#endif

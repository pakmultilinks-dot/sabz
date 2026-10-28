// Native executable runs exactly the same parser and state machine as the board.
#include "../esp32s3_bench/bench_core.h"
#include <iostream>
#include <string>
#include <sstream>
int main(){
    sabz::Controller board(0x0123456789abcdefull,0);
    std::string line;
    // Harness envelope: monotonic millis, clear(0/1), healthy stop loop(0/1), frame.
    while(std::getline(std::cin,line)){
        std::istringstream input(line);uint32_t now;int clear,stop;std::string frame;
        if(!(input>>now>>clear>>stop>>frame))return 2;
        board.advance(now,clear!=0,stop!=0);
        if(frame!="-")board.receive(frame.c_str(),now);
        char reply[128];board.reply(reply,sizeof(reply),now);std::cout<<reply<<std::flush;
    }
}

// ESP32-S3-DevKitC-1 LOW-VOLTAGE BENCH ONLY. No road relays or mains heads.
#include <Arduino.h>
#include <esp_system.h>
#include <esp_task_wdt.h>
#include <esp_idf_version.h>
#include <driver/gpio.h>
#include "bench_core.h"

static const gpio_num_t OUTPUTS[6]={GPIO_NUM_4,GPIO_NUM_5,GPIO_NUM_6,GPIO_NUM_7,GPIO_NUM_8,GPIO_NUM_9};
static const uint8_t CLEAR_PIN=10, STOP_LOOP_PIN=11;
static sabz::Controller* board=nullptr;
static char buffer[128];static size_t used=0;static bool discard=false;
static uint32_t partialAt=0,lastReport=0;static uint8_t written=255;
static void applyOutputs(){
    uint8_t desired=board->outputs();
    if(desired==written)return;
    // Deassert before asserting. Brief dark interval, never opposite greens.
    for(unsigned i=0;i<6;++i)gpio_set_level(OUTPUTS[i],0);
    for(unsigned i=0;i<6;++i)if(desired&(1u<<i))gpio_set_level(OUTPUTS[i],1);
    written=desired;
}
static uint8_t readOutputs(){uint8_t bits=0;for(unsigned i=0;i<6;++i)if(gpio_get_level(OUTPUTS[i]))bits|=(1u<<i);return bits;}
static void report(){char reply[128];board->reply(reply,sizeof(reply),millis(),readOutputs());Serial.print(reply);lastReport=millis();}
void setup(){
    gpio_config_t io={};
    for(unsigned i=0;i<6;++i)io.pin_bit_mask|=(1ull<<OUTPUTS[i]);
    io.mode=GPIO_MODE_INPUT_OUTPUT;io.pull_up_en=GPIO_PULLUP_DISABLE;io.pull_down_en=GPIO_PULLDOWN_DISABLE;io.intr_type=GPIO_INTR_DISABLE;
    esp_err_t configured=gpio_config(&io);
    static sabz::Controller controller(((uint64_t)esp_random()<<32)|esp_random(),millis());board=&controller;
    if(configured!=ESP_OK)board->trip(sabz::OUTPUT_MISMATCH,millis());
    applyOutputs(); // Startup red indications before accepting traffic data.
    pinMode(CLEAR_PIN,INPUT_PULLUP);pinMode(STOP_LOOP_PIN,INPUT_PULLUP);
    Serial.begin(115200);
#if ESP_IDF_VERSION_MAJOR >= 5
    esp_task_wdt_config_t config={};config.timeout_ms=2000;config.idle_core_mask=0;config.trigger_panic=true;
    esp_err_t watchdog=esp_task_wdt_init(&config);
    if(watchdog==ESP_ERR_INVALID_STATE)watchdog=esp_task_wdt_reconfigure(&config);
    if(watchdog!=ESP_OK){board->trip(sabz::MANUAL_STOP,millis());applyOutputs();}
#else
#error "Build with Arduino-ESP32 3.x / ESP-IDF 5.x or newer, then verify the actual board."
#endif
    if(esp_task_wdt_status(nullptr)!=ESP_OK && esp_task_wdt_add(nullptr)!=ESP_OK){board->trip(sabz::MANUAL_STOP,millis());applyOutputs();}
    report();
}
void loop(){
    uint32_t now=millis();
    board->advance(now,digitalRead(CLEAR_PIN)==LOW,digitalRead(STOP_LOOP_PIN)==LOW);
    if(used && (uint32_t)(now-partialAt)>100){board->trip(sabz::BAD_FRAME,now);used=0;discard=true;}
    // Bounded work per tick: traffic on USB/UART cannot monopolise this loop.
    for(unsigned budget=0;budget<64 && Serial.available();++budget){
        int ch=Serial.read();
        if(ch=='\n'){
            if(!discard){buffer[used]=0;board->receive(buffer,millis());}
            used=0;discard=false;applyOutputs();report();
        }else if(!discard){
            if(!used)partialAt=now;
            if(ch<32||ch>126||used>=126){board->trip(sabz::BAD_FRAME,now);used=0;discard=true;}
            else buffer[used++]=(char)ch;
        }
    }
    applyOutputs();
    if(readOutputs()!=board->outputs()){board->trip(sabz::OUTPUT_MISMATCH,millis());applyOutputs();}
    if(!board->hasCommand && (uint32_t)(now-lastReport)>=1000)report();
    esp_task_wdt_reset();
    delay(1);
}

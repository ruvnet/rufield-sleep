// ESP32-S3, Arduino-ESP32 3.3.2. MAX98357A I2S amp. See docs/hardware.md.
#include <ESP_I2S.h>
#include <esp_random.h>
#include <math.h>

I2SClass i2s;
constexpr int BCLK = 4, WS = 5, DOUT = 6, MUTE_BUTTON = 7;
constexpr uint32_t LEASE_MS = 3000, HARD_LIMIT_MS = 30UL * 60 * 1000;
bool playing = false, ready = false, overflow = false;
uint32_t lastKeep = 0, startTime = 0;
int level = 0;
char command[32];
size_t used = 0;
float b0 = 0, b1 = 0, b2 = 0, envelope = 0;

void stopSound() {
  playing = false;
  level = 0;
  envelope = 0;
}

void receiveCommand() {
  if (!strcmp(command, "HELLO")) {
    Serial.println(ready ? "RFS1" : "I2S_ERROR");
  } else if (!strcmp(command, "STOP")) {
    stopSound();
    Serial.println("STOPPED");
  } else if (!strcmp(command, "KEEP") && playing) {
    lastKeep = millis();
    Serial.println("ALIVE");
  } else if (!strncmp(command, "PLAY ", 5) && !playing && ready && digitalRead(MUTE_BUTTON)) {
    char *end;
    long requested = strtol(command + 5, &end, 10);
    if (*end || requested < 1 || requested > 10) { Serial.println("INVALID"); return; }
    level = requested;
    playing = true;
    lastKeep = startTime = millis();
    Serial.println("PLAYING");
  } else {
    Serial.println("IDLE");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(MUTE_BUTTON, INPUT_PULLUP);
  i2s.setPins(BCLK, WS, DOUT);
  ready = i2s.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO);
}

void loop() {
  if (!digitalRead(MUTE_BUTTON) || millis()-lastKeep >= LEASE_MS || millis()-startTime >= HARD_LIMIT_MS)
    stopSound();
  for (int n=0; n<48 && Serial.available(); ++n) {
    char c = Serial.read();
    if (c=='\n') {
      command[used]=0;
      if (!overflow) receiveCommand();
      used=0; overflow=false;
    } else if (c!='\r') {
      if (used+1<sizeof(command)) command[used++]=c; else overflow=true;
    }
  }
  if (!ready) { delay(8); return; }
  int16_t samples[256] = {};
  if (playing) {
    for (int i=0;i<128;++i) {
      float white = (int32_t)esp_random() / 2147483648.0f;
      b0=.99765f*b0+.099046f*white;
      b1=.963f*b1+.2965164f*white;
      b2=.57f*b2+1.0526913f*white;
      envelope=fminf(1,envelope+.00006f);
      float pink = fmaxf(-1, fminf(1,(b0+b1+b2+.1848f*white)*.15f));
      samples[2*i]=samples[2*i+1]=(int16_t)(pink*envelope*level*150);
    }
  }
  i2s.write((uint8_t*)samples,sizeof(samples));
}

#include <Arduino.h>

// ========== 示例6：呼吸灯（PWM 渐变） ==========
// PWM = 快速开关电源，让灯"感觉"像在调亮度
// ESP32 用 ledc（LED 控制通道），比 Arduino 的 analogWrite 更底层
// 板载 LED 在 GPIO8（C3 反接：值越大越暗）

const int LED_PIN = 8;
const int CH = 0;         // 通道号（0~15 随便选一个）
const int FREQ = 5000;    // PWM 频率 5kHz（听不见的"嗡嗡"）
const int RES = 8;        // 精度 8 位：0~255

void setup() {
  // 先把 8 号引脚设成普通输出（点亮功能）
  pinMode(LED_PIN, OUTPUT);
  // 配置 LEDC：通道0，频率5k，精度8位
  ledcSetup(CH, FREQ, RES);
  // 把引脚绑到通道上
  ledcAttachPin(LED_PIN, CH);
}

void loop() {
  // 从 0 到 255 慢慢变亮（C3 反接 -> 值越大越暗，先变"亮"）
  for (int i = 0; i <= 255; i++) {
    ledcWrite(CH, 255 - i);   // 反接所以取反
    delay(10);
  }
  // 从 255 回到 0（变暗）
  for (int i = 255; i >= 0; i--) {
    ledcWrite(CH, 255 - i);
    delay(10);
  }
}

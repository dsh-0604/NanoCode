#include <Arduino.h>

// ========== 示例1：点灯（Hello World 的硬件版） ==========
// ESP32-C3 mini 板载 LED 接在 GPIO8
// 注意：C3 的灯是"反接"的——输出 LOW(低电平) 灯亮，HIGH 灯灭

void setup() {
  pinMode(8, OUTPUT);   // 把 8 号引脚设置成"输出模式"
  // pinMode = Pin(引脚) Mode(模式)
  // OUTPUT = 输出：芯片从这个脚往外送电
}

void loop() {
  digitalWrite(8, LOW);   // 让 8 号脚输出低电平 -> 灯亮
  delay(500);             // 停 500 毫秒（半秒）
  digitalWrite(8, HIGH);  // 让 8 号脚输出高电平 -> 灯灭
  delay(500);             // 再停半秒
}

#include <Arduino.h>

// ========== 示例3：按钮控制灯 ==========
// 接线：
//   按钮一端 -> GND
//   按钮另一端 -> GPIO0（并到 3.3V，用上拉）
// 用法：按下按钮灯亮，松开灯灭

const int BTN = 0;    // 按钮接的引脚
const int LED = 8;    // 板载 LED 引脚（C3）

void setup() {
  pinMode(BTN, INPUT_PULLUP);  // 按钮：输入模式 + 内部上拉电阻
  // INPUT_PULLUP：芯片内部帮你接了个"上拉电阻"，
  // 不按的时候读到 HIGH，按下读到 LOW
  pinMode(LED, OUTPUT);        // LED：输出模式
}

void loop() {
  int value = digitalRead(BTN);  // 读按钮：HIGH=没按，LOW=按下
  if (value == LOW) {            // 如果按下了
    digitalWrite(LED, LOW);      //   LED 亮（C3 反接）
  } else {                       // 否则（没按）
    digitalWrite(LED, HIGH);     //   LED 灭
  }
  // 这个程序在 if / else 之间来回跳，像开关
}

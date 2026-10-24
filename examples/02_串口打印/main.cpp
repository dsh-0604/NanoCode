#include <Arduino.h>

// ========== 示例2：串口打印（让板子"说话"） ==========
// 点"烧录"后，打开下面的串口监视器，选对 COM 口、波特率 115200
// 就能在电脑上看到板子发过来的字

void setup() {
  Serial.begin(115200);   // 启动串口，速度 115200
  // Serial = 串口对象，begin = 开始
  // 波特率：电脑和板子约好的"说话速度"
}

void loop() {
  // println = print line：打印一行（后面自动换行）
  Serial.println("你好！我是 ESP32-C3");
  Serial.print("上电已过 ");    // print：打印但不换行
  Serial.print(millis());        // millis() = 开机到现在过了几毫秒
  Serial.println(" 毫秒");

  delay(1000);  // 每秒说一次
}

#include <Arduino.h>
#include <Servo.h>

// ========== 示例4：舵机（机器人关节的基础） ==========
// 接线：
//   舵机棕色线(棕/黑) -> GND
//   舵机红色线         -> 5V（舵机要单独供电，别吃板子）
//   舵机橙色线(信号)   -> GPIO4

Servo myservo;   // 造一个"舵机对象"，名字叫 myservo
// Servo 是类，myservo 是它的一个"实例"（真实的一台舵机）

int angle = 0;         // 当前角度
int step = 1;          // 每次转 1 度

void setup() {
  myservo.attach(4);   // 把舵机绑到 4 号引脚
  myservo.write(0);    // 先转到 0 度
}

void loop() {
  angle += step;       // angle = angle + step（转一格）
  if (angle >= 180) {  // 到 180 度了？
    step = -1;         //   掉头往回转
  }
  if (angle <= 0) {    // 回到 0 度了？
    step = 1;          //   再掉头往前转
  }
  myservo.write(angle);   // 让舵机转到 angle 这个角度
  delay(15);              // 每 15 毫秒动一次（转太快会抖）
}

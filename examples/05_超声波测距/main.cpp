#include <Arduino.h>

// ========== 示例5：超声波测距（机器人"眼睛"） ==========
// 模块：HC-SR04
// 接线：
//   VCC -> 5V     GND -> GND
//   Trig(发射) -> GPIO5     Echo(回波) -> GPIO18
// 原理：发一声"哒"，听回声要多久，就算出距离

const int TRIG = 5;   // 发射引脚
const int ECHO = 18;  // 接收引脚

void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT);  // 发射端：往外送信号
  pinMode(ECHO, INPUT);   // 接收端：往里读信号
}

float getDistance() {
  // 先让 Trig 低电平一下，保证干净
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  // 发一个 10 微秒的高电平脉冲（"哒"）
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  // 测回声持续的时间（微秒）
  long duration = pulseIn(ECHO, HIGH);
  // 声速约 340m/s = 0.034cm/微秒
  // 一来一回是两倍距离，所以除以 2
  float cm = duration * 0.034 / 2;
  return cm;
}

void loop() {
  float dist = getDistance();
  Serial.print("距离: ");
  Serial.print(dist);
  Serial.println(" cm");
  delay(300);
}

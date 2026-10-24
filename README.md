# NanoCode —— 新手 C++ 实战 IDE

> 给**刚学完 C++ 基础逻辑、想动手做项目**的初学者用的嵌入式 IDE。
> 名字：**Nano**（纳米 = 微小芯片）+ **Code**（代码）——你的代码跑在微小的芯片上。
> 痛点：VS Code 太复杂、Arduino IDE 补全太弱、命令行记不住。
> 目标：**打开就能写，点一下就能烧到板子上。**

## 长这样

![主界面：新建文件自带 Arduino 模板（include + setup + loop）](https://aka.doubaocdn.com/s/1ThvZGBPZo)

![补全列表：中文解释 + 类型标签，PyCharm 风格](https://aka.doubaocdn.com/s/OcRWTO1ikv)

## 它解决什么问题

| 痛点 | 解决方案 |
|---|---|
| 单词记不全，靠模糊记忆打代码 | **模糊补全**：输入 `pin` 就出 `pinMode`，输入 `dig` 出 `digitalWrite`，每个函数带**中文解释** |
| 界面英文、功能太多看不懂 | 小熊猫风格：中文大按钮，只有 新建/打开/保存/编译/烧录/串口/示例 |
| 不知道怎么开始写 | 内置**示例中心**：点灯、串口、按钮、舵机、超声波、PWM……点一下就插入代码 |
| 编译烧录命令记不住 | 一键 `编译` / 一键 `烧录`，底层自动调用 PlatformIO |
| 漏分号烧录失败 | 烧录前**自动帮你补上**，底部小提示告诉你改了哪几行（长记性，不打断进度） |
| 回车不会换行缩进 | 智能缩进：`{` 进一级、`}` 退一级，多行选中按 Tab 整块缩进 |

## 快速开始

**给新手（不用装任何东西）**：到 [Releases](https://github.com/dsh-0604/NanoCode/releases) 下载 `NanoCode.exe`，双击就能打开。
> 只写代码、看示例、学语法：什么都不用装。
> 要**烧录到板子**：还得装 [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation.html)（含 ESP32 平台），IDE 会自动调用它。

**给开发者（跑源码）**：
1. 安装依赖（只需要一次）：
   ```
   pip install PySide6
   ```
   另外需要 [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation.html)
   和 [Git](https://git-scm.com/)（装好后要能执行 `pio` 和 `git`）。

2. 双击 `启动.bat`，或者：
   ```
   python NanoCode.py
   ```

3. 顶部按钮：
   - **示例**：选一个内置例子，代码直接出现在编辑器里
   - **新建**：自动带上 Arduino 模板（`#include <Arduino.h>` + `setup` + `loop`），不用从零敲
   - **编译**：检查代码有没有写错（不用接板子）
   - **烧录**：插上板子，选好 COM 口，点一下写进板子（**会自动保存**，不怕忘点保存烧旧代码）
   - **串口**：选 COM 口 + 波特率（一般 115200），看板子"说话"

## 跑测试 / 打包

```
python tests/smoke_test.py   # 冒烟测试：启动、模板、示例、补全（无界面，秒级跑完）
python -m PyInstaller --noconfirm --windowed --name NanoCode --icon icons\ctps.ico --add-data "examples;examples" --add-data "icons;icons" NanoCode.py
```

## 模糊补全怎么用

- 输入几个字母就自动弹候选（不用等，也不用按快捷键）
- 候选会显示 **函数名 + 中文说明**，比如输入 `ser`：
  ```
  Serial.begin   串口开始
  Serial.print   串口打印（不换行）
  Serial.println 串口打印并换行
  ```
- 也支持"首字母模糊"：输入 `pM` 也能找到 `pinMode`
- 按 `Ctrl + 空格` 可以手动唤起补全

## 报错会教你怎么改

- 编译出错 → 自动**跳到出错行**，红色高亮；输出面板里的红字**点一下也能跳**
- 漏分号 → 编译/烧录前自动补上，小提示 + 输出面板列出"你写的 → 改好的"对照

## 项目结构

```
NanoCode/
├── NanoCode.py       # 主程序（纯 PySide6，无第三方编辑器依赖）
├── keywords.py        # 词库：C++ 关键字 + Arduino/ESP32 常用函数（带中文）
├── examples/          # 示例中心：每个例子一个文件夹
│   ├── 01_点灯/
│   ├── 02_串口打印/
│   ├── 03_按钮控制灯/
│   ├── 04_舵机/
│   ├── 05_超声波测距/
│   └── 06_呼吸灯PWM/
├── icons/ctps.ico     # 应用图标（黑底白字 </>）
├── tests/             # 冒烟测试（能启动/模板/示例/补全）
├── 启动.bat           # Windows 一键启动
└── README.md
```

## 适配的开发板

- 默认适配 **ESP32-C3**（外接 LED 推荐接 GPIO0，正极接引脚、负极接 GND）
- 想换板子：在"项目"栏填你的 PlatformIO 项目路径（每个板子一个项目文件夹）

## 技术栈

- Python 3.10+ / PySide6（Qt6 Widgets，**不是** Web 套壳）
- 编译/烧录：PlatformIO CLI（`pio run` / `pio run -t upload`）

## 开源

MIT License。欢迎 PR：加示例、加词库、改界面。

**给新手的约定**：这个项目就是为"你"做的——如果你看不懂某段代码，去 issue 里骂一句，作者会把它改成大白话。

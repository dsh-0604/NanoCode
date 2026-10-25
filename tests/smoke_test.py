# -*- coding: utf-8 -*-
"""NanoCode 冒烟测试（无界面运行，一分钟内跑完）
用法：python tests/smoke_test.py
检查：能启动主窗口、新建文件有基础模板、示例能载入、补全去重、模板补全数据正确。
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import NanoCode as C
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

FAILS = []


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        FAILS.append(name)


app = QApplication(sys.argv)
app.setStyle("Fusion")

# 1. 主窗口能启动
win = C.MainWindow()
check("主窗口能启动，标题含 NanoCode", "NanoCode" in win.windowTitle())
check("启动时没有任何空标签（点新建才建文件）", win.tabs.count() == 0)

# 2. 新建文件自带 Arduino 模板（传名字绕过弹窗）
win.newFile("smoke")
text = win.editor.toPlainText()
check("新建文件带 #include <Arduino.h>", "#include <Arduino.h>" in text)
check("新建文件带 void setup()", "void setup()" in text)
check("新建文件带 void loop()", "void loop()" in text)
check("新建文件已绑定为 src 下的 .cpp", win.currentFile is not None and win.currentFile.lower().endswith(".cpp"))

# 3. 示例能载入
win.loadExampleByName("01_点灯")
t1 = win.editor.toPlainText()
check("示例 01_点灯 载入（含 pinMode）", "pinMode" in t1 and "digitalWrite" in t1)

# 4. 补全去重 + 类型
res = C.build_completion_list("pin")
names = [n for n, d, s, k in res]
check("补全 pin 时 pinMode 只出现 1 次", names.count("pinMode") == 1)
kinds = dict((n, k) for n, d, s, k in res)
check("pinMode 类型为片段(模板)", kinds.get("pinMode") == C.KIND_SNIPPET)

# 5. 模板数据正确（$1 占位 + 括号分号）
sn = __import__("keywords").SNIPPETS["pinMode"]
check("pinMode 模板带括号和分号", sn == "pinMode($1, $2);")

# 5.1 固定句式模板扩充：结构语句 + 成员函数
sns = __import__("keywords").SNIPPETS
check("while/else/switch 都有固定句式模板",
      all(k in sns for k in ("while", "else", "switch", "include")))
check("Serial.begin 有模板", "Serial.begin($1);" in sns.get("Serial.begin", ""))
check("include 模板补全成 #include <...>", sns.get("include") == "#include <$1>")
check("setup/loop 模板补全成 void setup()/void loop()",
      sns.get("setup") == "void setup() {\n    $1\n}" and
      sns.get("loop") == "void loop() {\n    $1\n}")

# 6. 补全弹窗数据（QStandardItemModel 自定义角色）
ed = C.CodeEditor()
ed.setPlainText("pin")
cur = ed.textCursor()
cur.movePosition(QTextCursor.MoveOperation.End)
ed.setTextCursor(cur)
ed.triggerCompletion()
m = ed._completionModel
row0 = m.index(0, 0)
check("补全列表弹出且第一项是 pinMode", m.data(row0, Qt.DisplayRole) == "pinMode")
check("补全项带中文说明", bool(m.data(row0, Qt.UserRole)))
check("补全项带类型标签", m.data(row0, Qt.UserRole + 2) == C.KIND_SNIPPET)

# 6.1 带点补全：Serial. → Serial.begin/print/println
ed2 = C.CodeEditor()
ed2.setPlainText("Serial.")
cur2 = ed2.textCursor()
cur2.movePosition(QTextCursor.MoveOperation.End)
ed2.setTextCursor(cur2)
ed2.triggerCompletion()
m2 = ed2._completionModel
names2 = [m2.data(m2.index(i, 0), Qt.DisplayRole) for i in range(m2.rowCount())]
check("输入 Serial. 弹出成员函数", "Serial.begin" in names2 and "Serial.println" in names2)

# 7. 多文件标签：开第二个文件，新开标签页并切换，内容不串，旧文件不被删
before = win.tabs.count()
win.newFile("second")
check("多标签：再建一个文件后多开 1 个标签", win.tabs.count() == before + 1)
check("新建不删旧文件：smoke.cpp 还在磁盘上",
      os.path.isfile(os.path.join(win.projectDir, "src", "smoke.cpp")))
check("当前标签是第二个文件", win.currentFile is not None and win.currentFile.endswith("second.cpp"))
# 切回第一个标签，编辑器内容还是第一个文件
win.tabs.setCurrentIndex(0)
check("切回第一个标签，内容仍是原文件", win.editor.toPlainText().startswith("#include <Arduino.h>"))
# 再切到第二个标签
win.tabs.setCurrentIndex(1)
check("切到第二个标签，内容是新文件模板", win.editor.toPlainText().startswith("#include <Arduino.h>"))

# 8. 保存指定编辑器（关标签时存被关的那个，而不是当前页）
# tabs 顺序：0=smoke、1=示例：01_点灯、2=second
w2 = win.tabs.widget(2)   # second.cpp（有真实文件）
w2.setPlainText("// 这是第二个文件的独特内容\n" + w2.toPlainText())
win.tabs.setCurrentIndex(0)   # 当前页是 smoke
win.saveEditor(w2)            # 但保存的是 second.cpp 自己
with open(w2.filePath, "r", encoding="utf-8") as f:
    disk = f.read()
check("保存指定编辑器：写的是被保存文件自己的路径", disk.startswith("// 这是第二个文件的独特内容"))
check("保存指定编辑器：没有误改当前页文件", win.editor.toPlainText().startswith("#include <Arduino.h>"))
# 保存后当前页没变，第二个文件内容仍在内存里
win.tabs.setCurrentIndex(2)
check("保存指定编辑器：被保存文件内容保留", win.editor.toPlainText().startswith("// 这是第二个文件的独特内容"))
# 保存后标签名 = 磁盘文件名（铁律）
check("保存后标签名=磁盘文件名（second.cpp）",
      win.tabs.tabText(win.tabs.indexOf(w2)) == "second.cpp")

# 8.5 默认名推导（新手友好：示例名直接当文件名；未命名残留回退 main）
win._newEditorTab("示例：01_点灯", None)
idx = win.tabs.count() - 1
check("默认名推导：示例：01_点灯 → 01_点灯",
      win._defaultNameFromLabel(win.tabs.widget(idx)) == "01_点灯")
win._newEditorTab("示例（未命名）", None)
idx = win.tabs.count() - 1
check("默认名推导：示例（未命名）→ main",
      win._defaultNameFromLabel(win.tabs.widget(idx)) == "main")

print("\n结果：%d 项通过，%d 项失败" % (28 - len(FAILS), len(FAILS)))
sys.exit(1 if FAILS else 0)

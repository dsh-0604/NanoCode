# -*- coding: utf-8 -*-
"""
NanoCode —— 新手 C++ 实战 IDE
给"刚学完 C++ 基础、想动手做硬件项目"的初学者用：
  中文界面 + 模糊补全(带中文解释) + 一键编译/烧录 + 串口监视 + 示例中心
底层调用 PlatformIO CLI，纯 Qt6 Widgets（不是 Web 套壳）。
"""
import os
import re
import sys
import glob
import shutil

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QTextEdit, QTextBrowser, QToolBar,
    QCompleter, QComboBox, QCheckBox, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QFileDialog, QMessageBox, QLineEdit, QPushButton, QSplitter,
    QStyledItemDelegate, QListWidget, QListWidgetItem, QDialog, QStyle,
    QGraphicsOpacityEffect, QInputDialog, QTabWidget, QTabBar, QMenu
)
from PySide6.QtGui import (
    QFont, QColor, QTextCharFormat, QSyntaxHighlighter, QPainter,
    QTextFormat, QKeySequence, QAction, QTextCursor, QIcon, QLinearGradient,
    QStandardItemModel, QStandardItem
)
from PySide6.QtCore import (
    Qt, QStringListModel, QProcess, QRect, QSize, QUrl, QTimer, QRectF,
    QPropertyAnimation
)

from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

import keywords as KW

# PlatformIO 报错格式：src\main.cpp:7:5: error: xxx（也可能是 D:\...\main.cpp 绝对路径）
ERR_RE = re.compile(
    r"((?:[A-Za-z]:[\\/])?[^:\s]+\.(?:cpp|ino|h))\s*:\s*(\d+)\s*(?::\s*(\d+))?\s*:\s*(error|warning|fatal error):\s*(.*)",
    re.I)

# ==================== 路径配置（可在下边改，默认 D 盘） ====================
PIO_EXE = r"D:\platformio-core\penv\Scripts\pio.exe"
PLATFORMIO_CORE_DIR = r"D:\platformio-core"
DEFAULT_PROJECT = r"D:\PlatformIO\c3_blink"
FRAMEWORK_CORES = r"D:\platformio-core\packages\framework-arduinoespressif32\cores\esp32"
FRAMEWORK_LIBS = r"D:\platformio-core\packages\framework-arduinoespressif32\libraries"
EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")

# git 目录：编译时拼进 PATH（PlatformIO 有些库要 git 拉取）。
# detect_paths() 会实际探测，找不到就清空，绝不硬编码死路径。
GIT_CMD_DIR = r"D:\Git\cmd"

def detect_paths():
    """换电脑也能用：默认路径不存在时，自动去 PATH 里找 pio.exe / git。
    找不到就保持原路径，编译时再给友好提示。"""
    global PIO_EXE, PLATFORMIO_CORE_DIR, FRAMEWORK_CORES, FRAMEWORK_LIBS, GIT_CMD_DIR
    for d in os.environ.get("PATH", "").split(";"):
        cand = os.path.join(d, "pio.exe")
        if os.path.isfile(cand):
            PIO_EXE = cand
            PLATFORMIO_CORE_DIR = os.path.dirname(os.path.dirname(d))
            FRAMEWORK_CORES = os.path.join(
                PLATFORMIO_CORE_DIR, "packages",
                "framework-arduinoespressif32", "cores", "esp32")
            FRAMEWORK_LIBS = os.path.join(
                PLATFORMIO_CORE_DIR, "packages",
                "framework-arduinoespressif32", "libraries")
            break
    # git 探测：PATH 里有 git.exe 就用它；默认路径有效就保持；否则清空（不硬编码）
    g = shutil.which("git")
    if g:
        GIT_CMD_DIR = os.path.dirname(g)
    elif not (os.path.isdir(GIT_CMD_DIR)
              and os.path.isfile(os.path.join(GIT_CMD_DIR, "git.exe"))):
        GIT_CMD_DIR = ""

# 新建文件默认模板：写硬件的固定骨架，每次新建自动带上
DEFAULT_TEMPLATE = (
    "#include <Arduino.h>\n"
    "\n"
    "void setup() {\n"
    "  // 上电只执行一次：初始化都写这里\n"
    "  \n"
    "}\n"
    "\n"
    "void loop() {\n"
    "  // 一直反复执行：主要功能写这里\n"
    "  \n"
    "}\n"
)

# ==================== 自动扫描头文件补充词库 ====================
EXTRA_FUNCTIONS = set()
_FUNC_RE = re.compile(r"\b([a-zA-Z_]\w*)\s*\(")

def scan_arduino_headers():
    dirs = [FRAMEWORK_CORES]
    if os.path.isdir(FRAMEWORK_LIBS):
        try:
            libs = os.listdir(FRAMEWORK_LIBS)[:60]
        except OSError:
            libs = []
        for lib in libs:
            d = os.path.join(FRAMEWORK_LIBS, lib)
            if os.path.isdir(d):
                dirs.append(d)
    for d in dirs:
        for h in glob.glob(os.path.join(d, "*.h")):
            try:
                with open(h, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                for m in _FUNC_RE.finditer(text):
                    name = m.group(1)
                    if 2 <= len(name) <= 24 and not name.startswith("_"):
                        EXTRA_FUNCTIONS.add(name)
            except Exception:
                pass

# ==================== 模糊匹配 ====================
# 新手最常用的名字：权重 +20，排序优先
HOT = {
    "pinMode", "digitalWrite", "digitalRead", "analogRead", "delay",
    "millis", "Serial.begin", "Serial.print", "Serial.println",
    "LED_BUILTIN", "HIGH", "LOW", "INPUT", "OUTPUT", "INPUT_PULLUP",
    "setup", "loop", "void", "int", "if", "else", "for", "while",
    "return", "true", "false", "String", "float", "char", "bool",
    "delayMicroseconds", "map", "constrain",
}

def fuzzy_score(pattern, word):
    """模糊打分：前缀 > 中间包含 > 逐字符顺序（如 pM → pinMode）。越高越像。
    首字母缩写（pattern 首字 = 单词首字）单独加分，拉开和“随机包含”的差距，
    避免 pM 匹配出一堆 EEPROM 之类的噪声。"""
    p = pattern.lower()
    w = word.lower()
    if not p:
        return -1
    if w.startswith(p):
        s = 100 - len(w) * 0.1
    else:
        idx = w.find(p)
        if idx >= 0:
            s = 60 - idx * 0.4 - len(w) * 0.05
        else:
            last = -1
            cnt = 0
            for c in p:
                j = w.find(c, last + 1)
                if j < 0:
                    break
                last = j
                cnt += 1
            if cnt == len(p):
                s = 35 - len(w) * 0.05 - last * 0.08
                # 首字母缩写加分：pM → pinMode（首字对上了才算真缩写）
                if w.startswith(p[0]):
                    s += 18
            else:
                return -1
    if word in HOT:
        s += 20
    return s

# 补全结果缓存：同一前缀不重复全量扫描，打字不卡
_COMPLETION_CACHE = {}

# 候选类型（决定列表里左边的图标和右边的类型小字）
KIND_KEYWORD = "关键字"
KIND_FUNC = "函数"
KIND_SNIPPET = "片段"
KIND_CONST = "常量"

_CORE_NAMES = {n for n, _ in KW.CORE_KEYWORDS}
_CONST_NAMES = {"HIGH", "LOW", "INPUT", "OUTPUT", "INPUT_PULLUP",
                "true", "false", "NULL", "nullptr"}


def completion_kind(name):
    """给候选分类型：片段(模板) > 常量 > 关键字 > 函数"""
    if name in KW.SNIPPETS:
        return KIND_SNIPPET
    if name in _CONST_NAMES:
        return KIND_CONST
    if name in _CORE_NAMES:
        return KIND_KEYWORD
    return KIND_FUNC


def build_completion_list(pattern):
    key = pattern.lower()
    if key in _COMPLETION_CACHE:
        return _COMPLETION_CACHE[key]
    seen = set()          # 去重：同一个名字只留一个（避免两个 pinMode）
    results = []
    for group in (KW.CORE_KEYWORDS, KW.ARDUINO_KEYWORDS):
        for name, desc in group:
            if name in seen:
                continue
            s = fuzzy_score(pattern, name)
            if s >= 0:
                seen.add(name)
                results.append((name, desc, s, completion_kind(name)))
    for name in sorted(EXTRA_FUNCTIONS):
        if name in seen:
            continue
        s = fuzzy_score(pattern, name)
        if s >= 0:
            seen.add(name)
            results.append((name, "（自动扫描到的函数）", s, KIND_FUNC))
    results.sort(key=lambda x: (-x[2], len(x[0])))
    out = results[:12]
    if len(_COMPLETION_CACHE) > 300:
        _COMPLETION_CACHE.clear()
    _COMPLETION_CACHE[key] = out
    return out

# ==================== C++ 语法高亮 ====================
class CppHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)
        self.rules = []
        kw = QTextCharFormat()
        kw.setForeground(QColor("#c678dd"))
        kw.setFontWeight(QFont.Bold)
        self.rules.append((re.compile(
            r"\b(" + "|".join(k for k, _ in KW.CORE_KEYWORDS) + r")\b"), kw))
        func = QTextCharFormat()
        func.setForeground(QColor("#61afef"))
        self.rules.append((re.compile(r"\b[A-Za-z_]\w*(?=\s*\()"), func))
        num = QTextCharFormat()
        num.setForeground(QColor("#d19a66"))
        self.rules.append((re.compile(r"\b\d+\.?\d*[fF]?\b"), num))
        st = QTextCharFormat()
        st.setForeground(QColor("#98c379"))
        self.rules.append((re.compile(r"\"[^\"\\]*(\\.[^\"\\]*)*\""), st))
        self.rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), st))
        com = QTextCharFormat()
        com.setForeground(QColor("#7f848e"))
        self.rules.append((re.compile(r"//[^\n]*"), com))
        pre = QTextCharFormat()
        pre.setForeground(QColor("#e06c75"))
        self.rules.append((re.compile(r"^\s*#\w+"), pre))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

# ==================== 补全弹窗（PyCharm 风格：类型徽标 + 名字 + 中文说明 + 右侧类型） ====================
class TwoLineDelegate(QStyledItemDelegate):
    """左边一个类型小方块，中间名字（命中字符薄荷绿加粗），
    右边灰色类型小字，下面一行中文解释——模仿 PyCharm/小熊猫的补全列表"""
    BADGE = {
        KIND_KEYWORD: ("K", "#c678dd"),
        KIND_FUNC: ("f", "#61afef"),
        KIND_SNIPPET: ("\u26a1", "#e5c07b"),
        KIND_CONST: ("C", "#d19a66"),
    }

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        # 背景：选中薄荷绿 / 悬停灰蓝 / 普通深灰
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#274a38"))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor("#2e323c"))
        else:
            painter.fillRect(option.rect, QColor("#2c313a"))
        name = index.data(Qt.DisplayRole) or ""
        prefix = index.data(Qt.UserRole + 1) or ""
        desc = index.data(Qt.UserRole) or ""
        kind = index.data(Qt.UserRole + 2) or KIND_FUNC
        font = painter.font()
        half = option.rect.height() // 2

        # 右侧灰色类型小字（函数/关键字/片段/常量）
        type_w = 0
        if kind:
            small = QFont(font)
            small.setPointSize(max(font.pointSize() - 3, 7))
            painter.setFont(small)
            painter.setPen(QColor("#5c6370"))
            type_w = painter.fontMetrics().horizontalAdvance(kind) + 10
            painter.drawText(option.rect.adjusted(6, 1, -10, -half),
                             Qt.AlignRight | Qt.AlignVCenter, kind)

        # 左侧类型徽标：圆角小方块 + 字符
        badge_x = option.rect.left() + 7
        bsz = 22
        by = option.rect.top() + (option.rect.height() - bsz) // 2
        ch, col = self.BADGE.get(kind, ("?", "#9aa0aa"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1e2128"))
        painter.drawRoundedRect(QRectF(badge_x, by, bsz, bsz), 5, 5)
        bf = QFont(font)
        bf.setBold(True)
        bf.setPointSize(max(font.pointSize() - 3, 7))
        painter.setFont(bf)
        painter.setPen(QColor(col))
        painter.drawText(QRectF(badge_x, by, bsz, bsz), Qt.AlignCenter, ch)

        # 中间名字：按“命中的字符”分段画，命中加粗 + 薄荷绿
        x = badge_x + bsz + 8
        r = QRect(option.rect.left() + 8, option.rect.top() + 1,
                  option.rect.width() - 16 - type_w, half)
        hl = set(prefix.lower())
        segs = []
        cur, cur_hl = "", False
        for ch in name:
            is_hl = ch.lower() in hl
            if cur and cur_hl != is_hl:
                segs.append((cur, cur_hl))
                cur = ch
            else:
                cur += ch
            cur_hl = is_hl
        segs.append((cur, cur_hl))
        for seg, is_hl in segs:
            if x > r.right():
                break
            if is_hl:
                bf = QFont(font)
                bf.setBold(True)
                painter.setFont(bf)
                painter.setPen(QColor("#4ade80"))
            else:
                painter.setFont(font)
                painter.setPen(QColor("#e6e6e6"))
            painter.drawText(QRect(x, r.top(), 10000, r.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, seg)
            x += painter.fontMetrics().horizontalAdvance(seg)

        # 第二行：中文解释
        if desc:
            painter.setPen(QColor("#9aa0aa"))
            small = QFont(font)
            small.setPointSize(max(font.pointSize() - 2, 7))
            painter.setFont(small)
            painter.drawText(option.rect.adjusted(badge_x + bsz + 8, half, -8, -2),
                             Qt.AlignLeft | Qt.AlignVCenter, desc)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        return QSize(base.width() + 100, 40)

# ==================== 行号区 ====================
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#21252b"))
        block = self.codeEditor.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.codeEditor.blockBoundingGeometry(block).translated(
            self.codeEditor.contentOffset()).top())
        bottom = top + round(self.codeEditor.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#5c6370"))
                painter.drawText(0, top, self.codeEditor.lineNumberAreaWidth() - 8,
                                 self.codeEditor.fontMetrics().height(),
                                 Qt.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.codeEditor.blockBoundingRect(block).height())
            number += 1

# ==================== 编辑器（行号 + 语法高亮 + 模糊补全） ====================
class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.completer = None
        self.initCompleter()
        # 片段占位跳转：打字离开占位符后，标记自动失效
        self._snippetMarks = None
        self._snippetIdx = 0
        self.document().contentsChanged.connect(self._clearSnippetMarksIfMoved)

    def initCompleter(self):
        model = QStandardItemModel(self)
        self.completer = QCompleter(model, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self.insertCompletion)
        pop = self.completer.popup()
        pop.setItemDelegate(TwoLineDelegate(pop))
        pop.setMinimumWidth(400)

    def insertCompletion(self, comp):
        prefix = self.completer.completionPrefix()
        if comp in KW.SNIPPETS:
            # 固定句式：自动补齐括号 + 分号 + 缩进，光标停在第 1 个空位
            self._insertSnippet(KW.SNIPPETS[comp])
            return
        extra = comp[len(prefix):] if comp.startswith(prefix) else comp
        self.textCursor().insertText(extra)

    def _insertSnippet(self, snippet):
        """插入代码模板：删掉刚输入的前缀，填完整句式，光标停在第 1 个占位处。
        关键：$1 的位置要在“删掉所有占位符之后”的正文里重新算，
        否则有换行缩进或多个占位符时光标会停错。
        记录所有 $N 占位位置，之后按 Tab 可以在占位符之间跳（switch 那种多占位）。"""
        tc = self.textCursor()
        prefix = self.completer.completionPrefix()
        block = tc.block()
        rel = tc.position() - block.position()
        text = block.text()
        start = rel - len(prefix)
        if start >= 0 and text[start:rel].lower() == prefix.lower():
            tc.setPosition(block.position() + start)
            tc.setPosition(block.position() + rel, QTextCursor.KeepAnchor)
            tc.removeSelectedText()
        first_raw = snippet.find("$1")
        body = re.sub(r"\$[0-9]+", "", snippet)
        pos = 0
        if first_raw >= 0:
            # $1 之前每有一个占位符（$N 占 2 个字符），body 里就少 2 个字符
            before_raw = snippet[:first_raw]
            n_placeholders = len(re.findall(r"\$[0-9]+", before_raw))
            pos = len(before_raw) - n_placeholders * 2
        tc.insertText(body)
        if first_raw >= 0:
            cur = QTextCursor(self.document())
            cur.setPosition(tc.position() - len(body) + pos)
            self.setTextCursor(cur)
        # 记录所有占位位置（body 中的偏移），供 Tab 跳转
        marks = []
        offset = 0
        for m in re.finditer(r"\$[0-9]+", snippet):
            marks.append(m.start() - offset)
            offset += 2
        self._snippetMarks = marks
        self._snippetIdx = 0

    def _jumpSnippetMark(self, delta):
        """在代码片段的占位符之间跳（Tab 下一个，Shift+Tab 上一个）"""
        marks = getattr(self, "_snippetMarks", None)
        if not marks:
            return
        n = len(marks)
        self._snippetIdx = (self._snippetIdx + delta) % n
        cur = QTextCursor(self.document())
        cur.setPosition(marks[self._snippetIdx])
        self.setTextCursor(cur)

    def _clearSnippetMarksIfMoved(self):
        """用户真的打字了（光标离开占位符）→ 占位跳转标记作废"""
        marks = getattr(self, "_snippetMarks", None)
        if not marks:
            return
        pos = self.textCursor().position()
        if pos not in marks:
            self._snippetMarks = None

    def _zoomFont(self, delta):
        """Ctrl+= / Ctrl+- 调字号（8~30 之间）"""
        f = self.font()
        size = f.pointSize() + delta
        if 8 <= size <= 30:
            f.setPointSize(size)
            self.setFont(f)
            self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

    def currentWord(self):
        """光标前的补全前缀：支持单词（pin），也支持 Serial. 这种带点的"""
        tc = self.textCursor()
        pos = tc.position()
        block = tc.block()
        text = block.text()
        rel = pos - block.position()
        m = re.search(r"[A-Za-z_]\w*\.?\w*$", text[:rel])
        return m.group(0) if m else ""

    def keyPressEvent(self, e):
        if self.completer and self.completer.popup().isVisible():
            if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                self.insertCompletion(self.completer.currentCompletion())
                self.completer.popup().hide()
                return
            if e.key() in (Qt.Key_Escape, Qt.Key_Backtab):
                self.completer.popup().hide()
                return
            # 退格删字时，如果补全框还开着，跟着更新候选
            if e.key() == Qt.Key_Backspace and self.completer.popup().isVisible():
                super().keyPressEvent(e)
                self.triggerCompletion()
                return
        if e.key() == Qt.Key_Space and (e.modifiers() & Qt.ControlModifier):
            self.triggerCompletion()
            return
        if e.key() in (Qt.Key_Equal, Qt.Key_Plus) and (e.modifiers() & Qt.ControlModifier):
            self._zoomFont(1)
            return
        if e.key() == Qt.Key_Minus and (e.modifiers() & Qt.ControlModifier):
            self._zoomFont(-1)
            return
        if e.key() == Qt.Key_Tab:
            marks = getattr(self, "_snippetMarks", None)
            if marks and not self.textCursor().hasSelection():
                self._jumpSnippetMark(1)
                return
            if self.textCursor().hasSelection():
                self.indentBlock(1)
                return
            super().keyPressEvent(e)
            return
        if e.key() == Qt.Key_Backtab:
            marks = getattr(self, "_snippetMarks", None)
            if marks and not self.textCursor().hasSelection():
                self._jumpSnippetMark(-1)
                return
            if self.textCursor().hasSelection():
                self.indentBlock(-1)
                return
            super().keyPressEvent(e)
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.autoIndent()
            return
        super().keyPressEvent(e)

    def indentBlock(self, delta):
        """选中多行后按 Tab / Shift+Tab：整块缩进 / 退格"""
        tc = self.textCursor()
        start = tc.selectionStart()
        end = tc.selectionEnd()
        sb = self.document().findBlock(start)
        eb = self.document().findBlock(end)
        if end == eb.position() and eb != sb:
            eb = eb.previous()  # 选区止于行首 → 那行不算
        c = QTextCursor(self.document())
        c.beginEditBlock()
        b = sb
        while True:
            cur = QTextCursor(b)
            if delta > 0:
                cur.insertText("\t")
            else:
                t = b.text()
                if t.startswith("\t"):
                    cur.setPosition(b.position())
                    cur.setPosition(b.position() + 1, QTextCursor.KeepAnchor)
                    cur.removeSelectedText()
                elif t.startswith("    "):
                    cur.setPosition(b.position())
                    cur.setPosition(b.position() + 4, QTextCursor.KeepAnchor)
                    cur.removeSelectedText()
                elif t.startswith("  "):
                    cur.setPosition(b.position())
                    cur.setPosition(b.position() + 2, QTextCursor.KeepAnchor)
                    cur.removeSelectedText()
            if b == eb:
                break
            b = b.next()
        c.endEditBlock()

    def autoIndent(self):
        """回车换行：跟着缩进走。{ / else / do / case / default → 进一级；} → 退一级"""
        tc = self.textCursor()
        block = tc.block()
        text = block.text()
        rel = tc.position() - block.position()
        before = text[:rel].rstrip()
        indent = re.match(r"^\s*", text).group(0)
        stripped = text.strip()
        unit = "\t" if "\t" in indent else "    "
        if before.endswith("{"):
            indent += unit
        elif before.endswith(":") or re.search(r"(?:else|do)\b\s*$", before):
            # case 1: / default: / else / do 单独一行（或 "} else" 同行）→ 进一级
            if not before.endswith(";"):
                indent += unit
        elif stripped.startswith("}"):
            # 退一级：按行首用的缩进单位（tab 或 4/2 空格）减
            if "\t" in indent:
                indent = indent[:-1]
            elif indent.endswith("    "):
                indent = indent[:-4]
            elif indent.endswith("  "):
                indent = indent[:-2]
            else:
                indent = ""
        elif not stripped:
            # 空行回车：继承上一个非空行的缩进
            prev = block.previous()
            while prev.isValid() and not prev.text().strip():
                prev = prev.previous()
            if prev.isValid():
                indent = re.match(r"^\s*", prev.text()).group(0)
        tc.insertBlock()
        tc.insertText(indent)
        self.setTextCursor(tc)

    def triggerCompletion(self):
        prefix = self.currentWord()
        if not prefix:
            if self.completer:
                self.completer.popup().hide()
            return
        candidates = build_completion_list(prefix)
        if not candidates:
            self.completer.popup().hide()
            return
        texts = [c[0] for c in candidates]
        descs = {c[0]: c[1] for c in candidates}
        kinds = {c[0]: c[3] for c in candidates}
        # 复用同一个 model，避免打字时反复重建（更快不卡）
        # 用 QStandardItemModel：支持自定义角色，中文说明/类型才能存进去
        if not hasattr(self, "_completionModel") or self._completionModel is None:
            self._completionModel = QStandardItemModel(self)
        else:
            self._completionModel.clear()
        for i, t in enumerate(texts):
            item = QStandardItem(t)
            item.setData(descs[t], Qt.UserRole)
            item.setData(prefix, Qt.UserRole + 1)
            item.setData(kinds[t], Qt.UserRole + 2)
            self._completionModel.appendRow(item)
        self.completer.setModel(self._completionModel)
        self.completer.setCompletionPrefix(prefix)
        cr = self.cursorRect()
        cr.setWidth(460)
        self.completer.complete(cr)

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(
            cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def lineNumberAreaWidth(self):
        digits = len(str(max(1, self.blockCount())))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def highlightCurrentLine(self):
        selections = []
        cur = QTextEdit.ExtraSelection()
        cur.format.setBackground(QColor("#2c313a"))
        cur.format.setProperty(QTextFormat.FullWidthSelection, True)
        cur.cursor = self.textCursor()
        cur.cursor.clearSelection()
        selections.append(cur)
        # 编译出错的行：红底
        for ln in getattr(self, "errorLines", []):
            block = self.document().findBlockByNumber(ln - 1)
            if block.isValid():
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(QColor("#4a2430"))
                sel.format.setProperty(QTextFormat.FullWidthSelection, True)
                sel.cursor = QTextCursor(block)
                sel.cursor.clearSelection()
                selections.append(sel)
        # 疑似漏分号的行：红色波浪下划线
        for ln in getattr(self, "semiLines", []):
            block = self.document().findBlockByNumber(ln - 1)
            if block.isValid():
                sel = QTextEdit.ExtraSelection()
                sel.format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
                sel.format.setUnderlineColor(QColor("#e06c75"))
                sel.format.setForeground(QColor("#e06c75"))
                sel.cursor = QTextCursor(block)
                sel.cursor.clearSelection()
                selections.append(sel)
        self.setExtraSelections(selections)

    def setErrorLines(self, lines):
        self.errorLines = list(lines)
        self.highlightCurrentLine()

    def setSemiLines(self, lines):
        self.semiLines = list(lines)
        self.highlightCurrentLine()

    def findMissingSemicolons(self):
        """扫描全文，找出‘可能漏了分号 ; ’的行（大白话启发式检查，不是编译器）"""
        lines = self.toPlainText().split("\n")
        bad = []
        for i, s in enumerate(lines):
            st = s.strip()
            if not st or st[0] in "#/*":
                continue
            code = st.split("//")[0].rstrip()
            if not code or code[-1] in "{;":
                continue
            if code[-1] in ",(=+-*<>|&":
                continue  # 这行没写完，下边还有内容
            if code[-1] == ")":
                nxt = ""
                for j in range(i + 1, len(lines)):
                    nxt = lines[j].strip()
                    if nxt:
                        break
                if nxt.startswith("{"):
                    continue  # 函数头 / if 括号后跟 {，不需要分号
                bad.append(i + 1)
                continue
            if code[-1] == "}":
                # 一行多语句：void loop(){ digitalWrite(8, HIGH) }
                # } 之前最近是 ")" 且是函数调用（不是 setup() { 这种头）→ 漏分号
                before_brace = code[:-1].rstrip()
                if re.search(r"[A-Za-z_]\w*\s*\([^()]*\)\s*$", before_brace):
                    bad.append(i + 1)
                continue
            if code[-1].isalnum() or code[-1] == "]":
                bad.append(i + 1)
        return bad

    def autoFixSemicolons(self):
        """自动补上漏掉的分号（和 findMissingSemicolons 同一套启发式）。
        返回 [(行号, 原行, 补好后), ...]；从下往上改，避免行号偏移。
        改完不弹窗、不打断，让编译/烧录正常继续。"""
        bad = self.findMissingSemicolons()
        if not bad:
            return []
        lines = self.toPlainText().split("\n")
        fixes = []
        tc = QTextCursor(self.document())
        tc.beginEditBlock()
        for ln in reversed(bad):
            i = ln - 1
            line = lines[i]
            idx = line.find("//")
            if idx >= 0:
                code_end = len(line[:idx].rstrip())   # 注释前还有空格：分号加在代码末尾、空格之前
            else:
                code_end = len(line.rstrip())
            before = line[:code_end].rstrip()
            block = self.document().findBlockByNumber(i)
            c = QTextCursor(block)
            c.setPosition(block.position() + code_end)
            c.insertText(";")
            fixes.append((ln, before, (line[:code_end].rstrip() + ";" + line[code_end:]).rstrip()))
        tc.endEditBlock()
        fixes.sort(key=lambda f: f[0])
        return fixes

    def setMainActions(self, compile_cb, burn_cb):
        """给编辑器挂上主窗口的「编译」「烧录」动作，右键菜单里用"""
        self._compileCb = compile_cb
        self._burnCb = burn_cb

    def contextMenuEvent(self, e):
        """中文右键菜单：剪切/复制/粘贴 + 编译 + 烧录（不用英文的默认菜单）"""
        menu = QMenu(self)
        act_cut = menu.addAction("剪切")
        act_copy = menu.addAction("复制")
        act_paste = menu.addAction("粘贴")
        act_cut.setEnabled(self.textCursor().hasSelection())
        act_copy.setEnabled(self.textCursor().hasSelection())
        menu.addSeparator()
        act_compile = menu.addAction("编译（只检查，不用接板子）")
        act_burn = menu.addAction("烧录到板子")
        act = menu.exec(e.globalPos())
        if act is None:
            return
        if act == act_cut:
            self.cut()
        elif act == act_copy:
            self.copy()
        elif act == act_paste:
            self.paste()
        elif act == act_compile:
            cb = getattr(self, "_compileCb", None)
            if cb:
                cb()
        elif act == act_burn:
            cb = getattr(self, "_burnCb", None)
            if cb:
                cb()

# ==================== 灵动流光进度条 ====================
class FlowBar(QWidget):
    """编译/烧录时的动画进度条：薄荷绿光带循环流动，完成后变全绿/全红"""
    def __init__(self):
        super().__init__()
        self.busy = False
        self.ok = None
        self.phase = 0
        self.setFixedHeight(8)
        self.setVisible(False)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._tick)

    def _tick(self):
        self.phase += 1
        self.update()

    def startBusy(self):
        self.busy = True
        self.ok = None
        self.phase = 0
        self.timer.start()
        self.setVisible(True)

    def finish(self, ok):
        self.busy = False
        self.ok = ok
        self.timer.stop()
        self.setVisible(True)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2c313a"))
        p.drawRoundedRect(r, 3, 3)
        if self.busy:
            w = self.width()
            bar = max(90, w // 3)
            total = w + bar
            x = (self.phase % total) - bar
            grad = QLinearGradient(x, 0, x + bar, 0)
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            grad.setColorAt(0.5, QColor(74, 222, 128))
            grad.setColorAt(0.65, QColor(34, 211, 238))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(x, 1, bar, self.height() - 2), 2.5, 2.5)
        elif self.ok is True:
            p.setBrush(QColor("#4ade80"))
            p.drawRoundedRect(r, 3, 3)
        elif self.ok is False:
            p.setBrush(QColor("#e06c75"))
            p.drawRoundedRect(r, 3, 3)

# ==================== 窗口打开动画 ====================
def animate_window_open(widget, duration=180):
    """打开窗口时的淡入动画：透明度 0→1，不卡界面"""
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.start(QPropertyAnimation.DeleteWhenStopped)


# ==================== 示例中心对话框 ====================
class ExampleDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("示例中心")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        tip = QLabel("点一个示例，代码会直接进编辑器（接线说明在代码注释里）")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.searchEdit = QLineEdit()
        self.searchEdit.setPlaceholderText("搜示例：比如「灯」「串口」「PWM」")
        self.searchEdit.textChanged.connect(self.applyFilter)
        lay.addWidget(self.searchEdit)
        self.list = QListWidget(self)
        self.items = []
        if os.path.isdir(EXAMPLES_DIR):
            for d in sorted(os.listdir(EXAMPLES_DIR)):
                code = os.path.join(EXAMPLES_DIR, d, "main.cpp")
                if os.path.isfile(code):
                    with open(code, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                    first = text.splitlines()[0].strip(" /=-") if text.strip() else ""
                    item = QListWidgetItem(f"{d}   ——  {first}")
                    self.items.append((item, code, d, first))
                    self.list.addItem(item)
        lay.addWidget(self.list)
        self.list.itemDoubleClicked.connect(self.accept)

    def applyFilter(self, kw):
        """按名字/注释关键字过滤示例列表"""
        kw = self.searchEdit.text().strip().lower()
        for item, code, d, first in self.items:
            hit = (not kw) or kw in d.lower() or kw in first.lower()
            item.setHidden(not hit)

    def showEvent(self, e):
        super().showEvent(e)
        animate_window_open(self)

    def selectedCode(self):
        """返回 (示例名, 代码)：示例名直接当保存时的默认文件名。
        关键：用 currentItem() 反查全量列表——搜索过滤后 currentRow()
        返回的是“可见行号”，跟 self.items 的原始索引会错位，绝不能再用行号取值。"""
        item = self.list.currentItem()
        if item is None:
            return "", ""
        for it, code, d, first in self.items:
            if it is item:
                with open(code, "r", encoding="utf-8", errors="ignore") as f:
                    return d, f.read()
        return "", ""

# ==================== 主窗口 ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NanoCode —— 新手 C++ 实战 IDE")
        self.resize(1200, 780)
        self.currentFile = None
        self.projectDir = DEFAULT_PROJECT
        self.process = None
        self.errorLines = []
        self.serial = QSerialPort(self)
        self.serial.readyRead.connect(self.onSerialData)

        # 自动保存：每 30 秒静默存一次所有已命名的文件（没起名的文件不自动命名）
        self._autosaveTimer = QTimer(self)
        self._autosaveTimer.setInterval(30000)
        self._autosaveTimer.timeout.connect(self.autosave)
        self._autosaveTimer.start()

        # ---- 编辑器区：多文件标签（像小熊猫/PyCharm 一样来回切） ----
        # 启动时不开任何标签：啥也没有，点「新建」才建文件
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.closeTab)
        self.tabs.currentChanged.connect(self.onTabChanged)
        self.tabs.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self.onTabMenu)

        # ---- 输出面板 ----
        self.output = QTextBrowser()
        self.output.setReadOnly(True)
        self.output.setOpenLinks(False)
        self.output.anchorClicked.connect(self.onOutputAnchor)
        self.output.setLineWrapMode(QTextEdit.WidgetWidth)
        self.output.setFont(QFont("Consolas", 10))
        self.output.setStyleSheet(
            "QTextBrowser{background:#1e2227;color:#d4d4d4;border:none;}")

        # 编译/烧录进度条（灵动流光动画）
        self.progressBar = FlowBar()
        self.progressLabel = QLabel("")
        self.progressLabel.setStyleSheet("color:#9aa0aa; font-size:12px; padding:0 6px;")
        outWrap = QWidget()
        ol = QVBoxLayout(outWrap)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(2)
        ol.addWidget(self.progressLabel)
        ol.addWidget(self.progressBar)
        ol.addWidget(self.output)
        # 串口发送行：打开串口后可以给板子发指令（回车或点按钮）
        sendRow = QWidget()
        sr = QHBoxLayout(sendRow)
        sr.setContentsMargins(8, 2, 8, 4)
        sr.setSpacing(6)
        self.sendEdit = QLineEdit()
        self.sendEdit.setPlaceholderText("给板子发指令（回车发送；末尾自动加换行）")
        self.sendEdit.setEnabled(False)
        self.sendEdit.returnPressed.connect(self.sendSerial)
        self.sendNlCheck = QCheckBox("自动加换行")
        self.sendNlCheck.setChecked(True)
        self.sendNlCheck.setToolTip("发送时末尾自动加换行（板子一般按行读取）")
        sendBtn = QPushButton("发送")
        sendBtn.clicked.connect(self.sendSerial)
        sr.addWidget(self.sendEdit, 1)
        sr.addWidget(self.sendNlCheck)
        sr.addWidget(sendBtn)
        ol.addWidget(sendRow)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.tabs)
        splitter.addWidget(outWrap)
        splitter.setSizes([540, 200])
        splitter.setHandleWidth(9)
        splitter.setChildrenCollapsible(False)

        # ---- 快捷栏（项目 + 串口：放在编辑器上方，下拉列表往应用内延伸）----
        quick = QWidget()
        ql = QHBoxLayout(quick)
        ql.setContentsMargins(10, 8, 10, 4)
        ql.setSpacing(8)
        ql.addWidget(QLabel("项目:"))
        self.projectEdit = QLineEdit(self.projectDir)
        self.projectEdit.setMinimumWidth(240)
        ql.addWidget(self.projectEdit)
        btnDir = QPushButton("浏览")
        btnDir.clicked.connect(self.pickProjectDir)
        ql.addWidget(btnDir)
        ql.addSpacing(8)
        ql.addWidget(QLabel("COM口:"))
        self.comCombo = QComboBox()
        self.comCombo.setMinimumWidth(130)
        ql.addWidget(self.comCombo)
        btnRefresh = QPushButton("刷新")
        btnRefresh.clicked.connect(self.refreshPorts)
        ql.addWidget(btnRefresh)
        ql.addWidget(QLabel("波特率:"))
        self.baudCombo = QComboBox()
        self.baudCombo.addItems(["115200", "9600", "57600", "74880", "230400"])
        self.baudCombo.setCurrentText("115200")
        ql.addWidget(self.baudCombo)
        self.serialBtn = QPushButton("打开串口")
        self.serialBtn.clicked.connect(self.toggleSerial)
        ql.addWidget(self.serialBtn)
        btnClear = QPushButton("清空")
        btnClear.clicked.connect(self.output.clear)
        ql.addWidget(btnClear)
        ql.addStretch(1)

        # ---- 底部状态栏 ----
        status = QWidget()
        sl = QHBoxLayout(status)
        sl.setContentsMargins(14, 4, 14, 8)
        self.statusLabel = QLabel("就绪：先点「示例」选个例子，再点「烧录」")
        sl.addWidget(self.statusLabel)
        sl.addStretch(1)

        central = QWidget()
        vv = QVBoxLayout(central)
        vv.setContentsMargins(0, 0, 0, 0)
        vv.setSpacing(0)
        vv.addWidget(quick)
        vv.addWidget(splitter, 1)
        vv.addWidget(status)
        self.setCentralWidget(central)

        # ---- 工具栏 ----
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        tb.setIconSize(QSize(24, 24))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(tb)
        self._add(tb, "示例", "内置实战示例", self.showExamples)
        tb.addSeparator()
        self._add(tb, "新建", "新建文件", self.newFile)
        self._add(tb, "打开", "打开文件", self.openFile)
        self._add(tb, "保存", "保存文件", self.saveFile, "Ctrl+S")
        tb.addSeparator()
        self._add(tb, "编译", "编译检查（不用接板子）", self.build)
        self._add(tb, "烧录", "编译并烧录到板子", self.upload)
        self._add(tb, "停止", "停止正在进行的编译/烧录", self.stopProc)
        self._add(tb, "串口", "打开/关闭串口监视", self.toggleSerial)

        self.refreshPorts()

    @property
    def editor(self):
        """当前标签页的编辑器（老代码都用 self.editor，保持兼容）"""
        return self.tabs.currentWidget()

    def _newEditorTab(self, title, path=None):
        """开一个新标签页，里面放一个独立编辑器（每个文件各占一个）"""
        ed = CodeEditor()
        ed.errorLines = []
        ed.semiLines = []
        ed.filePath = path
        ed.textChanged.connect(self.onEditorTextChanged)
        ed.setMainActions(self.build, self.upload)
        font = QFont("Consolas", 13)
        font.setStyleHint(QFont.Monospace)
        ed.setFont(font)
        ed.setStyleSheet(
            "QPlainTextEdit{background:#282c34;color:#abb2bf;border:none;}")
        CppHighlighter(ed.document())
        self.tabs.addTab(ed, title)
        self.tabs.setCurrentWidget(ed)
        return ed

    def onTabMenu(self, pos):
        """对标签页标题点右键：重命名 / 编译 / 烧录 / 关闭（全中文）"""
        tab = self.tabs.tabBar().tabAt(pos)
        if tab < 0:
            return
        self.tabs.setCurrentIndex(tab)
        menu = QMenu(self)
        act_rename = menu.addAction("重命名文件…")
        menu.addSeparator()
        act_compile = menu.addAction("编译（只检查，不用接板子）")
        act_burn = menu.addAction("烧录到板子")
        act_close = menu.addAction("关闭")
        act = menu.exec(self.tabs.tabBar().mapToGlobal(pos))
        if act is None:
            return
        if act == act_rename:
            self.renameTab(tab)
        elif act == act_compile:
            self.build()
        elif act == act_burn:
            self.upload()
        elif act == act_close:
            self.closeTab(tab)

    def _cleanNameForFile(self, s):
        """把标签名/用户输入变成合法文件名：
        清掉“示例：”前缀、中文括号里的说明文字、Windows 非法字符"""
        s = s.replace("示例：", "").replace("示例", "")
        s = re.sub(r"（[^（）]*）", "", s)
        for ch in '\\/:*?"<>|':
            s = s.replace(ch, "_")
        return s.strip()

    def renameTab(self, idx):
        """重命名：给文件起新名字（自动 .cpp），磁盘文件、标签、绑定一起改"""
        ed = self.tabs.widget(idx)
        if ed is None:
            return
        old_path = getattr(ed, "filePath", None)
        old_name = self.tabs.tabText(idx)
        default = os.path.basename(old_path) if old_path else old_name
        default = self._cleanNameForFile(default)
        if default.lower().endswith(".cpp"):
            default = default[:-4]
        name, ok = QInputDialog.getText(
            self, "重命名",
            f"把「{old_name}」改成什么名字？（不用打 .cpp，自动给你加上）",
            text=default)
        if not ok or not name.strip():
            return
        name = name.strip()
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        if not name.lower().endswith(".cpp"):
            name += ".cpp"
        if old_path and os.path.isfile(old_path):
            new_path = os.path.join(os.path.dirname(old_path), name)
            if os.path.abspath(new_path) != os.path.abspath(old_path):
                if os.path.isfile(new_path):
                    QMessageBox.warning(self, "重命名", f"{name} 已存在，换个名字吧。")
                    return
                try:
                    os.rename(old_path, new_path)
                except OSError as err:
                    QMessageBox.warning(self, "重命名", f"改名失败：{err}")
                    return
                ed.filePath = new_path
        self.tabs.setTabText(idx, name)
        self.currentFile = getattr(ed, "filePath", None)
        self.statusLabel.setText("已重命名为 " + name)

    def onTabChanged(self, idx):
        ed = self.tabs.widget(idx)
        if ed is None:
            return
        # 切标签时，把所有已命名且有改动的文件静默存一遍（不弹窗、不动标签名）
        self.autosave()
        self.currentFile = getattr(ed, "filePath", None)
        # 窗口还没搭完时（状态栏未创建）不刷状态，避免启动报错
        if not hasattr(self, "statusLabel"):
            return
        if self.currentFile:
            self.statusLabel.setText(os.path.basename(self.currentFile))
        else:
            self.statusLabel.setText(self.tabs.tabText(idx) + "（还没存盘，点保存会先起名）")

    def autosave(self):
        """静默自动保存：只存「已命名且内容有改动」的标签。
        不弹窗、不自动起名、不改标签名——未命名的新手文件等他自己点保存。
        对「还没命名但有内容」的标签：只在状态栏提个醒，绝不擅自起名。"""
        unnamed = 0
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if w is None:
                continue
            p = getattr(w, "filePath", None)
            if not p or not os.path.isfile(p):
                if w.toPlainText().strip():
                    unnamed += 1
                continue
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    if f.read() != w.toPlainText():
                        with open(p, "w", encoding="utf-8") as f2:
                            f2.write(w.toPlainText())
            except OSError:
                pass
        if unnamed and hasattr(self, "statusLabel"):
            self.statusLabel.setText(
                f"⚠ 有 {unnamed} 个文件还没保存（点「保存」起个名字，防止丢内容）")

    def closeTab(self, idx):
        ed = self.tabs.widget(idx)
        if ed is None:
            return
        p = getattr(ed, "filePath", None)
        dirty = False
        if p and os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                dirty = f.read() != ed.toPlainText()
        elif ed.toPlainText().strip():
            dirty = True   # 还没命名但有内容
        if dirty:
            r = QMessageBox.question(
                self, "内容没保存",
                f"「{self.tabs.tabText(idx)}」有改动没保存，要现在保存吗？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Save:
                # 关键：保存的是【被关闭的这个文件】，不是当前选中的那个！
                self.saveEditor(ed)
        i2 = self.tabs.indexOf(ed)
        if i2 >= 0:
            self.tabs.removeTab(i2)
            ed.deleteLater()

    def _add(self, tb, text, tip, slot, shortcut=None):
        act = QAction(text, self)
        act.setToolTip(tip)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(shortcut)
        tb.addAction(act)
        return act

    # ---------- 文件 ----------
    def newFile(self, name=None):
        """新建文件：先让用户输入名字（强制 .cpp 结尾），
        然后真的在 src 下创建这个文件。
        绝不删除任何已有文件——多个文件可以并存，编译时只编当前那个。"""
        if name is None:
            # 默认名 = 当前标签上显示的名字（去掉“示例：”），少打一次字
            # 先把窗口顶到最前面，免得弹窗被盖住看起来像“没反应”
            self.raise_()
            self.activateWindow()
            cur = self.tabs.tabText(self.tabs.currentIndex()) or ""
            default = self._cleanNameForFile(cur) or "main"
            name, ok = QInputDialog.getText(
                self, "新建文件",
                "给新文件起个名字（不用打 .cpp，自动给你加上）：",
                text=default)
            if not ok or not name.strip():
                self.statusLabel.setText("已取消新建")
                return
        name = self._cleanNameForFile(name)
        # 强制 .cpp 结尾：不管用户输什么，最后一定是 xxx.cpp
        if not name.lower().endswith(".cpp"):
            name += ".cpp"
        src_dir = os.path.join(self.projectDir, "src")
        os.makedirs(src_dir, exist_ok=True)
        target = os.path.join(src_dir, name)
        # 同名文件已存在：先问用户，绝不偷偷覆盖
        if os.path.isfile(target):
            r = QMessageBox.question(
                self, "文件已存在",
                f"{name} 已经存在，要覆盖吗？（会丢掉原来的内容）",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                self.statusLabel.setText("已取消新建（同名文件已存在）")
                return
        with open(target, "w", encoding="utf-8") as f:
            f.write(DEFAULT_TEMPLATE)
        ed = self._newEditorTab(name, target)
        ed.setPlainText(DEFAULT_TEMPLATE)
        self.currentFile = target
        msg = "新文件 " + name
        self.statusLabel.setText(msg)
        self.toast(msg)

    def openFile(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "打开文件", self.projectDir,
            "代码文件 (*.cpp *.h *.ino);;所有文件 (*)")
        if p:
            # 已经开着这个文件？直接切过去，不重复开
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if getattr(w, "filePath", None) == p:
                    self.tabs.setCurrentIndex(i)
                    self.statusLabel.setText(os.path.basename(p))
                    return
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            ed = self._newEditorTab(os.path.basename(p), p)
            ed.setPlainText(text)
            self.currentFile = p
            self.statusLabel.setText(os.path.basename(p))

    def saveFile(self):
        """保存：写到你当前这个文件（新建时定的名字）。
        还没命名的话，弹窗起名——默认名就是当前标签上显示的名字，
        直接回车就行，不用重新打字。"""
        if self.editor is None:
            self.newFile()
            return
        self.saveEditor(self.editor)

    def _defaultNameFromLabel(self, ed):
        """从标签名推导“默认文件名”：清掉“示例：”前缀和所有中文括号残留，
        再不行就回退 main。保证存出来的文件名不奇怪。"""
        cur = self.tabs.tabText(self.tabs.indexOf(ed)) or ""
        default = self._cleanNameForFile(cur)
        if not default:
            default = "main"
        return default

    def saveEditor(self, ed):
        """把【指定编辑器】的内容存到它自己的文件。
        传 ed 而不是只存当前页——关标签时存被关的那个，才不会存错文件。
        铁律：保存后标签名 = 磁盘文件名（永远同步）。
        返回 True=保存成功，False=用户取消了命名（没存上）。"""
        if ed is None:
            return False
        p = getattr(ed, "filePath", None)
        if not p:
            # 还没命名：从标签名推导默认名，只起名保存，
            # 绝不删除任何文件（覆盖同名文件前会先问）。
            default = self._defaultNameFromLabel(ed)
            name, ok = QInputDialog.getText(
                self, "保存文件",
                "给文件起个名字（不用打 .cpp，自动给你加上）：",
                text=default)
            if not ok or not name.strip():
                self.statusLabel.setText("已取消保存")
                return False
            name = self._cleanNameForFile(name)
            if not name.lower().endswith(".cpp"):
                name += ".cpp"
            src_dir = os.path.join(self.projectDir, "src")
            os.makedirs(src_dir, exist_ok=True)
            p = os.path.join(src_dir, name)
            if os.path.isfile(p):
                r = QMessageBox.question(
                    self, "文件已存在",
                    f"{name} 已经存在，要覆盖吗？（会丢掉原来的内容）",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if r != QMessageBox.Yes:
                    self.statusLabel.setText("已取消保存（同名文件已存在）")
                    return False
            ed.filePath = p
            self.tabs.setTabText(self.tabs.indexOf(ed), name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(ed.toPlainText())
        # 铁律：保存后，标签名永远 = 磁盘文件名（清掉任何残留后缀）
        self.tabs.setTabText(self.tabs.indexOf(ed), os.path.basename(p))
        if self.tabs.currentWidget() is ed:
            self.currentFile = p
        self.statusLabel.setText("已保存 " + p)
        return True

    def pickProjectDir(self):
        d = QFileDialog.getExistingDirectory(self, "选择 PlatformIO 项目文件夹", self.projectDir)
        if d:
            self.projectDir = d
            self.projectEdit.setText(d)

    def loadExampleByName(self, name):
        code = os.path.join(EXAMPLES_DIR, name, "main.cpp")
        if os.path.isfile(code):
            with open(code, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            ed = self.editor
            # 当前标签是空的“未命名”标签？直接用它，不额外开新页
            if ed is not None and not ed.toPlainText().strip() \
                    and not getattr(ed, "filePath", None):
                self.tabs.setTabText(self.tabs.indexOf(ed), f"示例：{name}")
            else:
                ed = self._newEditorTab(f"示例：{name}", None)
            ed.setPlainText(text)
            # 示例只是“代码素材”：不绑定文件名，保存时会让你重新起名，
            # 免得示例内容把你自己写的程序盖掉。
            self.currentFile = None
            self.statusLabel.setText(f"已载入示例：{name}（接线说明在注释里）")

    def showExamples(self):
        dlg = ExampleDialog(self)
        if dlg.exec():
            name, code = dlg.selectedCode()
            if code:
                # 和 loadExampleByName 走同一套逻辑：当前是空标签就复用，
                # 标签名显示“示例：xxx”，保存时默认文件名就是 xxx
                self.loadExampleByName(name)

    # ---------- 补全 ----------
    def onEditorTextChanged(self):
        # 谁改的代码就处理谁（多标签：不一定是当前显示的页）
        ed = self.sender()
        if ed is None or not isinstance(ed, CodeEditor):
            ed = self.editor
        # 代码一改，旧的报错/漏分号标记就失效，清掉
        if ed.errorLines:
            ed.errorLines = []
            ed.highlightCurrentLine()
        if ed.semiLines:
            ed.semiLines = []
            ed.highlightCurrentLine()
        tc = ed.textCursor()
        block = tc.block().text()
        rel = tc.position() - tc.block().position()
        if rel == 0:
            return
        last = block[rel - 1]
        if last.isalpha() or last == "_" or last == ".":
            ed.triggerCompletion()

    # ---------- 轻提示（淡入淡出，不弹窗不打断） ----------
    def toast(self, msg, color="#4ade80", ms=3200):
        """编辑器底部的小提示：自动淡入淡出，不挡操作、不用点任何按钮"""
        ed = self.editor
        if ed is None:      # 一个文件都没有时：退化成状态栏提示，不崩
            self.statusLabel.setText(msg)
            return
        if getattr(self, "_toast", None) is not None:
            self._toast.deleteLater()
            self._toast = None
        t = QLabel(ed.viewport())
        t.setWordWrap(True)
        t.setMaximumWidth(560)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(
            f"background:#1f252e;color:{color};border:1px solid #313747;"
            f"border-radius:12px;padding:10px 18px;font-size:13px;")
        t.setText(msg)
        t.adjustSize()
        vp = ed.viewport()
        x = max(8, (vp.width() - t.width()) // 2)
        y = max(8, vp.height() - t.height() - 26)
        t.move(x, y)
        t.show()
        self._toast = t
        eff = QGraphicsOpacityEffect(t)
        t.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        QTimer.singleShot(ms, lambda: self._fadeOutToast(t))

    def _fadeOutToast(self, t):
        if getattr(self, "_toast", None) is not t:
            return
        self._toast = None
        eff = QGraphicsOpacityEffect(t)
        t.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(300)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(t.deleteLater)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    # ---------- 编译 / 烧录 ----------
    def build(self):
        self.runPio(["run"], "编译")

    def upload(self):
        self.runPio(["run", "-t", "upload"], "烧录")

    def runPio(self, args, label):
        ed = self.editor
        if ed is None:
            QMessageBox.information(
                self, label,
                "现在还没有文件。先点「新建」建一个文件，或点「示例」选个例子。")
            return
        if not os.path.isfile(PIO_EXE):
            QMessageBox.warning(
                self, label,
                "没找到 pio 编译器（pio.exe）。\n\n"
                "1. 安装 PlatformIO（VS Code 里装 PlatformIO 插件即可）；\n"
                "2. 或把 D:\\platformio-core 拷到这台电脑；\n"
                "3. 或改 NanoCode.py 顶部的 PIO_EXE 路径。\n\n"
                "编辑器功能不受影响，可以继续写代码。")
            return
        ini = os.path.join(self.projectDir, "platformio.ini")
        if not os.path.isfile(ini):
            QMessageBox.warning(self, "项目不对",
                                f"没找到 platformio.ini：\n{self.projectDir}")
            return

        # 烧录/编译前：自动补漏掉的分号（不弹窗、不打断，照样继续）
        fixes = self.editor.autoFixSemicolons()
        self.editor.setSemiLines([])
        if fixes:
            txt = "\n".join(
                f"第{ln}行  {before} → {after}" for ln, before, after in fixes[:6])
            if len(fixes) > 6:
                txt += f"\n……还有 {len(fixes)-6} 处"
            self.output.append(
                f"<span style='color:#e5c07b'>✔ 已自动补上 {len(fixes)} 处分号 "
                f"（长记性：下次记得自己加 ; ）：</span><br>{txt}")
            self.statusLabel.setText(f"已自动补 {len(fixes)} 处分号，继续{label}")
            self.toast(f"帮你补了 {len(fixes)} 处分号 ; 下次记得自己加哦")

        # 编译/烧录前：确保当前文件已命名并保存（未命名就先起名保存，取消就中断）
        ed = self.editor
        target = getattr(ed, "filePath", None)
        if not target or not os.path.isfile(target):
            if not self.saveEditor(ed):
                self.statusLabel.setText(f"已取消{label}（文件还没存盘）")
                return
            target = ed.filePath
        src_dir = os.path.join(self.projectDir, "src")
        if os.path.dirname(os.path.abspath(target)) != os.path.abspath(src_dir):
            # 打开的是项目外的文件：先另存到项目 src 下再编译
            new_target = os.path.join(src_dir, os.path.basename(target))
            if os.path.isfile(new_target):
                r = QMessageBox.question(
                    self, "文件已存在",
                    f"项目里已有 {os.path.basename(target)}，"
                    "要覆盖成当前内容吗？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if r != QMessageBox.Yes:
                    self.statusLabel.setText(f"已取消{label}")
                    return
            with open(new_target, "w", encoding="utf-8") as f:
                f.write(ed.toPlainText())
            ed.filePath = new_target
            target = new_target
            # 标签名 = 磁盘文件名，保持同步
            self.tabs.setTabText(self.tabs.indexOf(ed), os.path.basename(target))
        # 保存当前编辑器内容到文件（防止编译的是磁盘上的旧代码）
        with open(target, "w", encoding="utf-8") as f:
            f.write(ed.toPlainText())
        self.currentFile = target
        self.output.append(
            f"<span style='color:#98c379'>✔ 已自动保存编辑器内容 → {target}</span>")

        # 只编译当前这一个文件：给 platformio.ini 加 src_filter，编完立刻恢复
        self._patch_ini_for_single_file(os.path.basename(target))

        # 首次编译这个项目：要先下载/准备依赖，提前打招呼，别让新手以为卡死
        if not os.path.isdir(os.path.join(self.projectDir, ".pio")):
            QMessageBox.information(
                self, "第一次编译",
                "这是第一次编译这个项目，要先准备编译工具和依赖，"
                "可能要几分钟。\n\n别关窗口、别拔线，等进度条走完就行。\n"
                "第二次开始就会快很多。")
            self.output.append(
                "<span style='color:#e5c07b'>ℹ 第一次编译要下依赖，耐心等几分钟，别关窗口</span>")

        env = os.environ.copy()
        env["PLATFORMIO_CORE_DIR"] = PLATFORMIO_CORE_DIR
        if GIT_CMD_DIR:
            env["PATH"] = env.get("PATH", "") + ";" + GIT_CMD_DIR
        # 国内镜像，避免 pio 装 Python 依赖时连 pypi.org 超时
        env["PIP_INDEX_URL"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
        env["UV_INDEX_URL"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
        env["UV_DEFAULT_INDEX"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
        self.output.append(f"<span style='color:#61afef'>== {label}：{self.projectDir} ==</span>")
        self.errorLines = []
        self.editor.setErrorLines([])
        self.progressLabel.setText(f"⏳ {label}中… 耐心等一下，第一次编译会久一点")
        self.progressBar.startBusy()
        self.statusLabel.setText(f"{label}中…")
        p = QProcess(self)
        p.setWorkingDirectory(self.projectDir)
        p.setEnvironment([f"{k}={v}" for k, v in env.items()])
        p.readyReadStandardOutput.connect(lambda: self.readProc(p.readAllStandardOutput()))
        p.readyReadStandardError.connect(lambda: self.readProc(p.readAllStandardError()))
        p.finished.connect(lambda code, st: self.onProcFinished(code, label))
        p.start(PIO_EXE, args)
        self.process = p
        self._stopped = False

    def stopProc(self):
        """停止正在进行的编译/烧录（点了没反应/卡住时用）"""
        if self.process and self.process.state() != QProcess.NotRunning:
            self._stopped = True
            self.process.kill()
            self.progressBar.finish(False)
            self._restore_ini()
            self.output.append("<span style='color:#e5c07b'>■ 正在停止…</span>")
            self.statusLabel.setText("正在停止…")

    def _patch_ini_for_single_file(self, fname):
        """在 platformio.ini 里把编译范围限定到当前文件（src_filter）。
        备份原 ini，编译结束后恢复，不破坏用户自己的配置。"""
        ini = os.path.join(self.projectDir, "platformio.ini")
        try:
            with open(ini, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return
        self._ini_backup = content
        line = f"src_filter = +<{fname}>"
        if re.search(r"^\s*src_filter\s*=", content, re.M):
            new = re.sub(r"(?m)^\s*src_filter\s*=.*$", line, content)
        else:
            m = re.search(r"\[[^\]]*\]", content)
            if not m:
                new = content.rstrip() + "\n" + line + "\n"
            else:
                # 在第一个环境区块的末尾插入
                nxt = re.search(r"\n\s*\[", content[m.end():])
                ins = m.end() + nxt.start() if nxt else len(content)
                new = content[:ins].rstrip() + "\n" + line + "\n" + content[ins:].lstrip()
        with open(ini, "w", encoding="utf-8") as f:
            f.write(new)

    def _restore_ini(self):
        """编译/烧录结束后恢复 platformio.ini 原样"""
        backup = getattr(self, "_ini_backup", None)
        if not backup:
            return
        ini = os.path.join(self.projectDir, "platformio.ini")
        try:
            with open(ini, "w", encoding="utf-8") as f:
                f.write(backup)
        except OSError:
            pass
        self._ini_backup = None

    def readProc(self, data):
        try:
            text = bytes(data).decode("utf-8", errors="replace")
        except Exception:
            text = str(data)
        for line in text.splitlines():
            m = ERR_RE.search(line)
            if m:
                fname, ln, col, kind, msg = m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(5).strip()
                if kind == "error" or kind == "fatal error":
                    self.errorLines.append(ln)
                    self.output.append(
                        f"<a style='color:#e06c75;text-decoration:none' href='{ln}'>"
                        f"✘ 第 {ln} 行：{msg}</a>")
                else:
                    self.output.append(
                        f"<span style='color:#d19a66'>⚠ 第 {ln} 行（警告）：{msg}</span>")
            elif "error" in line.lower():
                self.output.append(f"<span style='color:#e06c75'>{line}</span>")
            else:
                self.output.append(line)
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def onProcFinished(self, code, label):
        self.progressBar.finish(code == 0)
        self._restore_ini()
        if code == 0:
            self.output.append(f"<span style='color:#98c379'>✔ {label}完成！</span>")
            self.statusLabel.setText(f"{label}完成 ✔")
            self.progressLabel.setText(f"✔ {label}完成")
            if label == "烧录":
                # 烧录完可能重新枚举出 COM 口，刷新一下，顺便提示下一步
                self.refreshPorts()
                self.statusLabel.setText("烧录完成 ✔ 想看板子输出？点上方「打开串口」")
        else:
            if getattr(self, "_stopped", False):
                self._stopped = False
                self.output.append("<span style='color:#e5c07b'>■ 已停止</span>")
                self.statusLabel.setText("已停止")
                self.progressLabel.setText("已停止")
                return
            self.output.append(f"<span style='color:#e06c75'>✘ {label}出错（代码 {code}）</span>")
            if self.errorLines:
                first = self.errorLines[0]
                self.editor.setErrorLines(self.errorLines)
                self.jumpToLine(first)
                self.statusLabel.setText(f"{label}失败 ✘ 第 {first} 行有错（点输出里的红字可跳转）")
                self.progressLabel.setText(f"✘ 第 {first} 行有错，光标已跳过去")
                self.output.append(
                    "<span style='color:#e5c07b'>💡 编译错多半是：忘了加分号 ; 、"
                    "括号没配对、单词拼错。点上面红字直接跳到出错行。</span>")
            else:
                self.statusLabel.setText(f"{label}失败 ✘ 看上面红字")
                self.progressLabel.setText(f"✘ {label}失败")
                if label == "烧录":
                    self.output.append(
                        "<span style='color:#e5c07b'>💡 烧录连不上常见原因："
                        "① USB 线没插好或只能充电不能传数据；② COM 口没选对；"
                        "③ 板子驱动没装；④ 板子被其他程序占用。</span>")

    def jumpToLine(self, ln):
        block = self.editor.document().findBlockByNumber(ln - 1)
        if block.isValid():
            tc = QTextCursor(block)
            self.editor.setTextCursor(tc)
            self.editor.centerCursor()

    def onOutputAnchor(self, url):
        try:
            ln = int(url.toString())
        except Exception:
            return
        self.jumpToLine(ln)

    # ---------- 串口 ----------
    def refreshPorts(self):
        self.comCombo.clear()
        ports = QSerialPortInfo.availablePorts()
        for info in ports:
            name = info.portName()
            desc = info.description() or ""
            vid = info.vendorIdentifier()
            pid = info.productIdentifier()
            # 过滤蓝牙虚拟串口（BTHENUM）——打开它会卡死程序
            if "bth" in (info.systemLocation() or "").lower():
                continue
            if "蓝牙" in desc or "Bluetooth" in desc:
                continue
            tag = f"{name}  {desc}"
            self.comCombo.addItem(tag, name)
        if self.comCombo.count() == 0:
            self.comCombo.addItem("（未检测到 USB 串口，插好板子点「刷新」）", "")
        self.comCombo.setMaxVisibleItems(6)

    def toggleSerial(self):
        if self.serial.isOpen():
            self.serial.close()
            self.serialBtn.setText("打开串口")
            self.serialBtn.setStyleSheet("")
            self.sendEdit.setEnabled(False)
            self.statusLabel.setText("串口已关闭")
            return
        name = self.comCombo.currentData()
        if not name:
            QMessageBox.information(self, "串口", "没检测到串口。先插上板子，点「刷新」。")
            return
        self.serial.setPortName(name)
        self.serial.setBaudRate(int(self.baudCombo.currentText()))
        try:
            ok = self.serial.open(QSerialPort.ReadWrite)
        except Exception as e:
            ok = False
        if ok:
            self.serialBtn.setText("关闭串口")
            self.serialBtn.setStyleSheet(
                "QPushButton{background:#1f6e43;border:1px solid #4ade80;"
                "border-radius:10px;padding:7px 14px;font-size:13px;color:#ffffff;}")
            self.sendEdit.setEnabled(True)
            self.sendEdit.setFocus()
            self.statusLabel.setText(f"串口 {name} 已打开（波特率 {self.baudCombo.currentText()}）")
        else:
            err = self.serial.errorString()
            QMessageBox.warning(self, "串口", f"打不开 {name}：{err}\n可能被其他程序占用，或不是 USB 串口。")

    def sendSerial(self):
        """把发送框里的指令写给板子（打开串口后才能发）"""
        if not self.serial.isOpen():
            self.statusLabel.setText("串口没开，先点「打开串口」")
            self.toast("先点「打开串口」才能发指令哦", "#e5c07b")
            return
        text = self.sendEdit.text()
        if not text.strip():
            return
        if self.sendNlCheck.isChecked() and not text.endswith("\n"):
            text += "\n"
        self.serial.write(text.encode("utf-8"))
        shown = text.replace("\n", "↵")
        self.output.append(f"<span style='color:#61afef'>→ 发送: {shown}</span>")
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())
        self.sendEdit.clear()

    def onSerialData(self):
        data = bytes(self.serial.readAll()).decode("utf-8", errors="replace")
        self.output.append(f"<span style='color:#c678dd'>[串口] {data}</span>")
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, e):
        # 检查所有标签：有改动没保存的先问一下，别让新手白写半天
        dirty = []
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if w is None:
                continue
            p = getattr(w, "filePath", None)
            if p and os.path.isfile(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    if f.read() != w.toPlainText():
                        dirty.append((w, self.tabs.tabText(i)))
            elif w.toPlainText().strip():
                dirty.append((w, self.tabs.tabText(i)))
        if dirty:
            names = "、".join(n for _, n in dirty[:3])
            if len(dirty) > 3:
                names += f" 等 {len(dirty)} 个文件"
            r = QMessageBox.question(
                self, "有内容没保存",
                f"「{names}」有改动没保存，直接退出会丢掉哦。\n"
                "要现在保存吗？（选否=不保存直接退出）",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save)
            if r == QMessageBox.Cancel:
                e.ignore()
                return
            if r == QMessageBox.Save:
                # 逐个保存；中途取消命名的话就不关窗口，免得丢内容
                for w, _ in dirty:
                    if not self.saveEditor(w):
                        self.statusLabel.setText("有文件没保存，退出已取消")
                        e.ignore()
                        return
        if self.serial.isOpen():
            self.serial.close()
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
        super().closeEvent(e)


def main():
    detect_paths()
    scan_arduino_headers()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow { background: #16181d; }
        QToolBar { background: transparent; border: none; spacing: 8px;
                   padding: 12px 10px 6px 10px; }
        QToolBar::separator { background: #313747; width: 1px; margin: 4px 6px; }
        QToolButton { font-size: 13px; padding: 8px 16px; border-radius: 10px;
                      background: #23262e; color: #d4d4d4;
                      border: 1px solid #313747; }
        QToolButton:hover { background: #2e323c; border-color: #4ade80; }
        QToolButton:pressed { background: #1a1d23; border-color: #4ade80;
                              padding-top: 10px; padding-bottom: 6px; }
        QPushButton { background: #23262e; border: 1px solid #313747;
                      border-radius: 10px; padding: 7px 14px;
                      font-size: 13px; color: #d4d4d4; }
        QPushButton:hover { background: #2e323c; border-color: #4ade80; }
        QPushButton:pressed { background: #1a1d23; border-color: #4ade80;
                              padding-top: 9px; padding-bottom: 5px; }
        QPushButton:default { background: #1f6e43; border-color: #4ade80;
                              color: #ffffff; }
        QLineEdit, QComboBox { background: #1e2128; border: 1px solid #313747;
                               border-radius: 8px; padding: 6px 10px;
                               font-size: 13px; color: #d4d4d4; }
        QLineEdit:focus, QComboBox:focus { border-color: #4ade80; }
        QComboBox::drop-down { border: none; width: 24px; }
        QComboBox::down-arrow { image: none; border-left: 5px solid transparent;
                                border-right: 5px solid transparent;
                                border-top: 6px solid #9aa0aa; margin-right: 6px; }
        QComboBox QAbstractItemView { background: #1e2128; color: #d4d4d4;
                                      border: 1px solid #313747; border-radius: 8px;
                                      selection-background-color: #274a38;
                                      padding: 4px; outline: none; }
        QListWidget { background: #1e2128; border: 1px solid #313747;
                      border-radius: 10px; font-size: 13px; outline: none; }
        QListWidget::item { padding: 8px 10px; border-radius: 6px; }
        QListWidget::item:hover { background: #2e323c; }
        QListWidget::item:selected { background: #274a38; }
        QPlainTextEdit, QTextBrowser { border-radius: 12px; }
        QSplitter::handle { background: #16181d; height: 10px; }
        QSplitter::handle:hover { background: #2e323c; }
        QDialog, QMessageBox { background: #1e2128; }
        QLabel { font-size: 13px; color: #9aa0aa; }
        QScrollBar:vertical { background: transparent; width: 10px; }
        QScrollBar::handle:vertical { background: #3a3f4b; border-radius: 5px;
                                      min-height: 24px; }
        QScrollBar::handle:vertical:hover { background: #4b5263; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
    """)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "icons", "ctps.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    win = MainWindow()
    win.show()
    animate_window_open(win.centralWidget(), 320)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

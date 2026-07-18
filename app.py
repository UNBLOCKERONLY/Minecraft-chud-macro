#!/usr/bin/env python3
"""mac-macro — toggleable F-key macro: 2 → click → q → click.

Uses Quartz CGEvent APIs directly (pynput crashes on macOS 26+ due to
TSM calls from background threads).
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

import Quartz
from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtGui import QFont, QColor, QPainter, QLinearGradient, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)


STEP_DELAY = 0.05
DEBOUNCE_SEC = 0.15

# ANSI virtual keycodes
KEY_2 = 19
KEY_Q = 12
KEY_F = 3


def press_key(keycode: int) -> None:
    for is_down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(None, keycode, is_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def left_click() -> None:
    loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    for ev_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        ev = Quartz.CGEventCreateMouseEvent(
            None, ev_type, loc, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


class HotkeyListener:
    """Global F-key listener using a Quartz event tap on its own run loop."""

    def __init__(self, on_hotkey) -> None:
        self._on_hotkey = on_hotkey
        self._thread: Optional[threading.Thread] = None
        self._loop = None
        self.failed = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop is not None:
            Quartz.CFRunLoopStop(self._loop)
            self._loop = None
        self._thread = None

    def _run(self) -> None:
        def callback(_proxy, ev_type, event, _refcon):
            if ev_type == Quartz.kCGEventKeyDown:
                keycode = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode
                )
                is_repeat = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventAutorepeat
                )
                if keycode == KEY_F and not is_repeat:
                    self._on_hotkey()
            return event

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            callback,
            None,
        )
        if tap is None:
            # No Accessibility / Input Monitoring permission
            self.failed = True
            return

        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(
            self._loop, source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(tap, True)
        Quartz.CFRunLoopRun()


class ToggleSwitch(QWidget):
    """Compact iOS-style toggle."""

    toggled = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(58, 32)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool) -> None:
        if self._checked != value:
            self._checked = value
            self.update()
            self.toggled.emit(self._checked)

    def mousePressEvent(self, event) -> None:
        self.setChecked(not self._checked)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QColor("#22c55e") if self._checked else QColor("#334155")
        p.setBrush(QBrush(track))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 16, 16)

        knob_x = self.width() - 28 if self._checked else 4
        p.setBrush(QBrush(QColor("#f8fafc")))
        p.drawEllipse(knob_x, 4, 24, 24)
        p.end()


class GradientBackground(QWidget):
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0.0, QColor("#0b1020"))
        grad.setColorAt(0.55, QColor("#111827"))
        grad.setColorAt(1.0, QColor("#0f172a"))
        p.fillRect(self.rect(), QBrush(grad))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(56, 189, 248, 28))
        p.drawEllipse(-40, -30, 220, 180)
        p.setBrush(QColor(167, 139, 250, 22))
        p.drawEllipse(self.width() - 180, self.height() - 200, 240, 220)
        p.end()


class Chip(QFrame):
    def __init__(self, text: str, accent: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(74, 54)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: #0f141c;
                border: 1px solid {accent};
                border-radius: 12px;
            }}
            QLabel {{
                color: {accent};
                background: transparent;
                border: none;
                font-weight: 700;
                font-size: 13px;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)


class Bus(QObject):
    status = Signal(str, str)  # text, color


class MacroWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("mac-macro")
        self.setFixedSize(440, 540)

        self.enabled = False
        self.running = False
        self._listener: Optional[HotkeyListener] = None
        self._last_trigger = 0.0
        self.bus = Bus()
        self.bus.status.connect(self._set_pill)

        root = GradientBackground()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 28, 28, 24)
        outer.setSpacing(14)

        badge = QLabel("  MACRO  ")
        badge.setStyleSheet(
            """
            QLabel {
                color: #7dd3fc;
                background-color: #0c4a6e;
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )
        badge.setFixedWidth(78)
        outer.addWidget(badge, alignment=Qt.AlignLeft)

        title = QLabel("Key Click Combo")
        title.setFont(QFont(".AppleSystemUIFont", 28, QFont.Bold))
        title.setStyleSheet("color: #f8fafc; background: transparent;")
        outer.addWidget(title)

        subtitle = QLabel("Press  F  to fire when the switch is on")
        subtitle.setStyleSheet(
            "color: #94a3b8; background: transparent; font-size: 13px;"
        )
        outer.addWidget(subtitle)

        card = QFrame()
        card.setStyleSheet(
            """
            QFrame#card {
                background-color: rgba(22, 27, 34, 220);
                border: 1px solid #243044;
                border-radius: 18px;
            }
            """
        )
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 20)
        card_layout.setSpacing(16)

        seq_label = QLabel("SEQUENCE")
        seq_label.setStyleSheet(
            "color: #64748b; background: transparent; font-size: 11px; font-weight: 700;"
        )
        card_layout.addWidget(seq_label)

        steps = QHBoxLayout()
        steps.setSpacing(4)
        for i, (text, color) in enumerate(
            [("2", "#38bdf8"), ("CLICK", "#a78bfa"), ("Q", "#34d399"), ("CLICK", "#a78bfa")]
        ):
            steps.addWidget(Chip(text, color))
            if i < 3:
                arrow = QLabel("→")
                arrow.setStyleSheet(
                    "color: #475569; background: transparent; font-size: 16px;"
                )
                arrow.setAlignment(Qt.AlignCenter)
                steps.addWidget(arrow)
        card_layout.addLayout(steps)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #243044; border: none;")
        card_layout.addWidget(divider)

        toggle_row = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(2)
        self.status_title = QLabel("Macro Off")
        self.status_title.setStyleSheet(
            "color: #f1f5f9; background: transparent; font-size: 18px; font-weight: 700;"
        )
        self.status_detail = QLabel("Flip the switch, then press F")
        self.status_detail.setStyleSheet(
            "color: #64748b; background: transparent; font-size: 12px;"
        )
        left.addWidget(self.status_title)
        left.addWidget(self.status_detail)
        toggle_row.addLayout(left, stretch=1)

        self.switch = ToggleSwitch()
        self.switch.toggled.connect(self._on_toggle)
        toggle_row.addWidget(self.switch, alignment=Qt.AlignVCenter)
        card_layout.addLayout(toggle_row)

        self.pill = QLabel("●  Idle")
        self.pill.setAlignment(Qt.AlignCenter)
        self.pill.setFixedHeight(38)
        self.pill.setStyleSheet(
            """
            QLabel {
                color: #94a3b8;
                background-color: #0f141c;
                border-radius: 10px;
                font-size: 12px;
                font-weight: 700;
            }
            """
        )
        card_layout.addWidget(self.pill)

        tip = QLabel(
            "Needs macOS Accessibility permission for\n"
            "keyboard & mouse control (System Settings)."
        )
        tip.setStyleSheet("color: #475569; background: transparent; font-size: 11px;")
        card_layout.addWidget(tip)

        outer.addWidget(card, stretch=1)

        footer = QLabel("Hotkey  ·  F")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #475569; background: transparent; font-size: 12px;")
        outer.addWidget(footer)

    @Slot(str, str)
    def _set_pill(self, text: str, color: str) -> None:
        self.pill.setText(text)
        self.pill.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                background-color: #0f141c;
                border-radius: 10px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )

    def _on_toggle(self, checked: bool) -> None:
        self.enabled = checked
        if checked:
            self.status_title.setText("Macro On")
            self.status_title.setStyleSheet(
                "color: #86efac; background: transparent; font-size: 18px; font-weight: 700;"
            )
            self.status_detail.setText("Listening for F…")
            self._set_pill("●  Armed — press F", "#4ade80")
            self._start_listener()
        else:
            self.status_title.setText("Macro Off")
            self.status_title.setStyleSheet(
                "color: #f1f5f9; background: transparent; font-size: 18px; font-weight: 700;"
            )
            self.status_detail.setText("Flip the switch, then press F")
            self._set_pill("●  Idle", "#94a3b8")
            self._stop_listener()

    def _start_listener(self) -> None:
        self._stop_listener()
        self._listener = HotkeyListener(self._on_hotkey)
        self._listener.start()

        def check_permission():
            time.sleep(0.5)
            if self._listener is not None and self._listener.failed:
                self.bus.status.emit(
                    "●  No permission — grant Accessibility access", "#f87171"
                )

        threading.Thread(target=check_permission, daemon=True).start()

    def _stop_listener(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_hotkey(self) -> None:
        if not self.enabled or self.running:
            return
        now = time.monotonic()
        if now - self._last_trigger < DEBOUNCE_SEC:
            return
        self._last_trigger = now
        threading.Thread(target=self._run_macro, daemon=True).start()

    def _run_macro(self) -> None:
        self.running = True
        self.bus.status.emit("●  Running…", "#38bdf8")
        try:
            press_key(KEY_2)
            time.sleep(STEP_DELAY)

            left_click()
            time.sleep(STEP_DELAY)

            press_key(KEY_Q)
            time.sleep(STEP_DELAY)

            left_click()
        except Exception as exc:
            self.bus.status.emit(f"●  Error: {exc}", "#f87171")
        finally:
            self.running = False
            if self.enabled:
                self.bus.status.emit("●  Armed — press F", "#4ade80")
            else:
                self.bus.status.emit("●  Idle", "#94a3b8")

    def closeEvent(self, event) -> None:
        self.enabled = False
        self._stop_listener()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MacroWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

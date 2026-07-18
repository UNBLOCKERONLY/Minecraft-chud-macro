#!/usr/bin/env python3
"""Solar Macros — macro suite with sidebar UI.

The Mace tab contains the functional combo macro: press F to fire
2 → left click → Q → left click.

Uses Quartz CGEvent APIs directly (pynput crashes on macOS 26+ due to
TSM calls from background threads).
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

import Quartz
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


STEP_DELAY = 0.05
DEBOUNCE_SEC = 0.15

# macOS ANSI virtual keycodes for rebindable keys
KEYCODE_MAP = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31, "u": 32,
    "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
}

# Palette
BG = "#0b0d12"
SIDEBAR_BG = "#0e1116"
CARD_BG = "#14171d"
CARD_BORDER = "#232833"
CHIP_BG = "#0d1015"
CHIP_BORDER = "#2a303b"
TEXT = "#e5e7eb"
MUTED = "#8b93a1"
FAINT = "#586070"
GREEN = "#22c55e"
GREEN_SOFT = "#4ade80"
BLUE = "#38bdf8"
RED = "#f87171"


# ---------------------------------------------------------------- macro engine


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
    """Global hotkey listener using a Quartz event tap on its own run loop."""

    def __init__(self, get_keycode, on_hotkey) -> None:
        self._get_keycode = get_keycode
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
                if keycode == self._get_keycode() and not is_repeat:
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
        Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        Quartz.CFRunLoopRun()


# ------------------------------------------------------------------ ui pieces


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checked = False
        self._enabled_ui = True
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)

    def setUiEnabled(self, value: bool) -> None:
        self._enabled_ui = value
        self.setCursor(Qt.PointingHandCursor if value else Qt.ForbiddenCursor)
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool) -> None:
        if self._checked != value:
            self._checked = value
            self.update()
            self.toggled.emit(self._checked)

    def mousePressEvent(self, _event) -> None:
        if self._enabled_ui:
            self.setChecked(not self._checked)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._checked:
            track = QColor(GREEN)
        else:
            track = QColor("#2c333f")
        if not self._enabled_ui:
            track.setAlpha(120)
        p.setBrush(QBrush(track))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        knob_x = self.width() - 23 if self._checked else 3
        knob = QColor("#f8fafc")
        if not self._enabled_ui:
            knob.setAlpha(140)
        p.setBrush(QBrush(knob))
        p.drawEllipse(knob_x, 3, 20, 20)
        p.end()


class NavItem(QFrame):
    clicked = Signal()

    def __init__(self, icon: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(9)

        self.icon = QLabel(icon)
        self.icon.setFixedWidth(16)
        self.text = QLabel(text)
        self.badge = QLabel("")
        self.badge.setVisible(False)
        self.badge.setFixedHeight(16)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setStyleSheet(
            f"""
            QLabel {{
                color: #052e16;
                background-color: {GREEN};
                border-radius: 8px;
                padding: 0px 6px;
                font-size: 10px;
                font-weight: 700;
            }}
            """
        )

        layout.addWidget(self.icon)
        layout.addWidget(self.text)
        layout.addStretch(1)
        layout.addWidget(self.badge)
        self._restyle()

    def setBadge(self, value: Optional[int]) -> None:
        if value:
            self.badge.setText(str(value))
            self.badge.setVisible(True)
        else:
            self.badge.setVisible(False)

    def setSelected(self, value: bool) -> None:
        self._selected = value
        self._restyle()

    def _restyle(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"""
                NavItem {{ background-color: #1c222c; border-radius: 8px; }}
                QLabel {{ color: {TEXT}; background: transparent; font-size: 13px; }}
                """
            )
        else:
            self.setStyleSheet(
                f"""
                NavItem {{ background-color: transparent; border-radius: 8px; }}
                NavItem:hover {{ background-color: #141922; }}
                QLabel {{ color: {MUTED}; background: transparent; font-size: 13px; }}
                """
            )
        # badge style is overridden by the parent stylesheet; reapply
        self.badge.setStyleSheet(
            f"""
            QLabel {{
                color: #052e16;
                background-color: {GREEN};
                border-radius: 8px;
                padding: 0px 6px;
                font-size: 10px;
                font-weight: 700;
            }}
            """
        )

    def mousePressEvent(self, _event) -> None:
        self.clicked.emit()


def chip(text: str, accent: bool = False) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    color = TEXT if accent else MUTED
    border = "#3b82f6" if accent else CHIP_BORDER
    label.setStyleSheet(
        f"""
        QLabel {{
            color: {color};
            background-color: {CHIP_BG};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        """
    )
    return label


class KeybindChip(QLabel):
    """Clickable key box: click it, then press a letter or digit to rebind."""

    changed = Signal(str)

    def __init__(self, char: str, parent=None) -> None:
        super().__init__(char.upper(), parent)
        self._char = char.lower()
        self._capturing = False
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.ClickFocus)
        self._restyle()

    def char(self) -> str:
        return self._char

    def mousePressEvent(self, _event) -> None:
        if not self._capturing:
            self._capturing = True
            self.setText("press a key…")
            self._restyle()
            self.grabKeyboard()

    def keyPressEvent(self, event) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key_Escape:
            self._finish(None)
            return
        ch = event.text().lower()
        if ch in KEYCODE_MAP:
            self._finish(ch)
        # other keys (modifiers, symbols) are ignored while capturing

    def focusOutEvent(self, event) -> None:
        if self._capturing:
            self._finish(None)
        super().focusOutEvent(event)

    def _finish(self, ch: Optional[str]) -> None:
        self.releaseKeyboard()
        self._capturing = False
        if ch is not None and ch != self._char:
            self._char = ch
            self.changed.emit(ch)
        self.setText(self._char.upper())
        self._restyle()

    def _restyle(self) -> None:
        border = "#f59e0b" if self._capturing else "#3b82f6"
        self.setStyleSheet(
            f"""
            QLabel {{
                color: {TEXT};
                background-color: {CHIP_BG};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            """
        )


class SegmentedControl(QWidget):
    """Static segmented display (visual only)."""

    def __init__(self, options: list, selected: int, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for i, option in enumerate(options):
            label = QLabel(option)
            label.setAlignment(Qt.AlignCenter)
            if i == selected:
                label.setStyleSheet(
                    f"""
                    QLabel {{
                        color: {TEXT};
                        background-color: #262d3a;
                        border: 1px solid #3a4354;
                        border-radius: 7px;
                        padding: 4px 8px;
                        font-size: 11px;
                        font-weight: 700;
                    }}
                    """
                )
            else:
                label.setStyleSheet(
                    f"""
                    QLabel {{
                        color: {FAINT};
                        background-color: {CHIP_BG};
                        border: 1px solid {CHIP_BORDER};
                        border-radius: 7px;
                        padding: 4px 8px;
                        font-size: 11px;
                    }}
                    """
                )
            layout.addWidget(label)


class MacroCard(QFrame):
    def __init__(
        self,
        abbrev: str,
        title: str,
        description: str,
        interactive: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("macroCard")
        self.setStyleSheet(
            f"""
            QFrame#macroCard {{
                background-color: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 14px;
            }}
            """
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)
        self._layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)

        badge = QLabel(f" {abbrev} ")
        badge.setStyleSheet(
            f"""
            QLabel {{
                color: {MUTED};
                background-color: #1b212b;
                border: 1px solid {CHIP_BORDER};
                border-radius: 6px;
                padding: 3px 5px;
                font-size: 10px;
                font-weight: 700;
            }}
            """
        )
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color: {TEXT}; background: transparent; font-size: 15px; font-weight: 700;"
        )
        self.switch = ToggleSwitch()
        self.switch.setUiEnabled(interactive)

        header.addWidget(badge)
        header.addWidget(title_label)
        header.addStretch(1)
        header.addWidget(self.switch)
        self._layout.addLayout(header)

        desc = QLabel(description)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {MUTED}; background: transparent; font-size: 12px;"
        )
        self._layout.addWidget(desc)

        self.status_label: Optional[QLabel] = None

    def add_row(self, label_text: str, value) -> None:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setStyleSheet(
            f"color: {MUTED}; background: transparent; font-size: 12px;"
        )
        row.addWidget(label)
        row.addStretch(1)
        if isinstance(value, str):
            row.addWidget(chip(value, accent=True))
        else:
            row.addWidget(value)
        self._layout.addLayout(row)

    def add_status(self, text: str = "Inactive") -> None:
        self.status_label = QLabel(f"●  {text}")
        self.status_label.setStyleSheet(
            f"color: {FAINT}; background: transparent; font-size: 11px; font-weight: 600;"
        )
        self._layout.addWidget(self.status_label)

    def set_status(self, text: str, color: str) -> None:
        if self.status_label is not None:
            self.status_label.setText(f"●  {text}")
            self.status_label.setStyleSheet(
                f"color: {color}; background: transparent; font-size: 11px; font-weight: 600;"
            )


class Page(QWidget):
    def __init__(self, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(34, 28, 34, 24)
        outer.setSpacing(6)

        title_label = QLabel(title)
        title_label.setFont(QFont(".AppleSystemUIFont", 22, QFont.Bold))
        title_label.setStyleSheet(f"color: {TEXT}; background: transparent;")
        outer.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet(
            f"color: {MUTED}; background: transparent; font-size: 12px;"
        )
        outer.addWidget(subtitle_label)
        outer.addSpacing(14)

        self.body = QVBoxLayout()
        self.body.setSpacing(14)
        outer.addLayout(self.body)
        outer.addStretch(1)

    def add_empty_state(self, text: str = "No macros here yet — coming soon.") -> None:
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"""
            QLabel {{
                color: {FAINT};
                background-color: {CARD_BG};
                border: 1px dashed {CHIP_BORDER};
                border-radius: 14px;
                padding: 44px;
                font-size: 13px;
            }}
            """
        )
        self.body.addWidget(label)


class Bus(QObject):
    status = Signal(str, str)  # text, color


# ---------------------------------------------------------------- main window


NAV_SECTIONS = [
    ("MACROS", [("crystal", "◈", "Crystal"), ("sword", "⚔", "Sword"),
                ("mace", "⚒", "Mace"), ("cart", "▣", "Cart"), ("uhc", "◉", "UHC"),
                ("other", "✧", "Other")]),
    ("TOOLS", [("optimizer", "◎", "Optimizer"), ("profiles", "☰", "Profiles")]),
    ("APP", [("themes", "◐", "Themes"), ("settings", "⚙", "Settings"),
             ("changelog", "≡", "Changelog")]),
]


class SolarWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Solar Macros")
        self.resize(1060, 640)
        self.setMinimumSize(940, 600)

        self.enabled = False
        self.running = False
        self._listener: Optional[HotkeyListener] = None
        self._last_trigger = 0.0
        self.hotkey_char = "f"
        self.key1_char = "2"
        self.key2_char = "q"
        self.bus = Bus()
        self.bus.status.connect(self._on_status)

        central = QWidget()
        central.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ------------------------------------------------------------ sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(198)
        sidebar.setStyleSheet(
            f"background-color: {SIDEBAR_BG}; border-right: 1px solid #161b23;"
        )
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 18, 12, 16)
        side_layout.setSpacing(3)

        brand = QLabel("SOLAR MACROS")
        brand.setStyleSheet(
            f"color: {TEXT}; background: transparent; font-size: 13px; "
            "font-weight: 800; letter-spacing: 1px; border: none;"
        )
        side_layout.addWidget(brand)
        side_layout.addSpacing(14)

        self.nav_items: dict = {}
        for section, items in NAV_SECTIONS:
            header = QLabel(section)
            header.setStyleSheet(
                f"color: {FAINT}; background: transparent; font-size: 10px; "
                "font-weight: 700; letter-spacing: 1px; border: none; padding-left: 4px;"
            )
            side_layout.addSpacing(8)
            side_layout.addWidget(header)
            side_layout.addSpacing(2)
            for key, icon, text in items:
                item = NavItem(icon, text)
                item.clicked.connect(lambda k=key: self.show_page(k))
                side_layout.addWidget(item)
                self.nav_items[key] = item

        side_layout.addStretch(1)
        root.addWidget(sidebar)

        # ------------------------------------------------------------- pages
        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        self.page_index: dict = {}
        self._build_pages()
        self.show_page("mace")

    # -------------------------------------------------------------- page setup

    def _build_pages(self) -> None:
        # Crystal
        crystal = Page("Crystal", "Crystal PVP automation")
        crystal.add_empty_state()
        self._add_page("crystal", crystal)

        # Sword
        sword = Page("Sword", "Sword PVP automation")
        row = QHBoxLayout()
        row.setSpacing(14)

        asb = MacroCard(
            "ASB",
            "Auto Shield Breaker",
            "Swaps to axe, attacks to disable shield, returns to sword. Coming soon.",
            interactive=False,
        )
        asb.add_row("Keybind", "R")
        asb.add_row("Axe key", "Q")
        asb.add_row("Sword key", "1")
        asb.add_row("Swap delay (ms)", "1")
        asb.add_status("Coming soon")
        row.addWidget(asb, stretch=1)

        tb = MacroCard(
            "TB",
            "Triggerbot",
            "Auto left-clicks when crosshair turns red or blue on target. "
            "Requires Adv. Crosshair mod. Coming soon.",
            interactive=False,
        )
        tb.add_row("Toggle keybind", "J")
        tb.add_row("Mode", SegmentedControl(["Normal", "Smart Crit", "S-Tap"], 2))
        tb.add_row("Hit cooldown (ms)", "200")
        tb.add_row("S-Tap hold (ms)", "150")
        tb.add_status("Coming soon")
        row.addWidget(tb, stretch=1)

        sword.body.addLayout(row)
        self._add_page("sword", sword)

        # Mace — the functional macro
        mace = Page("Mace", "Mace PVP automation")
        self.combo_card = MacroCard(
            "SS",
            "Stun Slam",
            "Fires: first key → left click → second key → left click. "
            "Click a key box to rebind it.",
        )
        self.hotkey_chip = KeybindChip(self.hotkey_char)
        self.hotkey_chip.changed.connect(self._set_hotkey)
        self.key1_chip = KeybindChip(self.key1_char)
        self.key1_chip.changed.connect(self._set_key1)
        self.key2_chip = KeybindChip(self.key2_char)
        self.key2_chip.changed.connect(self._set_key2)
        self.combo_card.add_row("Keybind", self.hotkey_chip)
        self.combo_card.add_row("First key", self.key1_chip)
        self.combo_card.add_row("Second key", self.key2_chip)
        self.combo_card.add_row("Step delay (ms)", str(int(STEP_DELAY * 1000)))
        self.combo_card.add_status("Inactive")
        self.combo_card.switch.toggled.connect(self._on_toggle)
        self.combo_card.setMaximumWidth(520)
        mace.body.addWidget(self.combo_card, alignment=Qt.AlignLeft)
        self._add_page("mace", mace)

        # Cart / UHC
        cart = Page("Cart", "Minecart automation")
        cart.add_empty_state()
        self._add_page("cart", cart)

        uhc = Page("UHC", "UHC automation")
        uhc.add_empty_state()
        self._add_page("uhc", uhc)

        other = Page("Other", "Everything else")
        other.add_empty_state()
        self._add_page("other", other)

        # Tools
        optimizer = Page("Optimizer", "Performance tweaks")
        optimizer.add_empty_state("Nothing to optimize yet — coming soon.")
        self._add_page("optimizer", optimizer)

        profiles = Page("Profiles", "Save and switch macro loadouts")
        profiles.add_empty_state("Profiles are coming soon.")
        self._add_page("profiles", profiles)

        # App
        themes = Page("Themes", "Customize the look")
        themes.add_empty_state("More themes are coming soon.")
        self._add_page("themes", themes)

        settings = Page("Settings", "App configuration")
        settings.add_empty_state("No settings yet.")
        self._add_page("settings", settings)

        changelog = Page("Changelog", "What's new")
        log = QLabel(
            "v2.1 — Stun Slam rename, editable keybinds, new Other tab.\n"
            "v2.0 — Solar Macros redesign: sidebar UI, tabs, macro cards.\n"
            "v1.0 — First release: F-key combo macro (2 → click → Q → click)."
        )
        log.setStyleSheet(
            f"""
            QLabel {{
                color: {MUTED};
                background-color: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 14px;
                padding: 20px;
                font-size: 12px;
            }}
            """
        )
        changelog.body.addWidget(log)
        self._add_page("changelog", changelog)

    def _add_page(self, key: str, page: QWidget) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setWidget(page)
        self.page_index[key] = self.stack.addWidget(scroll)

    def show_page(self, key: str) -> None:
        self.stack.setCurrentIndex(self.page_index[key])
        for item_key, item in self.nav_items.items():
            item.setSelected(item_key == key)

    # ------------------------------------------------------------ macro logic

    def _set_hotkey(self, ch: str) -> None:
        self.hotkey_char = ch

    def _set_key1(self, ch: str) -> None:
        self.key1_char = ch

    def _set_key2(self, ch: str) -> None:
        self.key2_char = ch

    def _on_toggle(self, checked: bool) -> None:
        self.enabled = checked
        self.nav_items["mace"].setBadge(1 if checked else None)
        if checked:
            self.combo_card.set_status(
                f"Armed — press {self.hotkey_char.upper()}", GREEN_SOFT
            )
            self._start_listener()
        else:
            self.combo_card.set_status("Inactive", FAINT)
            self._stop_listener()

    def _on_status(self, text: str, color: str) -> None:
        self.combo_card.set_status(text, color)

    def _start_listener(self) -> None:
        self._stop_listener()
        self._listener = HotkeyListener(
            lambda: KEYCODE_MAP[self.hotkey_char], self._on_hotkey
        )
        self._listener.start()

        def check_permission():
            time.sleep(0.5)
            if self._listener is not None and self._listener.failed:
                self.bus.status.emit(
                    "No permission — grant Accessibility access", RED
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
        self.bus.status.emit("Running…", BLUE)
        try:
            press_key(KEYCODE_MAP[self.key1_char])
            time.sleep(STEP_DELAY)

            left_click()
            time.sleep(STEP_DELAY)

            press_key(KEYCODE_MAP[self.key2_char])
            time.sleep(STEP_DELAY)

            left_click()
        except Exception as exc:
            self.bus.status.emit(f"Error: {exc}", RED)
        finally:
            self.running = False
            if self.enabled:
                self.bus.status.emit(
                    f"Armed — press {self.hotkey_char.upper()}", GREEN_SOFT
                )
            else:
                self.bus.status.emit("Inactive", FAINT)

    def closeEvent(self, event) -> None:
        self.enabled = False
        self._stop_listener()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Solar Macros")
    window = SolarWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# FORUM SCOUT Qt — Multi-forum search tool (PyQt6)
# Forum registry loaded from forums.conf (see forums.conf for format).
# ─────────────────────────────────────────────────────────────────────────────

import sys
import threading
import os
import json
import subprocess
import datetime
import urllib.parse
import locale
from html.parser import HTMLParser

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLineEdit, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem,
        QHeaderView, QStatusBar, QLabel, QSpinBox, QCheckBox, QMenu,
        QMessageBox, QAbstractItemView, QSizePolicy, QGridLayout, QFrame, QLayout,
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QObject, pyqtSignal, QSortFilterProxyModel, QStringListModel,
        QSize, QPoint, QRect, QEvent,
    )
    from PyQt6.QtGui import (
        QColor, QFont, QKeySequence, QShortcut, QFontMetrics, QBrush,
        QAction,
    )
    from PyQt6.QtWidgets import QCompleter
except ImportError:
    print("Error: 'PyQt6' not found. Install with: pip install PyQt6")
    raise SystemExit(1)

try:
    import requests
except ImportError:
    print("Error: 'requests' not found. Install with: pip install requests")
    raise SystemExit(1)

# ─── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR     = os.path.expanduser("~/.cache/forum-scout")
BOOKMARK_FILE = os.path.join(CACHE_DIR, "bookmarks.log")
HISTORY_FILE  = os.path.join(CACHE_DIR, "history.log")
os.makedirs(CACHE_DIR, exist_ok=True)

CONFIG_DIR    = os.path.expanduser("~/.config/forum-scout")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
os.makedirs(CONFIG_DIR, exist_ok=True)

_FORUMS_SEARCH = [
    os.path.join(CONFIG_DIR, "forums.conf"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "forums.conf"),
    os.path.expanduser("~/.local/share/forum-scout/forums.conf"),
    "/usr/local/share/forum-scout/forums.conf",
    "/usr/share/forum-scout/forums.conf",
]

APP_TITLE    = "Forum Scout"
DEFAULT_HITS = 10

_VERSION = "__VERSION__"
if _VERSION.startswith("__"):
    try:
        _VERSION = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")).read().strip()
    except Exception:
        _VERSION = "dev"

# ─── Forum registry ───────────────────────────────────────────────────────────
def _load_forums() -> list:
    for path in _FORUMS_SEARCH:
        if not os.path.exists(path):
            continue
        entries = []
        seen = set()
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    e     = json.loads(line)
                    name  = str(e.get("name",  "")).strip()
                    type_ = str(e.get("type",  "discourse")).strip()
                    url   = str(e.get("url",   "")).strip()
                    color = str(e.get("color", "#888888")).strip()
                    on    = bool(e.get("on",   True))
                    group = str(e.get("group", "distro")).strip()
                    if not name or not url or name.lower() in seen:
                        continue
                    entry = {"name": name, "type": type_, "url": url,
                             "color": color, "on": on, "group": group}
                    if "page" in e:
                        entry["page"] = str(e["page"])
                    entries.append(entry)
                    seen.add(name.lower())
                except Exception:
                    continue
        return entries
    return []

FORUMS = _load_forums()

# ─── i18n ─────────────────────────────────────────────────────────────────────
_lang = (locale.getlocale()[0] or "en")[:2]

_EN_STRINGS = {
    "search_ph":   "Type keywords and press Enter or click Search…",
    "search_btn":  "Search",
    "tab_results": "Results",
    "tab_bm":      "Bookmarks",
    "tab_hist":    "History",
    "tab_about":   "About",
    "hits_label":  "Hits per source:",
    "ready":       "Ready.",
    "fetching":    "Fetching: '{}'…",
    "done":        "{} result(s) from {} source(s).",
    "no_results":  "No results.",
    "col_n":       "#",
    "col_forum":   "Forum",
    "col_title":   "Title",
    "col_link":    "Link",
    "col_time":    "Time",
    "col_query":   "Query",
    "ctx_open":      "Open in browser",
    "ctx_copy":      "Copy link",
    "ctx_bm":        "Add to bookmarks",
    "ctx_bm_remove": "Remove bookmark",
    "bm_open":     "Open",
    "bm_copy":     "Copy link",
    "bm_del":      "Remove",
    "bm_added":    "Bookmark added: {}",
    "bm_removed":  "Bookmark removed.",
    "hist_rerun":  "Re-run search",
    "hist_clear":  "Clear history",
    "via_ddg":     " ⁽ᴰᴰᴳ⁾",
    "col_date":    "Added",
}

def _load_translation(lang: str) -> dict:
    search_dirs = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "translations"),
        os.path.expanduser("~/.local/share/forum-scout/translations"),
        "/usr/share/forum-scout/translations",
    ]
    for lang_code in (lang, "en"):
        for d in search_dirs:
            path = os.path.join(d, f"{lang_code}.json")
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                        return {**_EN_STRINGS, **data}
                except Exception:
                    pass
    return _EN_STRINGS

S = _load_translation(_lang)

# ─── HTTP session ─────────────────────────────────────────────────────────────
_session = requests.Session()
_session.headers["User-Agent"] = (
    f"forum-scout/{_VERSION} (https://github.com/musqz/forum-scout)"
)

# ─── DuckDuckGo HTML parser ───────────────────────────────────────────────────
class _DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._link: str | None = None
        self._title_buf: list[str] = []
        self._in_a: bool = False

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        d = dict(attrs)
        cls = d.get("class", "")
        if "result__a" not in cls:
            return
        href = d.get("href", "")
        if "uddg=" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = urllib.parse.unquote(qs.get("uddg", [""])[0])
        self._link = href
        self._title_buf = []
        self._in_a = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
            title = "".join(self._title_buf).strip()
            if self._link and title:
                self.results.append((title, self._link))
            self._link = None
            self._title_buf = []

    def handle_data(self, data):
        if self._in_a:
            self._title_buf.append(data)


# ─── Fetcher functions ────────────────────────────────────────────────────────
def _fmt_date(iso: str) -> str:
    try:
        return datetime.datetime.fromisoformat(
            iso.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d")
    except Exception:
        return ""


class _ForumUnreachable(Exception):
    pass


_NET_ERRORS = (requests.ConnectionError, requests.Timeout, requests.exceptions.SSLError)


def _fetch_discourse(forum: dict, query: str, hits: int) -> list[tuple[str, str, str, bool]]:
    url = f"{forum['url']}/search.json"
    try:
        r = _session.get(url, params={"q": query}, timeout=9)
        data = r.json()
        out = []
        base = forum["url"]
        for t in data.get("topics", [])[:hits]:
            link   = f"{base}/t/{t['slug']}/{t['id']}"
            date   = _fmt_date(t.get("created_at", ""))
            solved = bool(t.get("has_accepted_answer", False))
            out.append((t["title"], link, date, solved))
        return out
    except _NET_ERRORS:
        raise _ForumUnreachable
    except Exception:
        return []


def _fetch_mediawiki(forum: dict, query: str, hits: int) -> list[tuple[str, str, str]]:
    try:
        r = _session.get(
            f"{forum['url']}/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": hits,
                "format": "json",
            },
            timeout=9,
        )
        data = r.json()
        out = []
        base = forum["url"]
        page_tpl = forum.get("page", "title/{slug}")
        for item in data.get("query", {}).get("search", []):
            slug = urllib.parse.quote(item["title"].replace(" ", "_"))
            date = _fmt_date(item.get("timestamp", ""))
            out.append((item["title"], f"{base}/{page_tpl.format(slug=slug)}", date, False))
        return out
    except _NET_ERRORS:
        raise _ForumUnreachable
    except Exception:
        return []


def _fetch_ddg(forum: dict, query: str, hits: int) -> list[tuple[str, str, str]]:
    site = forum["url"]
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": f"site:{site} {query}"},
            headers={"User-Agent": _session.headers["User-Agent"]},
            timeout=12,
        )
        parser = _DDGParser()
        parser.feed(r.text)
        out = []
        for title, link in parser.results:
            if site in link:
                out.append((title, link, "—", False))
                if len(out) >= hits:
                    break
        return out
    except _NET_ERRORS:
        raise _ForumUnreachable
    except Exception:
        return []


_FETCHERS = {
    "discourse":  _fetch_discourse,
    "mediawiki":  _fetch_mediawiki,
    "ddg":        _fetch_ddg,
}

# ─── Live suggestion fetchers ─────────────────────────────────────────────────
_SUGGEST_LIMIT   = 5
_SUGGEST_TIMEOUT = 4
_SUGGEST_DELAY   = 400


def _suggest_discourse(forum: dict, term: str) -> list[str]:
    try:
        r = _session.get(
            f"{forum['url']}/search.json",
            params={"q": term},
            timeout=_SUGGEST_TIMEOUT,
        )
        data = r.json()
        return [t["title"] for t in data.get("topics", [])[:_SUGGEST_LIMIT]]
    except Exception:
        return []


def _suggest_mediawiki(forum: dict, term: str) -> list[str]:
    try:
        r = _session.get(
            f"{forum['url']}/api.php",
            params={
                "action":    "opensearch",
                "search":    term,
                "limit":     _SUGGEST_LIMIT,
                "namespace": 0,
                "format":    "json",
            },
            timeout=_SUGGEST_TIMEOUT,
        )
        data = r.json()
        return list(data[1])[:_SUGGEST_LIMIT] if len(data) > 1 else []
    except Exception:
        return []


_SUGGESTERS = {
    "discourse": _suggest_discourse,
    "mediawiki": _suggest_mediawiki,
}

_FORUM_COLOR: dict[str, str] = {f["name"]: f["color"] for f in FORUMS}

# ─── Autocomplete seed terms ──────────────────────────────────────────────────
_SEED_TERMS = [
    "black screen after update", "black screen on boot", "boot loop",
    "grub not found", "uefi boot", "initramfs error", "kernel panic",
    "slow boot", "systemd timeout", "failed to start",
    "nvidia driver", "amd gpu", "intel graphics", "screen tearing",
    "wifi not working", "bluetooth not working", "no sound", "audio crackling",
    "touchpad not working", "webcam not detected", "dual monitor setup",
    "monitor not detected", "hdmi no signal",
    "pacman error", "yay aur", "package conflict", "dependency error",
    "signature invalid", "keyring update", "partial upgrade",
    "picom animations", "picom vsync", "openbox keybind", "tint2 config",
    "conky not showing", "jgmenu setup", "wayland issues", "xorg crash",
    "plasma crash", "plasma black screen", "kwin compositor",
    "kde panel not showing", "plasma widget", "kde slow",
    "dolphin not opening", "kde login loop", "sddm not starting",
    "kde wayland issues", "krunner not working", "kde notifications",
    "gnome shell crash", "gnome extensions not working", "gdm not starting",
    "gnome panel missing", "nautilus not opening", "gnome slow",
    "gnome wayland black screen", "gnome login loop", "gnome freezes",
    "gnome screen flickering", "gnome night light", "dash to dock",
    "networkmanager wifi", "ethernet not working", "vpn setup", "dns slow",
    "suspend not working", "hibernate resume", "wake from sleep",
    "screen blank after suspend", "battery drain",
    "firefox slow", "steam not launching", "flatpak permission",
    "wine not working", "virtualbox error",
]


# ─── Worker signals (thread → main thread) ───────────────────────────────────
class _WorkerSignals(QObject):
    forum_done   = pyqtSignal(list, object, object)   # results, ddg_empty, unreachable
    suggest_done = pyqtSignal(list, int)              # suggestions, token


# ─── Multi-word completer proxy ───────────────────────────────────────────────
class _MultiWordCompleter(QCompleter):
    """Matches a suggestion if every space-separated word typed appears in it."""

    def __init__(self, model, parent=None):
        super().__init__(model, parent)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

    def splitPath(self, path: str) -> list[str]:
        # Return path unchanged so pathFromIndex works normally.
        # We override the filter via a proxy instead.
        return [path]

    def pathFromIndex(self, index):
        return self.model().data(index, Qt.ItemDataRole.DisplayRole)


class _MultiWordProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._words: list[str] = []

    def set_filter_text(self, text: str):
        self._words = text.lower().split()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent):
        if not self._words:
            return True
        idx   = self.sourceModel().index(source_row, 0, source_parent)
        value = self.sourceModel().data(idx, Qt.ItemDataRole.DisplayRole) or ""
        lower = value.lower()
        return all(w in lower for w in self._words)


class FlowLayout(QLayout):
    """Wrapping flow layout — items wrap to the next row when the width is exceeded."""
    def __init__(self, parent=None, h_spacing=8, v_spacing=4):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            next_x = x + w + self._h_spacing
            if x > eff.x() and next_x - self._h_spacing > eff.right():
                x = eff.x()
                y += line_h + self._v_spacing
                next_x = x + w + self._h_spacing
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_h = max(line_h, h)
        return y + line_h - rect.y() + m.bottom()


# ─── Main window ──────────────────────────────────────────────────────────────
class ScoutWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_FileDialogContentsView
        ))
        self.resize(820, 520)
        self.setMinimumSize(700, 300)

        self._busy               = False
        self._results            = []
        self._bm_data            = []
        self._suggest_timer      = None
        self._suggest_token      = 0
        self._live_suggestions   = []
        self._forums_bar_visible = True
        self._bm_bulk_confirm    = True
        self._bm_undo_data       = []
        self._hover_link         = None

        # Worker signals live on main thread (QObject), emitted from worker threads
        self._signals = _WorkerSignals()
        self._signals.forum_done.connect(self._add_forum_results)
        self._signals.suggest_done.connect(self._apply_live_suggestions)

        self._build_ui()
        self._load_settings()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 0)
        root.setSpacing(4)

        root.addWidget(self._build_topbar())
        root.addWidget(self._build_notebook(), stretch=1)

        self._build_statusbar()
        self._setup_shortcuts()

    # ── Top bar ───────────────────────────────────────────────────────────────
    def _build_topbar(self) -> QWidget:
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        # Row 1 — search
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText(S["search_ph"])
        self._entry.returnPressed.connect(self._on_search)
        self._entry.textChanged.connect(self._on_entry_changed)
        self._build_completer()
        row1.addWidget(self._entry, stretch=1)

        self._btn = QPushButton(S["search_btn"])
        self._btn.clicked.connect(self._on_search)
        self._btn.setFixedWidth(80)
        row1.addWidget(self._btn)

        self._spinner_lbl = QLabel("⏳")
        self._spinner_lbl.setFixedWidth(22)
        self._spinner_lbl.setVisible(False)
        row1.addWidget(self._spinner_lbl)

        self._forums_toggle = QPushButton("Forums ▾")
        self._forums_toggle.setToolTip("Show/hide forums bar (Ctrl+F)")
        self._forums_toggle.clicked.connect(self._toggle_forums_bar)
        row1.addWidget(self._forums_toggle)

        help_btn = QPushButton("?")
        help_btn.setToolTip("Keyboard shortcuts")
        help_btn.setFixedWidth(28)
        help_btn.clicked.connect(self._show_shortcuts)
        row1.addWidget(help_btn)
        self._help_btn = help_btn

        vbox.addLayout(row1)

        # Forums bar
        self._forums_bar = QWidget()
        fbox = QVBoxLayout(self._forums_bar)
        fbox.setContentsMargins(0, 0, 0, 0)
        fbox.setSpacing(2)

        distro_widget = QWidget()
        distro_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        row2 = FlowLayout(distro_widget, h_spacing=8, v_spacing=4)
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row4 = QHBoxLayout()
        row4.setSpacing(8)

        self._checks: dict[str, QCheckBox] = {}
        for f in FORUMS:
            cb = QCheckBox(f["name"])
            cb.setChecked(f["on"])
            cb.setStyleSheet(f"color: {f['color']}; font-weight: bold;")
            self._checks[f["name"]] = cb
            if f["group"] == "distro":
                row2.addWidget(cb)
            elif f["group"] == "wiki":
                row3.addWidget(cb)
            else:
                row4.addWidget(cb)

        row3.addStretch()
        row4.addStretch()
        hits_lbl = QLabel(S["hits_label"])
        hits_lbl.setStyleSheet("color: gray;")
        row4.addWidget(hits_lbl)
        self._hits_spin = QSpinBox()
        self._hits_spin.setRange(1, 50)
        self._hits_spin.setValue(DEFAULT_HITS)
        self._hits_spin.setFixedWidth(55)
        row4.addWidget(self._hits_spin)

        fbox.addWidget(distro_widget)
        fbox.addLayout(row3)
        fbox.addLayout(row4)
        vbox.addWidget(self._forums_bar)

        return container

    def _toggle_forums_bar(self):
        self._forums_bar_visible = not self._forums_bar_visible
        self._forums_bar.setVisible(self._forums_bar_visible)
        self._forums_toggle.setText("Forums ▾" if self._forums_bar_visible else "Forums ▸")

    def _show_shortcuts(self):
        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setFrameShape(QFrame.Shape.StyledPanel)
        popup.setFrameShadow(QFrame.Shadow.Raised)

        grid = QGridLayout(popup)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(5)
        for row, (key, desc) in enumerate([
            ("Ctrl+L",          "Focus search bar"),
            ("F6",              "Focus table (tab-aware)"),
            ("Ctrl+F",          "Toggle forums bar"),
            ("F5",              "Re-run last search"),
            ("Escape",          "Clear search"),
            ("Enter",           "Open focused row in browser"),
            ("Ctrl+Enter",      "Open all selected results in browser"),
            ("Ctrl+B",          "Bookmark / un-bookmark selected result(s)"),
            ("Del",             "Delete selected bookmark(s)"),
            ("Ctrl+Z",          "Undo last bookmark delete"),
            ("Ctrl+Tab",        "Switch tabs"),
            ("?",               "Show this help"),
        ]):
            k = QLabel(f"<b>{key}</b>")
            k.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(k,            row, 0)
            grid.addWidget(QLabel(desc), row, 1)

        popup.adjustSize()
        btn_global = self._help_btn.mapToGlobal(QPoint(0, self._help_btn.height()))
        popup.move(btn_global.x() - popup.width() + self._help_btn.width(), btn_global.y())
        popup.show()

    # ── Notebook ──────────────────────────────────────────────────────────────
    def _build_notebook(self) -> QTabWidget:
        self._notebook = QTabWidget()
        self._notebook.addTab(self._build_results_tab(),  S["tab_results"])
        self._notebook.addTab(self._build_bm_tab(),       S["tab_bm"])
        self._notebook.addTab(self._build_hist_tab(),     S["tab_hist"])
        self._notebook.addTab(self._build_about_tab(),    S["tab_about"])
        return self._notebook

    # ── Results tab ───────────────────────────────────────────────────────────
    def _build_results_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)

        self._res_table = QTableWidget(0, 5)
        self._res_table.setHorizontalHeaderLabels([
            S["col_n"], S["col_forum"], S["col_title"], S["col_date"], "✓"
        ])
        self._res_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._res_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._res_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._res_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._res_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._res_table.setColumnWidth(0, 30)
        self._res_table.setColumnWidth(1, 150)
        self._res_table.setColumnWidth(3, 100)
        self._res_table.setColumnWidth(4, 22)
        self._res_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._res_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._res_table.setShowGrid(False)
        self._res_table.verticalHeader().setVisible(False)
        self._res_table.setSortingEnabled(True)
        self._res_table.setMouseTracking(True)
        self._res_table.itemDoubleClicked.connect(self._on_result_double_click)
        self._res_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._res_table.customContextMenuRequested.connect(self._on_result_context_menu)
        self._res_table.mouseMoveEvent = self._on_result_hover
        self._res_table.leaveEvent    = self._on_result_hover_leave
        self._res_table.installEventFilter(self)

        v.addWidget(self._res_table)
        return w

    # ── Bookmarks tab ─────────────────────────────────────────────────────────
    def _build_bm_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        self._bm_filter = QLineEdit()
        self._bm_filter.setPlaceholderText("Filter bookmarks…")
        self._bm_filter.textChanged.connect(self._bm_refresh)
        v.addWidget(self._bm_filter)

        tb = QHBoxLayout()
        tb.setSpacing(4)
        for label, cb in [
            (S["bm_open"], self._bm_open),
            (S["bm_copy"], self._bm_copy),
            (S["bm_del"],  self._bm_remove),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(cb)
            tb.addWidget(btn)
        tb.addStretch()

        self._undo_btn = QPushButton("Undo")
        self._undo_btn.setToolTip("Restore last deleted bookmark(s) (Ctrl+Z)")
        self._undo_btn.clicked.connect(self._bm_undo)
        self._undo_btn.setVisible(False)
        tb.addWidget(self._undo_btn)
        v.addLayout(tb)

        self._bm_table = QTableWidget(0, 4)
        self._bm_table.setHorizontalHeaderLabels([S["col_forum"], S["col_title"], S["col_date"], "✓"])
        self._bm_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._bm_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._bm_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._bm_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._bm_table.setColumnWidth(0, 130)
        self._bm_table.setColumnWidth(2, 145)
        self._bm_table.setColumnWidth(3, 22)
        self._bm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._bm_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._bm_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._bm_table.setShowGrid(False)
        self._bm_table.verticalHeader().setVisible(False)
        self._bm_table.setSortingEnabled(True)
        self._bm_table.itemDoubleClicked.connect(self._on_bm_double_click)
        self._bm_table.installEventFilter(self)
        v.addWidget(self._bm_table)

        self._load_bookmarks()
        return w

    # ── History tab ───────────────────────────────────────────────────────────
    def _build_hist_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        tb = QHBoxLayout()
        tb.setSpacing(4)
        for label, cb in [
            (S["hist_rerun"], self._hist_rerun),
            (S["hist_clear"], self._hist_clear),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(cb)
            tb.addWidget(btn)
        tb.addStretch()
        v.addLayout(tb)

        self._hist_table = QTableWidget(0, 2)
        self._hist_table.setHorizontalHeaderLabels([S["col_time"], S["col_query"]])
        self._hist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._hist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._hist_table.setColumnWidth(0, 160)
        self._hist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._hist_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._hist_table.setShowGrid(False)
        self._hist_table.verticalHeader().setVisible(False)
        self._hist_table.setSortingEnabled(False)
        self._hist_table.itemDoubleClicked.connect(self._on_hist_double_click)
        self._hist_table.installEventFilter(self)
        v.addWidget(self._hist_table)

        self._load_history()
        return w

    # ── About tab ─────────────────────────────────────────────────────────────
    def _build_about_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)

        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(8)
        scroll.setWidget(inner)

        title = QLabel("Forum Scout")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        v.addWidget(title)

        ver = QLabel(f"v{_VERSION}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(ver)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        v.addWidget(sep)

        link = QLabel('<a href="https://github.com/musqz/forum-scout">github.com/musqz/forum-scout</a>')
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setOpenExternalLinks(True)
        v.addWidget(link)

        author = QLabel("musqz · MIT")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(author)

        return scroll

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_lbl = QLabel(S["ready"])
        sb.addWidget(self._status_lbl, 1)
        self._hover_lbl = QLabel("")
        self._hover_lbl.setStyleSheet("color: gray;")
        sb.addPermanentWidget(self._hover_lbl)
        self._suggest_lbl = QLabel("loading suggestions…")
        self._suggest_lbl.setStyleSheet("color: gray;")
        self._suggest_lbl.setVisible(False)
        sb.addPermanentWidget(self._suggest_lbl)

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)

    # ── Autocomplete ──────────────────────────────────────────────────────────
    def _build_completer(self):
        self._completion_list: list[str] = []
        self._completion_seen: set[str]  = set()
        self._live_count                 = 0

        for term in _SEED_TERMS:
            key = term.lower()
            if key not in self._completion_seen:
                self._completion_seen.add(key)
                self._completion_list.append(term)

        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            _, query = line.split(" - ", 1)
                            self._completion_add(query)
                        except Exception:
                            pass
            except Exception:
                pass

        self._completion_model = QStringListModel(self._completion_list)
        self._completion_proxy = _MultiWordProxyModel()
        self._completion_proxy.setSourceModel(self._completion_model)

        completer = QCompleter(self._completion_proxy, self._entry)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated.connect(self._on_completion_selected)
        self._entry.setCompleter(completer)
        self._completer = completer

    def _completion_add(self, query: str):
        key = query.strip().lower()
        if key and key not in self._completion_seen:
            self._completion_seen.add(key)
            self._completion_list.insert(0, query.strip())
            self._completion_model.setStringList(self._completion_list)

    def _on_completion_selected(self, text: str):
        self._entry.setText(text)
        self._on_search()

    # ── Live suggestions ──────────────────────────────────────────────────────
    def _on_entry_changed(self, text: str):
        if self._suggest_timer is not None:
            self._suggest_timer.stop()
            self._suggest_timer = None

        # Update completer filter
        self._completion_proxy.set_filter_text(text)

        if len(text.strip()) < 3 or self._busy:
            return

        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.timeout.connect(lambda: self._fire_suggestions(text.strip()))
        self._suggest_timer.start(_SUGGEST_DELAY)

    def _fire_suggestions(self, term: str):
        self._suggest_timer = None
        self._suggest_token += 1
        token = self._suggest_token

        active = [
            f for f in FORUMS
            if self._checks[f["name"]].isChecked()
            and f["type"] in _SUGGESTERS
        ]
        if not active:
            return

        self._suggest_lbl.setVisible(True)
        threading.Thread(
            target=self._suggestions_thread,
            args=(term, token, active),
            daemon=True,
        ).start()

    def _suggestions_thread(self, term: str, token: int, forums: list):
        seen:    set[str]  = set()
        results: list[str] = []
        for f in forums:
            for title in _SUGGESTERS[f["type"]](f, term):
                key = title.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(title)
        self._signals.suggest_done.emit(results, token)

    def _apply_live_suggestions(self, suggestions: list[str], token: int):
        if token != self._suggest_token:
            return
        self._suggest_lbl.setVisible(False)

        # Remove previously prepended live suggestions
        for _ in range(self._live_count):
            if self._completion_list:
                self._completion_list.pop(0)
                if s := next((s for s in self._completion_seen if True), None):
                    pass  # seen set stays (permanent terms should stay seen)
        self._live_count = 0

        new_live = [s for s in suggestions if s.lower() not in self._completion_seen]
        for s in reversed(new_live):
            self._completion_list.insert(0, s)
        self._live_count = len(new_live)
        self._completion_model.setStringList(self._completion_list)

        if new_live:
            self._completer.complete()

    # ── Search logic ──────────────────────────────────────────────────────────
    def _on_search(self):
        query = self._entry.text().strip()
        if not query or self._busy:
            return

        active = [f for f in FORUMS if self._checks[f["name"]].isChecked()]
        if not active:
            self._set_status(S["no_results"])
            return

        self._undo_btn.setVisible(False)
        self._bm_undo_data = []
        self._busy = True
        self._btn.setEnabled(False)
        self._spinner_lbl.setVisible(True)

        # Disable sorting during population to avoid index shuffling mid-insert
        self._res_table.setSortingEnabled(False)
        self._res_table.setRowCount(0)

        self._results       = []
        self._search_total  = len(active)
        self._search_done   = 0
        self._search_idx    = 0
        self._ddg_empty     = []
        self._unreachable   = []
        self._search_query  = query
        self._tab_switched  = False
        self._bm_urls       = self._bookmarked_urls()

        self._set_status(S["fetching"].format(query))
        self._log_history(query)

        hits = self._hits_spin.value()
        for f in active:
            threading.Thread(
                target=self._fetch_one_forum,
                args=(query, hits, f),
                daemon=True,
            ).start()

    def _fetch_one_forum(self, query: str, hits: int, forum: dict):
        try:
            items = _FETCHERS[forum["type"]](forum, query, hits)
            unreachable = None
        except _ForumUnreachable:
            items = []
            unreachable = forum["name"]
        via_ddg = forum["type"] == "ddg"
        results = [
            (forum["name"], forum["color"], title, link, date, via_ddg, solved)
            for title, link, date, solved in items
        ]
        ddg_empty = forum["name"] if via_ddg and not items and not unreachable else None
        self._signals.forum_done.emit(results, ddg_empty, unreachable)

    def _add_forum_results(self, new_results: list, ddg_empty_name, unreachable_name):
        for forum, color, title, link, date, via_ddg, solved in new_results:
            self._search_idx += 1
            display = forum + (S["via_ddg"] if via_ddg else "")
            marker  = "★" if link in self._bm_urls else ""

            row = self._res_table.rowCount()
            self._res_table.insertRow(row)

            item_n = QTableWidgetItem(marker)
            item_n.setData(Qt.ItemDataRole.UserRole, link)
            item_n.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_f = QTableWidgetItem(display)
            item_f.setForeground(QBrush(QColor(color)))
            font_f = item_f.font()
            font_f.setBold(True)
            item_f.setFont(font_f)

            item_t = QTableWidgetItem(title)
            font_t = item_t.font()
            font_t.setWeight(QFont.Weight.DemiBold)
            item_t.setFont(font_t)

            item_d = QTableWidgetItem(date)

            item_s = QTableWidgetItem("✓" if solved else "")
            item_s.setForeground(QBrush(QColor("#4caf50")))
            item_s.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self._res_table.setItem(row, 0, item_n)
            self._res_table.setItem(row, 1, item_f)
            self._res_table.setItem(row, 2, item_t)
            self._res_table.setItem(row, 3, item_d)
            self._res_table.setItem(row, 4, item_s)

            self._results.append((self._search_idx, forum, color, title, link, date, via_ddg, solved))

        if ddg_empty_name:
            self._ddg_empty.append(ddg_empty_name)
        if unreachable_name:
            self._unreachable.append(unreachable_name)

        self._search_done += 1
        total = len(self._results)
        tab_label = f"{S['tab_results']} ({total})"
        self._notebook.setTabText(0, tab_label)

        if self._search_done < self._search_total:
            self._set_status(
                f"{S['fetching'].format(self._search_query)}"
                f"  ({self._search_done}/{self._search_total})"
            )
        else:
            sources = len({r[1] for r in self._results})
            status  = S["done"].format(total, sources)
            if self._ddg_empty:
                status += "  ·  " + ", ".join(self._ddg_empty) + ": no results (DDG — try again)"
            if self._unreachable:
                status += "  ·  ⚠ " + ", ".join(self._unreachable) + ": unreachable"
            self._set_status(status)
            self._spinner_lbl.setVisible(False)
            self._btn.setEnabled(True)
            self._busy = False
            self._res_table.setSortingEnabled(True)

        if new_results and not self._tab_switched:
            self._notebook.setCurrentIndex(0)
            self._tab_switched = True

    # ── Result interactions ───────────────────────────────────────────────────
    def _result_link_for_row(self, row: int) -> str:
        item = self._res_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if obj is self._res_table:
                row = self._res_table.currentRow()
                if row >= 0:
                    link = self._result_link_for_row(row)
                    if link:
                        self._open_url(link)
                return True
            if obj is self._bm_table:
                self._bm_open()
                return True
            if obj is self._hist_table:
                self._hist_rerun()
                return True
        return super().eventFilter(obj, event)

    def _on_result_double_click(self, item):
        link = self._result_link_for_row(item.row())
        if link:
            self._open_url(link)

    def _result_selected_rows(self) -> list[int]:
        return sorted({idx.row() for idx in self._res_table.selectedIndexes()})

    def _on_result_context_menu(self, pos):
        row = self._res_table.rowAt(pos.y())
        if row < 0:
            row = self._res_table.currentRow()
            if row < 0:
                return
            rect = self._res_table.visualRect(
                self._res_table.model().index(row, 2)
            )
            pos = rect.bottomLeft()

        selected = self._result_selected_rows()
        if row not in selected:
            self._res_table.selectRow(row)
            selected = [row]

        links = [self._result_link_for_row(r) for r in selected]
        links = [l for l in links if l]
        if not links:
            return

        menu = QMenu(self)
        n = len(links)

        if n == 1:
            link  = links[0]
            forum = self._res_table.item(row, 1).text() if self._res_table.item(row, 1) else ""
            title = self._res_table.item(row, 2).text() if self._res_table.item(row, 2) else ""
            solved_item = self._res_table.item(row, 4)
            solved = solved_item.text() if solved_item else ""
            already_bm = link in {r[2] for r in self._bm_data}
            menu.addAction(S["ctx_open"], lambda: self._open_url(link))
            menu.addAction(S["ctx_copy"], lambda: self._copy(link))
            if already_bm:
                menu.addAction(S["ctx_bm_remove"], lambda: self._bm_remove_by_link(link))
            else:
                menu.addAction(S["ctx_bm"], lambda: self._add_bookmark(forum, title, link, solved))
        else:
            bm_urls = {r[2] for r in self._bm_data}
            to_add    = [r for r in selected if self._result_link_for_row(r) not in bm_urls]
            to_remove = [r for r in selected if self._result_link_for_row(r) in bm_urls]

            menu.addAction(f"Open {n} in browser", lambda: self._open_results_multi(selected))
            if to_add:
                menu.addAction(
                    f"Add {len(to_add)} to bookmarks",
                    lambda rows=to_add: self._bookmark_results_multi(rows),
                )
            if to_remove:
                menu.addAction(
                    f"Remove {len(to_remove)} bookmark(s)",
                    lambda rows=to_remove: self._unbookmark_results_multi(rows),
                )

        menu.exec(self._res_table.viewport().mapToGlobal(pos))

    def _on_result_hover(self, event):
        item = self._res_table.itemAt(event.pos())
        if item:
            link = self._result_link_for_row(item.row())
            if link != self._hover_link:
                self._hover_link = link
                self._hover_lbl.setText(link)
        else:
            self._hover_link = None
            self._hover_lbl.setText("")
        QTableWidget.mouseMoveEvent(self._res_table, event)

    def _on_result_hover_leave(self, event):
        self._hover_link = None
        self._hover_lbl.setText("")
        QTableWidget.leaveEvent(self._res_table, event)

    def _open_results_multi(self, rows: list[int]):
        links = [self._result_link_for_row(r) for r in rows]
        links = [l for l in links if l]
        if not links:
            return
        if len(links) > 5:
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Question)
            mb.setWindowTitle("Open multiple")
            mb.setText(f"Open {len(links)} tabs in your browser?")
            mb.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            mb.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if mb.exec() != QMessageBox.StandardButton.Ok:
                return
        for url in links:
            self._open_url(url)

    def _bookmark_results_multi(self, rows: list[int]):
        bm_urls = self._bookmarked_urls()
        added = 0
        for r in rows:
            link  = self._result_link_for_row(r)
            if not link or link in bm_urls:
                continue
            forum = self._res_table.item(r, 1).text() if self._res_table.item(r, 1) else ""
            title = self._res_table.item(r, 2).text() if self._res_table.item(r, 2) else ""
            solved_item = self._res_table.item(r, 4)
            solved = solved_item.text() if solved_item else ""
            self._add_bookmark(forum, title, link, solved)
            bm_urls.add(link)
            added += 1
        if added:
            self._set_status(f"{added} bookmark(s) added.")

    def _unbookmark_results_multi(self, rows: list[int]):
        links = {self._result_link_for_row(r) for r in rows}
        links.discard("")
        to_remove = {bm[2] for bm in self._bm_data} & links
        if not to_remove:
            return
        self._bm_undo_data = [bm for bm in self._bm_data if bm[2] in to_remove]
        self._bm_data      = [bm for bm in self._bm_data if bm[2] not in to_remove]
        self._bm_refresh()
        for link in to_remove:
            self._mark_result_bookmarked(link, False)
        self._save_bookmarks()
        self._set_status(f"{len(to_remove)} bookmark(s) removed.")
        self._undo_btn.setVisible(True)

    # ── Bookmarks ─────────────────────────────────────────────────────────────
    def _add_bookmark(self, forum: str, title: str, link: str, solved: str = ""):
        date  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        color = _FORUM_COLOR.get(forum, "#cdd6f4")
        with open(BOOKMARK_FILE, "a") as f:
            f.write(f"[{forum}] {title} - {link}|||{date}|||{solved}\n")
        self._bm_data.append([forum, title, link, date, color, solved])
        self._bm_refresh()
        self._mark_result_bookmarked(link, True)
        self._set_status(S["bm_added"].format(title))

    def _mark_result_bookmarked(self, link: str, bookmarked: bool):
        marker = "★" if bookmarked else ""
        for row in range(self._res_table.rowCount()):
            item = self._res_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == link:
                item.setText(marker)

    def _bookmarked_urls(self) -> set:
        return {row[2] for row in self._bm_data}

    def _bm_refresh(self, *_):
        text = self._bm_filter.text().strip().lower()
        self._bm_table.setSortingEnabled(False)
        self._bm_table.setRowCount(0)
        for row in self._bm_data:
            forum, title, link, date, color, solved = row
            if text and not (text in forum.lower() or text in title.lower() or text in link.lower()):
                continue
            r = self._bm_table.rowCount()
            self._bm_table.insertRow(r)

            item_f = QTableWidgetItem(forum)
            item_f.setForeground(QBrush(QColor(color)))
            font_f = item_f.font()
            font_f.setBold(True)
            item_f.setFont(font_f)
            item_f.setData(Qt.ItemDataRole.UserRole, link)

            item_t = QTableWidgetItem(title)
            font_t = item_t.font()
            font_t.setWeight(QFont.Weight.DemiBold)
            item_t.setFont(font_t)

            item_s = QTableWidgetItem("✓" if solved else "")
            item_s.setForeground(QBrush(QColor("#4caf50")))
            item_s.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self._bm_table.setItem(r, 0, item_f)
            self._bm_table.setItem(r, 1, item_t)
            self._bm_table.setItem(r, 2, QTableWidgetItem(date))
            self._bm_table.setItem(r, 3, item_s)
        self._bm_table.setSortingEnabled(True)

    def _load_bookmarks(self):
        self._bm_data = []
        if not os.path.exists(BOOKMARK_FILE):
            self._bm_refresh()
            return
        with open(BOOKMARK_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    forum = line.split("]")[0].lstrip("[")
                    rest  = line.split("] ", 1)[1]
                    parts  = rest.split("|||")
                    body   = parts[0]
                    date   = parts[1] if len(parts) > 1 else ""
                    solved = parts[2] if len(parts) > 2 else ""
                    cut = body.rfind(" - http")
                    if cut == -1:
                        cut = body.rfind(" - ")
                    title = body[:cut]
                    link  = body[cut + 3:]
                    color = _FORUM_COLOR.get(forum, "#cdd6f4")
                    self._bm_data.append([forum, title, link, date, color, solved])
                except Exception:
                    pass
        self._bm_refresh()

    def _bm_selected_links(self) -> set:
        links = set()
        for item in self._bm_table.selectedItems():
            if item.column() == 0:
                links.add(item.data(Qt.ItemDataRole.UserRole))
        return links

    def _bm_open(self):
        links = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._bm_table.selectedItems()
            if item.column() == 0
        ]
        if not links:
            return
        if len(links) > 5:
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Question)
            mb.setWindowTitle("Open multiple")
            mb.setText(f"Open {len(links)} tabs in your browser?")
            mb.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            mb.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if mb.exec() != QMessageBox.StandardButton.Ok:
                return
        for url in links:
            self._open_url(url)

    def _bm_copy(self):
        links = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._bm_table.selectedItems()
            if item.column() == 0
        ]
        if links:
            self._copy("\n".join(links))

    def _bm_remove(self):
        links = self._bm_selected_links()
        if not links:
            return
        if len(links) > 5 and self._bm_bulk_confirm:
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Warning)
            mb.setWindowTitle("Confirm Delete")
            mb.setText(f"Delete {len(links)} bookmarks?")
            mb.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            mb.setDefaultButton(QMessageBox.StandardButton.Cancel)
            from PyQt6.QtWidgets import QCheckBox as QCB
            dont_ask = QCB("Don't ask again")
            mb.setCheckBox(dont_ask)
            if mb.exec() != QMessageBox.StandardButton.Ok:
                return
            if dont_ask.isChecked():
                self._bm_bulk_confirm = False
                self._save_settings()

        self._bm_undo_data = [r for r in self._bm_data if r[2] in links]
        self._bm_data = [r for r in self._bm_data if r[2] not in links]
        self._bm_refresh()
        self._save_bookmarks()
        self._set_status(S["bm_removed"])
        self._undo_btn.setVisible(True)

    def _bm_remove_by_link(self, link: str):
        self._bm_undo_data = [r for r in self._bm_data if r[2] == link]
        self._bm_data = [r for r in self._bm_data if r[2] != link]
        self._bm_refresh()
        self._mark_result_bookmarked(link, False)
        self._save_bookmarks()
        self._set_status(S["bm_removed"])
        self._undo_btn.setVisible(True)

    def _bm_undo(self):
        if not self._bm_undo_data:
            return
        self._bm_data.extend(self._bm_undo_data)
        self._bm_undo_data = []
        self._bm_refresh()
        self._save_bookmarks()
        self._undo_btn.setVisible(False)
        self._set_status("Undo: bookmark(s) restored.")

    def _save_bookmarks(self):
        with open(BOOKMARK_FILE, "w") as fh:
            for f, t, l, d, _, s in self._bm_data:
                fh.write(f"[{f}] {t} - {l}|||{d}|||{s}\n")

    def _on_bm_double_click(self, item):
        link = None
        for col_item in [self._bm_table.item(item.row(), 0)]:
            if col_item:
                link = col_item.data(Qt.ItemDataRole.UserRole)
        if link:
            self._open_url(link)

    def _on_bm_del_key(self):
        if self._notebook.currentIndex() == 1:
            self._bm_remove()

    # ── History ───────────────────────────────────────────────────────────────
    def _log_history(self, query: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(HISTORY_FILE, "a") as f:
            f.write(f"{ts} - {query}\n")
        self._hist_table.insertRow(0)
        self._hist_table.setItem(0, 0, QTableWidgetItem(ts))
        self._hist_table.setItem(0, 1, QTableWidgetItem(query))
        self._completion_add(query)

    def _load_history(self):
        self._hist_table.setRowCount(0)
        if not os.path.exists(HISTORY_FILE):
            return
        rows = []
        with open(HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ts, query = line.split(" - ", 1)
                    rows.append((ts, query))
                except Exception:
                    pass
        for ts, query in reversed(rows):
            r = self._hist_table.rowCount()
            self._hist_table.insertRow(r)
            self._hist_table.setItem(r, 0, QTableWidgetItem(ts))
            self._hist_table.setItem(r, 1, QTableWidgetItem(query))

    def _hist_rerun(self):
        row = self._hist_table.currentRow()
        if row >= 0:
            item = self._hist_table.item(row, 1)
            if item:
                self._entry.setText(item.text())
                self._on_search()
                self._notebook.setCurrentIndex(0)

    def _hist_clear(self):
        self._hist_table.setRowCount(0)
        open(HISTORY_FILE, "w").close()
        # Reset completion to seeds
        self._completion_list.clear()
        self._completion_seen.clear()
        self._live_count = 0
        for term in _SEED_TERMS:
            key = term.lower()
            if key not in self._completion_seen:
                self._completion_seen.add(key)
                self._completion_list.append(term)
        self._completion_model.setStringList(self._completion_list)

    def _on_hist_double_click(self, item):
        row = item.row()
        q_item = self._hist_table.item(row, 1)
        if q_item:
            self._entry.setText(q_item.text())
            self._on_search()
            self._notebook.setCurrentIndex(0)

    # ── Keyboard shortcuts ────────────────────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Tab"),       self).activated.connect(self._tab_next)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(self._tab_prev)
        QShortcut(QKeySequence("Ctrl+L"),      self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("Ctrl+F"),      self).activated.connect(self._toggle_forums_bar)
        QShortcut(QKeySequence("F5"),          self).activated.connect(self._on_search)
        QShortcut(QKeySequence("F6"),          self).activated.connect(self._focus_active_table)
        QShortcut(QKeySequence("Escape"),      self).activated.connect(self._clear_search)
        QShortcut(QKeySequence("Delete"),      self).activated.connect(self._on_bm_del_key)
        QShortcut(QKeySequence("Ctrl+Z"),      self).activated.connect(self._bm_undo)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._on_results_open_selected)
        QShortcut(QKeySequence("Ctrl+B"),      self).activated.connect(self._on_results_bookmark_selected)
        QShortcut(QKeySequence("?"),           self).activated.connect(self._show_shortcuts)

    def _tab_next(self):
        navigable = self._notebook.count() - 1   # exclude About tab
        page = min(self._notebook.currentIndex(), navigable - 1)
        self._notebook.setCurrentIndex((page + 1) % navigable)

    def _tab_prev(self):
        navigable = self._notebook.count() - 1   # exclude About tab
        page = min(self._notebook.currentIndex(), navigable - 1)
        self._notebook.setCurrentIndex((page - 1) % navigable)

    def _focus_active_table(self):
        self._completer.popup().hide()
        self._entry.clearFocus()
        idx = self._notebook.currentIndex()
        if idx == 0:
            self._res_table.setFocus(Qt.FocusReason.ShortcutFocusReason)
            if not self._result_selected_rows() and self._res_table.rowCount() > 0:
                self._res_table.selectRow(0)
        elif idx == 1:
            self._bm_table.setFocus(Qt.FocusReason.ShortcutFocusReason)
            if not self._bm_table.selectedItems() and self._bm_table.rowCount() > 0:
                self._bm_table.selectRow(0)
        elif idx == 2:
            self._hist_table.setFocus(Qt.FocusReason.ShortcutFocusReason)
            if not self._hist_table.selectedItems() and self._hist_table.rowCount() > 0:
                self._hist_table.selectRow(0)

    def _on_results_open_selected(self):
        if self._notebook.currentIndex() != 0 or self._entry.hasFocus():
            return
        rows = self._result_selected_rows()
        if rows:
            self._open_results_multi(rows)

    def _on_results_bookmark_selected(self):
        if self._notebook.currentIndex() != 0 or self._entry.hasFocus():
            return
        rows = self._result_selected_rows()
        if not rows:
            return
        bm_urls = self._bookmarked_urls()
        all_bookmarked = all(self._result_link_for_row(r) in bm_urls for r in rows)
        if all_bookmarked:
            self._unbookmark_results_multi(rows)
        else:
            self._bookmark_results_multi(rows)

    def _focus_search(self):
        self._entry.setFocus()
        self._entry.selectAll()

    def _clear_search(self):
        self._entry.clear()
        self._entry.setFocus()

    # ── Settings persist ──────────────────────────────────────────────────────
    def _load_settings(self):
        try:
            with open(SETTINGS_FILE) as f:
                cfg = json.load(f)
            self.resize(cfg.get("width", 820), cfg.get("height", 520))
            self._hits_spin.setValue(cfg.get("hits", DEFAULT_HITS))
            self._forums_bar_visible = cfg.get("forums_bar_visible", True)
            self._forums_bar.setVisible(self._forums_bar_visible)
            self._forums_toggle.setText("Forums ▾" if self._forums_bar_visible else "Forums ▸")
            self._bm_bulk_confirm = cfg.get("bm_bulk_confirm", True)
            for name, state in cfg.get("forums", {}).items():
                if name in self._checks:
                    self._checks[name].setChecked(state)
        except Exception:
            pass

    def _save_settings(self):
        try:
            cfg = {
                "width":              self.width(),
                "height":             self.height(),
                "hits":               self._hits_spin.value(),
                "forums_bar_visible": self._forums_bar_visible,
                "bm_bulk_confirm":    self._bm_bulk_confirm,
                "forums":             {n: cb.isChecked() for n, cb in self._checks.items()},
            }
            with open(SETTINGS_FILE, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def closeEvent(self, event):
        self._save_settings()
        event.accept()

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _open_url(url: str):
        subprocess.Popen(["xdg-open", url],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    @staticmethod
    def _copy(text: str):
        QApplication.clipboard().setText(text)


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationVersion(_VERSION)
    app.setDesktopFileName("forum-scout-qt")
    win = ScoutWindow()
    win.show()
    sys.exit(app.exec())

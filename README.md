# Forum Scout

A lightweight PyQt6 desktop app that searches multiple Arch-based Linux forums at once. Built for KDE and Qt-based desktops.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![PyQt6](https://img.shields.io/badge/PyQt-6-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

![result](images/result.png)

![info](images/info.png)

---

## Features

- **Multi-source search** — query Discourse forums, Arch Wiki and Arch BBS in one go
- **Sortable results** — click any column header to sort by forum, title or date
- **Bookmarks** — save topics, open or copy links, filter and sort · results marked ★ when already bookmarked · remove directly from the results list · multi-select delete with `Del` · undo last delete with `Ctrl+Z`
- **Search history** — re-run any previous search with one click
- **Forums toggle** — hide the forum selector with the **Forums ▾** button to free up space for results
- **Dropdown suggestions** — live topic suggestions as you type (press Space)
- **Color-coded forums** — consistent colors across Results and Bookmarks tabs
- **Hover tooltip** — full URL shown in the status bar on mouse-over
- **Keyboard shortcuts** — `Ctrl+L` focus search · `Ctrl+F` toggle forums bar · `Escape` clear · `F5` re-run · `Del` delete bookmark(s) · `Ctrl+Z` undo delete
- **Persistent settings** — window size, hits per source, active forums and forums bar state saved on exit
- **Shared config with GTK version** — bookmarks, history and settings are fully compatible; switching between the GTK and Qt versions loses nothing
- **Multilingual** — 18 languages auto-detected from `$LANG`: Arabic, Chinese, Danish, Dutch, English, Farsi, French, German, Greek, Hebrew, Japanese, Polish, Portuguese, Romanian, Russian, Spanish, Turkish, Ukrainian

---

## Sources

| Forum | Type | API |
|---|---|---|
| Mabox | Discourse | Discourse JSON |
| EndeavourOS | Discourse | Discourse JSON |
| Manjaro | Discourse | Discourse JSON |
| CachyOS | Discourse | Discourse JSON |
| Garuda | Discourse | Discourse JSON |
| RebornOS | Discourse | Discourse JSON |
| Arch Wiki | Wiki | MediaWiki JSON |
| Manjaro Wiki | Wiki | MediaWiki JSON |
| Arch BBS | BBS | DuckDuckGo site-search *(off by default)* |
| KDE | DE | Discourse JSON |
| GNOME | DE | Discourse JSON |

---

## Install for Arch

repo:

- Mabox
- Manjaro
- AUR

```bash
yay -S forum-scout-qt
pacman -S forum-scout-qt
```

> Installs as `forum-scout` and conflicts with the GTK version — only one can be active at a time, but all your data carries over when switching.

---

## GTK version

Looking for the GTK3 version? → [github.com/musqz/forum-scout](https://github.com/musqz/forum-scout)

---

## Disclaimer

Parts of this tool were built with AI assistance (Claude Sonnet by Anthropic). All code has been reviewed and tested by me.

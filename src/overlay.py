"""Game hit HUD: always-topmost click-through cards.

Must stay visible over borderless-windowed games. Exclusive fullscreen
covers it — that is a Windows limitation, not a bug in this file.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020

user32 = ctypes.windll.user32
user32.SetWindowPos.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint,
]


def _format_candidates(items: list[dict]) -> str:
    return " · ".join(
        f"{item['grid'].replace('x', '×')} {item['name']}" if item.get("grid") else item["name"]
        for item in items
    )


@dataclass
class OverlayConfig:
    x: int = 40
    y: int = 180
    width: int = 380
    opacity: float = 0.82
    duration_ms: int = 2800
    max_simultaneous: int = 3
    show_score: bool = True
    bg: str = "#121a26"
    bg_hit: str = "#123528"
    fg: str = "#f2f8ff"
    accent: str = "#2ee59d"
    title: str = "SoundRadar-X"
    language: str = "zh"


class Overlay:
    def __init__(self, cfg: OverlayConfig | None = None) -> None:
        self.cfg = cfg or OverlayConfig()
        self._thread: threading.Thread | None = None
        self._hits: list[tuple[str, float, float, float, str, dict, bool]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._ok = False
        self._hwnd = 0

    @property
    def ok(self) -> bool:
        return self._ok

    @property
    def hwnd(self) -> int:
        return self._hwnd

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sradar-hud")
        self._thread.start()
        self._ready.wait(timeout=8.0)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def show_hit(
        self,
        name: str,
        score: float,
        margin: float,
        item_id: str = "",
        icon_path: str | None = None,
        candidate_hints: dict | None = None,
        unique: bool = False,
    ) -> None:
        now = time.time()
        with self._lock:
            self._hits.append((name, score, margin, now, icon_path or "", candidate_hints or {}, unique))
            self._hits = self._hits[-self.cfg.max_simultaneous :]

    def _force_topmost(self, hwnd: int) -> None:
        try:
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass

    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception as e:
            print(f"[hud] tkinter failed: {e}", file=sys.stderr)
            self._ready.set()
            return

        root = tk.Tk()
        root.withdraw()
        root.title("SoundRadarX-HUD")
        w = self.cfg.width
        h = 100 * self.cfg.max_simultaneous + 8
        root.geometry(f"{w}x{h}+{self.cfg.x}+{self.cfg.y}")
        root.configure(bg=self.cfg.bg)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", self.cfg.opacity)
        except Exception:
            pass
        root.overrideredirect(True)
        root.update_idletasks()

        hwnd = int(root.winfo_id())
        parent = user32.GetParent(hwnd) or hwnd
        self._hwnd = parent or hwnd
        self._force_topmost(self._hwnd or hwnd)

        cards = []
        for _ in range(self.cfg.max_simultaneous):
            frame = tk.Frame(root, bg=self.cfg.bg)
            icon = tk.Label(frame, text="★", bg=self.cfg.bg, fg=self.cfg.accent, font=("Segoe UI", 20))
            icon.pack(side="left", padx=(10, 10), pady=8)
            right = tk.Frame(frame, bg=self.cfg.bg)
            right.pack(side="left", fill="both", expand=True, pady=8)
            name_lab = tk.Label(right, text="", bg=self.cfg.bg, fg=self.cfg.fg,
                                font=("Microsoft YaHei UI", 14, "bold"), anchor="w")
            name_lab.pack(fill="x")
            score_lab = tk.Label(right, text="", bg=self.cfg.bg, fg=self.cfg.accent,
                                 font=("Consolas", 11, "bold"), anchor="w")
            score_lab.pack(fill="x")
            gold_lab = tk.Label(right, text="", bg=self.cfg.bg, fg="#ffd166",
                                font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
                                justify="left", wraplength=max(150, w - 90))
            non_gold_lab = tk.Label(right, text="", bg=self.cfg.bg, fg="#b8c5d6",
                                    font=("Microsoft YaHei UI", 9), anchor="w",
                                    justify="left", wraplength=max(150, w - 90))
            bar_bg = tk.Frame(right, bg="#223046", height=6)
            bar_bg.pack(fill="x", pady=(4, 0))
            bar_bg.pack_propagate(False)
            bar_fg = tk.Frame(bar_bg, bg=self.cfg.accent, height=6)
            bar_fg.place(x=0, y=0, relheight=1.0, relwidth=0.0)
            cards.append({"frame": frame, "icon": icon, "name": name_lab,
                          "score": score_lab, "gold": gold_lab, "non_gold": non_gold_lab,
                          "bar": bar_fg})

        self._ok = True
        self._ready.set()
        # stay hidden until first hit
        root.withdraw()

        def load_icon(path: str):
            if not path or not Path(path).exists():
                return None
            if not hasattr(self, "_ic"):
                self._ic = {}
            if path not in self._ic:
                try:
                    img = tk.PhotoImage(file=path)
                    ww, hh = int(img.width()), int(img.height())
                    if max(ww, hh) > 52:
                        f = max(1, max(ww, hh) // 52)
                        img = img.subsample(f, f)
                    self._ic[path] = img
                except Exception:
                    return None
            return self._ic[path]

        def tick() -> None:
            if self._stop.is_set():
                try:
                    root.destroy()
                except Exception:
                    pass
                return

            now = time.time()
            with self._lock:
                hits = [h for h in self._hits if now - h[3] < self.cfg.duration_ms / 1000.0]
                self._hits = hits
            show = list(reversed(hits))[: self.cfg.max_simultaneous]

            if not show:
                # no hits → fully hide (no constant strip)
                root.withdraw()
                root.after(100, tick)
                return

            self._force_topmost(self._hwnd or hwnd)
            root.deiconify()
            root.attributes("-topmost", True)

            for i, card in enumerate(cards):
                if i < len(show):
                    name, score, margin, t, icon_path, candidate_hints, unique = show[i]
                    flash = (now - t) < 0.35
                    bg = self.cfg.bg_hit if flash else self.cfg.bg
                    card["frame"].configure(bg=bg)
                    card["icon"].configure(bg=bg)
                    card["name"].configure(bg=bg)
                    card["score"].configure(bg=bg)
                    card["frame"].pack(fill="x", padx=4, pady=2)
                    card["name"].config(text="★ " + name[:14])
                    card["score"].config(text=f"{score:.2f}  ·  margin {margin:.2f}")
                    gold_items = candidate_hints.get("gold", [])
                    non_gold_items = candidate_hints.get("nonGold", [])

                    is_english = self.cfg.language == "en"
                    gold_text = ("Unique Red Item" if is_english else "唯一类大金") if unique else (
                        ("Possible Red Item: " if is_english else "大金可能：") + _format_candidates(gold_items) if gold_items else ""
                    )
                    non_gold_text = (
                        ("Possible non-Red Item: " if is_english else "非大金：") + _format_candidates(non_gold_items) if non_gold_items else ""
                    )
                    if gold_text:
                        card["gold"].configure(text=gold_text)
                        card["gold"].pack(fill="x")
                    else:
                        card["gold"].pack_forget()
                    if non_gold_text:
                        card["non_gold"].configure(text=non_gold_text)
                        card["non_gold"].pack(fill="x")
                    else:
                        card["non_gold"].pack_forget()
                    card["bar"].place(x=0, y=0, relheight=1.0, relwidth=max(0.05, min(1.0, score)))
                    icon = load_icon(icon_path)
                    if icon is not None:
                        card["icon"].configure(image=icon, text="")
                        card["icon"].image = icon  # type: ignore
                    else:
                        card["icon"].configure(image="", text="★")
                else:
                    card["frame"].pack_forget()
            root.update_idletasks()
            visible_height = sum(cards[i]["frame"].winfo_reqheight() + 4 for i in range(len(show)))
            root.geometry(f"{w}x{max(1, visible_height)}+{self.cfg.x}+{self.cfg.y}")
            root.after(100, tick)

        root.after(100, tick)
        try:
            root.mainloop()
        except Exception:
            pass


def beep_hit() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass


def find_icon_for_name(items: list[dict], item_id: str, name: str) -> str | None:
    base = Path(__file__).resolve().parents[1] / "data" / "library" / "_raw" / "items"
    if item_id:
        cand = base / item_id / "icon.png"
        if cand.exists():
            return str(cand)
    for it in items:
        if it.get("id") == item_id or it.get("name") == name:
            cand = base / str(it.get("id", "")) / "icon.png"
            if cand.exists():
                return str(cand)
    return None

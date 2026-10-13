\
\
\
   

import queue as _queue
import threading
import time
import tkinter as tk
from urllib.parse import quote

from . import lazy
from .config import (
    BG_DARK, BG_CARD, BG_HOVER, ACCENT, TEXT_PRI, TEXT_MUTED,
    COL_FOUND, COL_NOTFOUND, COL_LOADING, COL_ERROR, BORDER,
)
from .utils import clean


                                                                                
_DRIVER_POOL_SIZE    = 3
_driver_pool         = _queue.Queue()
_drivers_init_lock   = threading.Lock()
_drivers_initialized = False
_pool_ready          = threading.Event()


def close_driver_pool():
    while True:
        try:
            _driver_pool.get_nowait().quit()
        except _queue.Empty:
            break
        except Exception:
            pass


def init_driver_pool():
    global _drivers_initialized
    with _drivers_init_lock:
        if _drivers_initialized:
            return
        _drivers_initialized = True

    Driver, _ = lazy.get_seleniumbase()
    for _i in range(_DRIVER_POOL_SIZE):
        try:
            d = Driver(uc=True, headless=True, disable_gpu=True, no_sandbox=True)
            _driver_pool.put(d)
            _pool_ready.set()
        except Exception as exc:
            print(f"[driver-pool] Failed to create driver: {exc}")


def _wait_for_page(driver, timeout=20):
    _, WebDriverWait = lazy.get_seleniumbase()
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def _wait_for_content(driver, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            html = driver.page_source or ""
            low = html.lower()
            if any(s in low for s in (
                "just a moment", "checking your browser", "verifying you are human"
            )):
                time.sleep(1)
                continue
            if len(html) > 1000:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def load_page_with_browser(url: str) -> str:
    init_driver_pool()
    _pool_ready.wait()
    drv = _driver_pool.get()
    try:
        opener = getattr(drv, "uc_open_with_reconnect", None)
        if callable(opener):
            opener(url, 8)
        else:
            drv.get(url)
        _wait_for_page(drv)
        _wait_for_content(drv)
        return drv.page_source
    finally:
        _driver_pool.put(drv)


                                                                                
def _soup(html: str):
    BeautifulSoup = lazy.get_bs4()
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _build_url(site: dict, query: str) -> str:
    return f"{site['query_url']}{quote(query, safe='')}"


def _extract_links(html: str, query: str, site_url: str):
    q    = clean(query)
    soup = _soup(html)
    seen = set()
    base = site_url.rstrip("/")
    links = []
    for a in soup.find_all("a", href=True):
        text = clean(a.get_text(" ", strip=True))
        if not text or q not in text:
            continue
        href = a["href"]
        if not href.startswith("http"):
            href = f"{base}/{href.lstrip('/')}"
        if href not in seen:
            seen.add(href)
            links.append(href)
    return links


                                                                                
_GOG_API   = "https://gog-games.to/api/web/all-games"
_gog_lock  = threading.Lock()
_gog_index = None


def _ensure_gog_cache():
    global _gog_index
    with _gog_lock:
        if _gog_index is None:
            try:
                httpx = lazy.get_httpx()
                resp = httpx.get(_GOG_API, timeout=10)
                resp.raise_for_status()
                _gog_index = {g["slug"]: clean(g.get("title", "")) for g in resp.json()}
            except Exception:
                _gog_index = {}
    return _gog_index


def _check_gog(site: dict, query: str) -> str:
    q = clean(query)
    for _, title in _ensure_gog_cache().items():
        if q in title:
            return "found"
    return "not_found"


                                                                                
def _check_generic(site: dict, query: str) -> str:
    url  = _build_url(site, query)
    html = None

    if not site.get("requires_selenium", False):
        try:
            httpx = lazy.get_httpx()
            resp = httpx.get(url, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 404:
                return "not_found"
            if resp.status_code < 400:
                candidate = resp.text
                low = candidate.lower()
                is_challenge = (
                    "just a moment" in low
                    or "checking your browser" in low
                    or "verifying you are human" in low
                    or "enable javascript" in low
                    or len(candidate) < 150
                )
                if not is_challenge:
                    html = candidate
        except Exception:
            pass

    if html is None:
        try:
            html = load_page_with_browser(url)
        except Exception:
            return "error"

    if not html or len(html) < 150:
        return "not_found"

    return "found" if _extract_links(html, query, site["url"]) else "not_found"


_SITE_DISPATCH = {"https://gog-games.to": _check_gog}

_SITE_CHECK_CACHE: dict = {}
_SITE_CHECK_CACHE_TTL = 60


def check_site_for_game(site: dict, game_name: str) -> str:
    cache_key = (site["url"], game_name)
    now = time.time()
    cached = _SITE_CHECK_CACHE.get(cache_key)
    if cached and now - cached[1] < _SITE_CHECK_CACHE_TTL:
        return cached[0]
    url = site.get("url", "")
    for prefix, handler in _SITE_DISPATCH.items():
        if url.startswith(prefix):
            result = handler(site, game_name)
            break
    else:
        result = _check_generic(site, game_name)
    _SITE_CHECK_CACHE[cache_key] = (result, now)
    return result


_ONLINE_FIX_CACHE     = {}
_ONLINE_FIX_CACHE_TTL = 15


def check_online_fix(site: dict, clean_search_name: str):
                                                                          
    now = time.time()
    cached = _ONLINE_FIX_CACHE.get(clean_search_name)
    if cached and now - cached[1] < _ONLINE_FIX_CACHE_TTL:
        return cached[0]

    try:
        httpx = lazy.get_httpx()
        url   = site["query_url"] + quote(clean_search_name, safe="")
        resp  = httpx.get(url, timeout=10)
        if resp.status_code < 400:
            html = resp.text
            low  = html.lower()
            is_challenge = (
                "just a moment" in low
                or "checking your browser" in low
                or "verifying you are human" in low
                or len(html) < 150
            )
            if not is_challenge:
                links = _extract_links(html, clean_search_name, site["url"])
                result = "found" if links else "not_found"
                _ONLINE_FIX_CACHE[clean_search_name] = (result, now)
                return result
        result = check_site_for_game(site, clean_search_name)
    except Exception:
        result = check_site_for_game(site, clean_search_name)

    _ONLINE_FIX_CACHE[clean_search_name] = (result, now)
    return result


                                                                                
class ScrollFrame(tk.Frame):
\
\
\
\
\
       

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)

        self.canvas = tk.Canvas(
            self,
            bg=BG_DARK,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )

        self.sb = tk.Scrollbar(
            self,
            orient="vertical",
            command=self._scrollbar_command,
        )
        self.inner = tk.Frame(
            self.canvas,
            bg=BG_DARK,
            highlightthickness=0,
            bd=0,
        )

        self._win = self.canvas.create_window(
            0,
            0,
            window=self.inner,
            anchor="nw",
        )

        self.canvas.configure(
            yscrollcommand=self.sb.set,
        )

        self.canvas.pack(
            side="left",
            fill="both",
            expand=True,
        )

        self.sb.pack(
            side="right",
            fill="y",
        )

                               
        self._cfg_job = None
        self._redraw_job = None

                               
        self._canvas_width = 1

                                                                      
                           
                                                                      

        self.inner.bind(
            "<Configure>",
            self._on_inner_config,
        )

        self.canvas.bind(
            "<Configure>",
            self._on_canvas_config,
        )

                                                                  
              
                                                                  
    def _scrollbar_command(self, *args):
                                                                    
        try:
            self.canvas.yview(*args)
            self._schedule_redraw()
        except tk.TclError:
            pass
        
    def _on_inner_config(self, _e=None):
                                                                         

        if self._cfg_job is not None:
            try:
                self.after_cancel(self._cfg_job)
            except Exception:
                pass

        self._cfg_job = self.after(
            10,
            self._apply_scrollregion,
        )

    def _apply_scrollregion(self):
        self._cfg_job = None

        try:
            bbox = self.canvas.bbox(self._win)

            if bbox:
                self.canvas.configure(
                    scrollregion=bbox,
                )

        except tk.TclError:
            pass

    def _on_canvas_config(self, event):
                                                                   

        try:
            width = max(1, int(event.width))

            if width != self._canvas_width:
                self._canvas_width = width

                self.canvas.itemconfigure(
                    self._win,
                    width=width,
                )

                                                                     
                                              
                self._schedule_redraw()

        except tk.TclError:
            pass

                                                                  
               
                                                                  

    def _scroll(self, event):
                                         

        try:
            delta = event.delta

            if delta:
                                           
                units = int(-delta / 120)

                                                         
                if units == 0:
                    units = -1 if delta > 0 else 1

                self.canvas.yview_scroll(
                    units,
                    "units",
                )

            elif getattr(event, "num", None) == 4:
                                      
                self.canvas.yview_scroll(
                    -3,
                    "units",
                )

            elif getattr(event, "num", None) == 5:
                                        
                self.canvas.yview_scroll(
                    3,
                    "units",
                )

            self._schedule_redraw()

        except tk.TclError:
            pass

                                                                  
                     
                                                                  

    def _schedule_redraw(self):
                                                   

        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except Exception:
                pass

        self._redraw_job = self.after(
            8,
            self._finish_redraw,
        )

    def _finish_redraw(self):
                                                        

        self._redraw_job = None

        try:
            self.canvas.update_idletasks()

                                                                      
                                                                
            bbox = self.canvas.bbox(self._win)

            if bbox:
                self.canvas.configure(
                    scrollregion=bbox,
                )

        except tk.TclError:
            pass

                                                                  
           
                                                                  

    def clear(self):
                                                                      

        try:
            for widget in self.inner.winfo_children():
                widget.destroy()

            self.canvas.yview_moveto(0)

                                                   
            if self._cfg_job is not None:
                try:
                    self.after_cancel(self._cfg_job)
                except Exception:
                    pass

                self._cfg_job = None

                                                                
            self._apply_scrollregion()

            self._schedule_redraw()

        except tk.TclError:
            pass

class ChipGrid(tk.Canvas):
\
                                                                               

    def __init__(self, parent, sites, cols=3, chip_h=52, gap=4, on_click=None):
        self.sites    = sites
        self.cols     = cols
        self.chip_h   = chip_h
        self.gap      = gap
        self.on_click = on_click
        rows = (len(sites) + cols - 1) // cols
        super().__init__(parent, bg=BG_DARK, highlightthickness=0, bd=0,
                         height=rows * (chip_h + gap) - gap)
        self.items = {}
        for idx, site in enumerate(sites):
            tag     = f"chip{idx}"
            starred = "\u2b50" in site["name"]
            label   = ("\u2605 " if starred else "") + site["name"].replace(" \u2b50", "")
            rect   = self.create_rectangle(0, 0, 1, 1, fill=BG_CARD, outline="", tags=(tag,))
            dot    = self.create_rectangle(0, 0, 7, 7, fill=COL_LOADING, outline="", tags=(tag,))
            name   = self.create_text(0, 0, text=label, anchor="nw", fill=TEXT_MUTED,
                                      font=("Segoe UI", 8, "bold" if starred else "normal"),
                                      tags=(tag,))
            status = self.create_text(0, 0, text="checking\u2026", anchor="nw", fill=TEXT_MUTED,
                                      font=("Segoe UI", 7), tags=(tag,))
            self.items[site["name"]] = (rect, dot, name, status)
            self.tag_bind(tag, "<Enter>",    lambda e, r=rect: self._hover(r, True))
            self.tag_bind(tag, "<Leave>",    lambda e, r=rect: self._hover(r, False))
            self.tag_bind(tag, "<Button-1>",
                          lambda e, s=site: self.on_click and self.on_click(s))
        self.bind("<Configure>", self._layout)

    def _hover(self, rect, on):
        self.itemconfigure(rect, fill=BG_HOVER if on else BG_CARD)
        self.configure(cursor="hand2" if on else "")

    def _layout(self, _e=None):
        w  = max(self.winfo_width(), 100)
        cw = (w - self.gap * (self.cols - 1)) / self.cols
        for idx, site in enumerate(self.sites):
            r, c = divmod(idx, self.cols)
            x = c * (cw + self.gap)
            y = r * (self.chip_h + self.gap)
            rect, dot, name, status = self.items[site["name"]]
            self.coords(rect,   x, y, x + cw, y + self.chip_h)
            self.coords(dot,    x + 8, y + 11, x + 15, y + 18)
            self.coords(name,   x + 20, y + 7)
            self.coords(status, x + 8,  y + 28)

    def set_result(self, site_name, result):
        rect, dot, name, status = self.items[site_name]
        color = COL_FOUND if result == "found" else COL_NOTFOUND
        text  = ("Found \u2713" if result == "found"
                 else "Not found" if result == "not_found" else "Error")
        self.itemconfigure(dot, fill=color)
        self.itemconfigure(name, fill=TEXT_PRI if result == "found" else TEXT_MUTED)
        self.itemconfigure(status, text=text)
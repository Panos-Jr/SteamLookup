import tkinter as tk
from tkinter import font as tkfont


BG_DARK  = "#0a0d14"
BG_CARD  = "#13161f"
ACCENT   = "#4fc3f7"
GREEN    = "#81c784"
TEXT_PRI = "#e8eaf6"
TEXT_SEC = "#9ca3af"
BORDER   = "#1e2433"


def show_toast(title: str, line1: str, line2: str = "", duration_ms: int = 4000):
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", 0.0)           
    except Exception:
        pass

                              
    wrap = tk.Frame(root, bg=BORDER, padx=1, pady=1)
    wrap.pack()

    card = tk.Frame(wrap, bg=BG_CARD, padx=14, pady=10)
    card.pack()

    hdr = tk.Frame(card, bg=BG_CARD)
    hdr.pack(anchor="w", fill="x")

    tk.Label(hdr, text="☁", font=("Segoe UI Emoji", 14),
             bg=BG_CARD, fg=ACCENT).pack(side="left", padx=(0, 8))
    tk.Label(hdr, text=title, font=("Segoe UI", 10, "bold"),
             bg=BG_CARD, fg=TEXT_PRI).pack(side="left")

    body = tk.Frame(card, bg=BG_CARD)
    body.pack(anchor="w", fill="x", pady=(6, 0))

    tk.Label(body, text="✓", font=("Segoe UI", 11, "bold"),
             bg=BG_CARD, fg=GREEN).pack(side="left", padx=(0, 8))

    txt = tk.Frame(body, bg=BG_CARD)
    txt.pack(side="left", fill="x", expand=True)

    tk.Label(txt, text=line1, font=("Segoe UI", 9),
             bg=BG_CARD, fg=TEXT_PRI, anchor="w").pack(anchor="w")
    if line2:
        tk.Label(txt, text=line2, font=("Segoe UI", 8),
                 bg=BG_CARD, fg=TEXT_SEC, anchor="w").pack(anchor="w", pady=(2, 0))

                                       
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    margin = 20
    x = sw - w - margin
    y = sh - h - margin - 40                     
    root.geometry(f"+{x}+{y}")

                      
    def dismiss(_=None):
        try:
            root.destroy()
        except Exception:
            pass

    for wdg in (root, wrap, card, hdr, body, txt):
        wdg.bind("<Button-1>", dismiss)

             
    def fade_in(alpha=0.0):
        alpha += 0.1
        if alpha >= 1.0:
            try:
                root.attributes("-alpha", 1.0)
            except Exception:
                pass
            return
        try:
            root.attributes("-alpha", alpha)
            root.after(15, lambda: fade_in(alpha))
        except Exception:
            pass

    try:
        fade_in()
    except Exception:
        try:
            root.attributes("-alpha", 1.0)
        except Exception:
            pass

                  
    root.after(duration_ms, dismiss)

    try:
        root.mainloop()
    except Exception:
        pass
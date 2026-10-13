import re

                                                                                
_RE_STRIP_CHARS = re.compile(r'[\\/:*?"<>|{}$!\'"&%`@+=,;.\-]')
_RE_NON_ASCII   = re.compile(r"[^\x00-\x7F]+")
_RE_SPACES      = re.compile(r"\s+")


def clean(text: str) -> str:
                                                                
    s = _RE_STRIP_CHARS.sub("", text)
    s = _RE_NON_ASCII.sub("", s)
    return _RE_SPACES.sub("", s).lower()


def clean_search_name(text: str) -> str:
                                                              
    s = re.sub(r"[™®©]", "", text)
    s = re.sub(r"[^\w\s\-]", "", s)
    return re.sub(r"\s+", " ", s).strip()


                                                                                
def blend(hex_color: str, bg: str = "#13161f", alpha: float = 0.15) -> str:
                                                            
    def parse(h):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    fr, fg, fb = parse(hex_color)
    br, bg2, bb = parse(bg)
    return "#{:02x}{:02x}{:02x}".format(
        int(br + (fr - br) * alpha),
        int(bg2 + (fg - bg2) * alpha),
        int(bb + (fb - bb) * alpha),
    )
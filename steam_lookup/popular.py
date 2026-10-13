\
\
\
\
\
   

import html
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .config import BROWSER_HEADERS


_SEARCH_URL = "https://store.steampowered.com/search/"


                                                              
                          
                                                              

                                                                 
                                                          
_steam_blocked_until = 0.0

                                          
_MAX_403_RETRIES = 2

                               
                                                                 
_403_RETRY_DELAYS = (3.0, 8.0)


                
TAG_IDS = {
            
    "Action": 19,
    "Adventure": 21,
    "RPG": 122,
    "Shooter": 1774,
    "Strategy": 9,
    "Simulation": 599,
    "Puzzle": 1664,
    "Racing": 699,
    "Sports": 701,

            
    "Horror": 1667,
    "Open World": 1695,
    "Survival": 1662,

             
    "Singleplayer": 4182,
    "Multiplayer": 3859,
    "Co-op": 1685,
    "Local Co-op": 3841,
    "Split Screen": 10816,
}


class _SteamSearchParser(HTMLParser):
                                                                          

    def __init__(self):
        super().__init__(convert_charrefs=True)

        self.games = []
        self.total = 0

        self._in_result = False
        self._current = None

        self._in_title = False
        self._title_parts = []

        self._in_result_count = False
        self._count_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())

                                                                      
                           
                                                                      
        if tag == "a" and "search_result_row" in classes:
            appid = attrs.get("data-ds-appid")

            if appid:
                                                                 
                try:
                    appid = int(str(appid).split(",")[0])
                except (TypeError, ValueError):
                    appid = None

            if appid:
                self._in_result = True

                self._current = {
                    "appid": appid,
                    "name": "",
                    "header_image": "",
                }

                self._title_parts = []

                                                          
                image_url = attrs.get("data-search-page-image")

                if image_url:
                    self._current["header_image"] = image_url

                                                                      
                      
                                                                      
        elif (
            self._in_result
            and tag == "span"
            and "title" in classes
        ):
            self._in_title = True
            self._title_parts = []

                                                                      
                             
                                                                      
        if tag == "div" and "search_results_count" in classes:
            self._in_result_count = True
            self._count_parts = []

                                                                      
                                   
                                                                      
        if self._in_result and tag == "img":
            src = (
                attrs.get("src")
                or attrs.get("data-src")
                or ""
            )

            if (
                src
                and self._current is not None
                and not self._current.get("header_image")
            ):
                self._current["header_image"] = src

    def handle_endtag(self, tag):
                                                                      
                          
                                                                      
        if tag == "span" and self._in_title:
            self._in_title = False

            if self._current is not None:
                self._current["name"] = html.unescape(
                    "".join(self._title_parts)
                ).strip()

                                                                      
                        
                                                                      
        if tag == "a" and self._in_result:
            if self._current:
                name = self._current.get("name", "").strip()
                appid = self._current.get("appid")

                if name and appid:
                    self.games.append(self._current)

            self._current = None
            self._in_result = False
            self._in_title = False

                                                                      
                                  
                                                                      
        if tag == "div" and self._in_result_count:
            self._in_result_count = False

            text = " ".join(self._count_parts)

            match = re.search(
                r"([\d,]+)\s+results?\s+match",
                text,
                re.IGNORECASE,
            )

            if match:
                try:
                    self.total = int(
                        match.group(1).replace(",", "")
                    )
                except ValueError:
                    pass

    def handle_data(self, data):
        if self._in_title:
            self._title_parts.append(data)

        if self._in_result_count:
            self._count_parts.append(data)


def _extract_total_from_html(source):
\
\
\
\
\
       

    if not source:
        return 0

    patterns = (
        r"([\d,]+)\s+results?\s+match",
        r"([\d,]+)\s+results?\s+found",
        r"([\d,]+)\s+results?",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            source,
            re.IGNORECASE,
        )

        if not match:
            continue

        try:
            value = int(
                match.group(1).replace(",", "")
            )

            if value > 0:
                return value

        except (TypeError, ValueError):
            pass

    return 0


def _wait_for_steam_cooldown():
                                                              

    global _steam_blocked_until

    remaining = _steam_blocked_until - time.monotonic()

    if remaining > 0:
        time.sleep(remaining)


def _mark_steam_blocked(seconds):
                                                           

    global _steam_blocked_until

    _steam_blocked_until = max(
        _steam_blocked_until,
        time.monotonic() + seconds,
    )


def _request_search(
    query="",
    page=0,
    page_size=30,
    tags=None,
):
                                             

    global _steam_blocked_until

                                    
    start = max(0, int(page)) * int(page_size)

    params = {
        "category1": "998",
        "supportedlang": "english",
        "ndl": "1",
        "start": str(start),
        "count": str(page_size),
    }

    if query:
                                                           
                                                            
        params["sort_by"] = "Relevance"
    else:
                                                      
        params["sort_by"] = "Reviews_DESC"

    if query:
        params["term"] = query

    if tags:
        tag_ids = [
            str(TAG_IDS[name])
            for name in tags
            if name in TAG_IDS
        ]

        if tag_ids:
            params["tags"] = ",".join(tag_ids)

    url = (
        _SEARCH_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    req = urllib.request.Request(
        url,
        headers={
            **BROWSER_HEADERS,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,image/webp,"
                "*/*;q=0.8"
            ),
            "Accept-Language": "en-GB,en;q=0.9",
            "Referer": "https://store.steampowered.com/",
        },
    )

    last_error = None

    for attempt in range(_MAX_403_RETRIES + 1):
                                                     
        _wait_for_steam_cooldown()

        try:
            with urllib.request.urlopen(
                req,
                timeout=15,
            ) as response:
                                                                  
                _steam_blocked_until = 0.0

                return response.read().decode(
                    "utf-8",
                    errors="replace",
                )

        except urllib.error.HTTPError as exc:
            last_error = exc

                                                                      
                                         
                                                                      
            if exc.code == 403:
                if attempt >= _MAX_403_RETRIES:
                    raise RuntimeError(
                        "Steam temporarily denied the request "
                        "(HTTP 403). Please wait a few minutes "
                        "before searching again."
                    ) from exc

                delay = (
                    _403_RETRY_DELAYS[
                        min(
                            attempt,
                            len(_403_RETRY_DELAYS) - 1,
                        )
                    ]
                    + random.uniform(0.5, 1.5)
                )

                _mark_steam_blocked(delay)

                time.sleep(delay)

                continue

                                                
            raise

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Network error while contacting Steam: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise RuntimeError(
                "Steam took too long to respond."
            ) from exc

                                       
    if last_error is not None:
        raise last_error

    raise RuntimeError("Steam request failed.")


def fetch_games(
    query="",
    page=0,
    page_size=30,
    tags=None,
):
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
       

    try:
        source = _request_search(
            query=query,
            page=page,
            page_size=page_size,
            tags=tags,
        )

    except Exception as exc:
        raise RuntimeError(
            f"Steam request failed: {exc}"
        ) from exc

                                                                  
                           
                                                                  
    parser = _SteamSearchParser()

    try:
        parser.feed(source)
        parser.close()

    except Exception as exc:
        raise RuntimeError(
            f"Couldn't parse Steam search results: {exc}"
        ) from exc

    games = parser.games

                                                                  
                       
     
                                                               
                                          
     
                                                                
                                          
                                                                  
    if query:
        search = query.casefold().strip()

        def search_score(game):
            name = game.get(
                "name",
                "",
            ).casefold().strip()

            if name == search:
                return 0

            if name.startswith(search):
                return 1

            if f" {search} " in f" {name} ":
                return 2

            if search in name:
                return 3

            return 4

        games.sort(key=search_score)

                                                                  
                                                     
                                                                  
    total = parser.total

    if not total:
        total = _extract_total_from_html(source)

                           
    if not total:
        total = len(games)

                                                                  
                                      
                                                                  
    games = games[:page_size]

    return games, total


def fetch_popular(
    page=0,
    page_size=30,
    tags=None,
):
                                                      

    return fetch_games(
        query="",
        page=page,
        page_size=page_size,
        tags=tags,
    )


def search_games(
    query,
    page=0,
    page_size=30,
    tags=None,
):
                                                           

    return fetch_games(
        query=query,
        page=page,
        page_size=page_size,
        tags=tags,
    )
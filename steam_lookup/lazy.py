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
   

import threading

_lock = threading.Lock()

                       
_httpx       = None
_requests    = None
_bs4         = None
_pil         = None                                       
_seleniumbase = None                                             


def get_httpx():
                                                              
    global _httpx
    if _httpx is None:
        with _lock:
            if _httpx is None:
                import httpx
                _httpx = httpx
    return _httpx


def get_requests():
                                                                 
    global _requests
    if _requests is None:
        with _lock:
            if _requests is None:
                import requests
                _requests = requests
    return _requests


def get_bs4():
                                                                      
    global _bs4
    if _bs4 is None:
        with _lock:
            if _bs4 is None:
                from bs4 import BeautifulSoup
                _bs4 = BeautifulSoup
    return _bs4


def get_pil():
                                                                       
    global _pil
    if _pil is None:
        with _lock:
            if _pil is None:
                from PIL import Image, ImageTk
                _pil = (Image, ImageTk)
    return _pil


def get_seleniumbase():
\
\
\
\
       
    global _seleniumbase
    if _seleniumbase is None:
        with _lock:
            if _seleniumbase is None:
                from seleniumbase import Driver
                from selenium.webdriver.support.ui import WebDriverWait
                _seleniumbase = (Driver, WebDriverWait)
    return _seleniumbase


def get_httpx_client(**kwargs):
\
\
\
       
    global _httpx_client
    try:
        _httpx_client
    except NameError:
        _httpx_client = None

    if _httpx_client is None:
        with _lock:
            if _httpx_client is None:
                httpx = get_httpx()
                _httpx_client = httpx.Client(**kwargs)
    return _httpx_client
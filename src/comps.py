"""Comps de revenda via Kijiji (paginas publicas, sem login).

O Facebook Marketplace exige login — fora dos limites (mesma regra do lance
manual). O Kijiji e publico e server-rendered: os cards de anuncio vem no HTML
com data-testid, ~5 anuncios por busca ja bastam para um termometro de preco
PEDIDO (asking). Lembrar: preco pedido != preco vendido; negociar ~10-20% abaixo.
"""

from __future__ import annotations

import re
import statistics
import time
from typing import Optional

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}

# Regiao de venda da familia: St. Catharines / Niagara
REGION_PATH = "b-st-catharines-niagara"
REGION_CODE = "k0l80016"

MIN_REQUEST_INTERVAL = 3.0
_last_request = 0.0


def _throttle() -> None:
    global _last_request
    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")


def kijiji_comps(query: str, region_path: str = REGION_PATH,
                 region_code: str = REGION_CODE,
                 timeout: int = 30) -> list[dict]:
    """Anuncios ativos no Kijiji da regiao para a busca. Lista de
    {title, price, location}; preco None quando 'Swap/Trade' etc."""
    _throttle()
    url = f"https://www.kijiji.ca/{region_path}/{_slug(query)}/{region_code}"
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    if resp.status_code != 200:
        return []
    cards = re.split(r'data-testid="listing-card"', resp.text)[1:]
    results = []
    for c in cards:
        title = re.search(r'data-testid="listing-title"[^>]*>(?:<[^>]+>)*([^<]+)', c)
        price = re.search(r'data-testid="listing-price"[^>]*>([^<]+)', c)
        loc = re.search(r'data-testid="listing-location"[^>]*>(?:<[^>]+>)*([^<]+)', c)
        amount: Optional[float] = None
        if price:
            m = re.search(r"[\d,]+(?:\.\d\d)?", price.group(1))
            if m:
                amount = float(m.group(0).replace(",", ""))
        results.append({
            "title": (title.group(1).strip() if title else "?"),
            "price": amount,
            "location": (loc.group(1).strip() if loc else "?"),
        })
    return results


def comps_summary(query: str, **kw) -> dict:
    """Resumo: mediana/faixa dos precos pedidos + exemplos."""
    listings = kijiji_comps(query, **kw)
    prices = [l["price"] for l in listings if l["price"]]
    return {
        "query": query,
        "count": len(listings),
        "median": statistics.median(prices) if prices else None,
        "low": min(prices) if prices else None,
        "high": max(prices) if prices else None,
        "examples": listings[:3],
    }

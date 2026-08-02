"""Cliente read-only da API GraphQL publica do HiBid (hibid.com/graphql).

Somente consultas publicas (busca de lotes, estado ao vivo, historico de
lances). NUNCA implementar login, lance ou qualquer mutation — lance e humano.

Descobertas empiricas (validadas em 02/08/2026):
- Endpoint aceita POST sem autenticacao; GET retorna 403 (Cloudflare).
- Headers User-Agent + Origin/Referer de hibid.com sao necessarios.
- Filtro de provincia usa SIGLA: state="ON" ("Ontario" retorna 0).
- Filtro por raio: zip="L4W 1S9" (postal canadense com espaco) + miles=N.
- lotState.timeLeftSeconds e o cronometro real (soft close estende o fim:
  lance nos ultimos softCloseMinutes reabre a contagem).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

GRAPHQL_URL = "https://hibid.com/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Origin": "https://hibid.com",
    "Referer": "https://hibid.com/ontario",
}

# Intervalo minimo entre requests (s) — ritmo humano, nao martelar o site.
MIN_REQUEST_INTERVAL = 2.0

_LOT_FIELDS = """
  id
  itemId
  lotNumber
  lead
  description
  quantity
  shippingOffered
  featuredPicture { thumbnailLocation fullSizeLocation }
  auction {
    id
    eventName
    eventCity
    eventState
    eventZip
    eventAddress
    bidCloseDateTime
    buyerPremium
    buyerPremiumRate
    currencyAbbreviation
    auctioneer { id name }
  }
  lotState {
    highBid
    minBid
    bidCount
    bidMax
    timeLeftSeconds
    softCloseMinutes
    softCloseSeconds
    isClosed
    isLive
    status
    reserveSatisfied
  }
"""

LOT_SEARCH_QUERY = f"""
query LotSearch($pageNumber: Int!, $pageLength: Int!, $searchText: String,
                $countryName: String, $state: String, $zip: String, $miles: Int,
                $status: AuctionLotStatus, $auctionId: Int,
                $sortOrder: EventItemSortOrder) {{
  lotSearch(
    input: {{searchText: $searchText, countryName: $countryName, state: $state,
            zip: $zip, miles: $miles, status: $status, auctionId: $auctionId,
            sortOrder: $sortOrder}}
    pageNumber: $pageNumber
    pageLength: $pageLength
    sortDirection: DESC
  ) {{
    pagedResults {{
      totalCount
      filteredCount
      results {{ {_LOT_FIELDS} }}
    }}
  }}
}}
"""

LOT_STATE_QUERY = """
query GetLotStateQuery($lotId: ID!) {
  lotState(input: $lotId) {
    highBid
    minBid
    bidCount
    timeLeftSeconds
    softCloseMinutes
    softCloseSeconds
    isClosed
    isLive
    status
    reserveSatisfied
  }
}
"""

BID_HISTORY_QUERY = """
query BidHistory($lotId: ID!) {
  bidHistory(input: $lotId) {
    currAbbrev
    lead
    lotNumber
    bids { bid username count datetime }
  }
}
"""


class HiBidError(RuntimeError):
    pass


@dataclass
class LotState:
    high_bid: float
    min_bid: float
    bid_count: int
    time_left_seconds: Optional[int]
    soft_close_minutes: Optional[int]
    is_closed: bool
    status: str
    raw: dict = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, d: dict) -> "LotState":
        return cls(
            high_bid=float(d.get("highBid") or 0),
            min_bid=float(d.get("minBid") or 0),
            bid_count=int(d.get("bidCount") or 0),
            time_left_seconds=d.get("timeLeftSeconds"),
            soft_close_minutes=d.get("softCloseMinutes"),
            is_closed=bool(d.get("isClosed")),
            status=str(d.get("status") or ""),
            raw=d,
        )


class HiBidClient:
    def __init__(self, min_interval: float = MIN_REQUEST_INTERVAL):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.min_interval = min_interval
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _query(self, query: str, variables: dict,
               operation: Optional[str] = None, retries: int = 3) -> dict:
        payload: dict[str, Any] = {"query": query, "variables": variables}
        if operation:
            payload["operationName"] = operation
        last_err: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.post(GRAPHQL_URL, json=payload, timeout=30)
                if resp.status_code == 403:
                    raise HiBidError("403 do Cloudflare — reduzir frequencia/rever headers")
                resp.raise_for_status()
                body = resp.json()
                if body.get("errors"):
                    raise HiBidError(str(body["errors"][:2]))
                return body["data"]
            except (requests.RequestException, HiBidError, KeyError) as e:
                last_err = e
                time.sleep(2 ** attempt * 2)
        raise HiBidError(f"falha apos {retries} tentativas: {last_err}")

    def search_lots(self, *, search_text: Optional[str] = None,
                    zip_code: Optional[str] = None, miles: Optional[int] = None,
                    state: Optional[str] = "ON", country: str = "Canada",
                    status: str = "OPEN", auction_id: Optional[int] = None,
                    page: int = 1, page_length: int = 50,
                    sort_order: Optional[str] = None) -> dict:
        """Retorna {'totalCount': int, 'results': [lote, ...]} de lotes publicos.

        Nota: zip+miles e state sao mutuamente sensiveis — quando zip e dado,
        deixar state/country como estao funciona; o raio domina o filtro.
        """
        variables = {
            "pageNumber": page,
            "pageLength": page_length,
            "searchText": search_text,
            "countryName": country,
            "state": state,
            "zip": zip_code,
            "miles": miles,
            "status": status,
            "auctionId": auction_id,
            "sortOrder": sort_order,
        }
        data = self._query(LOT_SEARCH_QUERY, variables, "LotSearch")
        return data["lotSearch"]["pagedResults"]

    def lot_state(self, lot_id: int | str) -> LotState:
        """Estado ao vivo de um lote: lance atual, tempo restante, soft close."""
        data = self._query(LOT_STATE_QUERY, {"lotId": str(lot_id)},
                           "GetLotStateQuery")
        return LotState.from_raw(data["lotState"])

    def bid_history(self, lot_id: int | str) -> dict:
        data = self._query(BID_HISTORY_QUERY, {"lotId": str(lot_id)},
                           "BidHistory")
        return data["bidHistory"]


def lot_url(lot_id: int | str) -> str:
    return f"https://hibid.com/lot/{lot_id}"


def all_in_cost(bid: float, premium_rate: float, hst: float = 0.13) -> float:
    """Custo real de um lance: lance + premio do comprador + HST sobre tudo."""
    return bid * (1 + premium_rate) * (1 + hst)

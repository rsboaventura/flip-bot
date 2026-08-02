#!/usr/bin/env python
"""Garimpo semanal: busca lotes por palavra-chave no raio de Mississauga e
gera relatorio markdown de oportunidades ordenado por fim do leilao.

Uso:
  python scripts/scan.py                    # usa config/flip.yaml
  python scripts/scan.py --keyword dyson    # so uma palavra-chave
  python scripts/scan.py --max-bid 80       # so lotes com lance atual <= 80
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.hibid import HiBidClient, all_in_cost, lot_url  # noqa: E402


def load_config() -> dict:
    with open(ROOT / "config" / "flip.yaml") as f:
        return yaml.safe_load(f)


def fmt_time_left(seconds) -> str:
    if seconds is None:
        return "?"
    seconds = int(seconds)
    if seconds <= 0:
        return "ENCERRADO"
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def scan(cfg: dict, keywords: list[str], max_bid_filter: float) -> list[dict]:
    client = HiBidClient()
    s = cfg["search"]
    costs = cfg["costs"]
    horizon = datetime.now() + timedelta(days=cfg["report"]["closing_within_days"])
    seen: set[str] = set()
    rows: list[dict] = []

    for kw in keywords:
        page = client.search_lots(
            search_text=kw, zip_code=s["zip"], miles=s["miles"],
            state=s["state"], country=s["country"], page_length=50,
        )
        print(f"  [{kw}] {page['totalCount']} lotes no raio", file=sys.stderr)
        for lot in page["results"]:
            lid = str(lot["id"])
            if lid in seen:
                continue
            seen.add(lid)
            st = lot.get("lotState") or {}
            if st.get("isClosed"):
                continue
            high = float(st.get("highBid") or 0)
            if high > max_bid_filter:
                continue
            tls = st.get("timeLeftSeconds")
            if tls is not None and datetime.now() + timedelta(seconds=tls) > horizon:
                continue
            auc = lot.get("auction") or {}
            premium = (auc.get("buyerPremiumRate") or 0) / 100 or costs["buyer_premium_default"]
            next_bid = float(st.get("minBid") or 0) or high + 1
            rows.append({
                "keyword": kw,
                "id": lid,
                "lead": (lot.get("lead") or "").strip(),
                "high_bid": high,
                "next_bid": next_bid,
                "all_in_next": all_in_cost(next_bid, premium, costs["hst"]),
                "bid_count": int(st.get("bidCount") or 0),
                "time_left_s": tls,
                "city": auc.get("eventCity") or "?",
                "auctioneer": (auc.get("auctioneer") or {}).get("name") or "?",
                "premium_pct": round(premium * 100),
                "url": lot_url(lid),
            })

    rows.sort(key=lambda r: (r["time_left_s"] is None, r["time_left_s"] or 0))
    return rows


def render_markdown(cfg: dict, rows: list[dict]) -> str:
    s = cfg["search"]
    mult = cfg["costs"]["resale_multiple"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Garimpo HiBid — {now}",
        "",
        f"Raio: {s['miles']} mi de {s['zip']} (Mississauga) · "
        f"{len(rows)} oportunidades · lance atual <= "
        f"CA${cfg['report']['max_current_bid']}",
        "",
        f"**Custo real** = proximo lance + premio do leiloeiro + HST 13%. "
        f"Regra: so compensa se revender por >= {mult}x o custo real.",
        "",
        "| Fim | Lote | Cidade | Lance | Prox. | Custo real | Revenda min. | Lances | Link |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lead = r["lead"][:60].replace("|", "/")
        lines.append(
            f"| {fmt_time_left(r['time_left_s'])} "
            f"| {lead} "
            f"| {r['city']} "
            f"| ${r['high_bid']:.0f} "
            f"| ${r['next_bid']:.0f} "
            f"| ${r['all_in_next']:.0f} "
            f"| ${r['all_in_next'] * mult:.0f} "
            f"| {r['bid_count']} "
            f"| [{r['id']}]({r['url']}) |"
        )
    lines += [
        "",
        "Para vigiar um lote: adicionar `id` + `max_bid` em config/watchlist.yaml "
        "e rodar `python scripts/watch.py`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", action="append",
                    help="palavra-chave unica (repetivel); default: config")
    ap.add_argument("--max-bid", type=float, default=None,
                    help="lance atual maximo (default: config report.max_current_bid)")
    args = ap.parse_args()

    cfg = load_config()
    keywords = args.keyword or cfg["search"]["keywords"]
    max_bid = args.max_bid if args.max_bid is not None else cfg["report"]["max_current_bid"]

    print(f"Garimpando {len(keywords)} palavras-chave...", file=sys.stderr)
    rows = scan(cfg, keywords, max_bid)
    md = render_markdown(cfg, rows)

    out_dir = ROOT / cfg["report"]["output_dir"]
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"garimpo-{datetime.now():%Y-%m-%d-%H%M}.md"
    out.write_text(md)
    print(md)
    print(f"\nRelatorio salvo: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()

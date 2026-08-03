#!/usr/bin/env python
"""Roda o garimpo completo (revenda + lista da casa) e manda o relatorio HTML
por e-mail via Gmail SMTP. Tambem salva o HTML em reports/.

Credenciais em .env.local (gitignored) na raiz do flip-bot:
  FLIP_SMTP_USER=rsbvnt@gmail.com
  FLIP_SMTP_PASS=<senha de app do Gmail — https://myaccount.google.com/apppasswords>
  FLIP_EMAIL_TO=rsbvnt@gmail.com,lucianacesar@gmail.com

Uso:
  python scripts/email_report.py           # scan + salva HTML + envia
  python scripts/email_report.py --no-send # so gera o HTML (teste)
"""

from __future__ import annotations

import argparse
import json
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scan import load_config, scan, scan_shopping  # noqa: E402
from src.comps import comps_summary  # noqa: E402
from src.report_html import render_email_html  # noqa: E402

import re

# Acessorio/peca nao vale a mediana da categoria (carregador de patinete nao
# vale $1500). Sem estimativa de lucro -> vai pro fim do ranking, mas fica.
ACCESSORY_RE = re.compile(
    r"charger|tire|tyre|inner tube|replacement|compatible|repair|part\b|parts\b"
    r"|accessor|cover|case\b|holder|mount\b|bracket|adapter|cable|controller"
    r"|remote\b|filter|\bbag\b|belt\b|brush|\bbatter(y|ies)\b|pump\b|lock\b"
    r"|\blight\b|bell\b|seat\b|helmet|sticker|decal|strap|nozzle|hose|attachment"
    r"|switch\b|dashboard|\bmotor\b|\bengine\b|ride.?on|handlebar|fender|kickstand"
    r"|\bcord\b|extension|inlet|outlet|plug\b|socket",
    re.IGNORECASE,
)


def _title_matches(keyword: str, lead: str) -> bool:
    """HiBid busca full-text (descricao inclusa) e por radical — 'generator'
    acha 'Generation'/'Generic'. So estima lucro se TODAS as palavras da
    keyword aparecem inteiras no titulo."""
    return all(re.search(rf"\b{re.escape(t)}s?\b", lead, re.IGNORECASE)
               for t in keyword.split())


def annotate_profit(rows: list[dict], comps: list[dict], haircut: float,
                    hst: float = 0.13, profit_multiple: float = 2.0) -> None:
    """Lucro estimado por lote via mediana Kijiji da keyword; acessorios e
    titulos que nao batem com a keyword ficam sem estimativa. Tambem calcula
    max_bid_2x: o LANCE maximo p/ garantir lucro >= 100% (venda liquida >=
    profit_multiple x custo real), ja descontando premio do leiloeiro + HST.
    Ordena in-place por lucro desc (sem estimativa no fim)."""
    median_by_kw = {c["query"]: c["median"] for c in comps if c.get("median")}
    for r in rows:
        med = median_by_kw.get(r["keyword"])
        if (med and _title_matches(r["keyword"], r["lead"])
                and not ACCESSORY_RE.search(r["lead"])):
            premium = (r.get("premium_pct") or 16) / 100
            resale_net = med * (1 - haircut)
            r["est_resale"] = med
            r["est_profit"] = resale_net - r["all_in_next"]
            r["max_bid_2x"] = (resale_net / profit_multiple
                               / ((1 + premium) * (1 + hst)))
        else:
            r["est_resale"] = None
            r["est_profit"] = None
            r["max_bid_2x"] = None
    rows.sort(key=lambda r: (r["est_profit"] is None, -(r["est_profit"] or 0)))


def load_env() -> dict:
    env = {}
    env_file = ROOT / ".env.local"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def send_gmail(env: dict, subject: str, html: str) -> list[str]:
    user = env.get("FLIP_SMTP_USER")
    password = env.get("FLIP_SMTP_PASS")
    to = [a.strip() for a in env.get("FLIP_EMAIL_TO", user or "").split(",") if a.strip()]
    if not (user and password and to):
        raise SystemExit(
            "Faltam credenciais: criar .env.local com FLIP_SMTP_USER, "
            "FLIP_SMTP_PASS (senha de app do Gmail) e FLIP_EMAIL_TO."
        )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText("Relatorio em HTML — abrir num cliente compativel.", "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.sendmail(user, to, msg.as_string())
    return to


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-send", action="store_true", help="so gera o HTML")
    args = ap.parse_args()

    cfg = load_config()
    print("Garimpando (revenda + lista da casa)...", file=sys.stderr)
    rows = scan(cfg, cfg["search"]["keywords"], cfg["report"]["max_current_bid"])
    shopping_rows = scan_shopping(cfg)
    # e-mail so com lote vivo e com pelo menos 10 min de jogo
    rows = [r for r in rows if (r["time_left_s"] or 0) > 600]
    shopping_rows = [r for r in shopping_rows if (r["time_left_s"] or 0) > 600]

    print("Termometro Kijiji (Niagara)...", file=sys.stderr)
    comps = []
    for kw in cfg["search"]["keywords"]:
        try:
            comps.append(comps_summary(kw))
        except Exception as e:
            print(f"  !! comps '{kw}': {e}", file=sys.stderr)

    annotate_profit(rows, comps, cfg["report"].get("haircut", 0.15),
                    hst=cfg["costs"].get("hst", 0.13),
                    profit_multiple=cfg["costs"].get("resale_multiple", 2.0))

    html = render_email_html(cfg, rows, shopping_rows, comps=comps)

    out_dir = ROOT / cfg["report"]["output_dir"]
    out_dir.mkdir(exist_ok=True)
    stamp = f"{datetime.now():%Y-%m-%d-%H%M}"
    out = out_dir / f"garimpo-{stamp}.html"
    out.write_text(html)
    (out_dir / f"garimpo-{stamp}.json").write_text(
        json.dumps({"rows": rows, "shopping": shopping_rows, "comps": comps},
                   ensure_ascii=False))
    print(f"HTML salvo: {out}", file=sys.stderr)

    if args.no_send:
        return
    subject = (f"🔨 Garimpo HiBid {datetime.now():%d/%m}: "
               f"{len(rows)} oportunidades na rota")
    to = send_gmail(load_env(), subject, html)
    print(f"E-mail enviado para: {', '.join(to)}", file=sys.stderr)


if __name__ == "__main__":
    main()

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
from src.report_html import render_email_html  # noqa: E402


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
    html = render_email_html(cfg, rows, shopping_rows)

    out_dir = ROOT / cfg["report"]["output_dir"]
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"garimpo-{datetime.now():%Y-%m-%d-%H%M}.html"
    out.write_text(html)
    print(f"HTML salvo: {out}", file=sys.stderr)

    if args.no_send:
        return
    subject = (f"🔨 Garimpo HiBid {datetime.now():%d/%m}: "
               f"{len(rows)} oportunidades na rota")
    to = send_gmail(load_env(), subject, html)
    print(f"E-mail enviado para: {', '.join(to)}", file=sys.stderr)


if __name__ == "__main__":
    main()

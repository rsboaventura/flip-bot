"""Renderiza o relatorio de garimpo em HTML bonito e compativel com e-mail
(estilos inline, tabelas simples — Gmail nao aceita <style> externo direito).
"""

from __future__ import annotations

from datetime import datetime

AZUL = "#1d6fd8"
LARANJA = "#d97706"
VERDE = "#16a34a"
INK = "#1f2937"
MUTED = "#6b7280"


def _fmt_time(seconds) -> str:
    if seconds is None:
        return "?"
    seconds = int(seconds)
    if seconds <= 0:
        return "encerrado"
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m} min"


def _row_style(i: int) -> str:
    bg = "#ffffff" if i % 2 == 0 else "#f4f6fa"
    return f"background:{bg};"


TD = "padding:7px 9px;font-size:13px;color:%s;border-bottom:1px solid #e5e7eb;" % INK
TH = ("padding:8px 9px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;"
      "color:#ffffff;text-align:left;")


def render_email_html(cfg: dict, rows: list[dict],
                      shopping_rows: list[dict]) -> str:
    mult = cfg["costs"]["resale_multiple"]
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    zonas = " · ".join(z["name"] for z in cfg["search"]["zones"])

    def opp_table(rs: list[dict]) -> str:
        if not rs:
            return (f'<p style="color:{MUTED};font-size:14px;">'
                    'Nenhuma oportunidade nesta rodada.</p>')
        trs = []
        for i, r in enumerate(rs):
            lead = r["lead"][:70]
            trs.append(f"""
<tr style="{_row_style(i)}">
  <td style="{TD}white-space:nowrap;"><b>{_fmt_time(r["time_left_s"])}</b></td>
  <td style="{TD}"><a href="{r["url"]}" style="color:{AZUL};text-decoration:none;"><b>{lead}</b></a>
      <br><span style="color:{MUTED};font-size:11px;">{r["city"]} · {r.get("zone", "")} · {r["bid_count"]} lances</span></td>
  <td style="{TD}text-align:right;">${r["high_bid"]:.0f}</td>
  <td style="{TD}text-align:right;"><b>${r["all_in_next"]:.0f}</b></td>
  <td style="{TD}text-align:right;color:{VERDE};"><b>${r["all_in_next"] * mult:.0f}+</b></td>
</tr>""")
        return f"""
<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;border-radius:10px;overflow:hidden;">
  <tr style="background:{AZUL};">
    <th style="{TH}">Fim</th><th style="{TH}">Lote (clique p/ abrir)</th>
    <th style="{TH}text-align:right;">Lance</th>
    <th style="{TH}text-align:right;">Custo real</th>
    <th style="{TH}text-align:right;">Revender por</th>
  </tr>
  {"".join(trs)}
</table>"""

    def casa_table(rs: list[dict]) -> str:
        if not rs:
            return (f'<p style="color:{MUTED};font-size:14px;">'
                    'Nenhuma barganha da lista de compras nesta rodada.</p>')
        trs = []
        for i, r in enumerate(rs[:15]):
            lead = r["lead"][:60]
            trs.append(f"""
<tr style="{_row_style(i)}">
  <td style="{TD}color:{VERDE};text-align:right;"><b>${r["saving"]:.0f}</b></td>
  <td style="{TD}"><a href="{r["url"]}" style="color:{AZUL};text-decoration:none;"><b>{lead}</b></a>
      <br><span style="color:{MUTED};font-size:11px;">{r["city"]} · fecha em {_fmt_time(r["time_left_s"])}</span></td>
  <td style="{TD}text-align:right;">${r["amazon_price"]:.0f}</td>
  <td style="{TD}text-align:right;"><b>${r["all_in_next"]:.0f}</b></td>
</tr>""")
        return f"""
<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;border-radius:10px;overflow:hidden;">
  <tr style="background:{LARANJA};">
    <th style="{TH}text-align:right;">Economia</th><th style="{TH}">Item</th>
    <th style="{TH}text-align:right;">Amazon</th>
    <th style="{TH}text-align:right;">Custo agora</th>
  </tr>
  {"".join(trs)}
</table>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#eef1f6;">
<div style="max-width:680px;margin:0 auto;padding:16px;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;">

  <div style="background:{AZUL};border-radius:14px 14px 0 0;padding:22px 24px;color:#fff;">
    <div style="font-size:22px;font-weight:800;">🔨 Garimpo HiBid da semana</div>
    <div style="font-size:13px;opacity:.85;margin-top:4px;">{now} · rota: {zonas}</div>
  </div>

  <div style="background:#ffffff;padding:20px 24px;">
    <p style="font-size:14px;color:{INK};margin:0 0 6px;">
      <b>{len(rows)} oportunidades de revenda</b> na rota da Luciana.
      <span style="color:{MUTED};">Custo real = próximo lance + taxa do leiloeiro + HST.
      Só vale se revender por <b>{mult:g}×</b> o custo real.</span></p>
  </div>

  <div style="background:#ffffff;padding:0 24px 20px;">
    <div style="font-size:16px;font-weight:700;color:{INK};margin:0 0 10px;">💰 Oportunidades de revenda</div>
    {opp_table(rows)}
  </div>

  <div style="background:#ffffff;padding:0 24px 20px;">
    <div style="font-size:16px;font-weight:700;color:{INK};margin:0 0 10px;">🏠 Lista de compras da casa (vs Amazon)</div>
    {casa_table(shopping_rows)}
    <p style="font-size:12px;color:{MUTED};margin:10px 0 0;">⚠️ Lance longe do fim ainda sobe — o custo mostrado é o de agora.
    Conferir se é o produto (não capa/peça) e NEW/SEALED vs USED.</p>
  </div>

  <div style="background:#10233f;border-radius:0 0 14px 14px;padding:16px 24px;color:#c9d8ee;font-size:12px;">
    <b style="color:#fff;">Como agir:</b> escolher lotes → definir teto no <code>watchlist.yaml</code> →
    rodar o watcher → dar o lance à mão quando ele avisar "HORA DO LANCE".
    O robô nunca dá lance — disciplina de teto é o lucro. 🤖+👤
  </div>

</div>
</body></html>"""

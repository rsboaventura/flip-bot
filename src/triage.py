"""Triagem por IA dos melhores lotes: real ou fake? estado? usavel?

Usa o gpt-5.4-mini (mesmo modelo barato do robo da Etsy) com VISAO — analisa
titulo + descricao + foto do lote e devolve um veredito estruturado. Roda so
no top-N por lucro estimado (custo ~centavos por rodada).

A chave vem de flip-bot/.env.local (OPENAI_API_KEY) ou, em fallback, do
.env.local do 3dprint-bot (mesma conta).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ETSY_ENV = Path(
    "/Users/rogerioboaventura/Documents/MAIN.nosync/3dprint-bot.nosync /.env.local"
)

MODEL = "gpt-5.4-mini"

PROMPT = """Es um perito em leilões de liquidação (devoluções de loja) no Canadá.
Analisa este lote e responde APENAS um JSON:

{"produto_real": true/false,      // é o produto principal da categoria "%(keyword)s"? (false se for peça/capa/acessório/compatível)
 "condicao": "novo"|"aberto"|"usado"|"as-is"|"incerto",   // pela foto e título (NEW/NIB/SEALED=novo; NOB/OB=aberto; GUC/USED=usado; AS-IS/parts=as-is)
 "risco_fake": "baixo"|"medio"|"alto",   // marcas visadas (Apple, Dyson, Nike, LEGO) sem caixa/foto genérica/stock photo = risco maior
 "usavel": true/false,            // dá para revender como funcional? (as-is/faltando peça = false)
 "nota": 0-100,                   // qualidade da oportunidade p/ revenda (considera tudo)
 "motivo": "até 12 palavras em pt-BR"}

Lote: %(lead)s
Descrição: %(description)s
Categoria buscada: %(keyword)s"""


def load_openai_key() -> str | None:
    for env_file in (ROOT / ".env.local", ETSY_ENV):
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.strip().startswith("OPENAI_API_KEY="):
                    # tirar comentario inline ("...  # cole a chave...") e aspas
                    value = line.split("=", 1)[1].split("#", 1)[0].strip()
                    return value.strip("'\"") or None
    return None


def triage_lot(row: dict, client) -> dict | None:
    """Veredito da IA para um lote do scan (usa foto quando disponível)."""
    prompt = PROMPT % {
        "keyword": row.get("keyword", "?"),
        "lead": row.get("lead", "?"),
        "description": (row.get("description") or "")[:800] or "(sem descrição)",
    }
    content: list = [{"type": "text", "text": prompt}]
    if row.get("picture"):
        content.append({"type": "image_url",
                        "image_url": {"url": row["picture"], "detail": "low"}})
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_completion_tokens=2000,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"  !! triagem falhou ({row.get('id')}): {e}", file=sys.stderr)
        return None


def triage_top(rows: list[dict], n: int = 30) -> int:
    """Roda a triagem nos top-N lotes com estimativa de lucro, anotando
    row['triage']. Lote reprovado (nao e o produto / as-is / fake alto) perde
    a estimativa de lucro e desce no ranking. Retorna quantos foram avaliados."""
    key = load_openai_key()
    if not key:
        print("  !! sem OPENAI_API_KEY — triagem pulada", file=sys.stderr)
        return 0
    from openai import OpenAI
    client = OpenAI(api_key=key)

    done = attempted = 0
    for r in rows:
        if attempted >= n:
            break
        if r.get("est_profit") is None:
            continue
        attempted += 1
        verdict = triage_lot(r, client)
        if verdict is None:
            continue
        r["triage"] = verdict
        done += 1
        reprovado = (verdict.get("produto_real") is False
                     or verdict.get("usavel") is False
                     or verdict.get("risco_fake") == "alto")
        if reprovado:
            r["est_profit"] = None
            r["est_resale"] = None
            r["max_bid_2x"] = None
    rows.sort(key=lambda r: (r["est_profit"] is None, -(r["est_profit"] or 0)))
    return done

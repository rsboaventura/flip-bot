# flip-bot — Garimpo de leilões HiBid p/ revenda (spin-off do 3dprint-bot)

Compra em leilão de liquidação (HiBid Ontario, retirada na rota
Mississauga→Niagara da Luciana) e revenda no Facebook Marketplace/Kijiji.
Família: Rogério (dev/lances), Luciana (retirada/logística).

## Regras de ouro (não violar)

1. **Lance é SEMPRE humano.** O robô só faz leitura pública (busca, estado do
   lote, histórico). NUNCA implementar login, mutation ou lance automático —
   risco de banimento da conta + ToS. Mesma filosofia do robô da Etsy.
2. **Ritmo humano nas requests**: `HiBidClient` tem throttle de 2 s; polling
   mínimo de 15 s (só nos últimos 10 min de um lote). Não reduzir.
3. **Disciplina de preço**: teto (`max_bid`) definido ANTES do leilão; o
   watcher manda "soltar" quando estoura. Custo real = lance × ~1,30
   (prêmio 14-17% + HST 13%). Só compra se revenda ≥ 2× o custo real.

## Pegadinhas técnicas (descobertas empiricamente, 02/08/2026)

- API GraphQL pública: `POST https://hibid.com/graphql` (GET → 403 Cloudflare).
  Precisa de User-Agent de browser + Origin/Referer hibid.com.
- Filtro de província usa **SIGLA**: `state: "ON"` (`"Ontario"` retorna 0!).
- Raio de retirada: `zip: "L4W 1S9"` (postal canadense COM espaço) + `miles`.
- Queries extraídas do bundle `cdn.hibid.com/cdn/pwa/<versão>/main.*.js`
  (fragments `lotState`, `auctionMinimum`). Se a API mudar, re-extrair de lá.
- **Soft close**: lance nos últimos `softCloseMinutes` ESTENDE o cronômetro.
  Sniping de último segundo não funciona; a janela boa é ~5 min do fim.
- Python: `/Users/rogerioboaventura/anaconda3/envs/llm-libs/bin/python`
  (mesmo env do 3dprint-bot; requests+yaml já instalados).

## Arquitetura

| Arquivo | Papel |
|---|---|
| `src/hibid.py` | Cliente GraphQL read-only (LotSearch, lotState, BidHistory) + `all_in_cost()` |
| `scripts/scan.py` | Garimpo semanal por keyword no raio de Mississauga → relatório md em `reports/` |
| `scripts/watch.py` | Watcher dinâmico: polling adaptativo da watchlist, notificação macOS "HORA DO LANCE" / "ESTOUROU O TETO" |
| `config/flip.yaml` | Raio, keywords, custos (prêmio/HST/múltiplo), cadência do watcher |
| `config/watchlist.yaml` | Lotes vigiados: id + max_bid (+ resale_estimate) |

## Fluxo semanal

1. Qui/sex: `scan.py` → relatório → Rogério escolhe lotes e define `max_bid`.
2. Preencher `watchlist.yaml`, rodar `watch.py` (fica aberto num terminal).
3. Alerta "HORA DO LANCE" → abrir o link e dar o lance À MÃO.
4. Ganhou → Luciana retira na ida ao storage → anunciar no Marketplace.
5. Registrar compra/venda no ledger (P1 — ainda não implementado).

## Roadmap

P0 piloto: 1 semana, budget CA$300, validar margem real ✓ código pronto ·
P1 ledger de compras/vendas + aprendizado de categorias que giram em Niagara ·
P2 comps automáticos de revenda (eBay sold) p/ sugerir max_bid ·
P3 relatório no Drive da família (reusar drive_inbox do 3dprint-bot).

Meta honesta: CA$1.5-3k/mês nos primeiros meses; $10k/mês só com escala
comprovada (ver conversa de 02/08/2026).

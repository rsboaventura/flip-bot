# flip-bot

Garimpo de leilões de liquidação no HiBid Ontario para revenda com lucro
(Facebook Marketplace / Kijiji, região de Niagara). Spin-off do 3dprint-bot.

**O robô pesquisa e avisa; o lance é sempre humano.** Nada de login ou lance
automático — só leitura de dados públicos, em ritmo respeitoso.

## Uso rápido

```bash
PY=/Users/rogerioboaventura/anaconda3/envs/llm-libs/bin/python

# 1. Garimpo semanal (qui/sex, antes da viagem da Luciana a Mississauga)
$PY scripts/scan.py                      # keywords do config/flip.yaml
$PY scripts/scan.py --keyword dyson      # busca pontual

# 2. Escolher lotes do relatório (reports/garimpo-*.md), definir teto de
#    lance em config/watchlist.yaml (id + max_bid)

# 3. Vigiar em tempo real — alerta macOS "HORA DO LANCE" na janela final
$PY scripts/watch.py
```

## A conta que importa

`custo real = lance × (1 + prêmio 14-17%) × (1 + HST 13%)` ≈ **lance × 1,30**.
Só compensa se revender por **≥ 2× o custo real** (devoluções têm 10-30% de
perda). O `max_bid` é definido ANTES e o watcher manda soltar quando estoura.

Detalhes técnicos e regras: [CLAUDE.md](CLAUDE.md).

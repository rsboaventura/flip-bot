#!/usr/bin/env python
"""Watcher dinamico: vigia os lotes de config/watchlist.yaml em tempo real e
avisa o MOMENTO DO LANCE. O lance em si e sempre manual (conta do Rogerio).

Estrategia (HiBid usa soft close — lance no final ESTENDE o cronometro):
  - Nao adianta "sniping" de ultimo segundo: lance nos ultimos
    softCloseMinutes reabre a contagem. O jogo e outro:
  - Entrar TARDE (nao inflar o preco cedo) mas com folga: o alerta
    "HORA DO LANCE" dispara faltando `bid_window_seconds` (default 5 min).
  - Se o lance atual passar do teu max_bid, o lote e dado como perdido
    (alerta "ESTOUROU O TETO") — disciplina de preco e o que da lucro.

Cadencia adaptativa de polling: 5 min longe do fim, 1 min na ultima hora,
15 s nos ultimos 10 min (respeitoso com o site; e leitura publica).

Uso:  python scripts/watch.py            # roda ate todos fecharem (Ctrl-C sai)
      python scripts/watch.py --once     # uma passada (p/ cron ou teste)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.hibid import HiBidClient, all_in_cost, lot_url  # noqa: E402


def load_yaml(name: str) -> dict:
    with open(ROOT / "config" / name) as f:
        return yaml.safe_load(f)


def notify(title: str, message: str, sound: bool = True) -> None:
    """Notificacao macOS + som. Falha silenciosa fora do macOS."""
    try:
        safe_t = title.replace('"', "'")
        safe_m = message.replace('"', "'")
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_m}" with title "{safe_t}"'],
            capture_output=True, timeout=10,
        )
        if sound:
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Glass.aiff"],
                capture_output=True, timeout=10,
            )
    except Exception:
        pass


def fmt(seconds) -> str:
    if seconds is None:
        return "?"
    seconds = max(0, int(seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


class LotWatch:
    def __init__(self, spec: dict, costs: dict):
        self.id = spec["id"]
        self.name = spec.get("nome") or str(spec["id"])
        self.max_bid = float(spec["max_bid"])
        self.resale = spec.get("resale_estimate")
        self.costs = costs
        self.done = False
        self.alerted_window = False
        self.alerted_over = False
        self.last_high = None

    def check(self, client: HiBidClient, cfg_w: dict) -> int:
        """Consulta o estado e emite alertas. Retorna segundos ate proxima
        checagem sugerida para este lote."""
        st = client.lot_state(self.id)
        tls = st.time_left_seconds
        stamp = datetime.now().strftime("%H:%M:%S")
        line = (f"[{stamp}] {self.name}: lance ${st.high_bid:.0f} "
                f"({st.bid_count} lances) · falta {fmt(tls)} · teto ${self.max_bid:.0f}")
        print(line)

        if st.is_closed or (tls is not None and tls <= 0):
            won_range = st.high_bid <= self.max_bid
            notify("Lote encerrado",
                   f"{self.name} fechou em ${st.high_bid:.0f} "
                   f"({'dentro' if won_range else 'acima'} do teto)")
            print(f"  >> ENCERRADO em ${st.high_bid:.0f}")
            self.done = True
            return 0

        # Preco passou do teto -> desistir (disciplina)
        if st.high_bid > self.max_bid and not self.alerted_over:
            self.alerted_over = True
            notify("ESTOUROU O TETO",
                   f"{self.name}: ${st.high_bid:.0f} > max ${self.max_bid:.0f}. Soltar.")
            print(f"  >> ESTOUROU O TETO (${st.high_bid:.0f} > ${self.max_bid:.0f})")

        # Momento do lance: janela final E preco ainda dentro do teto
        window = cfg_w.get("bid_window_seconds", 300)
        if (tls is not None and tls <= window
                and st.high_bid <= self.max_bid and not self.alerted_window):
            self.alerted_window = True
            allin = all_in_cost(min(st.min_bid or st.high_bid + 1, self.max_bid),
                                self.costs["buyer_premium_default"],
                                self.costs["hst"])
            extra = f" · revenda est. ${self.resale}" if self.resale else ""
            notify("HORA DO LANCE 🔨",
                   f"{self.name}: falta {fmt(tls)}, lance ${st.high_bid:.0f}, "
                   f"custo real ~${allin:.0f}{extra}")
            print(f"  >> HORA DO LANCE — abrir {lot_url(self.id)}")

        # Alguem cobriu desde a ultima checagem
        if self.last_high is not None and st.high_bid > self.last_high:
            print(f"  >> lance subiu ${self.last_high:.0f} -> ${st.high_bid:.0f}")
        self.last_high = st.high_bid

        if tls is None:
            return cfg_w.get("poll_far", 300)
        if tls < 600:
            return cfg_w.get("poll_final", 15)
        if tls < 3600:
            return cfg_w.get("poll_near", 60)
        return cfg_w.get("poll_far", 300)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="uma passada e sai")
    args = ap.parse_args()

    cfg = load_yaml("flip.yaml")
    wl = load_yaml("watchlist.yaml")
    lots = wl.get("lots") or []
    if not lots:
        print("watchlist vazia — adicionar lotes em config/watchlist.yaml "
              "(id + max_bid). Rodar scripts/scan.py para achar candidatos.")
        return

    cfg_w = cfg.get("watcher", {})
    client = HiBidClient()
    watches = [LotWatch(s, cfg["costs"]) for s in lots]
    print(f"Vigiando {len(watches)} lote(s). Lance e manual — o robo so avisa.\n")

    next_check = {w.id: 0.0 for w in watches}
    while True:
        now = time.monotonic()
        for w in watches:
            if w.done or now < next_check[w.id]:
                continue
            try:
                delay = w.check(client, cfg_w)
            except Exception as e:
                print(f"  !! erro em {w.name}: {e} (tento de novo em 60s)")
                delay = 60
            next_check[w.id] = time.monotonic() + delay
        if args.once or all(w.done for w in watches):
            break
        sleep_for = min((next_check[w.id] for w in watches if not w.done),
                        default=0) - time.monotonic()
        time.sleep(max(1.0, min(sleep_for, 60.0)))

    if all(w.done for w in watches):
        print("\nTodos os lotes encerrados. Registrar resultados no ledger!")


if __name__ == "__main__":
    main()

"""
Monitor Betfair Exchange Italia — Fase 0, filone TRADING (solo lettura).

A differenza del monitor su The Odds API, qui NON cerchiamo arbitraggi fra
bookmaker diversi: con un solo operatore non esistono. Qui misuriamo il book
del mercato su cui si puo' davvero operare, per rispondere alla domanda:

    lo spread back/lay e' abbastanza stretto, e i prezzi si muovono abbastanza,
    da poterci fare trading?

Per ogni corridore registra: miglior back, miglior lay, i volumi disponibili
su entrambi i lati e lo spread. Tutto finisce in data/betfair_book.csv, che
diventa la serie storica su cui misurare i movimenti.

Uso:
    python src/betfair_monitor.py           # una lettura sola
    python src/betfair_monitor.py --loop    # rilegge ogni BETFAIR_INTERVALLO_SEC
    python src/betfair_monitor.py --sport   # elenca gli sport disponibili ed esce
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from betfair_api import BetfairAPI, BetfairError  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "betfair_book.csv")
CSV_FIELDS = [
    "ts_utc", "market_id", "evento", "competizione", "start_time", "totale_scambiato",
    "selection_id", "corridore", "back", "back_size", "lay", "lay_size", "spread_pct",
]


def miglior_prezzo(lista):
    """Betfair ordina le offerte dalla migliore in poi. Ritorna (prezzo, volume)."""
    if not lista:
        return (None, None)
    return (lista[0].get("price"), lista[0].get("size"))


def spread_pct(back, lay):
    """
    Distanza fra i due lati, in percentuale sul back.
    E' il costo implicito di entrare e uscire: piu' e' stretto, piu' il
    trading e' possibile. Se risulta <= 0 il book e' incrociato = anomalia.
    """
    if not back or not lay:
        return None
    return round((lay - back) / back * 100, 3)


def leggi_book(api: BetfairAPI, cfg: dict):
    """Una lettura completa: catalogo dei mercati piu' liquidi + book corrente."""
    catalogo = api.list_market_catalogue(
        ore_avanti=cfg["ore_avanti"],
        max_risultati=cfg["max_mercati"],
        event_type_ids=cfg["event_type_ids"] or None,
    )
    if not catalogo:
        return []

    # Il book restituisce solo gli id: i nomi stanno nel catalogo, vanno uniti.
    per_id = {m["marketId"]: m for m in catalogo}
    nomi = {m["marketId"]: {r["selectionId"]: r["runnerName"]
                            for r in m.get("runners", [])}
            for m in catalogo}

    righe = []
    for book in api.list_market_book(list(per_id.keys())):
        mid = book["marketId"]
        meta = per_id.get(mid, {})
        evento = meta.get("event", {}) or {}
        comp = meta.get("competition", {}) or {}

        for r in book.get("runners", []):
            ex = r.get("ex", {}) or {}
            back, back_size = miglior_prezzo(ex.get("availableToBack"))
            lay, lay_size = miglior_prezzo(ex.get("availableToLay"))
            righe.append({
                "market_id": mid,
                "evento": evento.get("name", ""),
                "competizione": comp.get("name", ""),
                "start_time": meta.get("marketStartTime", ""),
                "totale_scambiato": book.get("totalMatched", 0),
                "selection_id": r.get("selectionId"),
                "corridore": nomi.get(mid, {}).get(r.get("selectionId"), ""),
                "back": back,
                "back_size": back_size,
                "lay": lay,
                "lay_size": lay_size,
                "spread_pct": spread_pct(back, lay),
            })
    return righe


def scrivi_csv(righe: list):
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    nuovo = not os.path.exists(CSV_PATH)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if nuovo:
            w.writeheader()
        for r in righe:
            w.writerow({"ts_utc": ts, **r})


def mediana(valori):
    v = sorted(valori)
    n = len(v)
    if not n:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def stampa(righe: list, min_scambiato: float):
    """Riepilogo leggibile: quanto e' stretto il mercato e dove ci sono anomalie."""
    validi = [r for r in righe if r["spread_pct"] is not None]
    if not validi:
        print("  nessun prezzo disponibile su entrambi i lati.")
        return

    # Book incrociato: lay piu' basso del back = profitto immediato.
    # Sull'Exchange e' rarissimo e di solito dura una frazione di secondo;
    # con la chiave delayed lo vedremmo comunque troppo tardi. Lo segnaliamo
    # perche' e' comunque un indicatore di quanto il mercato sia efficiente.
    incrociati = [r for r in validi if r["spread_pct"] <= 0]
    for r in incrociati:
        print(f"  !! BOOK INCROCIATO  {r['evento']} - {r['corridore']}: "
              f"back {r['back']} / lay {r['lay']}")

    # La media su tutti i corridori non dice niente: e' dominata dai mercati
    # morti, dove lo spread e' enorme perche' non c'e' nessuno dall'altra parte.
    # Quello che conta e' lo spread DOVE si potrebbe davvero operare.
    liquidi = [r for r in validi if (r["totale_scambiato"] or 0) >= min_scambiato]
    print(f"  {len(validi)} corridori letti, {len(liquidi)} su mercati con almeno "
          f"{min_scambiato:,.0f} EUR scambiati")
    if liquidi:
        sp = [r["spread_pct"] for r in liquidi]
        depth = [min(r["back_size"] or 0, r["lay_size"] or 0) for r in liquidi]
        print(f"  spread sui liquidi : mediana {mediana(sp):.2f}%  "
              f"(min {min(sp):.2f}%, max {max(sp):.2f}%)")
        print(f"  profondita' al top : mediana {mediana(depth):,.0f} EUR  "
              f"(e' quanto puoi muovere senza spostare il prezzo)")

    # I mercati piu' liquidi, che sono gli unici tradabili sul serio
    per_mercato = {}
    for r in validi:
        per_mercato.setdefault(r["market_id"], []).append(r)
    top = sorted(per_mercato.values(),
                 key=lambda rs: -(rs[0]["totale_scambiato"] or 0))[:5]

    print("\n  mercati piu' liquidi:")
    for rs in top:
        r0 = rs[0]
        sp = sum(x["spread_pct"] for x in rs) / len(rs)
        print(f"    {(r0['evento'] or '?')[:42]:42} "
              f"scambiati {r0['totale_scambiato']:>10,.0f} EUR   spread medio {sp:5.2f}%")
        for x in rs:
            print(f"        {(x['corridore'] or '?')[:30]:30} "
                  f"back {str(x['back']):>7} ({x['back_size'] or 0:>8,.0f})   "
                  f"lay {str(x['lay']):>7} ({x['lay_size'] or 0:>8,.0f})")


def carica_config():
    load_dotenv()
    app_key = os.getenv("BETFAIR_APP_KEY", "").strip()
    user = os.getenv("BETFAIR_USERNAME", "").strip()
    pwd = os.getenv("BETFAIR_PASSWORD", "").strip()

    if not app_key:
        print("!! Manca BETFAIR_APP_KEY in .env")
        return None
    if not user or not pwd:
        print("!! Mancano BETFAIR_USERNAME / BETFAIR_PASSWORD in .env")
        print("   Aprilo con Blocco note e compila le due righe: restano solo sul tuo PC.")
        return None

    ids = [i.strip() for i in os.getenv("BETFAIR_EVENT_TYPE_IDS", "").split(",") if i.strip()]
    return {
        "app_key": app_key,
        "username": user,
        "password": pwd,
        "max_mercati": int(os.getenv("BETFAIR_MAX_MERCATI", "20")),
        "ore_avanti": int(os.getenv("BETFAIR_ORE_AVANTI", "48")),
        "intervallo": int(os.getenv("BETFAIR_INTERVALLO_SEC", "60")),
        "min_scambiato": float(os.getenv("BETFAIR_MIN_SCAMBIATO", "1000")),
        "event_type_ids": ids,
    }


def main():
    ap = argparse.ArgumentParser(description="Monitor book Betfair Exchange Italia (read-only)")
    ap.add_argument("--loop", action="store_true", help="rilegge in continuo")
    ap.add_argument("--sport", action="store_true", help="elenca gli sport disponibili ed esce")
    ap.add_argument("--event-type", help="id sport da seguire (1=calcio, 2=tennis...)")
    args = ap.parse_args()

    cfg = carica_config()
    if not cfg:
        return
    if args.event_type:
        cfg["event_type_ids"] = [args.event_type]

    api = BetfairAPI(cfg["app_key"], cfg["username"], cfg["password"])
    try:
        api.login()
    except BetfairError as e:
        print(f"!! {e}")
        print("   Controlla username/password in .env. Se il conto ha la verifica in due")
        print("   passaggi attiva, il login via API va abilitato dalle impostazioni Betfair.")
        return
    print("login riuscito su betfair.it (dati ritardati 1-180 s, chiave delayed)\n")

    if args.sport:
        print("Sport disponibili sull'Exchange italiano:")
        for et in sorted(api.list_event_types(), key=lambda x: -x["marketCount"]):
            t = et["eventType"]
            print(f"  id {t['id']:>6}  {t['name']:<28} {et['marketCount']:>6} mercati")
        print("\n(per seguirne solo alcuni: BETFAIR_EVENT_TYPE_IDS=1,2 in .env)")
        return

    while True:
        print(f"--- lettura delle {datetime.now().strftime('%H:%M:%S')} ---")
        try:
            righe = leggi_book(api, cfg)
        except BetfairError as e:
            print(f"  ! {e}")
            righe = []

        if righe:
            scrivi_csv(righe)
            stampa(righe, cfg["min_scambiato"])
            print(f"\nLog: {CSV_PATH}")
        else:
            print("  nessun mercato trovato nella finestra richiesta.")

        if not args.loop:
            break
        print(f"\n(riprovo fra {cfg['intervallo']} s - Ctrl+C per fermare)\n")
        time.sleep(cfg["intervallo"])
        api.keep_alive()


if __name__ == "__main__":
    main()

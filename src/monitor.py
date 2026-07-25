"""
Monitor inefficienze — Fase 0 (solo misurazione, nessuna scommessa piazzata).

Per ogni match, su QUALSIASI sport:
  1. trova la MIGLIOR quota per ciascun esito tra tutti i bookmaker
  2. la converte in quota NETTA (le exchange trattengono commissione sulle vincite)
  3. somma le probabilita' implicite (1/quota_netta)
  4. se la somma < 100%  ->  ARBITRAGGIO (profitto garantito qualunque esito)

Ogni match analizzato finisce in data/osservazioni.csv: e' quello il vero
prodotto della Fase 0, perche' permette di misurare nel tempo quante
inefficienze escono, quanto grandi sono e quanto durano.

Uso:
    python src/monitor.py                  # una passata sola
    python src/monitor.py --loop           # continua a girare all'intervallo di .env
    python src/monitor.py --sport soccer_italy_serie_a
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from odds_api import OddsAPI  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "osservazioni.csv")
CSV_FIELDS = [
    "ts_utc", "sport_key", "sport_title", "match", "commence_time",
    "n_book", "margine_lordo_pct", "margine_netto_pct", "is_arb", "legs_json",
]

# Exchange: non incassi la quota piena, trattengono una commissione sulla vincita netta.
EXCHANGE_BOOKS = {"betfair", "matchbook", "smarkets", "betdaq"}


# --------------------------------------------------------------------------
# Calcoli
# --------------------------------------------------------------------------

def quota_netta(quota: float, book: str, commissione: float) -> float:
    """
    Quota realmente incassata. Su un'exchange la commissione si applica
    alla vincita netta, quindi 1 + (quota - 1) * (1 - commissione).
    Sui bookmaker tradizionali la quota resta quella esposta.
    """
    if book.lower().split()[0] in EXCHANGE_BOOKS:
        return 1.0 + (quota - 1.0) * (1.0 - commissione)
    return quota


def implied_prob(quota: float) -> float:
    """Probabilita' implicita di una quota decimale."""
    return 1.0 / quota


def best_odds_per_outcome(match: dict, cfg: dict):
    """
    Scorre tutti i bookmaker di un match e trova, per ogni esito, la quota
    piu' alta (= migliore per chi scommette) e chi la offre.

    Applica due filtri anti-falso-positivo:
      - quote sopra MAX_ODDS ignorate (le quote monstre tipo 501 sono residui,
        non prezzi su cui si punta davvero)
      - se BOOK_WHITELIST e' valorizzata, considera solo quei bookmaker

    Ritorna: { nome_esito: (quota_esposta, quota_netta, bookmaker) }
    """
    best = {}
    for bk in match.get("bookmakers", []):
        titolo = bk.get("title", "")
        if cfg["whitelist"] and titolo.lower() not in cfg["whitelist"]:
            continue
        for market in bk.get("markets", []):
            if market["key"] != "h2h":
                continue
            for outcome in market["outcomes"]:
                nome, quota = outcome["name"], outcome["price"]
                if quota > cfg["max_odds"] or quota <= 1.0:
                    continue
                netta = quota_netta(quota, titolo, cfg["commissione"])
                if nome not in best or netta > best[nome][1]:
                    best[nome] = (quota, netta, titolo)
    return best


def minuti_all_inizio(match: dict):
    """Minuti che mancano al via. Negativo se il match e' gia' cominciato."""
    grezzo = match.get("commence_time")
    if not grezzo:
        return None
    inizio = datetime.fromisoformat(grezzo.replace("Z", "+00:00"))
    return (inizio - datetime.now(timezone.utc)).total_seconds() / 60


def analyse(match: dict, cfg: dict):
    """
    Analizza un match. Ritorna sempre un dizionario (serve per il CSV),
    con is_arb=True solo se il margine netto supera la soglia.
    """
    # Match gia' iniziati: le quote sono in-play o non piu' aggiornate.
    # Sono la sorgente numero uno di arbitraggi finti, quindi fuori.
    mancano = minuti_all_inizio(match)
    if mancano is not None and mancano < cfg["min_minuti"]:
        return None

    best = best_odds_per_outcome(match, cfg)
    if len(best) < 2:
        return None  # servono almeno 2 esiti quotati

    # Quanti bookmaker quotano davvero questo match: e' la misura della
    # copertura. Un arb sostenuto da pochi book e' quasi sempre rumore
    # (quota stantia di uno solo), non una vera inefficienza di mercato.
    n_book = len({bk.get("title", "") for bk in match.get("bookmakers", [])
                  if any(mk["key"] == "h2h" for mk in bk.get("markets", []))
                  and (not cfg["whitelist"] or bk.get("title", "").lower() in cfg["whitelist"])})
    prob_lorda = sum(implied_prob(q) for q, _, _ in best.values())
    prob_netta = sum(implied_prob(n) for _, n, _ in best.values())

    profitto_netto = 1.0 - prob_netta
    is_arb = (
        profitto_netto >= cfg["min_profit"]
        and n_book >= cfg["min_book"]
    )

    return {
        "sport_key": match.get("sport_key", ""),
        "sport_title": match.get("sport_title", ""),
        "match": f'{match.get("home_team")} vs {match.get("away_team")}',
        "commence_time": match.get("commence_time", ""),
        "n_book": n_book,
        "margine_lordo_pct": round((1.0 - prob_lorda) * 100, 3),
        "margine_netto_pct": round(profitto_netto * 100, 3),
        "is_arb": is_arb,
        "legs": {nome: {"quota": q, "netta": round(n, 3), "book": b}
                 for nome, (q, n, b) in best.items()},
    }


def ripartizione_puntate(legs: dict, totale: float):
    """
    Come dividere una puntata totale fra gli esiti perche' l'incasso sia
    identico qualunque cosa succeda. Puntata_i proporzionale a 1/quota_netta_i.
    """
    inv = {nome: 1.0 / leg["netta"] for nome, leg in legs.items()}
    somma = sum(inv.values())
    return {nome: round(totale * v / somma, 2) for nome, v in inv.items()}


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

def scrivi_csv(righe: list):
    """Accoda le osservazioni al CSV, creando header e cartella se mancano."""
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    nuovo = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if nuovo:
            w.writeheader()
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for r in righe:
            w.writerow({
                "ts_utc": ts,
                "sport_key": r["sport_key"],
                "sport_title": r["sport_title"],
                "match": r["match"],
                "commence_time": r["commence_time"],
                "n_book": r["n_book"],
                "margine_lordo_pct": r["margine_lordo_pct"],
                "margine_netto_pct": r["margine_netto_pct"],
                "is_arb": int(r["is_arb"]),
                "legs_json": json.dumps(r["legs"], ensure_ascii=False),
            })


# --------------------------------------------------------------------------
# Configurazione
# --------------------------------------------------------------------------

def carica_config():
    load_dotenv()
    key = os.getenv("ODDS_API_KEY", "").strip()
    if not key or key.startswith("incolla"):
        print("!! Manca la API key. Copia .env.example in .env e incolla la tua key.")
        print("   Registrazione gratuita: https://the-odds-api.com")
        return None

    whitelist = {b.strip().lower()
                 for b in os.getenv("BOOK_WHITELIST", "").split(",") if b.strip()}

    return {
        "key": key,
        "regions": os.getenv("ODDS_REGIONS", "eu"),
        "sports": [s.strip() for s in os.getenv("ODDS_SPORTS", "upcoming").split(",") if s.strip()],
        "min_profit": float(os.getenv("MIN_ARB_PROFIT", "0.005")),
        "max_odds": float(os.getenv("MAX_ODDS", "30")),
        "min_book": int(os.getenv("MIN_BOOKMAKERS", "4")),
        "min_minuti": float(os.getenv("MIN_MINUTI_ALL_INIZIO", "15")),
        "commissione": float(os.getenv("BETFAIR_COMMISSION", "0.05")),
        "whitelist": whitelist,
        "intervallo_min": int(os.getenv("LOOP_MINUTES", "120")),
        "puntata": float(os.getenv("PUNTATA_ESEMPIO", "100")),
    }


# --------------------------------------------------------------------------
# Passata singola
# --------------------------------------------------------------------------

def passata(api: OddsAPI, cfg: dict):
    tutte = []
    for sport in cfg["sports"]:
        try:
            matches = api.get_h2h_odds(sport)
        except Exception as e:
            print(f"  ! errore su {sport}: {e}")
            continue

        analizzati = [a for a in (analyse(m, cfg) for m in matches) if a]
        tutte.extend(analizzati)
        print(f"[{sport}] {len(matches)} match ricevuti, {len(analizzati)} analizzabili")

    if not tutte:
        print("Nessun match analizzabile in questa passata.")
        return 0

    scrivi_csv(tutte)

    arbs = [a for a in tutte if a["is_arb"]]
    for a in sorted(arbs, key=lambda x: -x["margine_netto_pct"]):
        print(f"\n  >>> ARBITRAGGIO {a['margine_netto_pct']}% netto "
              f"({a['margine_lordo_pct']}% lordo)  |  {a['match']}")
        print(f"      {a['sport_title']} - inizio {a['commence_time']} - {a['n_book']} book")
        puntate = ripartizione_puntate(a["legs"], cfg["puntata"])
        for nome, leg in a["legs"].items():
            print(f"      - {nome}: quota {leg['quota']} @ {leg['book']}"
                  f"   -> punta {puntate[nome]} EUR")

    # I match piu' vicini all'arbitraggio: utile per capire quanto siamo lontani
    vicini = sorted(tutte, key=lambda x: -x["margine_netto_pct"])[:5]
    print("\n  margini netti migliori di questa passata:")
    for a in vicini:
        print(f"    {a['margine_netto_pct']:+7.2f}%  {a['match'][:55]:55} ({a['n_book']} book)")

    return len(arbs)


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Monitor inefficienze quote (read-only)")
    ap.add_argument("--loop", action="store_true", help="gira in continuo")
    ap.add_argument("--sport", help="forza una sport key (sovrascrive ODDS_SPORTS)")
    args = ap.parse_args()

    cfg = carica_config()
    if not cfg:
        return
    if args.sport:
        cfg["sports"] = [args.sport]

    api = OddsAPI(cfg["key"], cfg["regions"])
    costo = len(cfg["sports"]) * len(cfg["regions"].split(","))

    print(f"Sport monitorati : {cfg['sports']}")
    print(f"Regioni          : {cfg['regions']}")
    print(f"Costo per passata: {costo} richieste")
    if args.loop:
        passate_al_mese = (1440 / max(cfg["intervallo_min"], 1)) * 30
        al_mese = int(costo * passate_al_mese)
        avviso = "  <-- SFORA il piano gratuito!" if al_mese > 500 else ""
        print(f"Intervallo       : {cfg['intervallo_min']} min "
              f"(~{al_mese} richieste/mese, il piano gratuito ne da' 500){avviso}")
    print(f"Filtri           : quota max {cfg['max_odds']}, almeno {cfg['min_book']} book, "
          f"almeno {cfg['min_minuti']:.0f} min al via, "
          f"soglia {cfg['min_profit'] * 100:.2f}% netto, commissione exchange "
          f"{cfg['commissione'] * 100:.0f}%")
    print()

    totale = 0
    while True:
        inizio = datetime.now().strftime("%H:%M:%S")
        print(f"--- passata delle {inizio} ---")
        totale += passata(api, cfg)
        print(f"\nRichieste rimaste: {api.remaining}   |   arbitraggi totali finora: {totale}")
        print(f"Log: {CSV_PATH}")

        if not args.loop:
            break
        print(f"\n(attendo {cfg['intervallo_min']} minuti - Ctrl+C per fermare)\n")
        time.sleep(cfg["intervallo_min"] * 60)


if __name__ == "__main__":
    main()

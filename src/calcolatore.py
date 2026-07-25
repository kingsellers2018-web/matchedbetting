"""
Calcolatore matched betting — lato Betfair in tempo reale, lato bookmaker a mano.

Perche' cosi': non esiste una fonte di quote dei bookmaker italiani utilizzabile
(The Odds API non ne copre nessuno, lo scraping viola i termini d'uso). Ma il lato
che conta davvero — il LAY sull'Exchange, con il prezzo e la liquidita' reali — lo
prendiamo via API. La quota del bookmaker la leggi tu sul sito dove hai il conto e
la digiti: sono cinque secondi, e non serve alcuna scorciatoia discutibile.

Il programma calcola quanto layare perche' l'esito sia identico comunque vada, e
mostra il profitto nei due scenari. Applica i vincoli dell'Exchange italiano
(puntata minima 2,00 EUR a scatti di 0,50) e ricalcola sui valori arrotondati,
perche' e' quello che succede davvero quando piazzi.

TRE TIPI DI SCOMMESSA:
  qualifying  scommessa normale, il bookmaker ti restituisce la puntata.
              Serve a sbloccare il bonus: qui l'obiettivo e' perdere il MENO
              possibile, non guadagnare.
  freebet     bonus con puntata NON restituita (il caso normale). Qui si guadagna.
  freebet-sr  bonus con puntata restituita (raro, piu' generoso).

Solo lettura: nessuna scommessa viene piazzata, ne' su Betfair ne' altrove.

Uso:
    python src/calcolatore.py --cerca "Juventus"
    python src/calcolatore.py --market 1.2345 --runner "Juventus" --quota-book 3.5 --puntata 10
    python src/calcolatore.py --market 1.2345 --runner "Juventus" --quota-book 6.0 --puntata 25 --tipo freebet
"""
import argparse
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from betfair_api import BetfairAPI, BetfairError  # noqa: E402

# Vincoli regolamentari dell'Exchange italiano
PUNTATA_MINIMA = 2.00
SCATTO = 0.50
VINCITA_MASSIMA = 10000.0


def arrotonda(stake: float) -> float:
    """L'Exchange italiano accetta solo multipli di 0,50 EUR, minimo 2,00."""
    if stake <= 0:
        return 0.0
    return max(PUNTATA_MINIMA, round(stake / SCATTO) * SCATTO)


def lay_stake(tipo: str, quota_book: float, puntata: float,
              quota_lay: float, commissione: float) -> float:
    """
    Quanto layare per pareggiare i due scenari.

    Con la puntata restituita si copre l'intero ritorno (quota x puntata);
    con la free bet non restituita si copre solo la vincita netta, perche' la
    puntata non torna indietro.
    """
    denom = quota_lay - commissione
    if denom <= 0:
        return 0.0
    if tipo == "freebet":
        return (quota_book - 1) * puntata / denom
    return quota_book * puntata / denom


def esiti(tipo: str, quota_book: float, puntata: float, quota_lay: float,
          ls: float, commissione: float):
    """Profitto nei due scenari possibili. Con un lay stake corretto sono uguali."""
    responsabilita = ls * (quota_lay - 1)

    if tipo == "freebet":
        # La puntata non torna: se vince il book incassi solo la vincita netta.
        se_vince_book = puntata * (quota_book - 1) - responsabilita
        se_perde_book = ls * (1 - commissione)
    else:
        se_vince_book = puntata * (quota_book - 1) - responsabilita
        se_perde_book = ls * (1 - commissione) - puntata

    return se_vince_book, se_perde_book, responsabilita


def quota_pareggio(quota_lay: float, commissione: float, margine: float = 0.0):
    """
    Quota che il bookmaker deve superare perche' l'operazione sia in utile.

    Backando a quota B e layando a quota L, l'utile in rapporto alla puntata e'
    B(1-c)/(L-c) - 1. Azzerandolo si ottiene B = (L-c)/(1-c): sotto quella soglia
    si perde comunque, sopra si guadagna qualunque cosa succeda.
    """
    return (1 + margine) * (quota_lay - commissione) / (1 - commissione)


def soglie(api: BetfairAPI, market_id: str, commissione: float):
    """Per ogni esito: la quota da cercare sul sito del bookmaker."""
    libri = api.list_market_book([market_id])
    if not libri:
        print(f"!! market {market_id} non trovato.")
        return
    book = libri[0]
    cat = api._rpc("listMarketCatalogue", {
        "filter": {"marketIds": [market_id]},
        "marketProjection": ["EVENT", "RUNNER_DESCRIPTION"], "maxResults": 1,
    })
    nomi = {r["selectionId"]: r["runnerName"] for r in cat[0]["runners"]} if cat else {}

    print("=" * 74)
    print(f"  {cat[0]['event']['name'] if cat else '?'}")
    print(f"  scambiati {book.get('totalMatched', 0):,.0f} EUR  |  "
          f"commissione {commissione * 100:.0f}%")
    print("=" * 74)
    print(f"  {'esito':<22} {'lay Betfair':>12} {'disp.':>9}   "
          f"{'pari':>7} {'+1%':>7} {'+2%':>7}")
    print(f"  {'':<22} {'':>12} {'':>9}   {'<-- quota da battere sul bookmaker -->':>23}")

    for run in book.get("runners", []):
        ex = run.get("ex", {}) or {}
        atl = ex.get("availableToLay") or []
        if not atl:
            continue
        q, size = atl[0]["price"], atl[0]["size"]
        nome = nomi.get(run["selectionId"], "?")
        print(f"  {nome[:22]:<22} {q:>12} {size:>8,.0f}   "
              f"{quota_pareggio(q, commissione):>7.2f} "
              f"{quota_pareggio(q, commissione, 0.01):>7.2f} "
              f"{quota_pareggio(q, commissione, 0.02):>7.2f}")

    print("\n  Come si usa: apri il sito del bookmaker su questo evento. Se trovi una")
    print("  quota SOPRA la colonna 'pari', backi li' e layi su Betfair: guadagni")
    print("  qualunque sia il risultato. Sotto quella soglia si perde comunque.")


def cerca(api: BetfairAPI, testo: str):
    mercati = api._rpc("listMarketCatalogue", {
        "filter": {"textQuery": testo, "marketTypeCodes": ["MATCH_ODDS"]},
        "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
        "sort": "MAXIMUM_TRADED", "maxResults": 20,
    })
    if not mercati:
        print(f"Nessun mercato trovato per '{testo}'.")
        return

    libri = {b["marketId"]: b for b in api.list_market_book(
        [m["marketId"] for m in mercati])}

    for m in mercati:
        b = libri.get(m["marketId"], {})
        prezzi = {}
        for run in b.get("runners", []):
            atl = (run.get("ex", {}) or {}).get("availableToLay") or []
            prezzi[run["selectionId"]] = (atl[0]["price"], atl[0]["size"]) if atl else (None, 0)

        print(f"\n  market {m['marketId']}  |  {m['event']['name']}")
        print(f"    inizio {m.get('marketStartTime', '?')}  "
              f"scambiati {b.get('totalMatched', 0):,.0f} EUR")
        for run in m.get("runners", []):
            q, size = prezzi.get(run["selectionId"], (None, 0))
            print(f"      {run['runnerName'][:34]:34} lay {str(q):>7}  "
                  f"disponibili {size:>9,.0f} EUR")


def calcola(api: BetfairAPI, args):
    libri = api.list_market_book([args.market])
    if not libri:
        print(f"!! market {args.market} non trovato.")
        return
    book = libri[0]

    cat = api._rpc("listMarketCatalogue", {
        "filter": {"marketIds": [args.market]},
        "marketProjection": ["EVENT", "RUNNER_DESCRIPTION"], "maxResults": 1,
    })
    nomi = {r["selectionId"]: r["runnerName"] for r in cat[0]["runners"]} if cat else {}
    evento = cat[0]["event"]["name"] if cat else "?"

    sid = next((s for s, n in nomi.items()
                if args.runner.lower() in n.lower()), None)
    if sid is None:
        print(f"!! '{args.runner}' non e' fra i corridori: {list(nomi.values())}")
        return

    run = next((r for r in book.get("runners", []) if r["selectionId"] == sid), None)
    atl = ((run or {}).get("ex", {}) or {}).get("availableToLay") or []
    if not atl:
        print("!! nessun prezzo lay disponibile su questa selezione.")
        return
    quota_lay, disponibile = atl[0]["price"], atl[0]["size"]

    c = args.commissione
    teorico = lay_stake(args.tipo, args.quota_book, args.puntata, quota_lay, c)
    reale = arrotonda(teorico)

    v_teo, p_teo, _ = esiti(args.tipo, args.quota_book, args.puntata, quota_lay, teorico, c)
    v, p, resp = esiti(args.tipo, args.quota_book, args.puntata, quota_lay, reale, c)

    etichetta = {"qualifying": "scommessa normale (puntata restituita)",
                 "freebet": "free bet, puntata NON restituita",
                 "freebet-sr": "free bet, puntata restituita"}[args.tipo]

    print("=" * 70)
    print(f"  {evento} — {nomi[sid]}")
    print(f"  {etichetta}")
    print("=" * 70)
    print(f"  Bookmaker : back a quota {args.quota_book} con {args.puntata:.2f} EUR")
    print(f"  Betfair   : lay a quota {quota_lay}  "
          f"({disponibile:,.0f} EUR disponibili, commissione {c * 100:.0f}%)")
    print()
    print(f"  DA LAYARE : {reale:.2f} EUR      (calcolo esatto {teorico:.2f}, "
          f"arrotondato allo scatto di 0,50)")
    print(f"  Ti serve  : {resp:.2f} EUR liberi sul conto Betfair (responsabilita')")
    print()
    print("  RISULTATO")
    print(f"    se vince al bookmaker : {v:+.2f} EUR")
    print(f"    se vince su Betfair   : {p:+.2f} EUR")
    peggiore = min(v, p)
    print(f"    caso peggiore         : {peggiore:+.2f} EUR "
          f"({peggiore / args.puntata * 100:+.1f}% della puntata)")

    # Il calcolo esatto pareggia i due scenari per costruzione: se dopo
    # l'arrotondamento non pareggiano piu', il colpevole e' lo scatto da 0,50.
    if abs(v - p) > 0.05:
        print(f"\n  nota: con il lay stake esatto ({teorico:.2f} EUR) i due esiti")
        print(f"  sarebbero entrambi {v_teo:+.2f} EUR. Lo scatto obbligatorio da")
        print(f"  0,50 EUR li sbilancia di {abs(v - p):.2f} EUR: su puntate piccole")
        print("  pesa parecchio, e va sempre letto il caso peggiore.")

    if reale > disponibile:
        print(f"\n  !! ATTENZIONE: servono {reale:.2f} EUR ma al miglior prezzo ce ne")
        print(f"     sono solo {disponibile:,.0f}. Layando di piu' peggiori la quota")
        print("     e il conto torna diverso da quello qui sopra.")

    if args.tipo == "qualifying" and peggiore < 0:
        print(f"\n  Questa e' la 'qualifying loss': il costo per sbloccare il bonus.")
        print(f"  Ha senso solo se il bonus vale piu' di {abs(peggiore):.2f} EUR.")

    if reale * (quota_lay - 1) > VINCITA_MASSIMA:
        print("\n  !! Superi il tetto di 10.000 EUR di vincita potenziale "
              "dell'Exchange italiano.")


def main():
    ap = argparse.ArgumentParser(description="Calcolatore matched betting (read-only)")
    ap.add_argument("--cerca", help="cerca eventi per testo e mostra le quote lay")
    ap.add_argument("--soglie", action="store_true",
                    help="con --market: quota minima da cercare sul bookmaker")
    ap.add_argument("--market", help="market id Betfair")
    ap.add_argument("--runner", help="nome (anche parziale) della selezione")
    ap.add_argument("--quota-book", type=float, help="quota letta sul sito del bookmaker")
    ap.add_argument("--puntata", type=float, help="quanto punti al bookmaker")
    ap.add_argument("--tipo", default="qualifying",
                    choices=["qualifying", "freebet", "freebet-sr"])
    ap.add_argument("--commissione", type=float, default=0.05)
    args = ap.parse_args()

    load_dotenv()
    api = BetfairAPI(os.getenv("BETFAIR_APP_KEY", ""),
                     os.getenv("BETFAIR_USERNAME", ""),
                     os.getenv("BETFAIR_PASSWORD", ""))
    try:
        api.login()
    except BetfairError as e:
        print(f"!! login fallito: {e}")
        return

    if args.cerca:
        cerca(api, args.cerca)
        return

    if args.soglie:
        if not args.market:
            print("!! --soglie richiede anche --market")
            return
        soglie(api, args.market, args.commissione)
        return

    if not all([args.market, args.runner, args.quota_book, args.puntata]):
        ap.print_help()
        print("\nEsempio:")
        print('  python src/calcolatore.py --cerca "Milan"')
        print('  python src/calcolatore.py --market 1.2345 --runner "Milan" '
              '--quota-book 3.5 --puntata 10')
        return

    calcola(api, args)


if __name__ == "__main__":
    main()

"""
LA TABELLA OPERATIVA: back al bookmaker, lay su Betfair Italia, profitto garantito.

Incrocia le due fonti che abbiamo:
  - The Odds API  -> quote BACK di ~22 bookmaker internazionali
  - Betfair Italia -> quote LAY reali, con la liquidita' disponibile

Per ogni esito calcola se esiste un bookmaker che paga piu' di quanto costa
coprirsi su Betfair, e in caso affermativo stampa le istruzioni esatte:
quanto puntare, quanto bancare, quanta responsabilita' serve e quanto si
guadagna in ciascuno dei due scenari.

La struttura e' back-bookmaker / lay-exchange su UN SOLO esito: rende molto piu'
dell'arbitraggio a tre vie fra bookmaker, perche' non disperde la puntata.

    profitto/puntata = quota_book x (1 - commissione) / (quota_lay - commissione) - 1

Il dimensionamento tiene conto della liquidita' vera: se al miglior prezzo lay ci
sono 69 EUR, la puntata viene ridotta di conseguenza. Meglio un numero piccolo e
vero che uno grande e finto.

Solo lettura: non piazza nulla, ne' sul bookmaker ne' su Betfair.

Uso:
    python src/opportunita.py --sport soccer_sweden_allsvenskan
    python src/opportunita.py --sport soccer_sweden_allsvenskan,soccer_finland_veikkausliiga
    python src/opportunita.py --sport upcoming --puntata 200 --min-profit 1.0
    python src/opportunita.py --sport soccer_sweden_allsvenskan --book "Betsson,NordicBet"
"""
import argparse
import os
import sys
import unicodedata
from datetime import datetime, timezone

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from betfair_api import BetfairAPI, BetfairError  # noqa: E402
from odds_api import OddsAPI  # noqa: E402
from calcolatore import arrotonda, quota_pareggio  # noqa: E402

# Sull'Exchange il pareggio si chiama cosi'; sui bookmaker "Draw".
NOMI_PAREGGIO = {"draw", "the draw", "pareggio", "tie"}


# --------------------------------------------------------------------------
# Abbinamento dei nomi fra le due fonti
# --------------------------------------------------------------------------

def normalizza(s: str) -> str:
    """Minuscolo, senza accenti e senza punteggiatura: 'Mjällby AIF' -> 'mjallby aif'."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c if c.isalnum() or c.isspace() else " " for c in s.lower()).strip()


def token_significativi(s: str):
    """Le parole abbastanza lunghe da identificare una squadra: scarta IF, FC, AC..."""
    return {t for t in normalizza(s).split() if len(t) >= 4}


def stessa_squadra(a: str, b: str) -> bool:
    """
    Vero se i due nomi indicano la stessa squadra. Richiede che almeno un token
    lungo compaia da entrambe le parti: 'IF Brommapojkarna' e 'Brommapojkarna'
    combaciano, 'IK Sirius' e 'IR Reykjavik' no.
    """
    ta, tb = token_significativi(a), token_significativi(b)
    if not ta or not tb:
        return normalizza(a) == normalizza(b)
    if ta & tb:
        return True
    # fallback: un token contenuto dentro l'altro (Goteborg / Gothenburg no,
    # ma Mjallby / Mjallbyaif si')
    na, nb = normalizza(a).replace(" ", ""), normalizza(b).replace(" ", "")
    return any(t in nb for t in ta) or any(t in na for t in tb)


def istante(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def abbina(partita_odds: dict, mercati_bf: list, tolleranza_ore: float = 4.0):
    """Trova su Betfair il mercato che corrisponde alla partita di The Odds API."""
    casa, ospite = partita_odds.get("home_team", ""), partita_odds.get("away_team", "")
    t_odds = istante(partita_odds.get("commence_time"))

    for m in mercati_bf:
        nome = m["event"]["name"]
        if " v " not in nome:
            continue
        bf_casa, bf_ospite = nome.split(" v ", 1)

        if not (stessa_squadra(casa, bf_casa) and stessa_squadra(ospite, bf_ospite)):
            continue

        t_bf = istante(m.get("marketStartTime"))
        if t_odds and t_bf:
            if abs((t_bf - t_odds).total_seconds()) > tolleranza_ore * 3600:
                continue
        return m
    return None


def abbina_esito(nome_book: str, runners: dict):
    """Mappa il nome dell'esito del bookmaker sulla selezione Betfair."""
    if normalizza(nome_book) in NOMI_PAREGGIO:
        for sid, n in runners.items():
            if normalizza(n) in NOMI_PAREGGIO:
                return sid
        return None
    for sid, n in runners.items():
        if normalizza(n) in NOMI_PAREGGIO:
            continue
        if stessa_squadra(nome_book, n):
            return sid
    return None


# --------------------------------------------------------------------------
# Calcolo dell'operazione
# --------------------------------------------------------------------------

def operazione(quota_book: float, quota_lay: float, disponibile: float,
               puntata_max: float, commissione: float):
    """
    Dimensiona l'operazione sulla liquidita' reale e ritorna i numeri esatti.
    Ritorna None se non c'e' profitto o se non si rispettano i minimi italiani.
    """
    margine = quota_book * (1 - commissione) / (quota_lay - commissione) - 1
    if margine <= 0:
        return None

    # Il lay stake e' vincolato da quanto c'e' davvero al miglior prezzo.
    puntata = min(puntata_max, disponibile * (quota_lay - commissione) / quota_book)
    if puntata < 1:
        return None

    ls = arrotonda(quota_book * puntata / (quota_lay - commissione))
    if ls > disponibile:  # l'arrotondamento puo' sforare la liquidita'
        ls -= 0.50
    if ls < 2.0:
        return None

    responsabilita = ls * (quota_lay - 1)
    se_vince_book = puntata * (quota_book - 1) - responsabilita
    se_perde_book = ls * (1 - commissione) - puntata

    return {
        "margine_pct": margine * 100,
        "puntata": round(puntata, 2),
        "lay_stake": ls,
        "responsabilita": responsabilita,
        "se_vince_book": se_vince_book,
        "se_perde_book": se_perde_book,
        "garantito": min(se_vince_book, se_perde_book),
    }


# --------------------------------------------------------------------------
# Il motore, riutilizzabile: lo usano sia la riga di comando sia il worker
# --------------------------------------------------------------------------

def catalogo_betfair(bf: BetfairAPI, ore: int, event_type_ids=("1", "2", "7522")):
    """Mercati MATCH_ODDS in arrivo. Chiamata gratuita: si puo' fare sempre."""
    mercati = []
    for eid in event_type_ids:  # calcio, tennis, basket
        try:
            mercati.extend(bf.list_market_catalogue(
                ore_avanti=ore, max_risultati=200, event_type_ids=[eid]))
        except BetfairError:
            pass
    return mercati


def scegli_campionati(odds: OddsAPI, mercati: list, crediti_max: int, log=print):
    """
    Decide su quali campionati spendere crediti: solo quelli che esistono su
    entrambe le fonti, i piu' ricchi di eventi per primi.
    """
    from mappa_campionati import abbina_campionati, entro_budget

    sport = odds.list_sports(only_active=True)  # gratuita
    da_interrogare, orfani = abbina_campionati(mercati, sport)
    per_regione = len(odds.regions.split(","))
    tenuti, scartati = entro_budget(da_interrogare, crediti_max, per_regione)

    log(f"  campionati su entrambe le fonti : {len(da_interrogare)}")
    log(f"  solo su Betfair (nessun credito) : {len(orfani)}")
    if scartati:
        log(f"  esclusi per budget crediti       : {len(scartati)}")
    return tenuti, orfani, scartati


def scansiona(odds: OddsAPI, bf: BetfairAPI, sport_keys: list, ore: int = 72,
              puntata: float = 100, commissione: float = 0.05,
              whitelist: set = None, min_profit: float = 0.5,
              mercati: list = None, log=print):
    """
    Una passata completa. Ritorna un dizionario con tutto quello che serve sia
    per stampare a schermo sia per salvare a database.
    """
    whitelist = whitelist or set()

    if mercati is None:
        mercati = catalogo_betfair(bf, ore)
    log(f"  Betfair Italia : {len(mercati)} mercati nelle prossime {ore} ore")

    partite, errori = [], []
    for key in sport_keys:
        try:
            partite.extend(odds.get_h2h_odds(key))
        except Exception as e:
            errori.append(f"{key}: {e}")
            log(f"  ! errore su {key}: {e}")
    log(f"  The Odds API   : {len(partite)} partite  "
        f"(crediti rimasti: {odds.remaining})")

    coppie = [(p, m) for p in partite if (m := abbina(p, mercati))]
    log(f"  incrociati     : {len(coppie)} eventi su entrambe le fonti")

    trovate, vicine = [], []
    if coppie:
        libri = {b["marketId"]: b for b in bf.list_market_book(
            [m["marketId"] for _, m in coppie])}

        for p, m in coppie:
            libro = libri.get(m["marketId"])
            if not libro:
                continue
            runners = {r["selectionId"]: r["runnerName"] for r in m["runners"]}
            lay = {}
            for r in libro.get("runners", []):
                atl = (r.get("ex", {}) or {}).get("availableToLay") or []
                if atl:
                    lay[r["selectionId"]] = (atl[0]["price"], atl[0]["size"])

            for bk in p.get("bookmakers", []):
                if whitelist and bk["title"].lower() not in whitelist:
                    continue
                for mercato in bk.get("markets", []):
                    if mercato["key"] != "h2h":
                        continue
                    for o in mercato["outcomes"]:
                        sid = abbina_esito(o["name"], runners)
                        if sid is None or sid not in lay:
                            continue
                        q_lay, disp = lay[sid]
                        contesto = {
                            "market_id": m["marketId"],
                            "evento": m["event"]["name"],
                            "competizione": (m.get("competition") or {}).get("name", ""),
                            "inizio": m.get("marketStartTime", ""),
                            "esito": runners[sid],
                            "book": bk["title"],
                            "quota_book": o["price"],
                            "quota_lay": q_lay,
                            "disponibile": disp,
                        }
                        margine = (o["price"] * (1 - commissione)
                                   / (q_lay - commissione) - 1) * 100
                        vicine.append({**contesto, "margine_pct": margine})

                        op = operazione(o["price"], q_lay, disp, puntata, commissione)
                        if op and op["margine_pct"] >= min_profit:
                            trovate.append({**op, **contesto})

    trovate.sort(key=lambda x: -x["margine_pct"])
    vicine.sort(key=lambda x: -x["margine_pct"])
    return {
        "campionati": sport_keys,
        "crediti_spesi": len(sport_keys) * len(odds.regions.split(",")),
        "crediti_rimasti": odds.remaining,
        "partite": len(partite),
        "mercati_betfair": len(mercati),
        "coppie": len(coppie),
        "combinazioni": len(vicine),
        "trovate": trovate,
        "vicine": vicine,
        "errori": errori,
    }


def stampa_tabella(r: dict, commissione: float):
    trovate, vicine = r["trovate"], r["vicine"]

    if not trovate:
        print("\nNessuna operazione in utile in questo momento.")
        if vicine:
            print(f"\n  Le 10 combinazioni piu' vicine (su {len(vicine)} valutate):")
            print(f"  {'margine':>8}  {'esito':<24} {'book':<16} "
                  f"{'quota':>6} {'serve':>6} {'lay BF':>7}")
            for v in vicine[:10]:
                serve = quota_pareggio(v["quota_lay"], commissione)
                print(f"  {v['margine_pct']:>7.2f}%  {v['esito'][:24]:<24} "
                      f"{v['book'][:16]:<16} {v['quota_book']:>6} {serve:>6.2f} "
                      f"{v['quota_lay']:>7}")
            print("\n  'serve' = quota che il bookmaker deve superare per andare in utile.")
        print("\n  Soglie di un singolo evento: "
              "python src/calcolatore.py --market <id> --soglie")
        return

    print("\n" + "=" * 78)
    print(f"  {len(trovate)} OPERAZIONI IN UTILE")
    print("=" * 78)

    for i, t in enumerate(trovate, 1):
        print(f"\n  [{i}]  PROFITTO {t['margine_pct']:+.2f}%  |  {t['evento']}")
        print(f"       inizio {t['inizio']}   esito: {t['esito']}")
        print(f"       ------------------------------------------------------------")
        print(f"       1. SCOMMETTI  {t['puntata']:>8.2f} EUR su \"{t['esito']}\"")
        print(f"                     quota {t['quota_book']} presso {t['book']}")
        print(f"       2. BANCA(lay) {t['lay_stake']:>8.2f} EUR su \"{t['esito']}\"")
        print(f"                     quota {t['quota_lay']} su Betfair Italia")
        print(f"                     servono {t['responsabilita']:.2f} EUR liberi "
              f"(responsabilita')")
        print(f"       ------------------------------------------------------------")
        etichetta = f"se vince {t['esito'][:24]}"
        print(f"       {etichetta:<34}: {t['se_vince_book']:+8.2f} EUR")
        print(f"       {'se non vince (banca su Betfair)':<34}: "
              f"{t['se_perde_book']:+8.2f} EUR")
        print(f"       {'>>> PROFITTO GARANTITO':<34}: {t['garantito']:+8.2f} EUR")
        if t["lay_stake"] >= t["disponibile"] * 0.95:
            print(f"       nota: puntata limitata dalla liquidita' "
                  f"({t['disponibile']:,.0f} EUR al miglior prezzo)")

    print("\n" + "=" * 78)
    tot = sum(t["garantito"] for t in trovate)
    print(f"  Profitto garantito totale se le esegui tutte: {tot:+.2f} EUR")
    print("=" * 78)
    print("\n  Le quote si muovono: verifica sempre che siano ancora quelle prima di")
    print("  piazzare, ed esegui PRIMA il lato bookmaker (quello che sparisce prima).")


def apri_fonti():
    """Crea i due client e fa il login su Betfair. Ritorna (odds, bf) o (None, None)."""
    load_dotenv()
    odds = OddsAPI(os.getenv("ODDS_API_KEY", ""), os.getenv("ODDS_REGIONS", "eu"))
    bf = BetfairAPI(os.getenv("BETFAIR_APP_KEY", ""), os.getenv("BETFAIR_USERNAME", ""),
                    os.getenv("BETFAIR_PASSWORD", ""))
    try:
        bf.login()
    except BetfairError as e:
        print(f"!! login Betfair fallito: {e}")
        return None, None
    return odds, bf


def main():
    ap = argparse.ArgumentParser(
        description="Tabella operativa: back bookmaker / lay Betfair (read-only)")
    ap.add_argument("--sport", default="auto",
                    help="sport key separate da virgola, oppure 'auto' per farle "
                         "scegliere in base a cosa ha Betfair (default: auto)")
    ap.add_argument("--puntata", type=float, default=100,
                    help="puntata massima per operazione in EUR (default 100)")
    ap.add_argument("--min-profit", type=float, default=0.5,
                    help="margine minimo in %% per essere segnalato (default 0.5)")
    ap.add_argument("--book", default="",
                    help="solo questi bookmaker, separati da virgola (vuoto = tutti)")
    ap.add_argument("--commissione", type=float, default=0.05)
    ap.add_argument("--ore", type=int, default=72,
                    help="finestra Betfair in avanti (default 72)")
    ap.add_argument("--crediti", type=int, default=12,
                    help="crediti massimi da spendere in questa passata (default 12)")
    args = ap.parse_args()

    odds, bf = apri_fonti()
    if not odds:
        return

    mercati = catalogo_betfair(bf, args.ore)
    if args.sport == "auto":
        tenuti, _, _ = scegli_campionati(odds, mercati, args.crediti)
        sport_keys = [d["sport_key"] for d in tenuti]
        for d in tenuti:
            print(f"    {d['eventi']:>3} eventi  {d['competizione'][:32]:<32} "
                  f"-> {d['sport_key']}")
        if not sport_keys:
            print("\nNessun campionato in comune fra Betfair e The Odds API adesso.")
            return
    else:
        sport_keys = [s.strip() for s in args.sport.split(",") if s.strip()]

    print()
    r = scansiona(
        odds, bf, sport_keys, ore=args.ore, puntata=args.puntata,
        commissione=args.commissione, min_profit=args.min_profit,
        whitelist={b.strip().lower() for b in args.book.split(",") if b.strip()},
        mercati=mercati,
    )
    stampa_tabella(r, args.commissione)


if __name__ == "__main__":
    main()

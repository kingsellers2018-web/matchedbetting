"""
Quali campionati interrogare su The Odds API: la decisione che fa risparmiare quota.

Le chiamate a Betfair sono gratuite, quelle a The Odds API no (500 crediti/mese,
1 credito per campionato per regione). Quindi:

  1. si chiede a Betfair — gratis — quali competizioni hanno eventi in arrivo
  2. si abbinano ai campionati di The Odds API (anche /sports e' gratuito)
  3. si spende SOLO sui campionati presenti su entrambe le fonti

Sulla misura del 25/07/2026: Betfair aveva 200 eventi calcio in 72 ore, ma solo 53
in campionati coperti anche da The Odds API. Interrogare i 9 campionati utili invece
di tutti e 38 riduce il costo da 38 a 9 crediti a passata.
"""
import unicodedata

# Parole troppo comuni per identificare un campionato: compaiono ovunque.
RUMORE = {"the", "of", "and", "la", "el", "le", "league", "liga", "division",
          "primera", "super", "premier", "cup", "coppa", "serie", "first",
          "1st", "2nd", "national", "nacional", "championship"}


def normalizza(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c if c.isalnum() or c.isspace() else " " for c in s.lower())


def token(s: str) -> set:
    """Parole abbastanza lunghe e specifiche da identificare un campionato."""
    return {t for t in normalizza(s).split() if len(t) >= 3 and t not in RUMORE}


def competizioni_betfair(mercati: list) -> dict:
    """{nome competizione: numero di eventi} dal catalogo Betfair."""
    out = {}
    for m in mercati:
        nome = (m.get("competition") or {}).get("name")
        if nome:
            out[nome] = out.get(nome, 0) + 1
    return out


def abbina_campionati(mercati_betfair: list, sport_odds: list, gruppo: str = "Soccer"):
    """
    Ritorna (da_interrogare, orfani).

      da_interrogare: [{'sport_key', 'competizione', 'eventi', 'punteggio'}]
      orfani:         [{'competizione', 'eventi'}]  presenti su Betfair ma non
                      su The Odds API — nessun credito va sprecato su questi.
    """
    candidati = [s for s in sport_odds if s.get("group") == gruppo]
    da_interrogare, orfani = [], []

    for competizione, n_eventi in sorted(competizioni_betfair(mercati_betfair).items(),
                                         key=lambda x: -x[1]):
        tc = token(competizione)
        migliore, punteggio = None, 0
        for s in candidati:
            ts = token(s.get("title", "")) | token(
                s["key"].split("_", 1)[-1].replace("_", " "))
            comuni = len(tc & ts)
            if comuni > punteggio:
                migliore, punteggio = s, comuni

        if migliore and punteggio >= 1:
            da_interrogare.append({
                "sport_key": migliore["key"],
                "competizione": competizione,
                "eventi": n_eventi,
                "punteggio": punteggio,
            })
        else:
            orfani.append({"competizione": competizione, "eventi": n_eventi})

    # Lo stesso sport_key puo' uscire da piu' competizioni: si interroga una volta sola.
    visti, unici = set(), []
    for d in da_interrogare:
        if d["sport_key"] in visti:
            continue
        visti.add(d["sport_key"])
        unici.append(d)

    return unici, orfani


def entro_budget(da_interrogare: list, crediti_max: int, per_regione: int = 1):
    """
    Taglia la lista se sfora il budget di crediti, tenendo i campionati con
    piu' eventi: piu' partite = piu' probabilita' che ci sia un'anomalia.
    Ritorna (tenuti, scartati).
    """
    massimo = max(0, crediti_max // max(per_regione, 1))
    ordinati = sorted(da_interrogare, key=lambda d: -d["eventi"])
    return ordinati[:massimo], ordinati[massimo:]

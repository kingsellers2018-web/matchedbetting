"""
Confronto quote FRA MERCATI DIVERSI dello stesso evento, su Betfair Italia.

Con un solo operatore l'arbitraggio classico (bookmaker A contro bookmaker B)
non esiste. Ma sullo stesso evento Betfair quota una ventina di mercati legati
fra loro da vincoli matematici: se due mercati si contraddicono, il profitto e'
garantito e serve un conto solo — quello che l'utente ha gia'.

Due controlli:

  A) TENNIS — Match Odds contro Set Betting
     "A vince" e' lo stesso evento di "A vince 2-0 oppure 2-1".
     Due strade per ottenere la stessa posizione:
       - back su Match Odds        vs  lay su tutte le combinazioni Set Betting
       - back su tutte le combinazioni Set Betting  vs  lay su Match Odds
     Se una strada compra piu' caro di quanto l'altra vende, c'e' profitto.

  B) CALCIO — scaletta Over/Under
     "over 1.5" e' implicato da "over 2.5": non puo' essere MENO probabile.
     Se i prezzi invertono la scaletta, backare la linea bassa e layare quella
     alta e' un free roll: si vince o si pareggia, mai si perde.

Solo lettura: nessuna scommessa viene piazzata.

Uso:
    python src/crossmarket.py
    python src/crossmarket.py --min-profit 0.5 --min-size 20
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from betfair_api import BetfairAPI, BetfairError  # noqa: E402

LINEE_OU = ["OVER_UNDER_05", "OVER_UNDER_15", "OVER_UNDER_25",
            "OVER_UNDER_35", "OVER_UNDER_45", "OVER_UNDER_55"]


def odds_combinate_back(quote):
    """
    Backare piu' esiti che coprono lo stesso evento equivale a un back unico
    a quota 1 / somma(1/quota_i). Se manca un prezzo, la strada non esiste.
    """
    if not quote or any(not q for q in quote):
        return None
    tot = sum(1.0 / q for q in quote)
    return 1.0 / tot if tot > 0 else None


def profitto(back: float, lay: float, commissione: float):
    """
    Backare a quota `back` e layare lo stesso esito a quota `lay`.
    Si guadagna solo se si compra piu' caro di quanto si vende: back > lay.
    Ritorna il margine percentuale al netto della commissione.
    """
    if not back or not lay or back <= lay:
        return None
    lordo = (back - lay) / lay * 100
    return lordo * (1 - commissione)


class Scanner:
    def __init__(self, api: BetfairAPI, ore: int, commissione: float):
        self.api = api
        self.ore = ore
        self.commissione = commissione

    def _finestra(self):
        adesso = datetime.now(timezone.utc)
        return {
            "from": adesso.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "to": (adesso + timedelta(hours=self.ore))
                  .isoformat(timespec="seconds").replace("+00:00", "Z"),
        }

    def catalogo(self, event_type: str, tipi: list, n: int = 200):
        return self.api._rpc("listMarketCatalogue", {
            "filter": {"eventTypeIds": [event_type], "marketTypeCodes": tipi,
                       "marketStartTime": self._finestra()},
            "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
            "sort": "MAXIMUM_TRADED", "maxResults": n,
        })

    def libri(self, market_ids: list):
        out = {}
        for i in range(0, len(market_ids), 25):
            for b in self.api._rpc("listMarketBook", {
                "marketIds": market_ids[i:i + 25],
                "priceProjection": {"priceData": ["EX_BEST_OFFERS"], "virtualise": True},
            }):
                out[b["marketId"]] = b
        return out

    @staticmethod
    def prezzi(book: dict):
        """{selectionId: {'back':(q,size), 'lay':(q,size)}}"""
        r = {}
        for run in book.get("runners", []):
            ex = run.get("ex", {}) or {}
            atb = ex.get("availableToBack") or []
            atl = ex.get("availableToLay") or []
            r[run["selectionId"]] = {
                "back": (atb[0]["price"], atb[0]["size"]) if atb else (None, 0),
                "lay": (atl[0]["price"], atl[0]["size"]) if atl else (None, 0),
            }
        return r

    def per_evento(self, catalogo: list):
        ev = {}
        for m in catalogo:
            k = m["event"]["id"]
            ev.setdefault(k, {"nome": m["event"]["name"], "mercati": []})
            ev[k]["mercati"].append(m)
        return ev

    # ------------------------------------------------------------ TENNIS
    def tennis(self, min_profit: float, min_size: float):
        cat = self.catalogo("2", ["MATCH_ODDS", "SET_BETTING"], 200)
        eventi = {k: v for k, v in self.per_evento(cat).items()
                  if len(v["mercati"]) >= 2}
        if not eventi:
            return [], 0

        libri = self.libri([m["marketId"] for v in eventi.values() for m in v["mercati"]])
        trovati = []
        controllati = 0

        for v in eventi.values():
            mo = next((m for m in v["mercati"] if m["marketName"] == "Match Odds"), None)
            sb = next((m for m in v["mercati"] if m["marketName"] == "Set Betting"), None)
            if not mo or not sb:
                continue
            b_mo, b_sb = libri.get(mo["marketId"]), libri.get(sb["marketId"])
            if not b_mo or not b_sb:
                continue

            p_mo, p_sb = self.prezzi(b_mo), self.prezzi(b_sb)

            for run in mo.get("runners", []):
                nome = run["runnerName"]
                sid = run["selectionId"]
                # Le combinazioni Set Betting che significano "questo giocatore vince"
                combo = [r for r in sb.get("runners", [])
                         if r["runnerName"].startswith(nome)]
                if len(combo) < 2:
                    continue
                controllati += 1

                mo_back, mo_back_sz = p_mo.get(sid, {}).get("back", (None, 0))
                mo_lay, mo_lay_sz = p_mo.get(sid, {}).get("lay", (None, 0))

                sb_back = odds_combinate_back(
                    [p_sb.get(r["selectionId"], {}).get("back", (None, 0))[0] for r in combo])
                sb_lay = odds_combinate_back(
                    [p_sb.get(r["selectionId"], {}).get("lay", (None, 0))[0] for r in combo])
                sb_sz = min([p_sb.get(r["selectionId"], {}).get("back", (None, 0))[1]
                             for r in combo] or [0])
                sb_lay_sz = min([p_sb.get(r["selectionId"], {}).get("lay", (None, 0))[1]
                                 for r in combo] or [0])

                # Strada 1: compro su Match Odds, vendo via Set Betting
                m1 = profitto(mo_back, sb_lay, self.commissione)
                if m1 and m1 >= min_profit:
                    size = min(mo_back_sz, sb_lay_sz)
                    if size >= min_size:
                        trovati.append({
                            "evento": v["nome"], "esito": nome, "margine": m1,
                            "compra": f"back Match Odds @ {mo_back}",
                            "vende": f"lay Set Betting combinato @ {sb_lay:.3f}",
                            "size": size,
                            "scambiato": (b_mo.get("totalMatched", 0)
                                          + b_sb.get("totalMatched", 0)),
                        })

                # Strada 2: compro via Set Betting, vendo su Match Odds
                m2 = profitto(sb_back, mo_lay, self.commissione)
                if m2 and m2 >= min_profit:
                    size = min(sb_sz, mo_lay_sz)
                    if size >= min_size:
                        trovati.append({
                            "evento": v["nome"], "esito": nome, "margine": m2,
                            "compra": f"back Set Betting combinato @ {sb_back:.3f}",
                            "vende": f"lay Match Odds @ {mo_lay}",
                            "size": size,
                            "scambiato": (b_mo.get("totalMatched", 0)
                                          + b_sb.get("totalMatched", 0)),
                        })

        return trovati, controllati

    # ------------------------------------------------------------ CALCIO
    def calcio(self, min_profit: float, min_size: float):
        cat = self.catalogo("1", LINEE_OU, 300)
        eventi = {k: v for k, v in self.per_evento(cat).items()
                  if len(v["mercati"]) >= 2}
        if not eventi:
            return [], 0

        libri = self.libri([m["marketId"] for v in eventi.values() for m in v["mercati"]])
        trovati = []
        controllati = 0

        for v in eventi.values():
            # scaletta ordinata per linea: 0.5, 1.5, 2.5...
            scala = []
            for m in v["mercati"]:
                b = libri.get(m["marketId"])
                if not b:
                    continue
                p = self.prezzi(b)
                over = next((r for r in m.get("runners", [])
                             if r["runnerName"].lower().startswith("over")), None)
                if not over:
                    continue
                d = p.get(over["selectionId"], {})
                try:
                    linea = float(over["runnerName"].split()[1])
                except (IndexError, ValueError):
                    continue
                scala.append({"linea": linea, "nome": over["runnerName"],
                              "back": d.get("back", (None, 0)),
                              "lay": d.get("lay", (None, 0))})
            scala.sort(key=lambda x: x["linea"])

            for bassa, alta in zip(scala, scala[1:]):
                controllati += 1
                # "over linea_bassa" e' implicato da "over linea_alta":
                # backare la bassa e layare l'alta non puo' mai perdere.
                # Profitto se la quota back della bassa supera la lay dell'alta.
                m = profitto(bassa["back"][0], alta["lay"][0], self.commissione)
                if m and m >= min_profit:
                    size = min(bassa["back"][1], alta["lay"][1])
                    if size >= min_size:
                        trovati.append({
                            "evento": v["nome"],
                            "esito": f"{bassa['nome']} / {alta['nome']}",
                            "margine": m,
                            "compra": f"back {bassa['nome']} @ {bassa['back'][0]}",
                            "vende": f"lay {alta['nome']} @ {alta['lay'][0]}",
                            "size": size, "scambiato": 0,
                        })

        return trovati, controllati


def stampa(titolo, trovati, controllati, min_size):
    print(f"\n  {titolo}: {controllati} confronti eseguiti")
    if not trovati:
        print("    nessuna incoerenza sfruttabile.")
        return
    for t in sorted(trovati, key=lambda x: -x["margine"]):
        print(f"\n    >>> {t['margine']:.2f}% netto  |  {t['evento']} — {t['esito']}")
        print(f"        {t['compra']}")
        print(f"        {t['vende']}")
        print(f"        disponibile al miglior prezzo: {t['size']:,.0f} EUR")


def main():
    ap = argparse.ArgumentParser(description="Confronto quote fra mercati Betfair (read-only)")
    ap.add_argument("--min-profit", type=float, default=0.5,
                    help="margine netto minimo in %% (default 0.5)")
    ap.add_argument("--min-size", type=float, default=10,
                    help="euro minimi disponibili al miglior prezzo (default 10)")
    ap.add_argument("--ore", type=int, default=72, help="finestra in avanti (default 72)")
    ap.add_argument("--commissione", type=float, default=0.05)
    args = ap.parse_args()

    load_dotenv()
    api = BetfairAPI(os.getenv("BETFAIR_APP_KEY", ""),
                     os.getenv("BETFAIR_USERNAME", ""),
                     os.getenv("BETFAIR_PASSWORD", ""))
    try:
        api.login()
    except (BetfairError, Exception) as e:
        print(f"!! login fallito: {e}")
        return
    print("login riuscito su betfair.it\n")
    print(f"Soglie: margine >= {args.min_profit}% netto, almeno {args.min_size:.0f} EUR "
          f"disponibili, commissione {args.commissione * 100:.0f}%")

    s = Scanner(api, args.ore, args.commissione)

    t, ct = s.tennis(args.min_profit, args.min_size)
    stampa("TENNIS — Match Odds contro Set Betting", t, ct, args.min_size)

    c, cc = s.calcio(args.min_profit, args.min_size)
    stampa("CALCIO — scaletta Over/Under", c, cc, args.min_size)

    print(f"\n  Totale incoerenze sfruttabili: {len(t) + len(c)} "
          f"su {ct + cc} confronti")


if __name__ == "__main__":
    main()

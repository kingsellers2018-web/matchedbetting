"""
Analisi della serie storica raccolta da betfair_monitor.py.

Risponde alla domanda della Fase 0 sul filone trading:

    i prezzi si muovono PIU' di quanto costa entrare e uscire?

Il costo di un giro completo (entra + esci) e' lo spread back/lay, piu' la
commissione Betfair sull'eventuale utile. Se il prezzo, fra una lettura e
l'altra, si muove meno dello spread, il trading e' strutturalmente in perdita:
non e' questione di bravura, e' aritmetica.

Uso:
    python src/analisi.py
    python src/analisi.py --commissione 0.05
"""
import argparse
import csv
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "betfair_book.csv")


def mediana(v):
    v = sorted(v)
    n = len(v)
    if not n:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def carica():
    """Serie temporale per ogni corridore: [(ts, back, lay, back_size, lay_size, scambiato)]."""
    serie = defaultdict(list)
    meta = {}
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            back, lay = num(r["back"]), num(r["lay"])
            if not back or not lay:
                continue
            chiave = (r["market_id"], r["selection_id"])
            serie[chiave].append((
                r["ts_utc"], back, lay,
                num(r["back_size"]) or 0, num(r["lay_size"]) or 0,
                num(r["totale_scambiato"]) or 0,
            ))
            meta[chiave] = (r["evento"], r["corridore"], r["competizione"])
    return serie, meta


def analizza(serie, meta, commissione, min_scambiato):
    """
    Per ogni corridore confronta il movimento del prezzo medio fra letture
    successive con lo spread pagato per fare il giro.
    """
    movimenti = []       # variazione % del mid fra due letture
    spread_visti = []
    profondita = []
    occasioni = 0        # letture in cui il movimento avrebbe coperto i costi
    confronti = 0
    per_evento = defaultdict(lambda: {"mosse": [], "spread": []})

    for chiave, punti in serie.items():
        if len(punti) < 2:
            continue
        if punti[-1][5] < min_scambiato:
            continue

        evento, corridore, _ = meta[chiave]
        for (t0, b0, l0, bs0, ls0, _), (t1, b1, l1, _, _, _) in zip(punti, punti[1:]):
            mid0, mid1 = (b0 + l0) / 2, (b1 + l1) / 2
            sp = (l0 - b0) / b0 * 100
            mossa = abs(mid1 - mid0) / mid0 * 100

            # Costo del giro: lo spread, piu' la commissione sull'utile lordo.
            costo = sp + mossa * commissione
            confronti += 1
            if mossa > costo:
                occasioni += 1

            movimenti.append(mossa)
            spread_visti.append(sp)
            profondita.append(min(bs0, ls0))
            per_evento[evento]["mosse"].append(mossa)
            per_evento[evento]["spread"].append(sp)

    return {
        "movimenti": movimenti,
        "spread": spread_visti,
        "profondita": profondita,
        "occasioni": occasioni,
        "confronti": confronti,
        "per_evento": per_evento,
    }


def main():
    ap = argparse.ArgumentParser(description="Analisi serie storica Betfair")
    ap.add_argument("--commissione", type=float, default=0.05,
                    help="commissione Betfair sull'utile (default 0.05)")
    ap.add_argument("--min-scambiato", type=float, default=1000,
                    help="ignora i mercati sotto questo volume scambiato")
    args = ap.parse_args()

    if not os.path.exists(CSV_PATH):
        print(f"!! Non trovo {CSV_PATH}")
        print("   Lancia prima: python src/betfair_monitor.py --loop")
        return

    serie, meta = carica()
    if not serie:
        print("!! Il CSV non contiene prezzi utilizzabili.")
        return

    r = analizza(serie, meta, args.commissione, args.min_scambiato)
    if not r["confronti"]:
        print("!! Serve almeno una seconda lettura degli stessi mercati.")
        print("   Fai girare betfair_monitor.py --loop per qualche ora, poi ritenta.")
        return

    print("=" * 68)
    print(f"  ANALISI — {len(serie)} corridori, {r['confronti']} confronti fra letture")
    print("=" * 68)

    print("\n  COSTO DI UN GIRO (spread back/lay)")
    print(f"    mediana        {mediana(r['spread']):6.2f}%")
    print(f"    minimo         {min(r['spread']):6.2f}%")

    print("\n  MOVIMENTO DEL PREZZO fra due letture")
    print(f"    mediana        {mediana(r['movimenti']):6.2f}%")
    print(f"    massimo        {max(r['movimenti']):6.2f}%")
    fermi = sum(1 for m in r["movimenti"] if m == 0)
    print(f"    prezzo fermo   {fermi / len(r['movimenti']) * 100:5.1f}% delle volte")

    print("\n  PROFONDITA' al miglior prezzo")
    print(f"    mediana        {mediana(r['profondita']):6.0f} EUR")
    print("    (quanto puoi muovere senza spostare tu stesso il mercato)")

    quota = r["occasioni"] / r["confronti"] * 100
    print("\n" + "=" * 68)
    print(f"  MOVIMENTI CHE COPRONO I COSTI: {r['occasioni']} su {r['confronti']}  "
          f"({quota:.1f}%)")
    print("=" * 68)

    if quota < 5:
        print("\n  LETTURA: il prezzo si muove quasi sempre MENO di quanto costa")
        print("  entrare e uscire. Su questi mercati il trading e' in perdita")
        print("  strutturale, indipendentemente da quanto si e' bravi.")
    elif quota < 20:
        print("\n  LETTURA: occasioni presenti ma rare. Da incrociare con la")
        print("  profondita': se al miglior prezzo ci sono poche decine di euro,")
        print("  l'utile per operazione resta trascurabile in valore assoluto.")
    else:
        print("\n  LETTURA: i movimenti superano i costi con buona frequenza.")
        print("  Vale la pena guardare il dettaglio per evento qui sotto.")

    print("\n  Dettaglio per evento (i piu' mossi):")
    righe = [(ev, mediana(d["mosse"]), mediana(d["spread"]), len(d["mosse"]))
             for ev, d in r["per_evento"].items() if d["mosse"]]
    for ev, mossa, sp, n in sorted(righe, key=lambda x: -(x[1] or 0))[:10]:
        segno = "  <-- si muove piu' dello spread" if mossa > sp else ""
        print(f"    {ev[:38]:38} mossa {mossa:5.2f}%  spread {sp:5.2f}%  "
              f"({n} confronti){segno}")


if __name__ == "__main__":
    main()

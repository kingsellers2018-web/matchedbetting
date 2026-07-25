"""
Il sistema sta girando? Una risposta in dieci secondi, senza aprire nulla.

Legge da Supabase con la chiave anon (sola lettura) e risponde a tre domande:
  - quando e' stata l'ultima passata, e con che esito
  - quanti crediti restano del piano gratuito
  - quali occasioni sono aperte adesso

Utile all'inizio di ogni sessione, e ogni volta che si sospetta che il motore
si sia fermato: un worker morto e' altrimenti indistinguibile da "non ci sono
occasioni".

Uso:
    python src/stato.py
"""
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

CREDITI_PIANO = 500  # piano gratuito The Odds API


def da_quanto(iso: str) -> str:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    m = (datetime.now(timezone.utc) - t).total_seconds() / 60
    if m < 60:
        return f"{m:.0f} min fa"
    if m < 1440:
        return f"{m / 60:.1f} ore fa"
    return f"{m / 1440:.1f} giorni fa"


def main():
    load_dotenv()
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        print("!! Mancano SUPABASE_URL / SUPABASE_ANON_KEY in .env")
        sys.exit(1)

    h = {"apikey": key, "Authorization": f"Bearer {key}"}

    def leggi(risorsa, **p):
        r = requests.get(f"{url}/rest/v1/{risorsa}", headers=h, params=p, timeout=30)
        r.raise_for_status()
        return r.json()

    scansioni = leggi("scansioni", select="*", order="ts.desc", limit="8")
    attive = leggi("opportunita_attive", select="*", order="margine_pct.desc")

    print("=" * 72)
    if not scansioni:
        print("  MOTORE: nessuna passata registrata.")
        print("  Lancia:  C:\\matchedbetting\\scripts\\passata.cmd")
        print("=" * 72)
        return

    ultima = scansioni[0]
    minuti = (datetime.now(timezone.utc)
              - datetime.fromisoformat(ultima["ts"].replace("Z", "+00:00"))
              ).total_seconds() / 60

    # Le attivita' pianificate girano alle 11:00 e alle 18:00: oltre le ~18 ore
    # di silenzio significa che il PC era spento o qualcosa si e' rotto.
    if minuti < 60 * 18:
        salute = "ATTIVO"
    elif minuti < 60 * 36:
        salute = "IN RITARDO"
    else:
        salute = "FERMO"

    crediti = ultima.get("crediti_rimasti")
    print(f"  MOTORE {salute} — ultima passata {da_quanto(ultima['ts'])}")
    if crediti is not None:
        giorni = int(crediti) // 12 if int(crediti) else 0  # 6 crediti x 2 passate
        print(f"  Crediti: {crediti}/{CREDITI_PIANO}  "
              f"(~{giorni} giorni al ritmo attuale)")
    if ultima.get("errori"):
        print(f"  ERRORI nell'ultima passata: {ultima['errori']}")
    print("=" * 72)

    print("\n  PASSATE RECENTI")
    for s in scansioni:
        print(f"    {s['ts'][:16].replace('T', ' ')}  "
              f"{da_quanto(s['ts']):>12}  "
              f"crediti {s['crediti_spesi']:>2}  "
              f"incrociati {s['eventi_incrociati']:>3}  "
              f"trovate {s['opportunita']:>2}"
              + (f"   ! {s['errori'][:40]}" if s.get("errori") else ""))

    print(f"\n  OCCASIONI APERTE: {len(attive)}")
    if attive:
        totale = sum(float(o["profitto_garantito"] or 0) for o in attive)
        for o in attive:
            print(f"    +{float(o['margine_pct']):5.2f}%  "
                  f"{o['evento'][:32]:<32} {o['esito'][:16]:<16} "
                  f"{o['bookmaker'][:14]:<14} "
                  f"{float(o['profitto_garantito']):+6.2f} EUR  "
                  f"fra {float(o['ore_al_via']):.1f}h")
        print(f"\n    totale garantito: {totale:+.2f} EUR")
    else:
        print("    nessuna. Il margine del bookmaker piu' lo spread Betfair vale")
        print("    circa il 3%: serve un operatore fuori linea, non capita sempre.")

    print(f"\n  Pannello: https://matchedbetting-dusky.vercel.app/")


if __name__ == "__main__":
    main()

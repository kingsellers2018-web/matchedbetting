"""
Il motore automatico: una passata completa, pensata per girare da sola.

Gira su GitHub Actions (o su qualsiasi cosa sappia eseguire Python a orario) e:
  1. chiede a Betfair — gratis — quali campionati hanno eventi in arrivo
  2. spende crediti di The Odds API SOLO su quelli presenti su entrambe le fonti
  3. cerca le operazioni back-bookmaker / lay-Betfair in utile
  4. salva tutto su Supabase (o su file, se il database non e' configurato)
  5. manda una mail per le occasioni mai notificate prima

Il punto 1 e' quello che rende sostenibile il piano gratuito: 500 crediti al mese
finiscono in fretta se si interrogano campionati che Betfair non quota.

Uso:
    python src/worker.py
    python src/worker.py --crediti 8 --min-profit 1.0
    python src/worker.py --dry-run          # non salva e non manda mail
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from archivio import Archivio  # noqa: E402
from notifica import invia  # noqa: E402
from opportunita import (apri_fonti, catalogo_betfair, scegli_campionati,  # noqa: E402
                         scansiona, stampa_tabella)


def main():
    ap = argparse.ArgumentParser(description="Passata automatica del monitor")
    ap.add_argument("--crediti", type=int,
                    default=int(os.getenv("CREDITI_PER_PASSATA", "10")),
                    help="crediti massimi da spendere (default 10)")
    ap.add_argument("--min-profit", type=float,
                    default=float(os.getenv("MIN_PROFIT", "0.5")),
                    help="margine minimo in %% per segnalare (default 0.5)")
    ap.add_argument("--min-profit-mail", type=float,
                    default=float(os.getenv("MIN_PROFIT_MAIL", "1.0")),
                    help="margine minimo per far partire la mail (default 1.0)")
    ap.add_argument("--puntata", type=float,
                    default=float(os.getenv("PUNTATA_MAX", "100")))
    ap.add_argument("--commissione", type=float,
                    default=float(os.getenv("BETFAIR_COMMISSION", "0.05")))
    ap.add_argument("--ore", type=int, default=int(os.getenv("ORE_AVANTI", "72")))
    ap.add_argument("--book", default=os.getenv("BOOK_WHITELIST", ""),
                    help="solo questi bookmaker, separati da virgola")
    ap.add_argument("--dry-run", action="store_true",
                    help="esegue la scansione ma non salva e non notifica")
    args = ap.parse_args()

    inizio = datetime.now(timezone.utc)
    print(f"=== passata {inizio.isoformat(timespec='seconds')} ===")

    odds, bf = apri_fonti()
    if not odds:
        sys.exit(1)

    # 1) cosa c'e' da giocare, secondo Betfair (gratis)
    mercati = catalogo_betfair(bf, args.ore)

    # 2) dove conviene spendere i crediti
    tenuti, orfani, scartati = scegli_campionati(odds, mercati, args.crediti)
    if not tenuti:
        print("  nessun campionato in comune fra le due fonti: passata a costo zero")
        if not args.dry_run:
            Archivio().salva_scansione({
                "campionati": [], "crediti_spesi": 0,
                "crediti_rimasti": odds.remaining, "partite": 0,
                "mercati_betfair": len(mercati), "coppie": 0,
                "combinazioni": 0, "trovate": [], "vicine": [], "errori": [],
            })
        return

    for d in tenuti:
        print(f"    {d['eventi']:>3} eventi  {d['competizione'][:32]:<32} "
              f"-> {d['sport_key']}")

    # 3) la scansione vera
    r = scansiona(
        odds, bf, [d["sport_key"] for d in tenuti],
        ore=args.ore, puntata=args.puntata, commissione=args.commissione,
        min_profit=args.min_profit, mercati=mercati,
        whitelist={b.strip().lower() for b in args.book.split(",") if b.strip()},
    )
    stampa_tabella(r, args.commissione)

    if args.dry_run:
        print("\n(dry-run: niente salvataggi, niente mail)")
        return

    # 4) persistenza
    arch = Archivio()
    if not arch.attivo:
        print("\n  Supabase non configurato: salvo in data/*.jsonl")
    arch.salva_scansione(r)
    nuove = arch.salva_opportunita(r["trovate"])

    # 5) notifica, solo per quelle mai viste e sopra la soglia mail
    da_mandare = [o for o in nuove
                  if float(o.get("margine_pct", 0)) >= args.min_profit_mail]
    if da_mandare:
        print(f"\n  {len(da_mandare)} occasioni nuove sopra "
              f"{args.min_profit_mail}%: invio mail")
        if invia(da_mandare):
            arch.segna_notificate(da_mandare)
    elif nuove:
        print(f"\n  {len(nuove)} occasioni nuove ma sotto la soglia mail "
              f"({args.min_profit_mail}%): salvate, nessuna mail")

    durata = (datetime.now(timezone.utc) - inizio).total_seconds()
    print(f"\n=== fine in {durata:.1f}s | crediti spesi {r['crediti_spesi']} | "
          f"rimasti {r['crediti_rimasti']} ===")


if __name__ == "__main__":
    main()

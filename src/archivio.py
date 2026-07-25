"""
Persistenza: Supabase se configurato, altrimenti file locali.

Il worker deve poter girare anche senza database — durante lo sviluppo, o se
Supabase e' irraggiungibile — senza perdere la passata. Quindi c'e' sempre un
fallback su file JSON in data/.

Si parla con Supabase via PostgREST usando `requests`: nessuna dipendenza in piu'
rispetto a quelle gia' presenti.
"""
import json
import os
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def adesso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Archivio:
    """
    Scrive scansioni e opportunita'. Se mancano le credenziali Supabase
    funziona lo stesso, salvando in locale.
    """

    def __init__(self, url: str = None, key: str = None):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.getenv("SUPABASE_SERVICE_KEY", "")
        self.attivo = bool(self.url and self.key)
        os.makedirs(DATA, exist_ok=True)

    # -- interfaccia con PostgREST -----------------------------------------

    def _headers(self, extra: dict = None):
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def _post(self, tabella: str, righe, params: dict = None, prefer: str = None):
        r = requests.post(
            f"{self.url}/rest/v1/{tabella}",
            headers=self._headers({"Prefer": prefer} if prefer else None),
            params=params or {},
            json=righe,
            timeout=30,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"{tabella}: HTTP {r.status_code} {r.text[:300]}")
        return r.json() if r.text.strip() else []

    def _get(self, tabella: str, params: dict):
        r = requests.get(f"{self.url}/rest/v1/{tabella}",
                         headers=self._headers(), params=params, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"{tabella}: HTTP {r.status_code} {r.text[:300]}")
        return r.json()

    def _patch(self, tabella: str, params: dict, valori: dict):
        r = requests.patch(f"{self.url}/rest/v1/{tabella}",
                           headers=self._headers(), params=params,
                           json=valori, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"{tabella}: HTTP {r.status_code} {r.text[:300]}")

    # -- fallback locale ----------------------------------------------------

    def _accoda_locale(self, nome: str, righe: list):
        percorso = os.path.join(DATA, f"{nome}.jsonl")
        with open(percorso, "a", encoding="utf-8") as f:
            for r in righe:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        return percorso

    # -- operazioni ---------------------------------------------------------

    def salva_scansione(self, r: dict):
        """Registra la passata. Ritorna l'id assegnato (None in locale)."""
        riga = {
            "ts": adesso(),
            "campionati": r.get("campionati", []),
            "crediti_spesi": r.get("crediti_spesi", 0),
            "crediti_rimasti": int(r["crediti_rimasti"]) if str(
                r.get("crediti_rimasti") or "").isdigit() else None,
            "partite": r.get("partite", 0),
            "mercati_betfair": r.get("mercati_betfair", 0),
            "eventi_incrociati": r.get("coppie", 0),
            "combinazioni": r.get("combinazioni", 0),
            "opportunita": len(r.get("trovate", [])),
            "miglior_margine": round(r["vicine"][0]["margine_pct"], 3)
                               if r.get("vicine") else None,
            "errori": "; ".join(r.get("errori", [])) or None,
        }
        if not self.attivo:
            self._accoda_locale("scansioni", [riga])
            return None
        res = self._post("scansioni", riga, prefer="return=representation")
        return res[0]["id"] if res else None

    def salva_opportunita(self, trovate: list):
        """
        Inserisce o aggiorna. La chiave (market_id, esito, bookmaker) fa si' che
        la stessa occasione vista in due passate resti UNA riga.
        Ritorna la lista delle occasioni mai notificate.
        """
        if not trovate:
            return []

        righe = [{
            "market_id": t["market_id"],
            "esito": t["esito"],
            "bookmaker": t["book"],
            "evento": t["evento"],
            "competizione": t.get("competizione") or None,
            "inizio": t.get("inizio") or None,
            "quota_book": t["quota_book"],
            "quota_lay": t["quota_lay"],
            "liquidita": t.get("disponibile"),
            "margine_pct": round(t["margine_pct"], 3),
            "margine_max": round(t["margine_pct"], 3),
            "puntata": t.get("puntata"),
            "lay_stake": t.get("lay_stake"),
            "responsabilita": round(t.get("responsabilita", 0), 2),
            "profitto_garantito": round(t.get("garantito", 0), 2),
            "vista_ultima": adesso(),
        } for t in trovate]

        if not self.attivo:
            self._accoda_locale("opportunita", righe)
            return righe  # in locale si notifica tutto

        self._post("opportunita", righe,
                   params={"on_conflict": "market_id,esito,bookmaker"},
                   prefer="resolution=merge-duplicates,return=minimal")

        # margine_max non deve scendere: lo si rialza solo quando serve
        for r in righe:
            self._patch("opportunita", {
                "market_id": f"eq.{r['market_id']}",
                "esito": f"eq.{r['esito']}",
                "bookmaker": f"eq.{r['bookmaker']}",
                "margine_max": f"lt.{r['margine_pct']}",
            }, {"margine_max": r["margine_pct"]})

        return self.da_notificare()

    def da_notificare(self, margine_minimo: float = 0.0):
        """Occasioni ancora valide per cui non e' mai partita una mail."""
        if not self.attivo:
            return []
        return self._get("opportunita", {
            "select": "*",
            "notificata_at": "is.null",
            "margine_pct": f"gte.{margine_minimo}",
            "inizio": f"gt.{adesso()}",
            "order": "margine_pct.desc",
        })

    def segna_notificate(self, righe: list):
        if not self.attivo or not righe:
            return
        for r in righe:
            self._patch("opportunita", {"id": f"eq.{r['id']}"},
                        {"notificata_at": adesso()})

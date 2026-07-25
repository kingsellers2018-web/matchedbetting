"""
Client minimale per The Odds API (https://the-odds-api.com).
Legge le quote dai bookmaker + Betfair. Solo lettura, nessuna scommessa.

NOTA SUL COSTO: il piano gratuito da 500 richieste/mese conta
    costo = numero_mercati x numero_regioni
per ogni chiamata a /odds. Con markets=h2h e regions=eu -> 1 richiesta.
Con regions=eu,uk -> 2 richieste. L'endpoint /sports e' gratuito.
"""
import requests

BASE = "https://api.the-odds-api.com/v4"


class OddsAPI:
    def __init__(self, api_key: str, regions: str = "eu"):
        self.api_key = api_key
        self.regions = regions
        self.remaining = None  # aggiornato dagli header dopo ogni chiamata
        self.used = None

    def _get(self, path: str, **params):
        params["apiKey"] = self.api_key
        r = requests.get(f"{BASE}{path}", params=params, timeout=30)
        r.raise_for_status()
        # Header utili: quante richieste restano nel piano gratuito
        self.remaining = r.headers.get("x-requests-remaining", self.remaining)
        self.used = r.headers.get("x-requests-used", self.used)
        return r.json()

    def list_sports(self, only_active: bool = True):
        """Tutti gli sport. Chiamata gratuita, non consuma il piano."""
        params = {} if only_active else {"all": "true"}
        return self._get("/sports", **params)

    def list_active_keys(self, group: str = None):
        """Sport key attive adesso, eventualmente filtrate per gruppo (es. 'Tennis')."""
        sports = self.list_sports(only_active=True)
        if group:
            sports = [s for s in sports if s.get("group") == group]
        return [s["key"] for s in sports]

    def get_h2h_odds(self, sport_key: str):
        """
        Quote testa-a-testa (chi vince) per uno sport.
        sport_key puo' essere anche 'upcoming' = prossimi eventi su tutti gli sport,
        al costo di una sola chiamata: il modo piu' economico di campionare il mercato.
        """
        return self._get(
            f"/sports/{sport_key}/odds",
            regions=self.regions,
            markets="h2h",
            oddsFormat="decimal",
        )

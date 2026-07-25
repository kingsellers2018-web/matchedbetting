"""
Client per la Betfair Exchange API — versione ITALIANA (betfair.it).

Differenza fondamentale rispetto ai dati di The Odds API: qui leggiamo il vero
book dell'Exchange su cui l'utente ha il conto, con prezzi back E lay e con i
VOLUMI disponibili. E' l'unico mercato realmente operabile dall'Italia.

Attenzione: l'Exchange italiano e' un pool di liquidita' separato da quello
internazionale, quindi il login passa da identitysso.betfair.it (non .com).

Solo lettura: questo modulo non espone alcuna operazione di piazzamento scommesse.
"""
import requests

# L'Exchange italiano ha endpoint di login propri; la Betting API invece e' comune.
LOGIN_URL = "https://identitysso.betfair.it/api/login"
KEEPALIVE_URL = "https://identitysso.betfair.it/api/keepAlive"
BETTING_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"


class BetfairError(RuntimeError):
    pass


class BetfairAPI:
    def __init__(self, app_key: str, username: str, password: str):
        self.app_key = app_key
        self.username = username
        self.password = password
        self.token = None
        self.sessione = requests.Session()

    # -- autenticazione -----------------------------------------------------

    def login(self):
        """Login interattivo con username e password. Ritorna il session token."""
        r = self.sessione.post(
            LOGIN_URL,
            data={"username": self.username, "password": self.password},
            headers={
                "X-Application": self.app_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=30,
        )
        r.raise_for_status()
        d = r.json()
        if d.get("status") != "SUCCESS":
            raise BetfairError(
                f"login fallito: status={d.get('status')} error={d.get('error')}"
            )
        self.token = d["token"]
        return self.token

    def keep_alive(self):
        """Il token scade per inattivita': va rinnovato nei cicli lunghi."""
        r = self.sessione.post(
            KEEPALIVE_URL,
            headers={"X-Application": self.app_key,
                     "X-Authentication": self.token,
                     "Accept": "application/json"},
            timeout=30,
        )
        return r.json().get("status") == "SUCCESS"

    # -- chiamate alla Betting API -----------------------------------------

    def _rpc(self, metodo: str, params: dict):
        if not self.token:
            raise BetfairError("chiamata prima del login")
        payload = [{
            "jsonrpc": "2.0",
            "method": f"SportsAPING/v1.0/{metodo}",
            "params": params,
            "id": 1,
        }]
        r = self.sessione.post(
            BETTING_URL,
            json=payload,
            headers={"X-Application": self.app_key,
                     "X-Authentication": self.token,
                     "Content-Type": "application/json"},
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()[0]
        if "error" in d:
            raise BetfairError(f"{metodo}: {d['error']}")
        return d["result"]

    def list_event_types(self):
        """Gli sport disponibili sull'Exchange italiano, con il numero di eventi."""
        return self._rpc("listEventTypes", {"filter": {}})

    def list_market_catalogue(self, ore_avanti: int = 48, max_risultati: int = 20,
                              event_type_ids: list = None):
        """
        I mercati 1X2 / testa-a-testa piu' LIQUIDI in partenza nelle prossime ore.

        Ordinati per volume gia' scambiato (MAXIMUM_TRADED): la liquidita' e' la
        prima cosa che conta, un prezzo su un mercato vuoto non e' un prezzo.
        """
        from datetime import datetime, timedelta, timezone
        adesso = datetime.now(timezone.utc)
        filtro = {
            "marketTypeCodes": ["MATCH_ODDS"],
            "marketStartTime": {
                "from": adesso.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "to": (adesso + timedelta(hours=ore_avanti))
                      .isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
        }
        if event_type_ids:
            filtro["eventTypeIds"] = event_type_ids

        return self._rpc("listMarketCatalogue", {
            "filter": filtro,
            "marketProjection": ["EVENT", "COMPETITION", "MARKET_START_TIME",
                                 "RUNNER_DESCRIPTION"],
            "sort": "MAXIMUM_TRADED",
            "maxResults": max_risultati,
        })

    def list_market_book(self, market_ids: list):
        """
        Il book vero: migliori prezzi back e lay con i relativi volumi.

        Betfair limita il peso di ogni richiesta, quindi i mercati vanno chiesti
        a blocchi (EX_BEST_OFFERS pesa 5 punti su 200 -> max 40 per chiamata).
        """
        risultati = []
        for i in range(0, len(market_ids), 25):
            blocco = market_ids[i:i + 25]
            risultati.extend(self._rpc("listMarketBook", {
                "marketIds": blocco,
                "priceProjection": {
                    "priceData": ["EX_BEST_OFFERS"],
                    "virtualise": True,
                },
            }))
        return risultati

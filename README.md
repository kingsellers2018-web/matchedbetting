# matchedbetting — Monitor Inefficienze Quote (multi-sport)

Monitor **read-only** per rilevare inefficienze di prezzo sui mercati sportivi:
- **Arbing**: disallineamenti di quota tra bookmaker diversi (e Betfair Exchange)
- **Trading**: movimenti di quota sullo stesso mercato Betfair (back/lay)

> ⚠️ Questo è solo un **monitor**: legge e segnala. NON piazza scommesse. Zero rischio, zero soldi in gioco.

---

## Stato del progetto

🟡 **Fase 0 — Misurazione** (prima si misura, poi si decide)

L'obiettivo è rispondere con **dati reali** a una domanda:
> Le inefficienze esistono davvero? Quante, quanto grandi, quanto durano?

Se ci sono → si valuta la fase di esecuzione. Se non ci sono → ci siamo risparmiati tempo e soldi.

---

## Come si usa

1. **API key gratuita** — https://the-odds-api.com → "Get API Key" (basta un'email).
   Piano gratuito: 500 richieste/mese.
2. Copia `.env.example` in `.env` e incolla la tua key.
3. Installa le dipendenze: `pip install -r requirements.txt`
4. Lancia:
   ```
   python src/monitor.py            # una passata sola
   python src/monitor.py --loop     # in continuo, ogni LOOP_MINUTES minuti
   ```

Ogni passata scrive su `data/osservazioni.csv`: **quello è il prodotto della Fase 0.**
Non conta cosa esce da un singolo lancio, conta la statistica su giorni.

### Costo delle richieste

`costo = numero_mercati × numero_regioni` per ogni chiamata a `/odds`.
Con `ODDS_SPORTS=upcoming` e `ODDS_REGIONS=eu` una passata costa **1 richiesta**.
A 120 minuti di intervallo → ~360 richieste/mese, dentro il piano gratuito.
Il monitor stampa una stima all'avvio e avvisa se si sfora.

---

## Cosa abbiamo già imparato dai dati (25/07/2026)

### 1. Il tennis non è coperto in continuo
The Odds API espone il tennis **un torneo alla volta** (solo Slam, Masters 1000, WTA 1000)
e solo mentre è in corso. A fine luglio 2026 tutti e 41 i tornei risultano `active=False`.
→ Il progetto è stato reso **agnostico rispetto allo sport**: `ODDS_SPORTS=upcoming`
campiona qualsiasi cosa sia quotata adesso.

### 2. Gli arbitraggi "grezzi" sono quasi tutti finti
Al primo lancio senza filtri uscivano 6 arbitraggi su 15 match. Erano rumore:
- quote monstre (501.0) che sono residui, non prezzi reali → filtro `MAX_ODDS`
- match **già iniziati**, con quote in-play o stantie → filtro `MIN_MINUTI_ALL_INIZIO`
- arb sostenuti da 2-3 bookmaker soli → filtro `MIN_BOOKMAKERS`
- margine calcolato **al lordo** della commissione exchange → `BETFAIR_COMMISSION`

Con i filtri attivi resta circa **1 candidato su 14 match**, dell'ordine dello **0,9%**.

### 3. Il vincolo più serio: i bookmaker coperti non sono quelli italiani
In regione `eu` l'API restituisce 20 operatori:
1xBet, 888sport, BetOnline.ag, Betclic (FR), Betfair, Betsson, Coolbet, Everygame,
LeoVegas (SE), MyBookie.ag, Nordic Bet, PMU (FR), Pinnacle, Tipico, Unibet (FR/NL/SE),
William Hill, Winamax (DE/FR).

Sono le versioni `.com`/`.fr`/`.se`, **non** le `.it` con licenza ADM, che espongono quote
diverse. Alcuni non operano affatto in Italia.

> **Un arbitraggio visto dal monitor non è automaticamente eseguibile.**
> Il monitor misura il mercato internazionale; l'esecuzione va verificata sui conti
> che si possiedono davvero. Usa `BOOK_WHITELIST` per restringere ai soli book usabili.

---

---

## I due monitor

Il progetto ha **due motori distinti**, che guardano due mercati diversi.

### 1. `src/monitor.py` — The Odds API (misura di sfondo)
Cerca arbitraggi fra bookmaker internazionali. Gratis, ma **non esegue**: nessun
bookmaker italiano è coperto, quindi le sue segnalazioni non sono giocabili
dall'Italia. Serve solo a stimare l'ordine di grandezza del fenomeno.

### 2. `src/betfair_monitor.py` — Betfair Exchange Italia (mercato operabile)
Legge il book vero di `betfair.it`: miglior back, miglior lay e **i volumi su
entrambi i lati**. Con un solo operatore l'arbitraggio non esiste, quindi qui la
domanda è un'altra:

> lo spread back/lay è abbastanza stretto, e i prezzi si muovono abbastanza,
> da poterci fare **trading**?

```
python src/betfair_monitor.py --sport    # elenca gli sport disponibili
python src/betfair_monitor.py            # una lettura
python src/betfair_monitor.py --loop     # rilegge ogni BETFAIR_INTERVALLO_SEC
```

Scrive su `data/betfair_book.csv`, che diventa la serie storica dei prezzi.

**Chiavi Betfair**: la **Delayed App Key** è gratuita e dà dati ritardati di
1-180 secondi — sufficienti per *misurare*. La **Live App Key** costa **£499 una
tantum non rimborsabili** e Betfair non ne consente l'uso in sola lettura: da
valutare solo se la Fase 0 dà esito positivo.

**Vincoli dell'Exchange italiano**: puntata minima 2,00 € con incrementi da 0,50 €,
massimo 50 istruzioni per richiesta, vincita potenziale massima 10.000 €,
vietato combinare back e lay nella stessa richiesta.

### 3. `src/crossmarket.py` — confronto quote FRA MERCATI dello stesso evento
Con un solo operatore l'arbitraggio classico non esiste, ma sullo stesso evento
Betfair quota ~20 mercati legati da vincoli matematici (`P(A vince)` deve essere
uguale a `P(A 2-0) + P(A 2-1)`; `P(over 1.5) ≥ P(over 2.5)`). Se si contraddicono,
è profitto garantito con un conto solo.

```
python src/crossmarket.py
python src/crossmarket.py --min-profit 0.001 --min-size 0   # senza soglie
```

**Esito misurato il 25/07/2026: 0 incoerenze su 295 confronti.** L'Exchange è
internamente privo di arbitraggi — è il controllo che i bot fanno di continuo.
Lo strumento resta utile per riverificare in periodi più liquidi.

### 4. `src/calcolatore.py` — matched betting, lato Betfair in tempo reale
Il confronto quote nell'unica forma accessibile: **il lato exchange arriva
dall'API, la quota del bookmaker la digiti tu** leggendola sul sito dove hai il
conto. Nessuno scraping, nessuna violazione di termini d'uso.

```
python src/calcolatore.py --cerca "Milan"                    # trova il market id
python src/calcolatore.py --market 1.2345 --soglie           # quota da battere sul book
python src/calcolatore.py --market 1.2345 --runner "Milan" --quota-book 3.5 --puntata 10
python src/calcolatore.py --market 1.2345 --runner "Milan" --quota-book 5.5 --puntata 25 --tipo freebet
```

**`--soglie` è il modo più veloce di lavorare**: per ogni esito mostra la quota
minima che il bookmaker deve superare perché l'operazione sia in utile, secondo
`B* = (L - commissione) / (1 - commissione)`. Apri il sito del bookmaker, e se una
quota sta sopra quella soglia backi lì e layi su Betfair: guadagni comunque vada.

Calcola quanto layare, la responsabilità da tenere sul conto e il profitto nei due
scenari. Applica i vincoli italiani (minimo 2,00 € a scatti di 0,50) e **ricalcola
sui valori arrotondati**, avvisando quando lo scatto sbilancia il risultato — su
puntate piccole pesa parecchio.

Tre tipi: `qualifying` (scommessa normale, serve a sbloccare il bonus: si punta a
perdere poco), `freebet` (bonus con puntata non restituita, è qui che si guadagna),
`freebet-sr` (bonus con puntata restituita).

### 5. `src/opportunita.py` — **la tabella operativa**
Incrocia le due fonti e produce le istruzioni esatte: quanto puntare, dove,
quanto bancare su Betfair, quanta responsabilità serve, quanto si guadagna in
ciascuno scenario.

```
python src/opportunita.py --sport soccer_sweden_allsvenskan
python src/opportunita.py --sport soccer_epl,soccer_italy_serie_a --puntata 200
python src/opportunita.py --sport soccer_epl --book "Betsson,NordicBet"
```

La struttura è **back al bookmaker / lay su Betfair su un solo esito**: rende molto
più dell'arbitraggio a tre vie, che disperde la puntata. Formula:

```
profitto/puntata = quota_book × (1 - commissione) / (quota_lay - commissione) - 1
```

Il dimensionamento tiene conto della **liquidità reale**: se al miglior prezzo lay ci
sono 69 €, la puntata scende di conseguenza. Quando non trova nulla mostra le 10
combinazioni più vicine con la quota che servirebbe — dice *quanto* manca.

**Attenzione al consumo**: ogni campionato costa 1 richiesta su 500 mensili.
Una scansione di 10 campionati = 10 richieste, cioè ~47 scansioni al mese.

---

## Il sistema automatico

```
   Betfair Italia ──(gratis)──┐
                              ├──> worker.py ──> Supabase ──> pannello Vercel
   The Odds API ──(a crediti)─┘        │
                                       └──> mail (Resend o SMTP)
```

**`src/worker.py`** è una passata completa, pensata per girare da sola:

1. chiede a Betfair — **gratis** — quali campionati hanno eventi in arrivo
2. spende crediti di The Odds API **solo** sui campionati presenti su entrambe
3. cerca le operazioni in utile
4. salva su Supabase (o su file, se il database non è configurato)
5. manda una mail per le occasioni mai notificate prima

```
python src/worker.py --dry-run          # prova senza salvare né notificare
python src/worker.py --crediti 6
```

Il punto 1 è ciò che rende sostenibile il piano gratuito: sulla misura del
25/07/2026 Betfair aveva **200 eventi calcio**, ma solo **53** in campionati
coperti anche da The Odds API. Interrogare gli 8 utili invece di tutti e 38
porta il costo da 38 a 8 crediti a passata.

### Il vero collo di bottiglia: i crediti, non l'infrastruttura

| Piano The Odds API | Crediti/mese | Passate da 8 crediti |
|---|---|---|
| Gratuito | 500 | ~62 → **2 al giorno** |
| $30/mese | 20.000 | ~2.500 → **una ogni 20 min** |

Si può costruire il sistema più bello del mondo: col piano gratuito scansiona
due volte al giorno. Ha senso valutare i $30 **solo dopo** aver verificato che
escano occasioni davvero eseguibili.

### Perché GitHub Actions e non Vercel Cron

Sul piano **Hobby di Vercel il cron gira una volta al giorno**, e le espressioni
più frequenti fanno fallire il deploy. GitHub Actions arriva a 5 minuti di
intervallo ed esegue direttamente il Python già scritto.

**Non ha funzionato, e per un motivo strutturale.** Vedi sotto.

### Perché il motore gira in locale

**Betfair Italia risponde `403 Forbidden` a qualsiasi connessione che non arrivi
dall'Italia.** È un operatore con concessione ADM: deve servire solo il territorio
nazionale, ed è la ragione per cui esiste l'endpoint separato
`identitysso.betfair.it`.

Verificato il 25/07/2026 — stesso codice, stesse credenziali, stesso momento:

| Da dove | Esito |
|---|---|
| GitHub Actions (datacenter USA) | `403 Forbidden` |
| PC dell'utente (IP italiano) | login regolare |

Non è aggirabile con una configurazione, e non va aggirato: è un controllo di
conformità, non un difetto. I workflow GitHub Actions sono stati **rimossi** invece
di lasciarli fallire due volte al giorno.

Il motore gira quindi dall'**Utilità di pianificazione di Windows**, con due attività
giornaliere che eseguono `scripts/passata.cmd`:

```
schtasks /Create /TN "MonitorQuote-Mattina" /TR "C:\matchedbetting\scripts\passata.cmd" /SC DAILY /ST 11:00 /F
schtasks /Create /TN "MonitorQuote-Sera"    /TR "C:\matchedbetting\scripts\passata.cmd" /SC DAILY /ST 18:00 /F
```

L'output finisce in `data/worker.log`. Per rimuoverle:
`schtasks /Delete /TN "MonitorQuote-Mattina" /F`

**Limite:** il PC deve essere acceso all'orario previsto. Per una copertura 24/7
servirebbe una macchina in Italia — resta da verificare se Betfair accetti anche gli
IP dei datacenter italiani o soltanto quelli residenziali.

### Il pannello (`pannello/`)

Next.js su Vercel, sola lettura da Supabase. Ogni opportunità è resa come una
**schedina**: due gambe numerate (1. scommetti / 2. banca) separate da una
perforazione, col margine stampato a destra e la responsabilità in fondo.

In alto una riga di stato che risponde alla domanda «il motore sta girando?» —
senza quella, un worker morto è indistinguibile da «non ci sono occasioni».
Include i crediti residui con una barra: la quota è il vincolo vero.

```
cd pannello && npm install && npm run dev
```

Variabili: `SUPABASE_URL` e `SUPABASE_ANON_KEY`, **senza** prefisso
`NEXT_PUBLIC_` — le chiamate partono dal server, la chiave non arriva al
browser. Su Vercel imposta **Root Directory = `pannello`**, perché il repo
contiene anche il Python.

### Messa in opera

1. **Supabase** — nuovo progetto → SQL Editor → incolla ed esegui `db/schema.sql`
2. **GitHub** — push del repo, poi *Settings → Secrets and variables → Actions*:
   `ODDS_API_KEY`, `BETFAIR_APP_KEY`, `BETFAIR_USERNAME`, `BETFAIR_PASSWORD`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `RESEND_API_KEY`, `EMAIL_A`
3. **Prima prova** — tab *Actions* → *Monitor quote* → *Run workflow*
4. **Vercel** — pannello collegato a Supabase in sola lettura (anon key)

---

## Struttura

```
matchedbetting/
├── README.md              <- questo file
├── requirements.txt       <- dipendenze Python
├── .env.example           <- template di configurazione (commentato)
├── .gitignore
├── .github/workflows/
│   ├── monitor.yml        <- il motore: 2 passate al giorno
│   └── keepalive.yml      <- impedisce la disattivazione dopo 60 giorni
├── db/
│   └── schema.sql         <- tabelle Supabase (da eseguire una volta)
├── data/                  <- generato, non versionato
├── docs/
│   └── DECISIONI.md       <- perché siamo arrivati qui (log delle scelte)
└── src/
    ├── odds_api.py        <- client The Odds API
    ├── betfair_api.py     <- client Betfair Exchange Italia (solo lettura)
    ├── monitor.py         <- arbing fra bookmaker internazionali
    ├── betfair_monitor.py <- book back/lay + volumi, serie storica
    ├── analisi.py         <- il prezzo si muove più di quanto costa il giro?
    ├── crossmarket.py     <- incoerenze fra mercati dello stesso evento
    ├── calcolatore.py     <- matched betting: Betfair live + quota book a mano
    ├── opportunita.py     <- TABELLA OPERATIVA: back book / lay Betfair
    ├── mappa_campionati.py <- sceglie i campionati da interrogare (salva crediti)
    ├── archivio.py        <- persistenza Supabase, con fallback su file
    ├── notifica.py        <- mail via Resend o SMTP
    └── worker.py          <- IL MOTORE AUTOMATICO
```

## Prossimi passi

- [ ] Far girare `betfair_monitor.py --loop` e raccogliere qualche ora di serie storica
- [ ] Script di analisi: ampiezza dei movimenti di prezzo, spread medio per sport/lega,
      quanto a lungo un prezzo resta fermo → dice se il trading è possibile
- [ ] Capire quanto pesa il ritardo di 1-180 s: se i movimenti utili durano meno,
      la chiave delayed non basta e serve decidere sui £499
- [ ] Far girare `monitor.py --loop` in sottofondo come termine di paragone

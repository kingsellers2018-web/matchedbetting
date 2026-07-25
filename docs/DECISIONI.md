# Log delle decisioni

Riepilogo di come siamo arrivati a questo progetto, così domani ripartiamo con le idee chiare.

## Idee valutate e scartate

| Idea | Esito | Perché |
|---|---|---|
| Arbitraggio crypto cross-exchange | ❌ Scartata | Dominata da bot HFT, trasferimenti lenti, margini nulli per il retail |
| Funding rate crypto (delta-neutral) | 🟢 Valida ma in pausa | Legale e automatizzabile, ma è "rendita lenta" (giorni/settimane) |
| Matched betting con bonus bookmaker | 🟡 Valida ma limitata | Guadagno finito (bonus una tantum) + rischio ban conto (gubbing) |
| **Betfair × Polymarket** (tennis) | ❌ **BLOCCATA** | **Polymarket è inibito in Italia dall'ADM** (verificato: DNS reindirizza a `sito-inibito-giochi.adm.gov.it`). Operatore non autorizzato → illegale e non percorribile |

## Dove siamo atterrati

**Monitor delle inefficienze sul tennis, in ambito 100% legale (Betfair ADM + bookmaker ADM).**

Due filoni:
1. **Trading di quote su Betfair** (back/lay sullo stesso mercato) → NON serve alcun bookmaker → automazione piena via API Betfair
2. **Arbing Betfair vs bookmaker** → il monitor rileva i disallineamenti; l'esecuzione sul bookmaker resta manuale (no API bookmaker)

## Concetto chiave da ricordare

> **L'edge è SEMPRE il disallineamento di prezzo (o un bonus), MAI la probabilità dell'evento.**
> Un mercato "50/50" non fa guadagnare: guadagni solo dove due mercati prezzano diverso la stessa cosa.

## Vincolo tecnico noto

I bookmaker (Snai, Sisal, Bet365...) **non offrono API** per piazzare scommesse.
- Per **leggere** le quote → usiamo un aggregatore: **The Odds API** (gratis, 500 req/mese)
- Per **eseguire** → Betfair sì (API ufficiale), bookmaker no (manuale)

## Fase attuale

**Fase 0 — Misurazione.** Far girare il monitor qualche giorno e vedere coi dati reali
quante inefficienze escono, quanto grandi e quanto durano. Poi si decide.

---

## Aggiornamento 25/07/2026 — dal tennis a "qualsiasi sport"

Primo lancio con API key reale. Tre scoperte che hanno cambiato l'impostazione.

### Il tennis non si può monitorare in continuo
The Odds API non tratta il tennis come sport continuo: espone **un torneo alla volta**,
solo i grandi (Slam, Masters 1000, WTA 1000) e solo mentre sono in corso.
Il 25/07/2026 tutti e 41 i tornei in elenco sono `active=False` — buco di calendario
fra Wimbledon e il Canadian Open.

**Decisione**: il monitor diventa agnostico rispetto allo sport (`ODDS_SPORTS=upcoming`).
La logica di arbitraggio non aveva nulla di specifico sul tennis, quindi il cambio è
stato di sola configurazione. Il tennis resta monitorabile passando la sport key del
torneo quando è attivo.

### Gli arbitraggi grezzi sono quasi tutti rumore
Senza filtri: 6 "arbitraggi" su 15 match. Tutti spiegabili come artefatti.
Sono stati aggiunti quattro filtri, ognuno per una causa osservata:

| Filtro | Contro cosa |
|---|---|
| `MAX_ODDS` | quote residue tipo 501.0 su cui nessuno punta davvero |
| `MIN_MINUTI_ALL_INIZIO` | match già partiti → quote in-play o stantie (causa n.1) |
| `MIN_BOOKMAKERS` | arb sostenuti da 2-3 book soli = quota vecchia di uno solo |
| `BETFAIR_COMMISSION` | margine teorico ≠ margine incassato sulle exchange |

Con i filtri: ~1 candidato su 14 match, ampiezza ~0,9%.

### Vincolo nuovo e serio: copertura bookmaker ≠ mercato italiano
L'API in regione `eu` copre 20 operatori, ma sono le versioni `.com`/`.fr`/`.se`.
Le versioni `.it` con licenza ADM — le uniche accessibili legalmente dall'Italia —
espongono quote diverse, e diversi di quei marchi in Italia non esistono proprio
(Pinnacle, MyBookie.ag, BetOnline.ag, 1xBet).

L'unico arbitraggio superstite del primo giro filtrato (+0,91%, KBO baseball) poggiava
su 1xBet e BetOnline.ag: **matematicamente valido, praticamente inaccessibile.**

> **Conseguenza da tenere a mente:** il monitor misura il mercato internazionale.
> Serve a rispondere alla domanda della Fase 0 ("le inefficienze esistono?"), ma un arb
> che rileva non è automaticamente eseguibile. `BOOK_WHITELIST` esiste per restringere
> l'analisi ai soli book su cui si ha davvero un conto legale.

---

## Aggiornamento 25/07/2026 (bis) — The Odds API non serve per eseguire dall'Italia

Verificato dopo aver saputo che l'unico conto disponibile è **Betfair Exchange**.

### The Odds API non copre l'Italia, e non è un problema di conti
Le regioni disponibili sono sei: **US, UK, EU, FR, SE, AU**. Nessuna Italia.
Nessun bookmaker italiano è coperto: Sisal, Snai, Eurobet, Goldbet, Betflag,
Lottomatica, Planetwin365 — tutti assenti.

I 20 operatori in regione `eu` sono le versioni `.com`/`.fr`/`.se`, inaccessibili
dall'Italia per lo stesso motivo di Polymarket (blocco ADM). I marchi con licenza
italiana (888, LeoVegas, Betsson...) compaiono solo nella versione estera, con quote
diverse da quelle esposte sui rispettivi `.it`.

**Aprire altri conti non risolve**: il problema non è quanti conti si hanno, è che la
fonte dati non osserva il mercato su cui si può operare.

### Anche il Betfair del feed è il mercato sbagliato
Il feed espone `betfair_ex_eu` = exchange **internazionale**. L'Exchange italiano
(`betfair.it`) è un **pool di liquidità separato**, con prezzi e volumi propri
(confermato dalla documentazione Betfair: le API "return the markets that are available
to Italian Exchange customers via the Betfair.it domain").

### Nota positiva: il lato lay c'è
Verificato che `betfair_ex_eu` espone sia `h2h` sia `h2h_lay`. La voce "aggiungere il
lato lay" nella lista dei prossimi passi è quindi fattibile — ma resta sul mercato
internazionale, non su quello italiano.

## Decisione: Strada A — trading su Betfair Italia con la Delayed App Key

| Strada | Costo | Esito |
|---|---|---|
| **A. Trading back/lay su Betfair Italia** | **0 €** | 🟢 **Scelta** |
| B. Arbing fra book italiani via servizio a pagamento (BetBurger, OddsJam, RebelBetting) | abbonamento mensile | 🟡 In attesa: spesa ricorrente prima di sapere se funziona |
| C. Scraping dei siti `.it` | 0 € | ❌ Fragile e contrario ai termini d'uso |

Dettagli verificati sulla Strada A:
- **Delayed App Key: gratuita**, dati ritardati di **1-180 secondi**. Sufficiente per
  misurare l'ampiezza dei movimenti di prezzo, che è la domanda della Fase 0.
- **Live App Key: £499 una tantum, non rimborsabili**, e Betfair **non consente
  l'accesso in sola lettura** con la Live key. Da valutare solo se la Fase 0 dà esito
  positivo.
- Creazione key: [Accounts API Demo Tool](https://apps.betfair.com/visualisers/api-ng-account-operations/)
  → operazione `createDeveloperAppKeys`, serve il session token (ssoid) dal browser.
  Genera due chiavi insieme: una Live (inattiva) e una `1.0-DELAY` subito usabile.
- Login Exchange italiano: `https://identitysso.betfair.it/api/login`
  (endpoint diverso dal `.com`). Betting API su `https://api.betfair.com/exchange/betting/`.
- Vincoli regolamentari italiani: puntata minima 2,00 €, incrementi da 0,50 €,
  max 50 istruzioni per richiesta, vincita potenziale massima 10.000 €,
  vietato combinare back e lay nella stessa richiesta.

### Cosa resta di The Odds API
Non si butta: continua a girare gratis come **misura di sfondo del mercato
internazionale**. Risponde alla domanda "il fenomeno delle inefficienze esiste, e di che
ordine di grandezza?" — ma le sue segnalazioni non sono eseguibili dall'Italia.

---

## Aggiornamento 25/07/2026 (ter) — prime misure reali su Betfair Italia

Login riuscito con la Delayed App Key. Primi dati dal book vero.

### Il tennis c'è (l'idea originale non era sbagliata: era sbagliata la fonte)
Sport disponibili sull'Exchange italiano:

| Sport | Mercati |
|---|---|
| Soccer | 8.332 |
| Tennis | 135 |
| Basketball | 8 |

The Odds API non aveva **un solo** mercato tennis; Betfair Italia ne ha 135.

### Il problema non è lo spread, è la PROFONDITÀ
Misure del 25/07/2026, ore 10:45-10:48:

| Metrica | Calcio | Tennis |
|---|---|---|
| Mercato più scambiato | 17.538 € | 2.001 € |
| Spread mediano (mercati liquidi) | 3-5% | 2,11% (min 0,56%) |
| **Profondità mediana al miglior prezzo** | **12-460 €** | **24 €** |

Lo spread sui favoriti è spesso di **un solo tick** (es. 1,40 / 1,42 = 1,43%): in termini
relativi il mercato è stretto. Il problema è un altro: al miglior prezzo ci sono
**poche decine di euro**. Con una profondità mediana di 24 € non si costruisce una
posizione — e qualunque ordine appena più grande sposta il prezzo da solo.

Betfair Italia è un pool segregato e **molto** più piccolo di quello internazionale:
sul `.com` un mercato tennis di pari livello scambia ordini di grandezza in più.

### Attenuante stagionale importante
Le misure sono del 25 luglio: Serie A ferma, tennis fra Wimbledon e Canadian Open,
basket in pausa. **È il minimo stagionale della liquidità.** Questi numeri vanno letti
come pavimento, non come media. Va rimisurato a metà agosto, con la Serie A avviata,
prima di trarre conclusioni definitive.

### Strumento aggiunto: `src/analisi.py`
Confronta, letture successive alla mano, il **movimento del prezzo** con il **costo del
giro** (spread + commissione). La domanda è secca: il prezzo si muove più di quanto
costa entrare e uscire? Se no, il trading è in perdita per aritmetica, non per bravura.

Primo lancio: 4 soli confronti su 3 minuti → **campione insufficiente, nessuna
conclusione valida**. Serve far girare `--loop` per ore.

---

## Aggiornamento 25/07/2026 (quater) — il confronto quote interno all'Exchange: ZERO

Domanda posta: "non riusciamo in primis a fare confronto quote?" Verificato a fondo.

### Formula 1: non c'è
L'Exchange italiano ha **solo tre sport**: Soccer (8.320 mercati), Tennis (135),
Basketball (8). Ricerca testuale "Formula" → nessun risultato; "Motor" → solo squadre di
calcio. Sui bookmaker italiani l'F1 c'è, ma senza il lato exchange non c'è nulla da
confrontare.

### L'idea buona: confrontare mercati diversi dello STESSO evento
Sullo stesso evento Betfair quota ~20 mercati legati da vincoli matematici. Se due si
contraddicono il profitto è garantito **con un conto solo**. Implementato in
`src/crossmarket.py`:

| Controllo | Identità sfruttata |
|---|---|
| Tennis: Match Odds vs Set Betting | `P(A vince)` = `P(A 2-0)` + `P(A 2-1)` |
| Calcio: scaletta Over/Under | `P(over 1.5) ≥ P(over 2.5) ≥ ...` (implicazione logica) |

### Esito: 0 su 295 confronti
Con soglie azzerate (`--min-profit 0.001 --min-size 0`): **nessuna incoerenza, nemmeno
di un decimale di punto**. Le scalette Over/Under sono perfettamente monotone; il Set
Betting è sempre contenuto dentro il Match Odds, mai a cavallo.

> **Conclusione:** l'Exchange è internamente privo di arbitraggi. Non è una sorpresa —
> è esattamente il controllo che i bot fanno migliaia di volte al secondo. Questa strada
> è chiusa, ed è bene saperlo con un dato invece che con un'opinione.

### Cosa resta in piedi
Esclusi: arbing fra bookmaker (nessuna fonte quote `.it`), arbing interno all'Exchange
(misurato zero), F1 (assente). Restano due cose:

1. **Betfair contro un bookmaker italiano**, con il lato bookmaker inserito a mano.
   L'API dà il lato exchange in tempo (quasi) reale; l'utente legge la quota sul sito del
   bookmaker su cui ha il conto. Nessuno scraping, nessuna violazione di termini d'uso.
2. **Matched betting sui bonus** — già nella tabella iniziale come "valida ma limitata".
   Ora che tutto il resto è stato misurato a zero, diventa **l'unica struttura con valore
   atteso positivo dimostrabile**: l'edge è il bonus, non il disallineamento di prezzo,
   ed è esattamente il concetto chiave scritto in cima a questo documento.

Da qui nasce `src/calcolatore.py`.

---

## Aggiornamento 25/07/2026 (quinquies) — le inefficienze ESISTONO, il blocco è l'accesso

Domanda posta: "ma non riesci a vedere le quote su The Odds API?" Sì, e vederle bene
ha cambiato due conclusioni precedenti.

### Correzione: le quote Betfair delle due fonti sono quasi identiche
Confronto diretto sullo stesso evento (Degerfors v Djurgardens, 25/07):

| Esito | The Odds API "Betfair" | Betfair Italia (back) |
|---|---|---|
| Degerfors | 5.3 | 5.2 |
| Djurgardens | 1.72 | **1.72** |
| Pareggio | 4.2 | **4.2** |

I pool restano separati per **liquidità**, ma i **prezzi si allineano**. L'affermazione
precedente ("anche il dato Betfair non è il tuo mercato") era troppo drastica: come
riferimento di prezzo il feed è utilizzabile.

### Gli arbitraggi ci sono, e non sono briciole
`monitor.py --sport soccer_sweden_allsvenskan` (campionato con 22 bookmaker coperti):

| Match | Margine netto |
|---|---|
| IK Sirius vs IFK Goteborg | **2,01%** |
| IF Brommapojkarna vs Hammarby IF | **1,69%** |
| Degerfors IF vs Djurgardens IF | 0,77% |

**3 arbitraggi su 7 partite**, pre-match, con i filtri anti-rumore attivi.
Il monitor non li trovava prima solo perché campionava `upcoming` (15 eventi a caso)
invece di un campionato ben coperto. **Non era un problema di metodo, era di puntamento.**

### La causa è sempre la stessa: un bookmaker fuori linea
In tutti e tre i casi la quota anomala è di **Unibet (SE)** — 8,5 dove il resto del
mercato sta a 5-6. Non è "il mercato che sbaglia": è **un singolo operatore** con un
modello diverso o un errore. Gli altri lati sono Coolbet, GTbets, Pinnacle, Betsson:
nessuno accessibile legalmente dall'Italia.

### La struttura giusta non è a tre vie, è back-bookmaker / lay-exchange
Incrociando i due strumenti su Sirius v IFK Goteborg:

```
Betfair Italia   lay IFK Goteborg 7.20  (69 EUR disponibili)
Soglia pareggio                   7.53
Unibet (SE)                       8.50   ->  +12,9% garantito
```

Il monitor stimava 2,01% perché divide la puntata su tre esiti; backare **un solo
esito** al bookmaker e layare su Betfair rende molto di più. Formula della soglia:
`B* = (L - commissione) / (1 - commissione)`. Implementata in `calcolatore.py --soglie`.

### Conclusione operativa
Il fenomeno è **reale e misurabile**. L'unico blocco è l'accesso agli operatori che
producono le quote anomale. La domanda diventa quindi:

> **un bookmaker italiano ADM produce quote fuori linea come fa Unibet SE?**

Non è deducibile dai dati in nostro possesso — nessuna fonte copre i book italiani.
Si risponde solo guardando: `--soglie` dà la quota da battere, l'utente la confronta
col sito su cui ha il conto. Serve **un solo** bookmaker italiano, non due.

**Limite noto:** la liquidità di Betfair Italia. Nell'esempio sopra il lay ha 69 EUR
disponibili → puntata massima ~58 EUR → utile ~7,50 EUR per operazione.

---

## Aggiornamento 25/07/2026 (sexies) — `opportunita.py`: la tabella operativa

Richiesta esplicita: una tabella che dica *"scommetti qui questo esito, su Betfair
fai questo, profitto matematico di X"*. Realizzata in `src/opportunita.py`.

Include **tutti** i bookmaker, anche stranieri, senza filtri preimpostati
(`--book` per restringere a quelli su cui si ha davvero un conto).

### Come frequenti sono le occasioni: misurato
| Scansione | Eventi incrociati | Operazioni in utile |
|---|---|---|
| Allsvenskan (7 partite) | 7 | **3** (+12,94%, +6,95%, +6,15%) |
| 10 campionati (98 partite) | 30 | **0** su 2.025 combinazioni valutate |

Le tre occasioni dell'Allsvenskan hanno **tutte** la stessa gamba: Unibet (SE).
Sulle altre 30 partite la combinazione migliore è **-2,27%**: manca circa il 2,5-3,5%,
che è esattamente margine del bookmaker + spread Betfair + commissione.

> **L'arbitraggio non nasce dal mercato: nasce da un singolo operatore fuori linea.**
> Senza un bookmaker anomalo non c'è niente, e la distanza dal pareggio è strutturale.

### Barriera d'accesso a Unibet (SE), LeoVegas (SE), Coolbet
Non è una questione di volontà: la registrazione richiede **personnummer svedese con
BankID** o documento nordico/estone. Non è un requisito aggirabile. Altri operatori
(Betsson, NordicBet, 1xBet, Everygame, BetOnline.ag) accettano registrazioni
internazionali ma **non hanno licenza ADM** e in Italia sono inibiti via DNS —
stessa barriera di Polymarket, annotata all'inizio di questo documento.

Segnalato all'utente, che ha confermato di voler procedere comunque: lo strumento è
stato quindi realizzato completo, senza restrizioni preimpostate.

### Consumo del piano gratuito
1 richiesta per campionato per scansione. 10 campionati = 10 richieste → ~47
scansioni al mese sulle 500 disponibili. Da tenere d'occhio se si scansiona spesso.

---

## Aggiornamento 25/07/2026 (septies) — il sistema automatico

Richiesta: motore in background, pannello, notifiche via mail. Stack a disposizione:
GitHub, Vercel, Supabase.

### Il collo di bottiglia non è l'infrastruttura, è la quota
8 crediti a passata su 500 mensili → **~62 passate al mese, cioè 2 al giorno**.
Il piano da $30/mese (20.000 crediti) porterebbe a una passata ogni 20 minuti.
Con 2 passate al giorno si perde la maggior parte delle occasioni: le quote
anomale durano minuti. Il sistema gratuito serve a misurare *quanto spesso*
compaiono e *su quali bookmaker*, non a coglierle tutte.

### Vincoli dei piani verificati, non supposti
| Servizio | Vincolo | Conseguenza |
|---|---|---|
| Vercel Hobby | cron **una volta al giorno**; espressioni più frequenti fanno fallire il deploy | ❌ non può fare da motore |
| GitHub Actions | minimo 5 minuti; workflow disattivati dopo **60 giorni** senza attività sul repo | ✅ motore, con `keepalive.yml` |
| Supabase Free | progetti sospesi dopo 1 settimana di inattività | non applicabile: il progetto è **Pro** |
| The Odds API | 500 crediti/mese gratuiti | il vero limite |

### Risparmio di crediti: chiedere prima a Betfair
Le chiamate a Betfair sono gratuite. Quindi `mappa_campionati.py` interroga prima
Betfair per sapere quali competizioni hanno eventi, poi le abbina ai campionati di
The Odds API (anche `/sports` è gratuito) e spende **solo sull'intersezione**.

Misura: Betfair ha 200 eventi calcio in 72 ore, ma solo 53 in campionati coperti
da entrambe. **8 crediti a passata invece di 38.**

### Supabase: schema applicato e RLS verificate sul campo
Progetto `wizkizcnjpxjthqfgbva`, regione eu-west-1.
L'host `db.*` risolve **solo IPv6** e il PC dell'utente non ha IPv6: le migrazioni
passano dal **Session pooler** (`aws-0-eu-west-1.pooler.supabase.com:5432`), che
espone IPv4.

Permessi verificati con test reali, non per costruzione:

| Operazione | anon | service_role |
|---|---|---|
| SELECT | ✅ 200 | ✅ |
| INSERT | ❌ 401 (RLS) | ✅ 201 |
| DELETE | ⊘ nessun effetto | ✅ |

> Nota metodologica: il primo test aveva segnalato un falso allarme sul DELETE
> (HTTP 204 con anon key). PostgREST risponde 204 anche quando non cancella nulla,
> e la tabella era vuota. Rifatto inserendo prima una riga con `service_role`:
> la riga è sopravvissuta. **Le RLS funzionano.**

### Il chiave di unicità che evita le mail doppie
`opportunita_chiave` su `(market_id, esito, bookmaker)`: la stessa occasione vista
in due passate aggiorna la riga invece di duplicarla, e `notificata_at` fa partire
la mail una volta sola.

### Test end-to-end riuscito
Worker → Supabase: 6 opportunità scritte, vista `opportunita_attive` corretta,
scansione tracciata con crediti residui. Pannello Next.js: build ok, dati
renderizzati lato server.

Bookmaker delle occasioni trovate: Unibet (SE), 1xBet, Coolbet, Marathon Bet.
Il problema di accesso resta quello già documentato.

---

## Aggiornamento 25/07/2026 (octies) — il motore non può girare nel cloud

Prima esecuzione reale su GitHub Actions: **fallita**.

```
403 Client Error: Forbidden for url: https://identitysso.betfair.it/api/login
```

### Non è una credenziale, è la geografia
Verificato nello stesso minuto, con lo stesso codice e le stesse credenziali:

| Da dove | Esito |
|---|---|
| GitHub Actions (runner in datacenter USA) | `403 Forbidden` |
| PC dell'utente (IP residenziale italiano) | login OK, token ricevuto |

**Betfair Italia serve solo l'Italia.** È un operatore con concessione ADM ed è
tenuto a farlo: è esattamente la ragione per cui esiste l'endpoint separato `.it`
invece del `.com`. Non è un difetto da aggirare, è un controllo di conformità.

### Decisione: motore in locale, workflow rimossi
I due workflow GitHub Actions sono stati **cancellati** invece di essere lasciati a
fallire due volte al giorno. Un impianto che per costruzione non può funzionare è
peggio che nessun impianto: genera rumore e nasconde i guasti veri.

Il motore gira dall'**Utilità di pianificazione di Windows**, due attività giornaliere
(`MonitorQuote-Mattina` 11:00, `MonitorQuote-Sera` 18:00) che eseguono
`scripts/passata.cmd` e scrivono in `data/worker.log`.

Prima esecuzione dall'Utilità di pianificazione: riuscita in 10,9 s, 6 crediti spesi,
mail inviata con 2 occasioni nuove.

### Cosa cambia e cosa no
- ✅ Supabase, pannello Vercel, mail Resend: **inalterati**. Sono raggiungibili da
  ovunque, e il pannello legge dal database senza sapere chi lo abbia scritto.
- ⚠️ **Il PC deve essere acceso** agli orari previsti. È il nuovo limite del sistema.
- ❓ Per una copertura 24/7 servirebbe una macchina in Italia. **Da verificare prima
  di spendere**: Betfair potrebbe bloccare anche gli IP di datacenter italiani e non
  solo quelli esteri. Si prova con una VPS a consumo prima di impegnarsi.

> Nota di metodo: questo è il secondo vincolo di conformità ADM che ridisegna il
> progetto, dopo l'inibizione di Polymarket. Vale la pena assumere, per il futuro,
> che ogni servizio regolamentato italiano abbia una barriera analoga, e verificarlo
> **prima** di costruirci sopra.

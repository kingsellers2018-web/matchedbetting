-- ===========================================================================
--  Schema Supabase per il monitor.
--  Da incollare nell'SQL Editor di Supabase ed eseguire una volta sola.
-- ===========================================================================

-- ---------------------------------------------------------------------------
--  Storico delle passate: serve a sapere se il motore sta girando davvero
--  e quanti crediti restano. Senza questo, un worker morto e' indistinguibile
--  da "non ci sono opportunita'".
-- ---------------------------------------------------------------------------
create table if not exists scansioni (
    id                bigint generated always as identity primary key,
    ts                timestamptz not null default now(),
    campionati        text[]      not null default '{}',
    crediti_spesi     int         not null default 0,
    crediti_rimasti   int,
    partite           int         not null default 0,
    mercati_betfair   int         not null default 0,
    eventi_incrociati int         not null default 0,
    combinazioni      int         not null default 0,
    opportunita       int         not null default 0,
    miglior_margine   numeric,
    errori            text
);

create index if not exists scansioni_ts_idx on scansioni (ts desc);

-- ---------------------------------------------------------------------------
--  Opportunita' correnti.
--  La chiave (market_id, esito, bookmaker) identifica la stessa occasione nel
--  tempo: le passate successive la aggiornano invece di duplicarla. Cosi' il
--  pannello mostra lo stato attuale e la mail parte una volta sola.
-- ---------------------------------------------------------------------------
create table if not exists opportunita (
    id                 bigint generated always as identity primary key,
    market_id          text        not null,
    esito              text        not null,
    bookmaker          text        not null,

    evento             text        not null,
    competizione       text,
    inizio             timestamptz,

    quota_book         numeric     not null,
    quota_lay          numeric     not null,
    liquidita          numeric,

    margine_pct        numeric     not null,   -- margine all'ultima lettura
    margine_max        numeric     not null,   -- il migliore mai visto
    puntata            numeric,
    lay_stake          numeric,
    responsabilita     numeric,
    profitto_garantito numeric,

    vista_prima        timestamptz not null default now(),
    vista_ultima       timestamptz not null default now(),
    notificata_at      timestamptz,            -- null = mail non ancora inviata

    constraint opportunita_chiave unique (market_id, esito, bookmaker)
);

create index if not exists opportunita_margine_idx on opportunita (margine_pct desc);
create index if not exists opportunita_inizio_idx  on opportunita (inizio);
create index if not exists opportunita_daNotificare_idx
    on opportunita (notificata_at) where notificata_at is null;

-- ---------------------------------------------------------------------------
--  Vista per il pannello: solo le occasioni ancora giocabili.
--  Un'opportunita' su un evento gia' iniziato non serve a nulla.
-- ---------------------------------------------------------------------------
create or replace view opportunita_attive as
select *,
       extract(epoch from (inizio - now())) / 3600 as ore_al_via
from   opportunita
where  inizio > now()
  and  vista_ultima > now() - interval '6 hours'
order by margine_pct desc;

-- ---------------------------------------------------------------------------
--  Sicurezza.
--  Il worker scrive con la service_role key (che ignora le policy).
--  Il pannello legge con la anon key: sola lettura, nessuna scrittura.
-- ---------------------------------------------------------------------------
alter table scansioni   enable row level security;
alter table opportunita enable row level security;

drop policy if exists "lettura pubblica scansioni"   on scansioni;
drop policy if exists "lettura pubblica opportunita" on opportunita;

create policy "lettura pubblica scansioni"
    on scansioni for select using (true);

create policy "lettura pubblica opportunita"
    on opportunita for select using (true);

-- ---------------------------------------------------------------------------
--  Pulizia: le occasioni su eventi finiti da piu' di 3 giorni non servono.
--  Da schedulare con pg_cron se il database cresce troppo:
--      select cron.schedule('pulizia', '0 4 * * *',
--                           $$ select pulisci_vecchie() $$);
-- ---------------------------------------------------------------------------
create or replace function pulisci_vecchie() returns void
language sql as $$
    delete from opportunita where inizio < now() - interval '3 days';
    delete from scansioni   where ts     < now() - interval '90 days';
$$;

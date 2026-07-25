export const revalidate = 60; // il worker scrive 2 volte al giorno: 60s bastano

const URL = process.env.SUPABASE_URL;
const ANON = process.env.SUPABASE_ANON_KEY;

async function leggi(risorsa, parametri) {
    if (!URL || !ANON) return [];
    const qs = new URLSearchParams(parametri).toString();
    const r = await fetch(`${URL}/rest/v1/${risorsa}?${qs}`, {
        headers: { apikey: ANON, Authorization: `Bearer ${ANON}` },
        next: { revalidate: 60 },
    });
    if (!r.ok) return [];
    return r.json();
}

// --- formattazione ---------------------------------------------------------

const euro = (n) =>
    Number(n ?? 0).toLocaleString("it-IT", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });

function quandoInizia(ore) {
    const h = Number(ore ?? 0);
    if (h < 1) return `fra ${Math.round(h * 60)} min`;
    if (h < 24) return `fra ${h.toFixed(1)} ore`;
    return `fra ${Math.floor(h / 24)}g ${Math.round(h % 24)}h`;
}

function daQuanto(iso) {
    if (!iso) return "mai";
    const min = (Date.now() - new Date(iso).getTime()) / 60000;
    if (min < 60) return `${Math.round(min)} min fa`;
    if (min < 1440) return `${(min / 60).toFixed(1)} ore fa`;
    return `${Math.floor(min / 1440)} giorni fa`;
}

// --- pezzi -----------------------------------------------------------------

function Schedina({ o }) {
    // Quando il lay stake mangia quasi tutto il denaro disponibile al miglior
    // prezzo, l'importo non e' scalabile: va detto, non nascosto.
    const stretta =
        o.liquidita && Number(o.lay_stake) >= Number(o.liquidita) * 0.95;

    return (
        <article className="schedina">
            <div className="schedina-testa">
                <div>
                    <h3 className="evento">{o.evento}</h3>
                    <div className="contesto">
                        {o.competizione ? `${o.competizione} · ` : ""}
                        {quandoInizia(o.ore_al_via)} · esito{" "}
                        <strong>{o.esito}</strong>
                    </div>
                </div>
                <div className="margine">
                    +{Number(o.margine_pct).toFixed(2)}%
                    <small>{euro(o.profitto_garantito)} € garantiti</small>
                </div>
            </div>

            <div className="gambe">
                <div className="gamba">
                    <span className="passo">1 · scommetti</span>
                    <span className="importo">{euro(o.puntata)} €</span>
                    <span className="dove">
                        quota {o.quota_book} presso <b>{o.bookmaker}</b>
                    </span>
                </div>
                <div className="gamba">
                    <span className="passo">2 · banca su Betfair</span>
                    <span className="importo">{euro(o.lay_stake)} €</span>
                    <span className="dove">
                        quota {o.quota_lay} · lay su <b>Betfair Italia</b>
                    </span>
                </div>
            </div>

            <div className="schedina-piede">
                <span>
                    responsabilità <b>{euro(o.responsabilita)} €</b>
                </span>
                <span>
                    disponibile al prezzo <b>{euro(o.liquidita)} €</b>
                </span>
                {stretta && (
                    <span className="avviso-liquidita">
                        importo limitato dalla liquidità
                    </span>
                )}
            </div>
        </article>
    );
}

function Stato({ ultima }) {
    if (!ultima) {
        return (
            <div className="stato">
                <div className="tassello">
                    <span className="etichetta">Motore</span>
                    <span className="pillola fermo">mai eseguito</span>
                    <span className="nota">
                        Lancia il workflow «Monitor quote» su GitHub Actions.
                    </span>
                </div>
            </div>
        );
    }

    const minuti = (Date.now() - new Date(ultima.ts).getTime()) / 60000;
    const salute =
        minuti < 60 * 18 ? "ok" : minuti < 60 * 36 ? "avviso" : "fermo";
    const testoSalute =
        salute === "ok" ? "attivo" : salute === "avviso" ? "in ritardo" : "fermo";

    const crediti = Number(ultima.crediti_rimasti ?? 0);
    const quota = Math.max(0, Math.min(100, (crediti / 500) * 100));

    return (
        <div className="stato">
            <div className="tassello">
                <span className="etichetta">Motore</span>
                <span className={`pillola ${salute}`}>{testoSalute}</span>
                <span className="nota">ultima passata {daQuanto(ultima.ts)}</span>
            </div>

            <div className="tassello">
                <span className="etichetta">Crediti rimasti</span>
                <span className="valore">{crediti || "—"}</span>
                <div className="barra">
                    <span style={{ width: `${quota}%` }} />
                </div>
            </div>

            <div className="tassello">
                <span className="etichetta">Eventi incrociati</span>
                <span className="valore">{ultima.eventi_incrociati}</span>
                <span className="nota">
                    su {ultima.partite} partite, {ultima.campionati?.length ?? 0}{" "}
                    campionati
                </span>
            </div>

            <div className="tassello">
                <span className="etichetta">Miglior margine</span>
                <span className="valore">
                    {ultima.miglior_margine != null
                        ? `${Number(ultima.miglior_margine).toFixed(2)}%`
                        : "—"}
                </span>
                <span className="nota">
                    {ultima.combinazioni} combinazioni valutate
                </span>
            </div>
        </div>
    );
}

// --- pagina ----------------------------------------------------------------

export default async function Pagina() {
    const [attive, scansioni] = await Promise.all([
        leggi("opportunita_attive", {
            select: "*",
            order: "margine_pct.desc",
            limit: "40",
        }),
        leggi("scansioni", { select: "*", order: "ts.desc", limit: "12" }),
    ]);

    const ultima = scansioni[0];
    const totale = attive.reduce(
        (s, o) => s + Number(o.profitto_garantito ?? 0),
        0
    );

    return (
        <main className="guscio">
            <header className="testata">
                <h1 className="marchio">
                    Monitor quote <em>·</em> back bookmaker / lay Betfair
                </h1>
                <p className="sottotitolo">
                    Operazioni con esito identico qualunque cosa succeda: si
                    scommette dove la quota è fuori linea e si banca la stessa
                    selezione su Betfair Italia.
                </p>
            </header>

            <Stato ultima={ultima} />

            <section className="sezione">
                <h2 className="titolo-sezione">
                    <span>Operazioni aperte</span>
                    {attive.length > 0 && (
                        <span>{euro(totale)} € se le esegui tutte</span>
                    )}
                </h2>

                {attive.length === 0 ? (
                    <div className="vuoto">
                        <strong>Nessuna operazione in utile adesso.</strong>
                        Il margine dei bookmaker più lo spread di Betfair vale
                        circa il 3%: perché resti profitto serve un operatore
                        fuori linea, e non capita a ogni passata.
                    </div>
                ) : (
                    attive.map((o) => <Schedina key={o.id} o={o} />)
                )}
            </section>

            <section className="sezione">
                <h2 className="titolo-sezione">
                    <span>Passate recenti</span>
                </h2>
                <div className="tabella-guscio">
                    <table>
                        <thead>
                            <tr>
                                <th>Quando</th>
                                <th className="destra">Campionati</th>
                                <th className="destra">Crediti</th>
                                <th className="destra">Incrociati</th>
                                <th className="destra">Trovate</th>
                                <th className="destra">Miglior margine</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scansioni.map((s) => (
                                <tr key={s.id}>
                                    <td>{daQuanto(s.ts)}</td>
                                    <td className="num destra">
                                        {s.campionati?.length ?? 0}
                                    </td>
                                    <td className="num destra">
                                        {s.crediti_spesi}
                                    </td>
                                    <td className="num destra">
                                        {s.eventi_incrociati}
                                    </td>
                                    <td className="num destra">
                                        {s.opportunita}
                                    </td>
                                    <td className="num destra">
                                        {s.miglior_margine != null
                                            ? `${Number(
                                                  s.miglior_margine
                                              ).toFixed(2)}%`
                                            : "—"}
                                    </td>
                                </tr>
                            ))}
                            {scansioni.length === 0 && (
                                <tr>
                                    <td colSpan={6}>
                                        Nessuna passata registrata.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            <footer className="pie">
                Le quote si muovono in fretta: verifica che siano ancora quelle
                prima di piazzare, ed esegui <strong>prima</strong> il lato
                bookmaker, che è quello che sparisce per primo. Gli importi
                tengono conto della liquidità disponibile su Betfair al momento
                della rilevazione, e rispettano i limiti dell&apos;Exchange
                italiano: puntata minima 2,00 € a scatti di 0,50 €.
            </footer>
        </main>
    );
}

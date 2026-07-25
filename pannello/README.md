# Pannello

Sito di sola lettura che mostra le opportunità trovate dal worker.
Next.js (App Router), nessuna dipendenza oltre a React: parla con Supabase
via REST.

## Variabili d'ambiente

Su Vercel: *Settings → Environment Variables*.

```
SUPABASE_URL=https://xxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
```

Niente prefisso `NEXT_PUBLIC_`: le chiamate partono dal server, quindi la
chiave non arriva nemmeno al browser. Anche se ci arrivasse non sarebbe un
problema — le RLS la limitano alla sola lettura — ma tenerla lato server è
gratis e più pulito.

## In locale

```
cd pannello
npm install
npm run dev
```

Crea un `.env.local` con le stesse due variabili.

## Deploy su Vercel

1. Importa il repository
2. **Root Directory** → `pannello`
3. **Framework Preset** → `Next.js`
4. Aggiungi le due variabili d'ambiente
5. Deploy

### Se il build fallisce con «No python entrypoint found»

Sono i passi 2 e 3 non applicati. Vercel scansiona la radice del repository,
trova `requirements.txt`, conclude «progetto Python» e cerca `app.py` o
`main.py` — che qui non esistono e non devono esistere: il motore Python gira
su GitHub Actions, non su Vercel.

Si corregge in *Settings → Build and Deployment*, mettendo `pannello` in
**Root Directory** e `Next.js` in **Framework Preset**. Poi *Deployments →
Redeploy* **senza** la spunta *Use existing Build Cache*.

Da qui il `vercel.json` in questa cartella: dichiara il framework in modo
esplicito, così l'autodetezione non ha margine di errore.

La pagina si rigenera ogni 60 secondi. Il worker scrive due volte al giorno,
quindi non serve nulla di più reattivo.

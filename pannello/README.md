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
2. **Root Directory** → `pannello` (importante: il repo contiene anche il Python)
3. Aggiungi le due variabili d'ambiente
4. Deploy

La pagina si rigenera ogni 60 secondi. Il worker scrive due volte al giorno,
quindi non serve nulla di più reattivo.

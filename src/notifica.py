"""
Invio delle mail quando compare un'occasione.

Due strade, si usa quella configurata:
  - RESEND_API_KEY  -> Resend (nessun server SMTP da gestire)
  - SMTP_*          -> un qualsiasi server SMTP, per esempio Gmail con una
                       "password per le app" (serve la verifica in due passaggi
                       attiva sull'account Google)

Se non c'e' nessuna delle due, il worker continua a girare e salvare: la mail
e' un di piu', non una dipendenza.
"""
import os
import smtplib
from email.message import EmailMessage

import requests


def _riga_html(o: dict) -> str:
    inizio = (o.get("inizio") or "")[:16].replace("T", " ")
    return f"""
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">
        <div style="font-weight:600;font-size:15px">{o['evento']}</div>
        <div style="color:#6b7280;font-size:12px">{o.get('competizione') or ''} &middot; {inizio} UTC</div>
      </td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-size:13px">
        <b>{o['esito']}</b><br>
        <span style="color:#6b7280">punta</span> {o.get('puntata', 0):.2f}&euro;
        @ {o['quota_book']} &rarr; <b>{o['bookmaker']}</b><br>
        <span style="color:#6b7280">banca</span> {o.get('lay_stake', 0):.2f}&euro;
        @ {o['quota_lay']} &rarr; Betfair
      </td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right;white-space:nowrap">
        <div style="font-size:19px;font-weight:700;color:#047857">
          +{o['margine_pct']:.2f}%</div>
        <div style="color:#6b7280;font-size:12px">
          {o.get('profitto_garantito', 0):+.2f}&euro; garantiti</div>
        <div style="color:#9ca3af;font-size:11px">
          serve {o.get('responsabilita', 0):.0f}&euro;</div>
      </td>
    </tr>"""


def componi(opportunita: list) -> tuple:
    """Ritorna (oggetto, corpo_html, corpo_testo)."""
    n = len(opportunita)
    migliore = max(o["margine_pct"] for o in opportunita)
    oggetto = (f"{n} occasione trovata (+{migliore:.2f}%)" if n == 1
               else f"{n} occasioni trovate (max +{migliore:.2f}%)")

    righe = "".join(_riga_html(o) for o in opportunita)
    totale = sum(o.get("profitto_garantito", 0) for o in opportunita)

    html = f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;
                max-width:640px;margin:0 auto;color:#111827">
      <h2 style="margin:0 0 4px">Monitor quote</h2>
      <p style="color:#6b7280;margin:0 0 18px;font-size:14px">
        {n} operazione{'i' if n != 1 else ''} in utile.
        Profitto garantito totale: <b>{totale:+.2f}&euro;</b>
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px">{righe}</table>
      <p style="color:#9ca3af;font-size:12px;margin-top:18px;line-height:1.5">
        Le quote si muovono in fretta: verifica che siano ancora quelle prima di
        piazzare, ed esegui <b>prima</b> il lato bookmaker, che &egrave; quello
        che sparisce per primo. Gli importi tengono conto della liquidit&agrave;
        disponibile su Betfair al momento della rilevazione.
      </p>
    </div>"""

    testo = "\n".join(
        f"+{o['margine_pct']:.2f}%  {o['evento']} - {o['esito']}\n"
        f"   punta {o.get('puntata', 0):.2f} EUR @ {o['quota_book']} su {o['bookmaker']}\n"
        f"   banca {o.get('lay_stake', 0):.2f} EUR @ {o['quota_lay']} su Betfair\n"
        f"   profitto garantito {o.get('profitto_garantito', 0):+.2f} EUR"
        for o in opportunita)

    return oggetto, html, testo


def invia(opportunita: list, destinatario: str = None) -> bool:
    """Ritorna True se la mail e' partita davvero."""
    if not opportunita:
        return False
    destinatario = destinatario or os.getenv("EMAIL_A", "")
    if not destinatario:
        print("  (nessun destinatario configurato: EMAIL_A)")
        return False

    oggetto, html, testo = componi(opportunita)

    resend = os.getenv("RESEND_API_KEY", "")
    if resend:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend}",
                     "Content-Type": "application/json"},
            json={"from": os.getenv("EMAIL_DA", "onboarding@resend.dev"),
                  "to": [destinatario], "subject": oggetto, "html": html},
            timeout=30)
        if r.status_code >= 400:
            print(f"  ! Resend HTTP {r.status_code}: {r.text[:200]}")
            return False
        print(f"  mail inviata a {destinatario} via Resend")
        return True

    host = os.getenv("SMTP_HOST", "")
    if host:
        msg = EmailMessage()
        msg["Subject"] = oggetto
        msg["From"] = os.getenv("SMTP_USER", "")
        msg["To"] = destinatario
        msg.set_content(testo)
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
            s.starttls()
            s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            s.send_message(msg)
        print(f"  mail inviata a {destinatario} via SMTP")
        return True

    print("  (nessun canale mail configurato: RESEND_API_KEY o SMTP_HOST)")
    return False

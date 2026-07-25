import { Archivo, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

// next/font ospita i file localmente al build: niente CDN, niente fallback muti.
const archivo = Archivo({
    subsets: ["latin"],
    weight: ["600", "700"],
    variable: "--font-display",
});

const plexSans = IBM_Plex_Sans({
    subsets: ["latin"],
    weight: ["400", "500", "600"],
    variable: "--font-corpo",
});

const plexMono = IBM_Plex_Mono({
    subsets: ["latin"],
    weight: ["400", "500", "600"],
    variable: "--font-dati",
});

export const metadata = {
    title: "Monitor quote — back bookmaker / lay Betfair",
    description:
        "Operazioni con profitto garantito fra bookmaker e Betfair Exchange Italia.",
};

export default function RootLayout({ children }) {
    return (
        <html lang="it">
            <body
                className={`${archivo.variable} ${plexSans.variable} ${plexMono.variable}`}
                style={{
                    fontFamily: "var(--font-corpo), system-ui, sans-serif",
                }}
            >
                {children}
            </body>
        </html>
    );
}

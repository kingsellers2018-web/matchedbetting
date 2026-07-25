@echo off
REM ---------------------------------------------------------------------------
REM  Una passata del monitor, lanciata dall'Utilita' di pianificazione.
REM
REM  Deve girare da QUI e non dal cloud: Betfair Italia risponde 403 a qualsiasi
REM  connessione che non arrivi dall'Italia (e' un operatore ADM, deve servire
REM  solo il territorio nazionale). Verificato il 25/07/2026: stesso codice e
REM  stesse credenziali, 403 da GitHub Actions e login regolare da questo PC.
REM ---------------------------------------------------------------------------

cd /d C:\matchedbetting
if not exist data mkdir data

echo. >> data\worker.log
echo ======================================================== >> data\worker.log
echo Avvio: %DATE% %TIME% >> data\worker.log

python src\worker.py --crediti 6 >> data\worker.log 2>&1

echo Uscita con codice %ERRORLEVEL% >> data\worker.log
exit /b %ERRORLEVEL%

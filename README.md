# La spesa dello Stato, anno per anno

Una pagina statica che racconta il rendiconto generale dello Stato
(2012–2025) e le leggi di bilancio 2016 e 2026: stessa cifra letta per
chi spende o per finalità (COFOG), andamento storico voce per voce.

Nessuna compilazione: HTML + CSS + JavaScript nativo, dati in JSON già
pronti in `assets/`. La grafica è [Bootstrap Italia](https://italia.github.io/bootstrap-italia/)
(servita in locale da `assets/vendor/`, nessuna dipendenza da CDN);
tipografia Titillium Web e cifre in IBM Plex Mono. Funziona anche come
sito statico su GitHub Pages senza alcun passaggio di build.

## Struttura

```
index.html                  la pagina
assets/
  style.css                 livello di personalizzazione sopra Bootstrap Italia
  app.js                    tutto il comportamento (nessuna dipendenza)
  vendor/                   Bootstrap Italia compilata (css + js), in locale
  data.json                 dati dell'ultimo anno (fallback senza ?anno=)
  data_2011…2026.json       un file per anno
scarica_dati.py             scarica i CSV dal portale OpenBDAP e ricompila
costruisci_rendiconto.py    compila i CSV in JSON (descrizioni incluse)
data/                       i CSV originali di OpenBDAP, inclusi nel repository
LICENSE                     MIT per il codice; i dati restano CC BY RGS
```

## Da dove arrivano i dati

Tutti i dati sono open data della Ragioneria generale dello Stato,
pubblicati sul portale [OpenBDAP](https://bdap-opendata.rgs.mef.gov.it/)
(licenza CC BY):

- **Rendiconto** — dataset *«Rendiconto pubblicato triennio G8 OD action
  plan Capitolo»*, uno per anno, ad esempio
  [quello del 2025](https://bdap-opendata.rgs.mef.gov.it/content/2025-rendiconto-pubblicato-triennio-g8-od-action-plan-capitolo).
  Contiene gerarchia amministrazione → missione → programma e
  ripartizione COFOG con percentuali. Disponibile dal 2012 in poi
  (manca il 2016).
- **Previsione** — dataset *«Legge di Bilancio Pubblicata Elaborabile
  Spese Capitolo»*, ad esempio
  [quello del 2026](https://bdap-opendata.rgs.mef.gov.it/content/2026-legge-di-bilancio-pubblicata-elaborabile-spese-capitolo).
  Solo amministrazione → missione → programma: la classificazione COFOG
  esiste solo nel rendiconto. Per il 2016, privo di rendiconto G8, viene
  usata questa (spesa prevista, non avvenuta).

Il portale consegna i CSV attraverso tre passaggi (pagina dataset →
form «Pagina download» → URL di export): lo script li fa tutti.

## Come si aggiorna

Un solo comando: scarica i CSV che mancano in `data/` e subito dopo
compila i JSON della pagina (`assets/data_YYYY.json` + `data.json`).

```sh
python3 scarica_dati.py             # scarica + elabora
python3 scarica_dati.py --solo 2016 # un solo anno, sempre con elaborazione
python3 scarica_dati.py --forza     # riscarica anche i file presenti
python3 scarica_dati.py --no-compila
```

Per ogni anno lo script cerca prima il rendiconto e, se non esiste
(caso 2016 e 2026), la legge di bilancio pubblicata. Un file in `data/`
con un formato incompatibile viene saltato con un avviso, senza fermare
gli altri anni.

```sh
# per guardare la pagina
python3 -m http.server 8000
# poi apri http://localhost:8000/?anno=2013
```

## Note di metodo

- **Rendiconto**: importi in impegni di competenza; **legge di
  bilancio**: stanziamenti di competenza. Il confronto 2025 → 2026 dice
  quanto è *previsto* in più, non quanto è stato speso in più. Gli anni
  di previsione sono disegnati in tratteggio.
- Lo storico segue le voci **attraverso i codici** (amministrazione,
  missione, programma, COFOG), che restano stabili anche quando i
  ministeri cambiano nome (MIT → MIMS → MIT è un'unica serie). Le voci
  assenti in un anno lasciano un vuoto, non vengono interpolate.
- Un capitolo può servire più finalità: nella vista COFOG è ripartito
  secondo le percentuali indicate dalla Ragioneria; i due alberi chiudono
  sullo stesso totale al centesimo (lo script si ferma se non torna).
- «Per abitante» compare solo per gli anni con popolazione ISTAT
  verificata in `POP_ANNI` (dentro `costruisci_rendiconto.py`): i valori
  si aggiungono lì, con fonte, man mano che si verificano.
- Le descrizioni di ministeri, missioni e gruppi COFOG sono sintesi
  redazionali di testi ufficiali (D.Lgs. 300/1999 e riordini, L. 196/2016,
  classificazione COFOG dell'ONU), agganciate ai **codici** così
  sopravvivono alle rinomine. Stanno nei dizionari `DESCR_*` del
  compilatore: lì si correggono e si estendono (i programmi e le classi
  COFOG restano senza descrizione: i loro nomi ufficiali sono già
  espliciti).

## Licenza e pubblicazione

Il codice è rilasciato sotto licenza MIT (vedi `LICENSE`); i dati restano
open data della Ragioneria generale dello Stato, licenza CC BY, e vanno
citati come indicato dal portale OpenBDAP. La grafica è costruita su
Bootstrap Italia, il design system della pubblica amministrazione
(licenza dei titolari del progetto Bootstrap Italia).

Per pubblicare: il repository è pronto per GitHub Pages — i JSON compilati
e i CSV originali sono inclusi, quindi il sito funziona appena pushato
(Settings → Pages → branch principale, cartella radice) e chi clona può
ricostruire o aggiornare i dati con `python3 scarica_dati.py --forza`.

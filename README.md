# Dove vanno i soldi

Una pagina statica con **due viste** sulla stessa domanda, che si
parlano fra loro:

- **Tutta la spesa pubblica** *(vista predefinita)* — il bilancio di
  tutte le amministrazioni pubbliche (1995–2024) in contabilità
  nazionale: Stato, Regioni, Comuni, enti di previdenza. **Due lati** —
  le uscite e le entrate — e il saldo che ne risulta, che è
  l'indebitamento netto ufficiale. Sulle uscite: a cosa serve (COFOG),
  chi le spende davvero (livello di governo, consolidato) e come si
  spende (stipendi, acquisti, pensioni, interessi, investimenti). Sulle
  entrate: da dove vengono (imposte dirette, indirette, contributi, e
  dentro a queste IRPEF, IRES, IVA, accise, IRAP).
- **Solo il bilancio dello Stato** — il rendiconto generale (2012–2025)
  e le leggi di bilancio 2011, 2016 e 2026, capitolo per capitolo: chi
  spende (ministero → missione → programma) e a cosa serve (COFOG). È il
  solo Stato centrale.

Le due viste hanno perimetri e criteri contabili diversi e non si
sommano: dove condividono una funzione COFOG, la pagina lo dice e
permette di passare dall'una all'altra sulla stessa voce e sullo stesso
anno.

Nessuna compilazione: HTML + CSS + JavaScript nativo, dati in JSON già
pronti in `assets/`. La grafica è [Bootstrap Italia](https://italia.github.io/bootstrap-italia/)
(servita in locale da `assets/vendor/`, nessuna dipendenza da CDN);
tipografia Titillium Web e cifre in IBM Plex Mono. Funziona anche come
sito statico su GitHub Pages senza alcun passaggio di build.

## Struttura

```
index.html                  la pagina, unica per le due viste
assets/
  style.css                 livello di personalizzazione sopra Bootstrap Italia
  app.js                    tutto il comportamento (nessuna dipendenza)
  vendor/                   Bootstrap Italia compilata (css + js), in locale
  data.json                 bilancio dello Stato, ultimo anno (fallback)
  data_2011…2026.json       bilancio dello Stato, un file per anno
  pa.json                   spesa pubblica, ultimo anno (fallback)
  pa_1995…2024.json         spesa pubblica, un file per anno
  ponte.json                le funzioni COFOG nelle due viste, anno per anno
scarica_dati.py             scarica i CSV da OpenBDAP e ricompila il bilancio
costruisci_rendiconto.py    compila i CSV del bilancio in JSON
scarica_eurostat.py         scarica le tabelle Eurostat e ricompila la spesa pubblica
costruisci_spesa_pa.py      compila le tabelle Eurostat in JSON
data/                       i CSV originali di OpenBDAP, inclusi nel repository
data/eurostat/              le tabelle Eurostat grezze (JSON-stat), incluse
LICENSE                     MIT per il codice; i dati restano dei titolari
```

## Indirizzi

Ogni voce ha il suo indirizzo, condivisibile:

```
?                                     spesa pubblica, uscite, ultimo anno
?anno=2010                            uscite del 2010
?anno=2024&voce=cosa-07-03            ... aperte sui servizi ospedalieri
?anno=2024&voce=origine               le entrate del 2024
?anno=2024&voce=origine-indirette-iva ... aperte sull'IVA
?vista=stato                          bilancio dello Stato, ultimo anno
?vista=stato&anno=2024&voce=cosa-07   ... aperto sulla Sanità
```

Il lato del bilancio non ha un parametro suo: lo determina la voce,
perché le chiavi di lettura di entrate e uscite sono distinte.

Il tasto «indietro» del browser risale l'albero e ripercorre gli anni. Un
anno che non esiste nella vista richiesta ricade sull'ultimo disponibile.

## Come si muove la pagina

Una decisione per fascia, in ordine di conseguenza:

1. **Entrate o uscite** — le due cifre in cima, nell'ordine in cui si fa
   la sottrazione, con il saldo come terza carta. Le prime due sono
   anche il comando: cliccarle decide che cosa si esplora sotto. Il
   controllo sta dove sta il significato.
2. **L'anno** — le colonne del bilancio: ogni colonna è la spesa
   dell'anno, la parte piena sono le entrate, il cappello vuoto è il
   disavanzo. Si vede dove si è e com'è andata, e si sceglie cliccando.
   Il menù e le frecce fanno la stessa cosa da tastiera e sul telefono.
   Cambiare anno **non ricarica la pagina** e non fa perdere il posto: se
   stavi guardando la Sanità, resti sulla Sanità.
3. **La chiave di lettura** — le schede sopra la barra. Sulle uscite: a
   cosa serve, chi spende, come si spende. Sulle entrate ce n'è una sola,
   e la barra delle schede sparisce.

Poi si apre l'albero, voce per voce. Aprendo una voce il pannello
risponde a quattro domande in fila, ciascuna con la sua etichetta: che
cosa sto guardando (nome, importo, quota, spesa per abitante), che cos'è
(la descrizione, affiancata dal ponte verso l'altra vista), andamento (il
grafico a tutta larghezza), che cosa c'è dentro (la barra a fette e
l'elenco delle voci figlie, attaccati perché sono la stessa informazione
a due risoluzioni).

Il grafico d'andamento si legge in due modi, e il commutatore sopra il
grafico passa dall'uno all'altro: **valore**, gli euro anno per anno, e
**quota %**, quanto quella voce pesa sul totale. Sono due domande
diverse. La sanità nel 1995 valeva 45,8 miliardi e nel 2024 ne vale
146,1: più che triplicata. Ma come quota della spesa pubblica è passata
dal 9,9% al 13,2%, tre punti e mezzo in trent'anni. Molte voci crescono
in euro e restano ferme, o arretrano, in quota: con il solo asse in euro
quel movimento non si vede.

Il **perimetro** — tutta la spesa pubblica oppure il solo bilancio dello
Stato — non è un bivio in cima alla pagina: è una riga sotto la testata.
Chi arriva non sa ancora che differenza c'è fra le due cose (è quello che
il sito dovrebbe spiegargli) e non va costretto a sceglierlo per primo.
Chi cerca i ministeri la trova, e dal ponte su qualunque funzione COFOG
ci si arriva comunque.

## Da dove arrivano i dati

### Il bilancio dello Stato — OpenBDAP

Open data della Ragioneria generale dello Stato, pubblicati sul portale
[OpenBDAP](https://bdap-opendata.rgs.mef.gov.it/) (licenza CC BY):

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

### Tutta la spesa pubblica — Eurostat

Contabilità nazionale SEC 2010, trasmessa dall'Istat e pubblicata da
Eurostat (riuso libero con citazione della fonte). Cinque tabelle, tutte
scaricate via API JSON-stat:

- `gov_10a_exp` — *spesa delle amministrazioni pubbliche per funzione
  (COFOG)*, in tre tagli: la spesa totale (`na_item=TE`) per settore e
  funzione; i trasferimenti fra sottosettori (`D4/D7/D9_S13xx`), che
  servono a consolidare; le undici voci della classificazione economica.
- `gov_10a_main` — *aggregati*: entrate totali e le otto voci in cui si
  scompongono, con i sottolivelli (IRPEF, IRES, IVA, accise, contributi
  di datori e lavoratori), più spesa totale e indebitamento netto.
- `gov_10dd_edpt1` — debito pubblico consolidato.
- `nama_10_gdp` — PIL a prezzi correnti, per esprimere le cifre in
  percentuale del PIL.
- `demo_gind` — popolazione media annua (fonte Istat), per la spesa per
  abitante.

## Come si aggiorna

Due comandi indipendenti, uno per vista.

```sh
python3 scarica_dati.py             # bilancio dello Stato: scarica + elabora
python3 scarica_dati.py --solo 2016 # un solo anno, sempre con elaborazione
python3 scarica_dati.py --forza     # riscarica anche i file presenti
python3 scarica_dati.py --no-compila

python3 scarica_eurostat.py         # spesa pubblica: scarica + elabora
python3 scarica_eurostat.py --forza
python3 scarica_eurostat.py --no-compila
```

Per ricompilare senza rete: `python3 costruisci_rendiconto.py data/` e
`python3 costruisci_spesa_pa.py`. Il secondo va eseguito dopo il primo
se sono cambiati i dati del bilancio, perché `assets/ponte.json` li
legge.

```sh
# per guardare la pagina
python3 -m http.server 8000
# poi apri http://localhost:8000/?vista=pa&anno=2024
```

## Note di metodo

### Il bilancio dello Stato

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
  verificata in `POP_ANNI` (dentro `costruisci_rendiconto.py`).

### Tutta la spesa pubblica

- Gli importi sono spesa totale delle amministrazioni pubbliche (settore
  S13) in **competenza economica SEC 2010**: non sono impegni né
  pagamenti di bilancio, e non comprendono il rimborso del capitale del
  debito, che nei conti nazionali è un'operazione finanziaria.
- **Il consolidamento è il punto delicato.** I tre sottosettori — Stato
  centrale (S1311), amministrazioni locali (S1313), enti di previdenza
  (S1314) — dichiarano ciascuno la propria spesa lorda: sommati farebbero
  1.478 miliardi nel 2024, 369 in più del totale, perché i trasferimenti
  fra livelli di governo sarebbero spesa due volte. Eurostat pubblica
  quei flussi voce per voce (`D4/D7/D9` «di cui verso il sottosettore
  X»), anche per funzione COFOG: sottraendoli a chi li eroga si ottiene
  la spesa netta di ciascun sottosettore, che somma **esattamente** al
  totale consolidato. `costruisci_spesa_pa.py` verifica l'identità su
  tutte le celle (30 anni × 80 codici COFOG) e si ferma se una non torna.
- I **gruppi COFOG** (secondo livello) l'Italia li trasmette dal 2001:
  per gli anni 1995–2000 l'albero si ferma alla divisione e sotto ci sono
  direttamente i livelli di governo. Niente interpolazioni.
- Eurostat pubblica in milioni di euro con un decimale: la precisione
  degli importi è di **centomila euro**. Il totale mostrato è quello che
  Eurostat pubblica come tale, non la somma delle parti arrotondate.
- **Le entrate** si scompongono in otto voci che sommate danno il totale
  al centesimo, e i sottolivelli non sfondano mai la voce che li
  contiene: verificato su tutti gli anni. Dove una voce ha un «altro» è
  un resto vero (la voce meno i fratelli noti), non una cifra inventata.
- **Il saldo** è l'indebitamento netto pubblicato da Eurostat, ed è
  esattamente entrate meno uscite: il compilatore verifica l'identità
  anno per anno e si ferma se non torna. Fra 1995 e 2025 non c'è un solo
  anno in avanzo.
- **Due tabelle, due calendari.** Gli aggregati (`gov_10a_main`) e la
  ripartizione per funzione (`gov_10a_exp`) sono pubblicati
  separatamente. Per il 2018–2022 i totali di spesa coincidono al
  milione; per l'ultimo anno o due possono differire di qualche centinaio
  di milioni, meno di un decimo di punto. La fascia del bilancio usa gli
  aggregati, perché è lì che sta il saldo ufficiale e perché così la
  sottrazione che il lettore fa a mente torna sempre; l'albero della
  spesa usa la tabella per funzione, perché è l'unica che contiene le
  funzioni. Quando lo scarto c'è, la nota di metodo lo dice con la cifra.
- Il dato arriva con circa un anno di ritardo sulla fine dell'esercizio:
  non ci sono previsioni. Gli aggregati arrivano prima della
  ripartizione per funzione, quindi il sito si ferma all'ultimo anno che
  ha entrambi.

### Il ponte fra le due viste

Divisioni e gruppi COFOG hanno lo stesso identificativo nelle due viste
(`cosa-07`, `cosa-07-03`): `assets/ponte.json` mette in fila i due
importi anno per anno, e la pagina offre il salto da una vista all'altra
sulla stessa voce. **Le due cifre non si sottraggono e nessuna è una
quota dell'altra**: misurano perimetri diversi con criteri contabili
diversi, e la pagina lo dice ogni volta che le mostra vicine.

### Le descrizioni

Ogni voce dei primi livelli ha una descrizione di tre-sei righe: che cosa
contiene, chi la finanzia o la eroga quando la distinzione conta, e un
fatto che spieghi l'ordine di grandezza o l'andamento. Dove serve, anche
che cosa **non** è compreso — è l'informazione che evita il
fraintendimento più caro, per esempio che nella spesa in contabilità
nazionale non c'è il rimborso del capitale del debito.

Alcune voci hanno testo diverso nelle due viste, perché il perimetro
cambia: il gruppo COFOG «transazioni relative al debito pubblico»
comprende l'ammortamento nel bilancio dello Stato e non lo comprende nei
conti nazionali. `costruisci_spesa_pa.py` importa il dizionario condiviso
da `costruisci_rendiconto.py` e sovrascrive i casi in cui la differenza
conta.

Le descrizioni sono sintesi redazionali di testi ufficiali
(D.Lgs. 300/1999 e riordini, L. 196/2016, classificazione COFOG delle
Nazioni Unite, regolamento SEC 2010), agganciate ai **codici** così
sopravvivono alle rinomine. Stanno nei dizionari `DESCR_*` dei due
compilatori: lì si correggono e si estendono.

## Licenza e pubblicazione

Il codice è rilasciato sotto licenza MIT (vedi `LICENSE`). I dati del
bilancio restano open data della Ragioneria generale dello Stato,
licenza CC BY, e vanno citati come indicato dal portale OpenBDAP; i dati
di contabilità nazionale sono di Eurostat (fonte da citare, riuso
libero) su trasmissione dell'Istat.

Per pubblicare: il repository è pronto per GitHub Pages — i JSON
compilati e i dati originali sono inclusi, quindi il sito funziona
appena pushato (Settings → Pages → branch principale, cartella radice) e
chi clona può ricostruire o aggiornare i dati con i due script di
scaricamento.

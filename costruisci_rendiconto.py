#!/usr/bin/env python3
"""
Costruisce i JSON della pagina a partire dai CSV del Rendiconto generale
dello Stato pubblicati da OpenBDAP (dataset "Rendiconto Pubblicato triennio
G8 OD action plan Capitolo", che contiene sia la gerarchia
amministrazione/missione/programma sia la classificazione funzionale COFOG).

    python3 costruisci_rendiconto.py data/rendiconto_2025.csv   # un solo anno
    python3 costruisci_rendiconto.py data/                      # tutti gli anni

Produce due alberi sullo stesso totale:
  - "Chi spende"   : Amministrazione -> Missione -> Programma
  - "A cosa serve" : Divisione COFOG -> Gruppo -> Classe

In modalità multi-anno scrive assets/data_YYYY.json per ciascun anno e
copia l'ultimo in assets/data.json. Ogni nodo dei primi tre livelli porta
un array `storico` allineato a meta.anni (null dove la voce non esiste):
la corrispondenza fra anni è fatta sui CODICI (amministrazione, missione,
programma, COFOG), che restano stabili anche quando i nomi cambiano.

Se in data/ c'è anche previsione_YYYY.csv (dataset "Legge di Bilancio
Pubblicata Elaborabile Spese Capitolo", scaricabile con scarica_dati.py),
quell'anno entra come previsione: solo albero per amministrazione (il
COFOG esiste solo nel rendiconto) e importi in stanziamenti di competenza
anziché impegni. Gli anni di previsione sono elencati in
meta.anni_previsione, perché la pagina li disegni in tratteggio.

Lo script si ferma se i due alberi di un anno non chiudono sullo stesso
importo.
"""

import csv, json, re, sys, os, glob, unicodedata
from collections import defaultdict

# Popolazione residente ISTAT al 1° gennaio, solo per gli anni con fonte
# verificata: aggiungere qui sotto altri anni, non altrove.
POP_ANNI = {2025: 58934177}

MISURA = os.environ.get('MISURA', 'impegnato')   # impegnato | pagato | definitivo

# ── lettura tollerante del CSV ───────────────────────────────

def apri(percorso):
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            f = open(percorso, newline='', encoding=enc)
            campione = f.read(8192)
            f.seek(0)
            sep = ';' if campione.count(';') >= campione.count(',') else ','
            return csv.DictReader(f, delimiter=sep), f
        except UnicodeDecodeError:
            continue
    raise SystemExit('Non riesco a decodificare il file.')

def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', s.lower())

def trova(intestazioni, *frammenti):
    """Cerca la colonna che contiene tutti i frammenti indicati."""
    for h in intestazioni:
        n = norm(h)
        if all(norm(f) in n for f in frammenti):
            return h
    return None

def numero(v):
    if v is None: return 0.0
    v = str(v).strip().replace('"', '')
    if not v or v in ('-', 'N.D.'): return 0.0
    if ',' in v and '.' in v:
        v = v.replace('.', '').replace(',', '.')   # 1.234.567,89
    elif ',' in v:
        v = v.replace(',', '.')
    try:
        return float(v)
    except ValueError:
        return 0.0

# ── nomi leggibili ───────────────────────────────────────────

ACC = {'A': 'à', 'E': 'è', 'I': 'ì', 'O': 'ò', 'U': 'ù'}
SIGLE = ['PNRR', 'IRAP', 'IVA', 'IRPEF', 'UE', 'ISTAT', 'COFOG', 'PA', 'ASI', 'RAI',
         'INPS', 'INAIL', 'CNR', 'ENEA', 'CIPESS', 'ANAS', 'ANAC', 'AIFA', 'SSN']
PROPRI = [('ministero delleconomia', 'Ministero dell\u2019economia'),
          ('unione europea', 'Unione europea'), ('italia', 'Italia'),
          ('presidenza del consiglio dei ministri', 'Presidenza del Consiglio dei ministri')]

def frase(s):
    s = re.sub(r'\s+', ' ', (s or '').strip())
    if not s: return ''
    s = re.sub(r"([A-Za-z]+)che'", lambda m: m.group(1) + 'ché', s, flags=re.I)
    s = re.sub(r"([AEIOUaeiou])'(?=$|[\s,;.\)\"])",
               lambda m: ACC[m.group(1).upper()].upper() if m.group(1).isupper()
               else ACC[m.group(1).upper()], s)
    low = s.lower()
    for a, b in PROPRI:
        low = re.sub(r'(?<![\w\u00C0-\u017F])' + re.escape(a) + r'(?![\w\u00C0-\u017F])', b, low)
    for g in SIGLE:
        low = re.sub(r'(?<![\w\u00C0-\u017F])' + re.escape(g.lower()) + r'(?![\w\u00C0-\u017F])',
                     g, low)
    return low[:1].upper() + low[1:]

NOTE_COFOG = {
 '01': 'Amministrazione generale, servizi fiscali, affari esteri e aiuti '
       'internazionali, ricerca di base. Comprende le transazioni sul debito '
       'pubblico — interessi e ammortamento — che ne sono di gran lunga la '
       'componente maggiore.',
 '02': 'Forze armate, missioni internazionali, difesa civile, ricerca e '
       'approvvigionamenti militari.',
 '03': 'Polizia, vigili del fuoco, tribunali e istituti penitenziari: una '
       'funzione a forte intensità di personale, la cui spesa dipende '
       'soprattutto da organici e rinnovi contrattuali.',
 '04': 'Sostegno all’economia: trasporti e infrastrutture, energia, '
       'agricoltura, industria, comunicazioni e politiche del lavoro. Vi '
       'confluisce la gran parte degli incentivi alle attività produttive.',
 '05': 'Rifiuti, acque reflue, riduzione dell’inquinamento, tutela della '
       'biodiversità e del paesaggio. Nel bilancio dello Stato è una quota '
       'piccola, perché la spesa ambientale è in prevalenza comunale.',
 '06': 'Edilizia abitativa, assetto del territorio, servizio idrico e '
       'illuminazione pubblica. Comprende i crediti d’imposta per la '
       'riqualificazione edilizia, che dal 2021 ne hanno fatto oscillare '
       'fortemente l’importo.',
 '07': 'Ospedali, farmaci, servizi sanitari. Nel bilancio dello Stato la sanità '
       'compare quasi esclusivamente come trasferimento alle Regioni, che ne '
       'curano poi l’erogazione: la cifra misura il finanziamento, non il '
       'servizio.',
 '08': 'Sport, cultura, spettacolo, editoria, servizio pubblico radiotelevisivo '
       'e servizi di culto.',
 '09': 'Scuola di ogni ordine e grado, università e diritto allo studio. Il '
       'costo del personale docente ne determina quasi interamente l’andamento.',
 '10': 'Pensioni, sostegno alle famiglie, disoccupazione, invalidità, contrasto '
       'alla povertà. Nel bilancio dello Stato la voce è più piccola di quanto '
       'ci si aspetti, perché le prestazioni sono erogate dagli enti di '
       'previdenza: qui compare il concorso statale al loro finanziamento.',
}

# Le descrizioni che seguono sono sintesi redazionali di testi ufficiali:
# le competenze dei ministeri (D.Lgs. 300/1999 e riordini successivi),
# la struttura del bilancio per missioni e programmi (L. 196/2016) e la
# classificazione COFOG delle Nazioni Unite. Sono agganciate ai codici,
# non ai nomi, per sopravvivere alle rinomine dei ministeri.

DESCR_AMMINISTRAZIONE = {
 '2': 'La cassa e il bilancio dello Stato: fiscalità e agenzie fiscali, '
      'tesoreria, gestione del debito pubblico, retribuzioni e pensioni dei '
      'dipendenti pubblici, trasferimenti a Regioni ed enti previdenziali. È di '
      'gran lunga l’amministrazione con il peso maggiore, ma non perché decida '
      'quella spesa: vi transitano risorse decise altrove, che poi altri enti '
      'erogano. Qui sta anche il servizio del debito, che da solo vale circa un '
      'terzo del bilancio.',
 '3': 'Imprese e made in Italy: incentivi agli investimenti, crediti d’imposta '
      'per beni strumentali e ricerca, politiche industriali, commercio con '
      'l’estero, tutela del consumatore e della proprietà industriale. Buona '
      'parte del sostegno alle imprese passa da qui, ma in forma di '
      'agevolazione fiscale più che di erogazione diretta.',
 '4': 'Lavoro e politiche sociali: il concorso dello Stato al finanziamento '
      'dell’INPS per pensioni e maggiorazioni sociali, gli ammortizzatori '
      'sociali, gli incentivi all’occupazione, le misure di contrasto alla '
      'povertà. Gran parte della spesa non resta qui: è trasferita agli enti '
      'previdenziali, che sono quelli che poi pagano le prestazioni.',
 '5': 'Giustizia civile e penale: magistratura ordinaria e minorile, uffici '
      'giudiziari, avvocatura dello Stato, amministrazione penitenziaria. È un '
      'ministero a fortissima intensità di personale, quindi la spesa segue '
      'organici e rinnovi contrattuali più che le riforme processuali.',
 '6': 'Affari esteri e cooperazione internazionale: rete diplomatica e '
      'consolare, contributi alle organizzazioni internazionali, aiuto pubblico '
      'allo sviluppo, promozione culturale e servizi agli italiani all’estero.',
 '7': 'Istruzione scolastica: retribuzioni del personale docente e ausiliario '
      'di ogni ordine e grado, funzionamento degli istituti, diritto allo '
      'studio, edilizia scolastica. Il costo del personale ne determina quasi '
      'interamente l’andamento, il che rende la spesa poco flessibile da un '
      'anno all’altro.',
 '8': 'Interno: Polizia di Stato, prefetture, vigili del fuoco, sistema di '
      'accoglienza e immigrazione, consultazioni elettorali, servizi '
      'demografici. Comprende anche i trasferimenti agli enti locali gestiti '
      'dal ministero.',
 '9': 'Ambiente e sicurezza energetica: politiche per il clima, aree protette e '
      'biodiversità, ciclo dei rifiuti e delle acque, dissesto idrogeologico, '
      'sicurezza degli approvvigionamenti e incentivi alle fonti rinnovabili. '
      'La spesa energetica è la componente più volatile, perché reagisce ai '
      'prezzi internazionali.',
 '10': 'Infrastrutture e trasporti: rete stradale e autostradale, ferrovie, '
       'porti e aeroporti, trasporto pubblico locale, edilizia. È il ministero '
       'con la quota maggiore di spesa in conto capitale, quindi il più esposto '
       'ai tempi di realizzazione delle opere: fra quanto è stanziato e quanto '
       'è effettivamente speso in un anno la distanza è ampia.',
 '11': 'Università e ricerca: finanziamento ordinario degli atenei, enti di '
       'ricerca come CNR, ASI e INFN, borse di studio e dottorati, programmi di '
       'ricerca nazionali ed europei. Il ministero è tornato autonomo nel 2020: '
       'negli anni precedenti questa spesa figura sotto l’istruzione, e la '
       'serie storica ne risente.',
 '12': 'Difesa: personale militare e civile, esercizio e addestramento, mezzi e '
       'infrastrutture, missioni internazionali. Le retribuzioni ne assorbono '
       'la parte prevalente; gli investimenti in sistemi d’arma sono in parte '
       'iscritti al bilancio di altri ministeri, quindi la spesa militare '
       'complessiva non coincide con questa cifra.',
 '13': 'Agricoltura, sovranità alimentare e foreste: attuazione della politica '
       'agricola comune, sviluppo rurale, pesca, controlli sulla qualità e '
       'sulla sicurezza alimentare, gestione del patrimonio forestale. Una '
       'quota rilevante delle risorse è di origine europea e transita dal '
       'bilancio nazionale.',
 '14': 'Cultura: tutela e restauro del patrimonio, musei e siti archeologici '
       'statali, archivi e biblioteche, sostegno a cinema, spettacolo dal vivo '
       'ed editoria. La spesa di funzionamento e tutela prevale nettamente su '
       'quella di investimento.',
 '15': 'Salute: il concorso dello Stato al finanziamento del Servizio sanitario '
       'nazionale, la governance farmaceutica, la prevenzione, gli istituti di '
       'ricovero e cura a carattere scientifico. La quasi totalità della spesa '
       'è trasferita alle Regioni, che gestiscono il servizio: quanto lo Stato '
       'spende direttamente per la sanità è una frazione minima di quanto la '
       'finanzia.',
 '16': 'Turismo: promozione dell’offerta turistica italiana, sostegno alle '
       'imprese del settore, organizzazione dei grandi eventi. È il ministero '
       'con il bilancio più contenuto.',
}

DESCR_MISSIONE = {
 '001': 'Gli organi costituzionali e di rilievo costituzionale: Presidenza '
        'della Repubblica, Camera, Senato, Corte costituzionale, CSM e '
        'Presidenza del Consiglio. Le dotazioni sono determinate in autonomia '
        'dagli organi stessi, entro l’importo iscritto in bilancio.',
 '002': 'Il funzionamento del Governo e delle strutture che lo supportano: '
        'dipartimenti della Presidenza del Consiglio, uffici di diretta '
        'collaborazione dei ministri, rappresentanza.',
 '003': 'I rapporti finanziari fra Stato ed enti territoriali: il concorso alla '
        'spesa sanitaria delle Regioni, le compartecipazioni al gettito '
        'erariale, i fondi perequativi e le regolazioni contabili. È la '
        'missione attraverso cui lo Stato finanzia buona parte della spesa che '
        'poi Regioni e Comuni erogano.',
 '004': 'L’Italia in Europa e nel mondo: il contributo al bilancio dell’Unione '
        'europea — che ne è di gran lunga la componente maggiore — la rete '
        'diplomatica, la cooperazione allo sviluppo e la politica economica '
        'estera.',
 '005': 'Difesa e sicurezza del territorio: forze armate, mantenimento delle '
        'capacità operative, missioni internazionali, ammodernamento di mezzi e '
        'infrastrutture.',
 '006': 'Giustizia: magistratura e uffici giudiziari, avvocatura dello Stato, '
        'amministrazione penitenziaria, giustizia minorile e di comunità, spese '
        'di funzionamento dei processi.',
 '007': 'Ordine pubblico e sicurezza: Polizia di Stato, Arma dei Carabinieri, '
        'Guardia di finanza, sistema di informazione per la sicurezza, '
        'contrasto alla criminalità organizzata.',
 '008': 'Soccorso civile: previsione e prevenzione dei rischi, Corpo nazionale '
        'dei vigili del fuoco, interventi nelle emergenze e ricostruzione post '
        'calamità. È la missione la cui spesa varia di più da un anno '
        'all’altro, perché segue gli eventi.',
 '009': 'Agricoltura, politiche agroalimentari e pesca: sostegno ai redditi e '
        'alle filiere, sviluppo rurale, controlli di qualità. Larga parte delle '
        'risorse arriva dai fondi europei della politica agricola comune.',
 '010': 'Energia e diversificazione delle fonti: sicurezza degli '
        'approvvigionamenti, incentivi alle rinnovabili, misure di contenimento '
        'dei prezzi. La spesa si è impennata nel 2022 con gli interventi contro '
        'il caro energia ed è poi rientrata.',
 '011': 'Competitività e sviluppo delle imprese: incentivi agli investimenti, '
        'crediti d’imposta, sostegno all’innovazione e alle piccole e medie '
        'imprese. Una quota rilevante è concessa per via fiscale, quindi '
        'compare come minore entrata più che come spesa.',
 '012': 'Regolazione dei mercati: le autorità e le agenzie che vigilano su '
        'concorrenza, comunicazioni, energia, trasporti e servizi pubblici '
        'locali.',
 '013': 'Diritto alla mobilità e sviluppo dei sistemi di trasporto: contributi '
        'di esercizio al trasporto pubblico locale e ferroviario, rinnovo del '
        'materiale rotabile, continuità territoriale.',
 '014': 'Infrastrutture pubbliche e logistica: rete stradale e autostradale, '
        'ferrovie, porti, aeroporti, opere di rilevanza strategica. È spesa in '
        'conto capitale, con tempi di realizzazione lunghi e scarti ampi fra '
        'stanziamento e pagamento.',
 '015': 'Comunicazioni: servizi postali, telecomunicazioni, banda ultralarga e '
        'infrastrutture digitali, compresa la compensazione per il servizio '
        'universale.',
 '016': 'Commercio internazionale e internazionalizzazione: promozione del made '
        'in Italy, sostegno all’export, assicurazione e finanziamento agevolato '
        'delle operazioni con l’estero.',
 '017': 'Ricerca e innovazione: enti pubblici di ricerca, programmi spaziali, '
        'ricerca industriale, partecipazione ai programmi quadro europei.',
 '018': 'Sviluppo sostenibile e tutela del territorio e dell’ambiente: '
        'politiche per il clima, aree protette, ciclo dei rifiuti e delle '
        'acque, difesa del suolo e dissesto idrogeologico.',
 '019': 'Casa e assetto urbanistico: edilizia residenziale pubblica, recupero '
        'del patrimonio abitativo, sostegno all’affitto, programmi di '
        'rigenerazione urbana.',
 '020': 'Tutela della salute: il finanziamento del Servizio sanitario '
        'nazionale, la spesa farmaceutica, la prevenzione, la ricerca '
        'sanitaria. La quasi totalità è trasferimento alle Regioni, non '
        'erogazione diretta.',
 '021': 'Tutela e valorizzazione dei beni culturali e paesaggistici: '
        'soprintendenze, restauri, musei e siti statali, archivi e biblioteche.',
 '022': 'Istruzione scolastica: personale docente e ausiliario, funzionamento '
        'degli istituti di ogni ordine e grado, diritto allo studio, edilizia '
        'scolastica. È dominata dal costo del personale.',
 '023': 'Istruzione universitaria e formazione post-universitaria: '
        'finanziamento ordinario degli atenei, dottorati, borse e diritto allo '
        'studio universitario.',
 '024': 'Diritti sociali, politiche sociali e famiglia: trasferimenti '
        'assistenziali, in gran parte diretti all’INPS, che poi eroga le '
        'prestazioni; sostegno alla natalità e ai servizi per l’infanzia, '
        'interventi per la non autosufficienza e il terzo settore.',
 '025': 'Politiche previdenziali: il concorso dello Stato al pagamento di '
        'pensioni e trattamenti previdenziali. Non è la spesa pensionistica '
        'complessiva, che è erogata dagli enti di previdenza: è la parte che il '
        'bilancio statale mette per coprire la differenza fra contributi '
        'incassati e prestazioni dovute.',
 '026': 'Politiche per il lavoro: ammortizzatori sociali, integrazioni '
        'salariali, incentivi all’occupazione, politiche attive e servizi per '
        'l’impiego. La spesa è ciclica e cresce nelle fasi di crisi.',
 '027': 'Immigrazione, accoglienza e garanzia dei diritti: sistema di prima e '
        'seconda accoglienza, esame delle domande di protezione, rimpatri, '
        'integrazione.',
 '028': 'Sviluppo e riequilibrio territoriale: fondi per la coesione, programmi '
        'per il Mezzogiorno, cofinanziamento nazionale dei fondi strutturali '
        'europei. La spesa segue i cicli di programmazione pluriennale, quindi '
        'si concentra in alcuni anni.',
 '029': 'Politiche economico-finanziarie e di bilancio: agenzie fiscali, '
        'riscossione, tesoreria, rapporti con il sistema finanziario. È la '
        'missione più pesante del bilancio, perché comprende le regolazioni '
        'contabili e i rimborsi d’imposta.',
 '030': 'Giovani e sport: politiche giovanili, servizio civile universale, '
        'sostegno all’attività sportiva e agli organismi del settore, '
        'impiantistica.',
 '031': 'Turismo: promozione dell’immagine turistica del paese, sostegno alle '
        'imprese del settore, grandi eventi.',
 '032': 'Servizi istituzionali e generali delle amministrazioni pubbliche: '
        'personale, sedi, spese generali di funzionamento e trattamenti di '
        'quiescenza dei dipendenti statali. È spesa trasversale, presente nel '
        'bilancio di ogni ministero.',
 '033': 'Fondi da ripartire: accantonamenti iscritti in bilancio ma non ancora '
        'assegnati a una finalità precisa, che vengono destinati in corso '
        'd’anno con provvedimenti successivi. Un importo elevato qui indica '
        'decisioni di spesa rinviate, non spesa già orientata.',
 '034': 'Debito pubblico: interessi sui titoli di Stato e rimborsi di capitale '
        'alle scadenze. È la missione più grossa del bilancio, ma i due flussi '
        'hanno natura diversa: gli interessi sono un costo, il rimborso del '
        'capitale è la restituzione di somme prese a prestito, che i conti '
        'nazionali non considerano spesa.',
}

DESCR_GRUPPO_COFOG = {
 '01.01': 'Presidenza della Repubblica, Parlamento, Governo, organi di rilievo '
          'costituzionale, amministrazione finanziaria e rete diplomatica. Vi '
          'rientrano la gestione del bilancio pubblico, la riscossione dei '
          'tributi e i rapporti con l’estero, incluse le pensioni del personale '
          'di queste amministrazioni.',
 '01.02': 'Contributi alle organizzazioni internazionali e aiuto pubblico allo '
          'sviluppo: cooperazione bilaterale e multilaterale, contributi a '
          'banche e fondi di sviluppo, interventi umanitari. Non comprende la '
          'contribuzione al bilancio dell’Unione europea, classificata fra i '
          'servizi generali.',
 '01.03': 'Servizi trasversali che non appartengono a una politica specifica: '
          'gestione del personale pubblico, sedi e patrimonio immobiliare, '
          'servizi informatici e statistici comuni, approvvigionamenti '
          'centralizzati. È spesa di funzionamento della macchina, non di '
          'erogazione di un servizio al cittadino.',
 '01.04': 'Ricerca senza un’applicazione pratica immediata, finanziata perché '
          'accresce la conoscenza disponibile: enti di ricerca nazionali, '
          'programmi spaziali, grandi infrastrutture scientifiche, quota di '
          'ricerca degli atenei non riconducibile alla didattica.',
 '01.05': 'Ricerca e sviluppo applicati al funzionamento dell’amministrazione: '
          'metodi di gestione, sistemi informativi, statistica ufficiale. Voce '
          'di importo contenuto.',
 '01.06': 'Spese di carattere generale che non trovano collocazione negli altri '
          'gruppi della divisione, comprese alcune poste di regolazione '
          'contabile. Voce residuale: un importo elevato qui è di norma il '
          'segnale di una classificazione ancora da affinare.',
 '01.07': 'Interessi e ammortamento del debito pubblico: le cedole dei titoli '
          'di Stato e i rimborsi di capitale alle scadenze. Nel bilancio dello '
          'Stato i due flussi stanno insieme, ed è la ragione per cui questa è '
          'la voce singola più pesante del rendiconto. Nei conti nazionali il '
          'rimborso del capitale non è una spesa ma un’operazione finanziaria: '
          'lì la stessa funzione vale molto meno.',
 '01.08': 'Trasferimenti a Regioni, Comuni ed enti territoriali, con in testa '
          'il finanziamento del Servizio sanitario nazionale. Nel bilancio '
          'dello Stato compaiono per intero come spesa; nei conti nazionali '
          'consolidati sono attribuiti a chi li spende davvero, quindi lì '
          'questa voce è molto più piccola e la sanità compare sotto la propria '
          'funzione.',
 '02.01': 'Le forze armate: personale militare e civile, addestramento, '
          'esercizi, mezzi e armamenti, missioni internazionali. Le '
          'retribuzioni ne assorbono la parte prevalente, molto più degli '
          'investimenti in equipaggiamento.',
 '02.02': 'Protezione della popolazione civile in caso di calamità: '
          'pianificazione, scorte, addestramento e organizzazione degli '
          'interventi. In Italia coincide in buona parte con il sistema di '
          'protezione civile, la cui spesa cresce bruscamente negli anni '
          'segnati da eventi eccezionali.',
 '02.03': 'Aiuti militari a paesi terzi e a organizzazioni internazionali: '
          'cessione di equipaggiamenti, addestramento, contributi a missioni. '
          'Voce di importo variabile, legata al quadro internazionale.',
 '02.04': 'Ricerca e sviluppo applicati alla difesa: programmi di ricerca '
          'militare, sviluppo di sistemi d’arma, tecnologie duali.',
 '02.05': 'Spese di difesa che non rientrano negli altri gruppi della '
          'divisione, comprese amministrazione e regolazione del settore. Voce '
          'residuale.',
 '03.01': 'Polizia di Stato, Arma dei Carabinieri, Guardia di finanza, polizia '
          'penitenziaria e polizie locali: personale, mezzi, sedi e '
          'addestramento. È il gruppo più pesante della divisione ed è dominato '
          'dal costo del personale.',
 '03.02': 'Il servizio antincendio e di soccorso tecnico urgente: Corpo '
          'nazionale dei vigili del fuoco, mezzi, presidi territoriali e '
          'formazione.',
 '03.03': 'Il sistema giudiziario: magistratura ordinaria, amministrativa e '
          'contabile, uffici giudiziari, avvocatura dello Stato, spese di '
          'giustizia e patrocinio a spese dello Stato. La cifra misura il costo '
          'del servizio, non la sua efficienza.',
 '03.04': 'Istituti penitenziari per adulti e minori: personale, gestione '
          'quotidiana, edilizia carceraria, misure alternative alla detenzione.',
 '03.05': 'Ricerca e sviluppo applicati alla sicurezza e alla giustizia: '
          'tecnologie investigative, sistemi informativi, medicina legale. Voce '
          'di importo marginale.',
 '03.06': 'Spese di ordine pubblico e sicurezza che non rientrano negli altri '
          'gruppi, comprese amministrazione generale e coordinamento della '
          'divisione.',
 '04.01': 'Politiche economiche di carattere generale e politiche del lavoro: '
          'incentivi all’occupazione, formazione professionale, servizi per '
          'l’impiego, regolazione del commercio e tutela della concorrenza. Vi '
          'rientrano anche gli sgravi contributivi decisi per sostenere le '
          'assunzioni.',
 '04.02': 'Agricoltura, silvicoltura, pesca e caccia: sostegno ai redditi '
          'agricoli, sviluppo rurale, bonifiche e irrigazione, gestione '
          'forestale. È finanziata in larga parte da fondi europei della '
          'politica agricola comune, che transitano dal bilancio nazionale.',
 '04.03': 'Combustibili ed energia: sostegno alla produzione e alla '
          'distribuzione, sicurezza degli approvvigionamenti, incentivi alle '
          'fonti rinnovabili, misure di calmieramento dei prezzi. È la voce che '
          'si è gonfiata nel 2022 con gli interventi contro il caro energia.',
 '04.04': 'Attività estrattive, manifatturiere ed edilizia: incentivi agli '
          'investimenti delle imprese, crediti d’imposta per beni strumentali e '
          'per la ricerca, politiche industriali e di reindustrializzazione. '
          'Comprende buona parte delle agevolazioni concesse per via fiscale.',
 '04.05': 'Trasporti di ogni modalità: rete stradale e autostradale, ferrovie, '
          'porti, aeroporti, trasporto pubblico locale. Vi rientrano sia gli '
          'investimenti infrastrutturali sia i contributi di esercizio ai '
          'gestori del servizio. È il gruppo più grosso della divisione.',
 '04.06': 'Comunicazioni: servizi postali, telecomunicazioni, banda larga e '
          'infrastrutture digitali, comprese le compensazioni per il servizio '
          'universale.',
 '04.07': 'Altri settori produttivi non classificati altrove, in particolare '
          'turismo, commercio e servizi. Comprende gli interventi di sostegno '
          'alla ricettività e alla promozione.',
 '04.08': 'Ricerca e sviluppo applicati alle attività economiche: programmi di '
          'innovazione industriale, agricola, energetica e dei trasporti, '
          'spesso cofinanziati con fondi europei.',
 '04.09': 'Spese economiche che non rientrano negli altri gruppi della '
          'divisione, comprese amministrazione e vigilanza sui settori. Voce '
          'residuale, che può accogliere interventi straordinari non ancora '
          'riclassificati.',
 '05.01': 'Raccolta, trasporto, trattamento e smaltimento dei rifiuti urbani e '
          'speciali, compresi impianti e discariche. È spesa quasi interamente '
          'comunale, finanziata in larga parte dalla tariffa sui rifiuti.',
 '05.02': 'Reti fognarie e impianti di depurazione delle acque reflue: '
          'costruzione, gestione e manutenzione. Voce a lungo sotto-finanziata '
          'in Italia, all’origine di procedure di infrazione europee.',
 '05.03': 'Riduzione dell’inquinamento di aria, acqua e suolo: monitoraggio '
          'ambientale, bonifica dei siti contaminati, contenimento delle '
          'emissioni e del rumore.',
 '05.04': 'Protezione della biodiversità e del paesaggio: parchi e aree '
          'protette, tutela di flora e fauna, difesa del suolo e del patrimonio '
          'paesaggistico.',
 '05.05': 'Ricerca e sviluppo in campo ambientale: studi su clima, ecosistemi, '
          'tecnologie di depurazione e riciclo.',
 '05.06': 'Spese ambientali che non rientrano negli altri gruppi, comprese '
          'amministrazione e regolazione della materia.',
 '06.01': 'Edilizia residenziale pubblica e sostegno all’abitazione: '
          'costruzione e manutenzione di alloggi popolari, programmi di '
          'recupero, agevolazioni all’acquisto e alla ristrutturazione. Dal '
          '2021 vi confluiscono i crediti d’imposta per la riqualificazione '
          'edilizia, che ne hanno moltiplicato l’importo per alcuni anni.',
 '06.02': 'Sviluppo e assetto del territorio: pianificazione urbanistica, opere '
          'di urbanizzazione, riqualificazione di aree urbane e programmi di '
          'rigenerazione.',
 '06.03': 'Approvvigionamento idrico a uso civile: captazione, potabilizzazione '
          'e distribuzione dell’acqua, reti e serbatoi. In larga parte spesa di '
          'enti locali e gestori pubblici del servizio.',
 '06.04': 'Illuminazione di strade e spazi pubblici: impianti, consumi ed '
          'efficientamento. Voce interamente comunale.',
 '06.05': 'Ricerca e sviluppo su abitazioni e assetto del territorio: tecniche '
          'costruttive, efficienza energetica degli edifici, pianificazione '
          'urbana.',
 '06.06': 'Spese per abitazioni e territorio che non rientrano negli altri '
          'gruppi della divisione. Voce residuale.',
 '07.01': 'Farmaci, dispositivi medici, protesi e apparecchiature sanitarie '
          'erogati agli assistiti, compresa l’assistenza farmaceutica '
          'convenzionata attraverso le farmacie. La spesa è governata da tetti '
          'programmati e da meccanismi di ripiano a carico delle aziende '
          'farmaceutiche.',
 '07.02': 'Assistenza sanitaria fuori dall’ospedale: medicina generale e '
          'pediatria di libera scelta, specialistica ambulatoriale, diagnostica '
          'e riabilitazione, sia in strutture pubbliche sia in strutture '
          'private accreditate. È il perno della sanità territoriale.',
 '07.03': 'Assistenza ospedaliera: ricoveri ordinari e day hospital, pronto '
          'soccorso, chirurgia, terapie intensive, in ospedali pubblici e case '
          'di cura accreditate. È il gruppo più pesante della sanità, ed è '
          'quasi interamente spesa delle amministrazioni locali.',
 '07.04': 'Prevenzione e sanità pubblica: vaccinazioni, screening, igiene degli '
          'alimenti e dei luoghi di lavoro, veterinaria, sorveglianza '
          'epidemiologica. È una quota storicamente piccola della spesa '
          'sanitaria, cresciuta bruscamente negli anni della pandemia.',
 '07.05': 'Ricerca e sviluppo in campo sanitario: ricerca corrente e '
          'finalizzata degli istituti di ricovero e cura a carattere '
          'scientifico, programmi dell’Istituto superiore di sanità.',
 '07.06': 'Spese sanitarie che non rientrano negli altri gruppi, comprese '
          'amministrazione e programmazione del servizio sanitario.',
 '08.01': 'Impianti sportivi, parchi e verde attrezzato, sostegno alle società '
          'e alle federazioni sportive, manifestazioni. In larga parte spesa '
          'comunale.',
 '08.02': 'Musei, biblioteche, archivi, siti archeologici e monumenti, teatro, '
          'musica e cinema: gestione, tutela, restauro e sostegno alla '
          'produzione culturale, compreso il fondo per lo spettacolo.',
 '08.03': 'Servizio pubblico radiotelevisivo ed editoria: trasferimenti al '
          'concessionario del servizio pubblico, sostegno all’editoria e alle '
          'emittenti locali. Il canone corrispondente è registrato fra le '
          'entrate tributarie.',
 '08.04': 'Servizi religiosi e altri servizi resi alla comunità: intese con le '
          'confessioni religiose, quota dell’otto per mille di competenza '
          'pubblica, servizi cimiteriali.',
 '08.05': 'Ricerca e sviluppo su cultura, sport e tempo libero. Voce di importo '
          'marginale.',
 '08.06': 'Spese culturali e ricreative che non rientrano negli altri gruppi, '
          'comprese amministrazione e regolazione del settore.',
 '09.01': 'Scuola dell’infanzia e scuola primaria: retribuzioni del personale '
          'docente e ausiliario, funzionamento degli istituti, edilizia '
          'scolastica. Il costo del personale ne determina quasi interamente '
          'l’andamento.',
 '09.02': 'Scuola secondaria di primo e secondo grado, licei, istituti tecnici '
          'e professionali: personale, funzionamento, laboratori ed edilizia. È '
          'il gruppo più grosso dell’istruzione.',
 '09.03': 'Istruzione post-secondaria non universitaria: istituti tecnici '
          'superiori, formazione terziaria professionalizzante, percorsi di '
          'specializzazione tecnica.',
 '09.04': 'Università e alta formazione: finanziamento ordinario degli atenei, '
          'diritto allo studio, borse e dottorati, edilizia universitaria. La '
          'ricerca degli atenei non riconducibile alla didattica è classificata '
          'come ricerca di base, in un’altra divisione.',
 '09.05': 'Istruzione non attribuibile a uno specifico livello: formazione '
          'professionale regionale, educazione degli adulti, apprendimento '
          'permanente.',
 '09.06': 'Servizi ausiliari all’istruzione: trasporto scolastico, mense, '
          'convitti, materiale didattico, orientamento e sostegno agli '
          'studenti. In larga parte spesa di Comuni e Regioni.',
 '09.07': 'Ricerca e sviluppo sui metodi e sulle politiche dell’istruzione: '
          'valutazione dei sistemi scolastici, sperimentazione didattica.',
 '09.08': 'Spese per l’istruzione che non rientrano negli altri gruppi, '
          'comprese amministrazione e vigilanza sul sistema scolastico.',
 '10.01': 'Prestazioni per malattia, infortunio e invalidità: pensioni di '
          'inabilità e assegni di invalidità, indennità di malattia e '
          'infortunio, provvidenze per la disabilità, assistenza domiciliare e '
          'residenziale alle persone non autosufficienti.',
 '10.02': 'Le pensioni di vecchiaia e anticipate erogate dalla previdenza '
          'obbligatoria: l’INPS per la parte prevalente, più le casse dei '
          'liberi professionisti. È la singola voce più rilevante dell’intero '
          'bilancio pubblico. Il sistema è a ripartizione: i contributi versati '
          'da chi lavora oggi pagano le pensioni di chi è già in quiescenza, '
          'quindi la spesa dipende dal rapporto fra le due popolazioni prima '
          'ancora che dalle regole di calcolo. Le riforme del 1995 e del 2011 '
          'hanno legato l’assegno ai contributi effettivamente versati e '
          'all’età di uscita, ma si applicano per quote crescenti alle pensioni '
          'nuove: gli effetti sulla spesa si distribuiscono su decenni.',
 '10.03': 'Pensioni ai superstiti, cioè le prestazioni di reversibilità e '
          'indirette riconosciute a coniugi, figli e altri familiari del '
          'titolare defunto. La spesa segue con ritardo la dinamica delle '
          'pensioni dirette e la struttura demografica.',
 '10.04': 'Sostegno alle famiglie e alla natalità: assegno unico e universale '
          'per i figli, congedi parentali, servizi per la prima infanzia, '
          'prestazioni per maternità. In Italia è una quota della protezione '
          'sociale storicamente più bassa della media europea.',
 '10.05': 'Sostegno al reddito in caso di perdita del lavoro: indennità di '
          'disoccupazione, integrazioni salariali, indennità per i lavoratori '
          'autonomi, politiche passive del lavoro. La spesa è fortemente '
          'ciclica e sale nelle fasi di recessione.',
 '10.06': 'Sostegno all’abitare per le famiglie a basso reddito: contributi '
          'all’affitto, canoni agevolati, alloggi sociali. È una voce di '
          'importo modesto nel confronto europeo, perché in Italia il sostegno '
          'alla casa passa più dalle agevolazioni fiscali, che non compaiono '
          'qui, che dalla spesa diretta.',
 '10.07': 'Contrasto alla povertà e all’esclusione sociale: misure di reddito '
          'minimo, sostegno alle persone senza dimora, interventi dei servizi '
          'sociali comunali, prestazioni assistenziali non collegate a '
          'contributi versati.',
 '10.08': 'Ricerca e sviluppo sui sistemi di protezione sociale: studi '
          'previsionali su previdenza, povertà e non autosufficienza. Voce di '
          'importo marginale.',
 '10.09': 'Prestazioni e servizi di protezione sociale che non rientrano negli '
          'altri gruppi, compresi amministrazione e funzionamento degli enti '
          'previdenziali e assistenziali.',
}

# ── costruzione dell'albero ──────────────────────────────────

def albero(righe, livelli, prefisso):
    """livelli = lista di funzioni riga -> (chiave, etichetta)."""
    radice = {'_figli': {}, '_importo': 0.0}
    for r, imp in righe:
        nodo = radice
        nodo['_importo'] += imp
        for liv in livelli:
            k, etichetta = liv(r)
            if k not in nodo['_figli']:
                nodo['_figli'][k] = {'_nome': etichetta, '_cod': k, '_figli': {}, '_importo': 0.0}
            nodo = nodo['_figli'][k]
            nodo['_importo'] += imp
    return converti(radice, prefisso)

def converti(nodo, prefisso, prof=0):
    figli = []
    for k, f in nodo['_figli'].items():
        figli.append({
            'id': prefisso + '-' + re.sub(r'[^\w]+', '', str(k))[:24],
            'nome': f['_nome'],
            'importo': int(round(f['_importo'])),
            'cod': f['_cod'],
            'figli': converti(f, prefisso + '-' + re.sub(r'[^\w]+', '', str(k))[:24], prof + 1)
        })
    figli.sort(key=lambda x: -x['importo'])
    for f in figli:
        if not f['figli']:
            f.pop('figli')
    return figli

def raggruppa_zeri(nodi, prefisso, zero_nome='Voci senza importo'):
    vivi = [n for n in nodi if n['importo'] > 0]
    zeri = [n for n in nodi if n['importo'] <= 0]
    if len(zeri) >= 3:
        vivi.append({'id': prefisso + '-zero', 'nome': zero_nome,
                     'importo': 0, 'descrizione': 'Sono %d, tutte con importo zero.' % len(zeri),
                     'figli': zeri})
    else:
        vivi += zeri
    return vivi

def pulisci(nodi, prefisso, zero_nome='Voci senza importo'):
    """Raggruppa gli zero e ordina; i codici restano, servono allo storico.
    I nodi sintetici '-zero' non si ri-raggruppano: racchiudono già tutti
    i figli a zero e verrebbero impilati all'infinito."""
    for n in nodi:
        if n.get('figli') and not n['id'].endswith('-zero'):
            n['figli'] = pulisci(raggruppa_zeri(n['figli'], n['id'], zero_nome), n['id'], zero_nome)
    return nodi

def arricchisci_descrizioni(nodi, percorso=(), sezione=None):
    """Attacca le descrizioni per codice, dove mancano. Il percorso serve
    ai gruppi COFOG, che si chiamano 'divisione.gruppo'."""
    for n in nodi:
        cod = str(n.get('cod', ''))
        chiave = None
        if sezione == 'chi' and len(percorso) == 0:
            chiave = ('amm', cod)
        elif sezione == 'chi' and len(percorso) == 1:
            chiave = ('mis', cod.zfill(3))
        elif sezione == 'cosa' and len(percorso) == 1:
            chiave = ('grp', percorso[0].zfill(2) + '.' + cod.zfill(2))
        if chiave and not n.get('descrizione'):
            if chiave[0] == 'amm':
                n['descrizione'] = DESCR_AMMINISTRAZIONE.get(chiave[1], '')
            elif chiave[0] == 'mis':
                n['descrizione'] = DESCR_MISSIONE.get(chiave[1], '')
            elif chiave[0] == 'grp':
                n['descrizione'] = DESCR_GRUPPO_COFOG.get(chiave[1], '')
        if n.get('figli'):
            arricchisci_descrizioni(n['figli'], percorso + (cod,), sezione)

# ── elaborazione di un anno ──────────────────────────────────

class FormatoIncompatibile(Exception):
    """Il file non ha le colonne attese: si salta l'anno, si fermano gli altri no."""


def norm_cod(c):
    """I codici cambiano padding fra dataset ('02' e '2'): si normalizza."""
    c = (c or '').strip()
    return str(int(c)) if c.isdigit() else c

def elabora(percorso):
    """Ritorna {'anno','chi','cosa','tot','tipo'} con i codici nei nodi."""
    lettore, f = apri(percorso)
    H = lettore.fieldnames
    if not H:
        raise SystemExit('CSV senza intestazione: %s' % percorso)

    col = {
      'amm':   trova(H, 'descrizione', 'amministrazione') or trova(H, 'amministrazione'),
      'amm_c': trova(H, 'codice', 'amministrazione'),
      'mis_c': trova(H, 'codice', 'missione'),   'mis_d': trova(H, 'descrizione', 'missione'),
      'pro_c': trova(H, 'codice', 'programma'),  'pro_d': trova(H, 'descrizione', 'programma'),
      'div_c': trova(H, 'divisione'),            'div_d': trova(H, 'descr', 'divisione'),
      'gru_c': trova(H, 'codice', 'gruppo'),     'gru_d': trova(H, 'descr', 'gruppo'),
      'cla_c': trova(H, 'codice', 'classe'),     'cla_d': trova(H, 'descr', 'classe'),
      'perc':  trova(H, 'percentuale', 'cofog'),
      'cap':   trova(H, 'numero', 'capitolo'),
      'azi':   trova(H, 'codice', 'azione'),
      'imp':   trova(H, 'impegnato'),
      'pag':   trova(H, 'totale', 'pagato', 'cp'),
      'def':   trova(H, 'stanziamento', 'definitivo', 'cp'),
    }
    mancanti = [k for k in ('amm', 'mis_d', 'pro_d', 'div_d') if not col[k]]
    if mancanti:
        raise FormatoIncompatibile(
            'colonne non riconosciute (%s).' % ', '.join(mancanti))

    campo = {'impegnato': col['imp'], 'pagato': col['pag'], 'definitivo': col['def']}[MISURA]
    if not campo:
        raise FormatoIncompatibile('la misura "%s" non è presente nel file.' % MISURA)

    righe = list(lettore)
    f.close()
    print('%s: %d righe — misura %s' % (os.path.basename(percorso), len(righe), MISURA))

    # L'anno lo prende dai dati, non dal nome del file: il Rendiconto 2025 e'
    # approvato nel 2026, ed e' un errore facile scrivere l'anno sbagliato in pagina.
    col_es = trova(H, 'esercizio')
    anni = {}
    if col_es:
        for r in righe:
            a = (r.get(col_es) or '').strip()
            if a: anni[a] = anni.get(a, 0) + 1
    if not anni:
        raise SystemExit('Non trovo la colonna "Esercizio Finanziario": '
                         'senza l\'anno non posso intitolare la pagina.')
    ANNO = max(anni, key=anni.get)
    if len(anni) > 1:
        print('  ATTENZIONE: il file contiene piu\' esercizi %s. Uso %s e scarto il resto.'
              % (sorted(anni), ANNO))
        righe = [r for r in righe if (r.get(col_es) or '').strip() == ANNO]

    # Un capitolo può essere ripartito su più classi COFOG. Bisogna capire se
    # l'importo è ripetuto su ogni riga o già suddiviso, altrimenti si conta due volte.
    # La chiave deve identificare il capitolo *dentro* la sua gerarchia: i numeri
    # di capitolo e le azioni ripartono da zero in ogni amministrazione.
    def chiave_capitolo(r):
        return (r.get(col['amm'], ''), r.get(col['mis_c'], ''), r.get(col['pro_c'], ''),
                r.get(col['cap'], ''), r.get(col['azi'], ''))
    gruppi = defaultdict(list)
    for r in righe:
        gruppi[chiave_capitolo(r)].append(r)
    multipli = [g for g in gruppi.values() if len(g) > 1]
    ripetuto = False
    if multipli:
        uguali = sum(1 for g in multipli[:500]
                     if len({round(numero(r[campo]), 2) for r in g}) == 1
                     and round(numero(g[0][campo]), 2) != 0)
        ripetuto = uguali > len(multipli[:500]) * 0.5

    def quota(r):
        p = numero(r[col['perc']]) if col['perc'] else 100.0
        return p / 100.0 if (ripetuto and p) else 1.0

    righe_amm, righe_cof = [], []
    for chiave, g in gruppi.items():
        base = g[0]
        tot = numero(base[campo]) if ripetuto else sum(numero(r[campo]) for r in g)
        righe_amm.append((base, tot))
    for r in righe:
        righe_cof.append((r, numero(r[campo]) * quota(r)))

    tot_amm = sum(i for _, i in righe_amm)
    tot_cof = sum(i for _, i in righe_cof)
    print('  totale amministrazioni %15.2f — totale COFOG %15.2f' % (tot_amm, tot_cof))
    scarto = abs(tot_amm - tot_cof)
    if scarto > max(1.0, tot_amm * 1e-6):
        raise SystemExit('I due alberi non chiudono (scarto %.2f). Controlla le colonne.' % scarto)

    def etichetta(r, cc, cd):
        c = (r.get(cc) or '').strip() if cc else ''
        d = frase(r.get(cd) or '')
        return (c or d, d or c)

    def etichetta_cod(r, cc, cd):
        c = norm_cod(r.get(cc) or '') if cc else ''
        d = frase(r.get(cd) or '')
        return (c or d, d or c)

    chi = albero(righe_amm, [
        lambda r: etichetta_cod(r, col['amm_c'], col['amm']),
        lambda r: etichetta_cod(r, col['mis_c'], col['mis_d']),
        lambda r: etichetta_cod(r, col['pro_c'], col['pro_d']),
    ], 'chi')

    cosa = albero(righe_cof, [
        lambda r: etichetta(r, col['div_c'], col['div_d']),
        lambda r: etichetta(r, col['gru_c'], col['gru_d']),
        lambda r: etichetta(r, col['cla_c'], col['cla_d']),
    ], 'cosa')

    for n in cosa:
        cod = str(n.get('cod', '')).zfill(2)[:2]
        if cod in NOTE_COFOG:
            n['descrizione'] = NOTE_COFOG[cod]

    chi = pulisci(raggruppa_zeri(chi, 'chi', 'Capitoli senza impegni'), 'chi',
                  'Capitoli senza impegni')
    cosa = pulisci(raggruppa_zeri(cosa, 'cosa', 'Capitoli senza impegni'), 'cosa',
                   'Capitoli senza impegni')
    arricchisci_descrizioni(chi, sezione='chi')
    arricchisci_descrizioni(cosa, sezione='cosa')

    return {'anno': int(ANNO), 'chi': chi, 'cosa': cosa, 'tot': tot_amm,
            'tipo': 'rendiconto'}


def elabora_previsione(percorso):
    """Anno di previsione (legge di bilancio): solo albero per amministrazione,
    importi in stanziamenti di competenza. Niente COFOG."""
    lettore, f = apri(percorso)
    H = lettore.fieldnames
    if not H:
        raise SystemExit('CSV senza intestazione: %s' % percorso)

    col = {
      'stp':  trova(H, 'stato', 'previsione'),
      'amm':  next((h for h in H if h == 'Amministrazione'), None),
      'mis_c': trova(H, 'codice', 'missione'), 'mis_d': next((h for h in H if h == 'Missione'), None),
      'pro_c': trova(H, 'codice', 'programma'), 'pro_d': next((h for h in H if h == 'Programma'), None),
      'imp':  trova(H, 'legge', 'bilancio', 'cp'),
    }
    mancanti = [k for k in ('stp', 'amm', 'mis_c', 'mis_d', 'pro_c', 'pro_d', 'imp') if not col[k]]
    if mancanti:
        raise FormatoIncompatibile(
            'colonne non riconosciute (%s).' % ', '.join(mancanti))

    righe = list(lettore)
    f.close()
    col_es = trova(H, 'esercizio')
    anni = {}
    for r in righe:
        a = (r.get(col_es) or '').strip() if col_es else ''
        if a: anni[a] = anni.get(a, 0) + 1
    if not anni:
        raise SystemExit('Non trovo l\'esercizio in %s.' % percorso)
    ANNO = max(anni, key=anni.get)
    if len(anni) > 1:
        righe = [r for r in righe if ((r.get(col_es) or '').strip() == ANNO)]
    print('%s: %d righe — legge di bilancio, competenza' % (os.path.basename(percorso), len(righe)))

    def etichetta_cod(r, cc, cd):
        c = norm_cod(r.get(cc) or '') if cc else ''
        d = frase(r.get(cd) or '')
        return (c or d, d or c)

    righe_amm = [(r, numero(r[col['imp']])) for r in righe]
    tot = sum(i for _, i in righe_amm)
    print('  totale stanziamenti di competenza %15.2f' % tot)

    chi = albero(righe_amm, [
        lambda r: etichetta_cod(r, col['stp'], col['amm']),
        lambda r: etichetta_cod(r, col['mis_c'], col['mis_d']),
        lambda r: etichetta_cod(r, col['pro_c'], col['pro_d']),
    ], 'chi')
    chi = pulisci(raggruppa_zeri(chi, 'chi', 'Capitoli senza stanziamenti'), 'chi',
                  'Capitoli senza stanziamenti')
    arricchisci_descrizioni(chi, sezione='chi')

    return {'anno': int(ANNO), 'chi': chi, 'cosa': [], 'tot': tot,
            'tipo': 'previsione'}

# ── storico: corrispondenza fra anni sui codici ──────────────

PROFONDITA_STORICO = 3   # amministrazione/missione/programma e COFOG L1/L2/L3

def raccogli(nodi, prefisso, anno, stor, prof):
    for n in nodi:
        if n['id'].endswith('-zero'):
            continue
        k = prefisso + '/' + str(n.get('cod', ''))
        if prof <= PROFONDITA_STORICO:
            stor.setdefault(k, {})[anno] = n['importo']
        raccogli(n.get('figli') or [], k, anno, stor, prof + 1)

def timbra(nodi, prefisso, stor, anni, prof):
    for n in nodi:
        if not n['id'].endswith('-zero'):
            k = prefisso + '/' + str(n.get('cod', ''))
            serie = stor.get(k)
            if serie:
                n['storico'] = [serie.get(a) for a in anni]
            timbra(n.get('figli') or [], k, stor, anni, prof + 1)

def spoglia(nodi):
    """Toglie i codici: servivano solo per costruire lo storico."""
    for n in nodi:
        n.pop('cod', None)
        if n.get('figli'):
            spoglia(n['figli'])
    return nodi

# ── impaginazione e scrittura ────────────────────────────────

AVVISO = ('Il perimetro è il solo Stato centrale, non la spesa pubblica italiana: '
          'la sanità erogata dalle Regioni, i servizi dei Comuni e le prestazioni '
          'di INPS e INAIL restano in gran parte fuori.')

def impagina(el, anni, totali, anni_previsione):
    ANNO = el['anno']
    TOT = int(round(el['tot']))
    previsione = el['tipo'] == 'previsione'
    nome_misura = ('stanziamenti di competenza' if previsione else
                   {'impegnato': 'impegni', 'pagato': 'pagamenti',
                    'definitivo': 'stanziamenti definitivi'}[MISURA])
    if previsione:
        titolo = 'La spesa prevista dello Stato nel %s' % ANNO
        titolo_display = {'prima': 'La spesa', 'corsivo': 'dello Stato',
                          'dopo': 'prevista nel %s' % ANNO}
        sottotitolo = ('Quanto lo Stato è autorizzato a spendere nel %s: '
                       'stanziamenti di competenza, cioè autorizzazioni, non '
                       'impegni né pagamenti. Il confronto con la spesa impegnata '
                       'degli anni precedenti è possibile voce per voce, ma mette a '
                       'fianco due misure diverse.' % ANNO)
        apertura = ('Non è spesa e non è ancora un impegno: è quanto la legge di '
                    'bilancio autorizza a spendere nel %s. Diventa impegno quando '
                    'l\u2019amministrazione assume l\u2019obbligazione, e pagamento quando '
                    'il denaro esce effettivamente. ' % ANNO) + AVVISO
        fonte_nome = ("Legge di bilancio per l'anno %s, dati aperti della Ragioneria "
                      'generale dello Stato (OpenBDAP), licenza CC BY.' % ANNO)
        nota_metodo = ('Gli importi del %s sono stanziamenti di competenza della '
                       'legge di bilancio, cioè autorizzazioni di spesa. Negli anni '
                       'precedenti la spesa è misurata dagli impegni del rendiconto, '
                       'che sono obbligazioni già assunte: il confronto indica '
                       'quanto è autorizzato in più o in meno, non quanto si è speso '
                       'in più. La classificazione per finalità (COFOG) esiste solo '
                       'nel rendiconto e per il %s non è quindi disponibile.'
                       % (ANNO, ANNO))
        come_leggere = ('Gli importi sono stanziamenti: autorizzazioni di spesa, '
                        'non impegni né pagamenti. Se una voce indica 12%, prende il '
                        '12% della voce che la contiene al livello superiore, non '
                        'della spesa totale.')
    else:
        titolo = 'La spesa dello Stato nel %s' % ANNO
        titolo_display = {'prima': 'La spesa', 'corsivo': 'dello Stato', 'dopo': 'nel %s' % ANNO}
        if MISURA == 'impegnato':
            sottotitolo = ('Quanto lo Stato italiano ha impegnato nel %s: '
                           'obbligazioni di spesa assunte nell\u2019anno, non '
                           'pagamenti. La stessa cifra si può leggere per '
                           'amministrazione o per finalità.' % ANNO)
            testo_misura = ('Gli importi sono impegni di competenza dell\'esercizio '
                            '%s: obbligazioni assunte dall\'amministrazione '
                            'nell\'anno. Non sono previsioni e non sono pagamenti, '
                            'che seguono la gestione di cassa e altri tempi.' % ANNO)
            come_leggere = ('Gli importi sono impegni: obbligazioni assunte, non '
                            'pagamenti. Le percentuali sono riferite alla voce che '
                            'contiene, non al totale generale: 12% significa il 12% '
                            'del livello superiore.')
        else:
            # MISURA=pagato|definitivo: cambia la natura dei numeri,
            # e le formule sopra non varrebbero
            sottotitolo = ('Quanto lo Stato italiano ha messo in spesa nel %s, '
                           'in %s. Puoi leggere la stessa cifra per '
                           'amministrazione o per finalità.' % (ANNO, nome_misura))
            testo_misura = ('Gli importi sono %s di competenza dell\'esercizio %s.'
                            % (nome_misura, ANNO))
            come_leggere = ('Gli importi sono %s. Se una voce indica 12%, prende il '
                            '12% della voce che la contiene al livello superiore, '
                            'non della spesa totale.' % nome_misura)
        apertura = ('È il consuntivo in competenza, chiuso a fine %s e giudicato '
                    'dalla Corte dei conti l\u2019anno successivo. Scegli una voce e '
                    'la barra si ridisegna su quella, scomponendola nelle sue '
                    'parti. ' % ANNO) + AVVISO
        fonte_nome = ('Rendiconto generale dello Stato per l\'esercizio finanziario %s, '
                      'dati aperti della Ragioneria generale dello Stato (OpenBDAP), '
                      'licenza CC BY.' % ANNO)
        nota_metodo = (testo_misura + ' Un capitolo può servire più finalità: '
                       'nella vista per finalità è ripartito secondo le percentuali '
                       'COFOG indicate dalla Ragioneria, e i due totali coincidono '
                       'al centesimo. Gli andamenti storici seguono le voci '
                       'attraverso i codici, non attraverso i nomi: se un ministero '
                       'cambia denominazione la sua storia continua, e le voci '
                       'assenti in un anno lasciano un vuoto invece di una stima.')

    sezioni = [
        {'id': 'chi', 'nome': 'Chi spende', 'etichetta': 'Chi spende',
         'titolo': 'La spesa %s per amministrazione' % ANNO, 'importo': TOT,
         'descrizione': 'La stessa cifra ripartita per amministrazione titolare: '
                        'ogni ministero, le sue missioni, i loro programmi. '
                        'Gestire non equivale a decidere: dal Ministero '
                        'dell\u2019economia transita anche spesa decisa altrove. Per '
                        'la destinazione dei fondi si veda «A cosa serve».'
                        + (' Per il %s non è disponibile: la classificazione per '
                           'finalità esiste solo nel rendiconto.'
                           % ANNO if previsione else ''),
         'figli': el['chi']},
    ]
    if el['cosa']:
        sezioni.append(
            {'id': 'cosa', 'nome': 'A cosa serve', 'etichetta': 'A cosa serve',
             'titolo': 'La spesa %s per finalità' % ANNO, 'importo': TOT,
             'descrizione': 'La stessa spesa raggruppata per scopo con la '
                            'classificazione COFOG delle Nazioni Unite, '
                            'indipendentemente dall\u2019amministrazione titolare: '
                            'sotto «Difesa» confluisce tutto ciò che serve a '
                            'difendere il paese, da qualunque ministero transiti.',
             'figli': el['cosa']})

    return {
      'meta': {
        'ente': 'Rendiconto generale dello Stato' if not previsione
                else 'Legge di bilancio dello Stato',
        'titolo': titolo,
        'titolo_display': titolo_display,
        'anno': ANNO,
        'anni': anni,
        'totale_storico': totali,
        'anni_previsione': anni_previsione,
        'sottotitolo': sottotitolo,
        'apertura': apertura,
        'popolazione': POP_ANNI.get(ANNO),
        'come_leggere': come_leggere,
        'fonte_nome': fonte_nome,
        'fonte_url': ('https://bdap-opendata.rgs.mef.gov.it/content/'
                      '%d-legge-di-bilancio-pubblicata-elaborabile-spese-capitolo' % ANNO
                      if previsione else
                      'https://bdap-opendata.rgs.mef.gov.it/content/'
                      '%d-rendiconto-pubblicato-triennio-g8-od-action-plan-capitolo' % ANNO),
        'nota_metodo': nota_metodo,
        'portale': {'nome': 'OpenBDAP',
                    'url': 'https://bdap-opendata.rgs.mef.gov.it/'},
        'fonte_link_testo': 'Apri il dataset sul portale OpenBDAP',
        'descrizioni': ('Le descrizioni delle voci sono sintesi redazionali di '
                        'testi ufficiali: le competenze dei ministeri '
                        '(D.Lgs. 300/1999 e riordini successivi), la struttura '
                        'del bilancio per missioni e programmi (L. 196/2016) e '
                        'la classificazione COFOG delle Nazioni Unite.'),
        'vista_nota': ('Il perimetro è il solo Stato centrale, ma con il dettaglio '
                       'per capitolo: ministeri, missioni, programmi. Rendiconto e '
                       'legge di bilancio dal %d al %d, dati della Ragioneria '
                       'generale dello Stato.' % (anni[0], anni[-1])),
      },
      'sezioni': sezioni,
    }

def scrivi(dati, destinazione):
    json.dump(dati, open(destinazione, 'w'), ensure_ascii=False, separators=(',', ':'))
    print('  scritto %s (%.0f KB)' % (destinazione, os.path.getsize(destinazione) / 1e3))

# ── main ─────────────────────────────────────────────────────

def main():
    qui = os.path.dirname(os.path.abspath(__file__))
    assets = os.path.join(qui, 'assets')

    percorsi = []
    if len(sys.argv) >= 2 and os.path.isdir(sys.argv[1]):
        percorsi = sorted(glob.glob(os.path.join(sys.argv[1], 'rendiconto_*.csv'))) + \
                   sorted(glob.glob(os.path.join(sys.argv[1], 'previsione_*.csv')))
    elif len(sys.argv) >= 2:
        percorsi = [sys.argv[1]]
    else:
        percorsi = sorted(glob.glob(os.path.join(qui, 'data', 'rendiconto_*.csv'))) + \
                   sorted(glob.glob(os.path.join(qui, 'data', 'previsione_*.csv')))
    if not percorsi:
        raise SystemExit('Uso: python3 costruisci_rendiconto.py <file.csv | cartella data/>')

    elaborati = {}
    for p in percorsi:
        try:
            el = elabora_previsione(p) if 'previsione' in os.path.basename(p) else elabora(p)
        except FormatoIncompatibile as e:
            # un file di un'altra famiglia (es. "elaborabile" 2016, senza COFOG
            # e senza impegni) non deve fermare gli altri anni
            print('  SALTO %s: %s' % (os.path.basename(p), e))
            continue
        if el['anno'] in elaborati:
            raise SystemExit('Anno %d presente due volte.' % el['anno'])
        elaborati[el['anno']] = el

    if not elaborati:
        raise SystemExit('Nessun file elaborabile trovato in %s.' % ' '.join(percorsi))

    anni = sorted(elaborati)
    totali = [int(round(elaborati[a]['tot'])) for a in anni]
    anni_previsione = [a for a in anni if elaborati[a]['tipo'] == 'previsione']
    stor_chi, stor_cosa = {}, {}
    for a in anni:
        raccogli(elaborati[a]['chi'], '', a, stor_chi, 1)
        raccogli(elaborati[a]['cosa'], '', a, stor_cosa, 1)

    for a in anni:
        el = elaborati[a]
        timbra(el['chi'], '', stor_chi, anni, 1)
        timbra(el['cosa'], '', stor_cosa, anni, 1)
        spoglia(el['chi']); spoglia(el['cosa'])
        dati = impagina(el, anni, totali, anni_previsione)
        scrivi(dati, os.path.join(assets, 'data_%d.json' % a))

    # l'ultimo anno resta anche come data.json, per compatibilità
    ultimo = impagina(elaborati[anni[-1]], anni, totali, anni_previsione)
    scrivi(ultimo, os.path.join(assets, 'data.json'))

    print()
    print('Anni: %s' % ', '.join(
        str(a) + (' (previsione)' if a in anni_previsione else '') for a in anni))
    for a in anni:
        print('  %d  totale %s' % (a, format(int(round(elaborati[a]['tot'])), ',d').replace(',', '.')))
    for nome, stor in (('chi', stor_chi), ('cosa', stor_cosa)):
        piene = sum(1 for s in stor.values() if sum(1 for v in s.values() if v) >= 2)
        print('Voci "%s" con storia di almeno 2 anni: %d su %d' % (nome, piene, len(stor)))


if __name__ == '__main__':
    main()

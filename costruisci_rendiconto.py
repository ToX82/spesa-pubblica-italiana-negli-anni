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
 '01': 'Amministrazione generale, affari esteri, aiuti internazionali e — voce di gran lunga più pesante — le transazioni sul debito pubblico: interessi e ammortamento, cioè i rimborsi di capitale.',
 '02': 'Forze armate, missioni internazionali, ricerca militare.',
 '03': 'Polizia, vigili del fuoco, tribunali, carceri.',
 '04': 'Sostegno all\u2019economia: trasporti, energia, agricoltura, industria, comunicazioni, lavoro.',
 '05': 'Rifiuti, acque reflue, tutela della biodiversità, lotta all\u2019inquinamento.',
 '06': 'Edilizia abitativa, servizi idrici, illuminazione e sviluppo urbano.',
 '07': 'Ospedali, farmaci, servizi sanitari. Nel bilancio dello Stato compare soprattutto come trasferimento alle regioni, che gestiscono il Servizio sanitario nazionale.',
 '08': 'Sport, cultura, servizi ricreativi, editoria, culto.',
 '09': 'Scuola di ogni grado, università, diritto allo studio.',
 '10': 'Pensioni, sostegno a famiglie, disoccupazione, disabilità, esclusione sociale.',
}

# Le descrizioni che seguono sono sintesi redazionali di testi ufficiali:
# le competenze dei ministeri (D.Lgs. 300/1999 e riordini successivi),
# la struttura del bilancio per missioni e programmi (L. 196/2016) e la
# classificazione COFOG delle Nazioni Unite. Sono agganciate ai codici,
# non ai nomi, per sopravvivere alle rinomine dei ministeri.

DESCR_AMMINISTRAZIONE = {
 '2':  'La cassa e il bilancio dello Stato: fiscalità, tesoreria, debito pubblico, '
       'stipendi e pensioni dei dipendenti pubblici. Passa da qui gran parte della '
       'spesa, anche quella decisa altrove.',
 '3':  'Imprese, industria e made in Italy: incentivi alle imprese, commercio con '
       'l\u2019estero, tutela del consumatore e politiche del commercio.',
 '4':  'Welfare e lavoro: i trasferimenti a INPS per pensioni e maggiorazioni sociali, '
       'il sostegno al reddito e le politiche attive del lavoro.',
 '5':  'La giustizia civile e penale: magistratura, avvocatura dello Stato, '
       'carceri e cancellerie.',
 '6':  'La rappresentanza dell\u2019Italia nel mondo: rete diplomatica e consolare, '
       'cooperazione allo sviluppo, italiani all\u2019estero.',
 '7':  'La scuola di ogni ordine e grado: stipendi dei docenti, edilizia scolastica, '
       'diritto allo studio.',
 '8':  'Sicurezza e territorio: polizie di Stato, prefetture, vigili del fuoco, '
       'elezioni, cittadinanza e immigrazione.',
 '9':  'Ambiente e sicurezza energetica: clima, aree protette, rifiuti, risorse '
       'idriche e approvvigionamenti energetici.',
 '10': 'Opere pubbliche e trasporti: strade, ferrovie, porti, aeroporti e navigazione '
       'interna.',
 '11': 'Università e ricerca scientifica: atenei, enti di ricerca (CNR, ASI, INFN), '
       'borse di studio e dottorati. Il ministero è tornato autonomo nel 2021: prima '
       'questa spesa stava nell\u2019istruzione.',
 '12': 'Le forze armate: personale, missioni internazionali, mezzi e infrastrutture '
       'militari.',
 '13': 'Agricoltura, sovranità alimentare e foreste: la politica agricola comune, '
       'la pesca e le filiere agroalimentari.',
 '14': 'Beni culturali e spettacolo: musei statali, tutela e restauro, cinema, '
       'teatro ed editoria.',
 '15': 'Il finanziamento del Servizio sanitario nazionale: trasferimenti alle regioni, '
       'farmaci, veterinaria e profilassi.',
 '16': 'La promozione del turismo italiano e dei grandi eventi collegati.',
}

DESCR_MISSIONE = {
 '001': 'Il costo della testa dello Stato: Quirinale, Parlamento, Corte costituzionale, '
        'CSM e Presidenza del Consiglio.',
 '002': 'Il funzionamento del Governo e delle sue strutture di supporto e di '
        'rappresentanza.',
 '003': 'Come lo Stato finanzia Regioni ed enti locali: il concorso alla spesa sanitaria, '
        'le compartecipazioni fiscali e le altre regolazioni contabili.',
 '004': 'L\u2019Italia in Europa e nel mondo: il contributo al bilancio dell\u2019Unione '
        'europea (la parte più grossa), gli aiuti internazionali, la politica economica estera.',
 '005': 'Difesa e sicurezza del territorio: forze armate, missioni e capacità militari.',
 '006': 'Giustizia: magistratura, avvocatura dello Stato, carceri e giustizia minorile.',
 '007': 'Ordine pubblico: polizie di Stato, guardia di finanza e sicurezza democratica.',
 '008': 'Soccorso civile: previsione e prevenzione dei rischi, vigili del fuoco, '
        'interventi nelle emergenze e ricostruzione.',
 '009': 'Agricoltura e pesca: sostegno alle imprese e alle filiere, in larga parte con '
        'fondi europei della PAC.',
 '010': 'Energia: fonti, diversificazione degli approvvigionamenti e transizione.',
 '011': 'Sostegno alle imprese e alla competitività, in gran parte per via fiscale.',
 '012': 'Regolazione dei mercati: le agenzie e le autorità che vigilano su concorrenza, '
        'comunicazioni, energia e altri settori.',
 '013': 'Trasporto pubblico e diritto alla mobilità: contributi a regioni e comuni.',
 '014': 'Infrastrutture e logistica: grandi opere, strade, ferrovie, porti e aeroporti.',
 '015': 'Comunicazioni: posta, telecomunicazioni e banda ultralarga.',
 '016': 'Commercio internazionale: promozione del made in Italy all\u2019estero e '
        'internazionalizzazione delle imprese.',
 '017': 'Ricerca scientifica e tecnologica: enti di ricerca, spazio e programmi di '
        'innovazione.',
 '018': 'Ambiente e territorio: sviluppo sostenibile, clima, aree protette e dissesto '
        'idrogeologico.',
 '019': 'Casa: edilizia residenziale pubblica, recupero del patrimonio e sostegno '
        'all\u2019abitare.',
 '020': 'Salute: il finanziamento del Servizio sanitario nazionale e i farmaci.',
 '021': 'Beni culturali: tutela, restauro e fruizione di musei, siti e paesaggio.',
 '022': 'Istruzione scolastica: scuole, docenti e diritto allo studio.',
 '023': 'Università: atenei, dottorati e formazione superiore.',
 '024': 'Diritti sociali e famiglia: trasferimenti assistenziali (verso INPS, in gran '
        'parte), inclusione, disabilità e terzo settore.',
 '025': 'Previdenza: il concorso dello Stato al pagamento di pensioni e trattamenti '
        'previdenziali.',
 '026': 'Politiche del lavoro: ammortizzatori sociali, incentivi all\u2019occupazione, '
        'contrasto al lavoro nero.',
 '027': 'Immigrazione: accoglienza, richiedenti asilo, integrazione e garanzia dei diritti.',
 '028': 'Coesione: sviluppo del Mezzogiorno e riequilibrio territoriale, con fondi '
        'nazionali ed europei.',
 '029': 'La gestione del bilancio e delle entrate: agenzie fiscali, tesoreria e — la '
        'parte più pesante — restituzioni e rimborsi d\u2019imposta.',
 '030': 'Giovani e sport: politiche giovanili e sostegno allo sport, CONI in testa.',
 '031': 'Turismo: promozione del turismo e dei grandi eventi.',
 '032': 'Il funzionamento delle amministrazioni: personale, sedi, spese generali e '
        'trattamenti di quiescenza dei dipendenti statali.',
 '033': 'Fondi da ripartire: accantonamenti non ancora assegnati, che si destinano '
        'durante l\u2019anno.',
 '034': 'Debito pubblico: gli interessi e i rimborsi di capitale del debito accumulato. '
        'È la missione più grossa del bilancio.',
}

DESCR_GRUPPO_COFOG = {
 '01.01': 'Presidenza, Parlamento e gestione della finanza pubblica, incluse le pensioni dei dipendenti statali.',
 '01.02': 'Contributi alle organizzazioni internazionali e aiuti ai paesi in sviluppo.',
 '01.03': 'Personale, sedi e servizi amministrativi trasversali.',
 '01.04': 'Ricerca di base, senza applicazione immediata.',
 '01.05': 'Ricerca e sviluppo per i servizi pubblici generali.',
 '01.06': 'Spese generali non riconducibili ad alcun altro gruppo.',
 '01.07': 'La voce più grossa dell\u2019intera spesa: interessi e ammortamento del debito.',
 '01.08': 'Trasferimenti a Regioni, Comuni ed enti territoriali: in testa il finanziamento della sanità.',
 '02.01': 'Le forze armate e le loro operazioni.',
 '02.02': 'Protezione della popolazione: in Italia, la protezione civile.',
 '02.03': 'Aiuti militari ad altri paesi.',
 '02.04': 'Ricerca e sviluppo per la difesa.',
 '02.05': 'Spese di difesa non riconducibili ad altro.',
 '03.01': 'Le polizie.',
 '03.02': 'I vigili del fuoco.',
 '03.03': 'I tribunali.',
 '03.04': 'Le carceri.',
 '03.06': 'Spese di ordine pubblico non riconducibili ad altro.',
 '04.01': 'Politiche economiche generali, commercio e lavoro.',
 '04.02': 'Agricoltura, foreste, pesca e caccia.',
 '04.03': 'Combustibili ed energia.',
 '04.04': 'Attività estrattive, manifatturiere ed edilizia.',
 '04.05': 'Trasporti di ogni tipo.',
 '04.06': 'Comunicazioni: posta e telecomunicazioni.',
 '04.07': 'Sostegno ad altri settori produttivi, turismo incluso.',
 '04.08': 'Ricerca e sviluppo per l\u2019economia.',
 '04.09': 'Spese economiche non riconducibili ad altro.',
 '05.01': 'Trattamento dei rifiuti.',
 '05.02': 'Trattamento delle acque reflue.',
 '05.03': 'Riduzione dell\u2019inquinamento.',
 '05.04': 'Protezione della biodiversità e del paesaggio.',
 '05.05': 'Ricerca e sviluppo per l\u2019ambiente.',
 '05.06': 'Spese ambientali non riconducibili ad altro.',
 '06.01': 'Sviluppo delle abitazioni.',
 '06.02': 'Assetto territoriale e urbanistica.',
 '06.03': 'Approvvigionamento idrico.',
 '06.06': 'Spese per l\u2019abitare non riconducibili ad altro.',
 '07.01': 'Farmaci, prodotti e attrezzature sanitarie.',
 '07.02': 'Servizi sanitari non ospedalieri: distretti e medicina generale.',
 '07.03': 'Servizi ospedalieri.',
 '07.04': 'Sanità pubblica: prevenzione, profilassi, vigilanza.',
 '07.05': 'Ricerca e sviluppo per la sanità.',
 '07.06': 'Spese sanitarie non riconducibili ad altro.',
 '08.01': 'Attività ricreative e sport.',
 '08.02': 'Attività culturali: musei, biblioteche, archivi, spettacolo.',
 '08.03': 'Radiotelevisione pubblica ed editoria.',
 '08.04': 'Servizi di culto e per le comunità, incluse le intese con le confessioni religiose.',
 '08.05': 'Ricerca e sviluppo per cultura e tempo libero.',
 '08.06': 'Spese culturali non riconducibili ad altro.',
 '09.01': 'Istruzione prescolastica e primaria.',
 '09.02': 'Istruzione secondaria.',
 '09.03': 'Istruzione post-secondaria non superiore.',
 '09.04': 'Istruzione universitaria.',
 '09.05': 'Istruzione di altro tipo, formazione professionale inclusa.',
 '09.06': 'Servizi ausiliari all\u2019istruzione: trasporti scolastici, mense, orientamento.',
 '09.07': 'Ricerca e sviluppo per l\u2019istruzione.',
 '09.08': 'Spese per l\u2019istruzione non riconducibili ad altro.',
 '10.01': 'Pensioni e sostegno per malattia e invalidità.',
 '10.02': 'Pensioni di vecchiaia: la previdenza.',
 '10.03': 'Pensioni ai superstiti.',
 '10.04': 'Sostegno alle famiglie e alla natalità.',
 '10.05': 'Sostegno alla disoccupazione.',
 '10.06': 'Sostegno all\u2019abitare per le fasce deboli.',
 '10.07': 'Esclusione sociale non riconducibile ad altro.',
 '10.08': 'Ricerca e sviluppo per la protezione sociale.',
 '10.09': 'Altre spese di protezione sociale.',
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
        sottotitolo = ('Quanto lo Stato italiano è autorizzato a spendere nel %s, '
                       'in stanziamenti di competenza: autorizzazioni, non impegni '
                       'e non pagamenti. Si può confrontare voce per voce con la '
                       'spesa impegnata degli anni prima.' % ANNO)
        apertura = ('Questa non è spesa, e non è ancora un impegno: è la spesa '
                    'autorizzata dalla legge di bilancio per il %s. Le cifre '
                    'diventano impegni quando le amministrazioni assumono le '
                    'obbligazioni, e pagamenti quando il denaro esce davvero. '
                    'Qui sotto puoi aprirla e confrontarla con il consuntivo '
                    'degli anni precedenti.' % ANNO)
        fonte_nome = ("Legge di bilancio per l'anno %s, dati aperti della Ragioneria "
                      'generale dello Stato (OpenBDAP), licenza CC BY.' % ANNO)
        nota_metodo = ('Gli importi del %s sono stanziamenti di competenza della '
                       'legge di bilancio: autorizzazioni di spesa. Negli anni '
                       'precedenti la spesa è misurata dagli impegni del rendiconto, '
                       'che sono obbligazioni già assunte: il confronto dice quanto '
                       'è previsto in più o in meno, non quanto è stato speso in più. '
                       'La classificazione per finalità (COFOG) esiste solo nel '
                       'rendiconto: per il %s non è ancora disponibile.' % (ANNO, ANNO))
        come_leggere = ('Gli importi sono stanziamenti: autorizzazioni di spesa, '
                        'non impegni né pagamenti. Se una voce indica 12%, prende il '
                        '12% della voce che la contiene al livello superiore, non '
                        'della spesa totale.')
    else:
        titolo = 'La spesa dello Stato nel %s' % ANNO
        titolo_display = {'prima': 'La spesa', 'corsivo': 'dello Stato', 'dopo': 'nel %s' % ANNO}
        if MISURA == 'impegnato':
            sottotitolo = ('Quanto lo Stato italiano ha impegnato nel %s: obbligazioni '
                           'di spesa assunte nell\u2019anno, non pagamenti. Puoi leggere '
                           'la stessa cifra per amministrazione o per finalità.' % ANNO)
            testo_misura = ('Gli importi sono impegni di competenza dell\'esercizio %s: '
                            'obbligazioni che l\'amministrazione ha assunto nell\'anno. '
                            'Non sono previsioni, e non sono ancora pagamenti: quelli sono '
                            'in cassa e seguono altri tempi.' % ANNO)
            come_leggere = ('Gli importi sono impegni: obbligazioni di spesa assunte, '
                            'non pagamenti. Se una voce indica 12%, prende il 12% '
                            'della voce che la contiene al livello superiore, non '
                            'della spesa totale.')
        else:
            # MISURA=pagato|definitivo: cambia la natura dei numeri,
            # e le formule sopra non varrebbero
            sottotitolo = ('Quanto lo Stato italiano ha messo in spesa nel %s, '
                           'in %s. Puoi leggere la stessa cifra per amministrazione '
                           'o per finalità.' % (ANNO, nome_misura))
            testo_misura = ('Gli importi sono %s di competenza dell\'esercizio %s.'
                            % (nome_misura, ANNO))
            come_leggere = ('Gli importi sono %s. Se una voce indica 12%, prende il '
                            '12% della voce che la contiene al livello superiore, '
                            'non della spesa totale.' % nome_misura)
        apertura = ('Non è una previsione: è il consuntivo in competenza, chiuso a '
                    'fine %s, presentato al Parlamento e giudicato dalla Corte dei '
                    'conti l\u2019anno dopo. Qui sotto puoi aprirlo: ogni volta che '
                    'scegli una voce, la barra si ridisegna su quella voce e ti '
                    'mostra come è fatta dentro.' % ANNO)
        fonte_nome = ('Rendiconto generale dello Stato per l\'esercizio finanziario %s, '
                      'dati aperti della Ragioneria generale dello Stato (OpenBDAP), '
                      'licenza CC BY.' % ANNO)
        nota_metodo = (testo_misura + ' Un capitolo può servire più '
                       'finalità: nella vista per finalità è ripartito secondo le '
                       'percentuali COFOG indicate dalla Ragioneria, e i due totali '
                       'coincidono. Gli andamenti storici seguono le voci attraverso '
                       'i codici: se un ministero cambia nome, la sua storia continua; '
                       'le voci assenti in un anno lasciano un vuoto.')

    sezioni = [
        {'id': 'chi', 'nome': 'Chi spende', 'etichetta': 'Chi spende',
         'titolo': 'La spesa %s per amministrazione' % ANNO, 'importo': TOT,
         'descrizione': 'La stessa cifra della pagina, vista per chi la gestisce: '
                        'ogni ministero, le sue missioni, i loro programmi. Per '
                        'capire a che cosa servono i soldi, passa alla vista '
                        '«A cosa serve».'
                        + (' Per il %s quella vista non è ancora disponibile.'
                           % ANNO if previsione else ''),
         'figli': el['chi']},
    ]
    if el['cosa']:
        sezioni.append(
            {'id': 'cosa', 'nome': 'A cosa serve', 'etichetta': 'A cosa serve',
             'titolo': 'La spesa %s per finalità' % ANNO, 'importo': TOT,
             'descrizione': 'La stessa spesa, raggruppata per scopo con la '
                            'classificazione COFOG delle Nazioni Unite, '
                            'indipendentemente da chi la gestisce: «Difesa» somma '
                            'tutto ciò che serve a difendere il paese, chiunque lo faccia.',
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

main()

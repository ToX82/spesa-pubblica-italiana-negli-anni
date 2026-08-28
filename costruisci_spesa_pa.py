#!/usr/bin/env python3
"""
Costruisce i JSON della vista «Tutta la spesa pubblica» a partire dalle
tabelle Eurostat scaricate da scarica_eurostat.py.

    python3 costruisci_spesa_pa.py

Due lati. Sulle **uscite**, tre alberi che chiudono tutti sullo stesso
totale — la spesa delle amministrazioni pubbliche (S13) in contabilità
nazionale SEC 2010:

  «A cosa serve»   Divisione COFOG -> Gruppo -> chi la eroga
  «Chi spende»     Sottosettore -> Divisione COFOG -> Gruppo
  «Come si spende» Voce economica SEC 2010 -> Divisione COFOG

Sulle **entrate**, un albero:

  «Da dove vengono» Tipo di entrata -> dettaglio (IRPEF, IRES, IVA,
                    accise, contributi di datori e lavoratori)

E in cima la fascia del bilancio: entrate, uscite, saldo. Il saldo è
l'indebitamento netto pubblicato da Eurostat, e le tre cifre vengono
tutte dalla stessa tabella (gov_10a_main), così la sottrazione che il
lettore fa a mente torna sempre.

Il punto delicato è il consolidamento. Ogni sottosettore dichiara la
propria spesa lorda: la somma dei tre supera il totale di parecchie
centinaia di miliardi, perché i trasferimenti fra livelli di governo
(Stato -> Regioni per la sanità, Stato -> INPS per le pensioni) sono
spesa per chi li eroga e di nuovo spesa per chi li riceve. Eurostat
pubblica quei flussi voce per voce (D4/D7/D9 «di cui verso il
sottosettore X»), anche per funzione COFOG: sottraendoli si ottiene la
spesa netta di ciascun sottosettore, che somma esattamente al totale
consolidato. Lo script verifica l'identità su ogni cella e si ferma se
non torna.

Attenzione a una cosa: Eurostat pubblica gli aggregati (gov_10a_main) e
la ripartizione per funzione (gov_10a_exp) in due tabelle distinte, con
calendari di aggiornamento diversi. Per l'ultimo anno o due i due totali
di spesa possono differire di qualche centinaio di milioni — meno di un
decimo di punto. La fascia del bilancio usa gli aggregati, perché è lì
che sta il saldo ufficiale; l'albero della spesa usa la tabella per
funzione, perché è l'unica che la contiene. Lo scarto, quando c'è, va
scritto nella nota di metodo, non nascosto.

Scrive assets/pa_YYYY.json per ogni anno, assets/pa.json (copia
dell'ultimo) e assets/ponte.json, che tiene insieme le due viste del
sito mettendo in fila, per ogni funzione COFOG, la spesa pubblica
complessiva e quella registrata nel bilancio dello Stato.
"""

import json, os, glob, sys

QUI = os.path.dirname(os.path.abspath(__file__))
EUROSTAT = os.path.join(QUI, 'data', 'eurostat')
ASSETS = os.path.join(QUI, 'assets')

PRIMO_ANNO = 1995
# I gruppi COFOG (secondo livello) l'Italia li trasmette dal 2001: per gli
# anni prima l'albero si ferma alla divisione, e sotto ci vanno subito i
# sottosettori. Non si interpola nulla.
PRIMO_ANNO_GRUPPI = 2001

# ── nomenclatura ─────────────────────────────────────────────

DIVISIONI = {
 '01': 'Servizi generali delle pubbliche amministrazioni',
 '02': 'Difesa',
 '03': 'Ordine pubblico e sicurezza',
 '04': 'Affari economici',
 '05': "Protezione dell'ambiente",
 '06': 'Abitazioni e assetto territoriale',
 '07': 'Sanità',
 '08': 'Attività ricreative, culturali e di culto',
 '09': 'Istruzione',
 '10': 'Protezione sociale',
}

GRUPPI = {
 '01.01': 'Organi esecutivi e legislativi, attività finanziarie e fiscali, affari esteri',
 '01.02': 'Aiuti economici internazionali',
 '01.03': 'Servizi generali',
 '01.04': 'Ricerca di base',
 '01.05': 'R&S per i servizi pubblici generali',
 '01.06': 'Servizi pubblici generali non altrove classificati',
 '01.07': 'Transazioni relative al debito pubblico',
 '01.08': 'Trasferimenti a carattere generale tra diversi livelli di governo',
 '02.01': 'Difesa militare',
 '02.02': 'Difesa civile',
 '02.03': "Aiuti militari all'estero",
 '02.04': 'R&S per la difesa',
 '02.05': 'Difesa non altrove classificata',
 '03.01': 'Servizi di polizia',
 '03.02': 'Servizi antincendio',
 '03.03': 'Tribunali',
 '03.04': 'Carceri',
 '03.05': "R&S per l'ordine pubblico e la sicurezza",
 '03.06': 'Ordine pubblico e sicurezza non altrove classificati',
 '04.01': 'Affari generali economici, commerciali e del lavoro',
 '04.02': 'Agricoltura, silvicoltura, pesca e caccia',
 '04.03': 'Combustibili ed energia',
 '04.04': 'Attività estrattive, manifatturiere ed edilizie',
 '04.05': 'Trasporti',
 '04.06': 'Comunicazioni',
 '04.07': 'Altri settori produttivi',
 '04.08': 'R&S per gli affari economici',
 '04.09': 'Affari economici non altrove classificati',
 '05.01': 'Trattamento dei rifiuti',
 '05.02': 'Trattamento delle acque reflue',
 '05.03': "Riduzione dell'inquinamento",
 '05.04': 'Protezione della biodiversità e del paesaggio',
 '05.05': "R&S per la protezione dell'ambiente",
 '05.06': "Protezione dell'ambiente non altrove classificata",
 '06.01': 'Sviluppo delle abitazioni',
 '06.02': 'Sviluppo del territorio',
 '06.03': 'Approvvigionamento idrico',
 '06.04': 'Illuminazione stradale',
 '06.05': "R&S per le abitazioni e l'assetto territoriale",
 '06.06': 'Abitazioni e assetto territoriale non altrove classificati',
 '07.01': 'Prodotti, apparecchi e attrezzature sanitarie',
 '07.02': 'Servizi ambulatoriali',
 '07.03': 'Servizi ospedalieri',
 '07.04': 'Servizi di sanità pubblica',
 '07.05': 'R&S per la sanità',
 '07.06': 'Sanità non altrove classificata',
 '08.01': 'Attività ricreative e sportive',
 '08.02': 'Servizi culturali',
 '08.03': 'Servizi radiotelevisivi ed editoriali',
 '08.04': 'Servizi religiosi e altri servizi comunitari',
 '08.05': 'R&S per attività ricreative, culturali e di culto',
 '08.06': 'Attività ricreative, culturali e di culto non altrove classificate',
 '09.01': 'Istruzione prescolastica e primaria',
 '09.02': 'Istruzione secondaria',
 '09.03': 'Istruzione post-secondaria non universitaria',
 '09.04': 'Istruzione universitaria',
 '09.05': 'Istruzione non attribuibile ad alcun livello',
 '09.06': "Servizi ausiliari dell'istruzione",
 '09.07': "R&S per l'istruzione",
 '09.08': 'Istruzione non altrove classificata',
 '10.01': 'Malattia e invalidità',
 '10.02': 'Vecchiaia',
 '10.03': 'Superstiti',
 '10.04': 'Famiglia',
 '10.05': 'Disoccupazione',
 '10.06': 'Abitazione',
 '10.07': 'Esclusione sociale non altrove classificata',
 '10.08': 'R&S per la protezione sociale',
 '10.09': 'Protezione sociale non altrove classificata',
}

SOTTOSETTORI = ['S1311', 'S1313', 'S1314']

NOMI_SOTTOSETTORE = {
 'S1311': 'Amministrazioni centrali',
 'S1313': 'Amministrazioni locali',
 'S1314': 'Enti di previdenza',
}

DESCR_SOTTOSETTORE = {
 'S1311': 'Lo Stato in senso stretto — ministeri, agenzie fiscali, organi '
          'costituzionali — insieme agli enti pubblici nazionali: università, '
          'enti di ricerca, ANAS, autorità indipendenti. Raccoglie la quasi '
          'totalità delle imposte e ne trasferisce una parte rilevante agli '
          'altri due livelli, in particolare alle Regioni per la sanità e agli '
          'enti previdenziali per le pensioni. La cifra indicata qui è al netto '
          'di quei trasferimenti: misura quanto lo Stato spende direttamente, '
          'non quanto incassa e ridistribuisce.',
 'S1313': 'Regioni, Province, Città metropolitane e Comuni, con gli enti che '
          'dipendono da loro: le aziende sanitarie e ospedaliere ne '
          'costituiscono da sole la parte prevalente. Le entrate proprie sono '
          'limitate — IRAP, addizionali, imposte immobiliari, tariffe — mentre '
          'la maggior parte delle risorse arriva da trasferimenti statali. È il '
          'livello che eroga materialmente la sanità e i servizi di prossimità, '
          'e quindi quello dove si vede la spesa che i cittadini incontrano.',
 'S1314': 'INPS e INAIL, più le casse previdenziali dei liberi professionisti. '
          'Incassano contributi sociali ed erogano pensioni, indennità e '
          'prestazioni assistenziali: la loro spesa è quasi interamente '
          'protezione sociale. I contributi non bastano a coprire le '
          'prestazioni, e la differenza è colmata da trasferimenti dello Stato; '
          'nella cifra indicata qui quei trasferimenti sono attribuiti a chi '
          'eroga la prestazione, non a chi la finanzia.',
}

ECONOMICHE = [
 ('D62',       'Prestazioni sociali in denaro'),
 ('D1',        'Redditi da lavoro dipendente'),
 ('P2',        'Consumi intermedi'),
 ('D9',        'Trasferimenti in conto capitale'),
 ('D4',        'Redditi da capitale (interessi)'),
 ('P5',        'Investimenti'),
 ('D632',      'Prestazioni sociali in natura acquistate sul mercato'),
 ('D3',        'Contributi alla produzione'),
 ('D7',        'Altri trasferimenti correnti'),
 ('D29_D5_D8', 'Imposte pagate e altre partite'),
 ('NP',        'Acquisti netti di terreni e altri beni non prodotti'),
]

DESCR_ECONOMICA = {
 'D62': 'Pensioni, indennità di disoccupazione, assegni familiari, sostegni al '
        'reddito: denaro versato direttamente alle persone, senza che vi '
        'corrisponda la fornitura di un bene o di un servizio. È la componente '
        'più grossa della spesa pubblica italiana e passa quasi interamente '
        'dagli enti di previdenza. Non comprende le prestazioni ricevute in '
        'natura, come le cure sanitarie, che sono classificate altrove.',
 'D1': 'Retribuzioni lorde, contributi sociali a carico del datore e oneri '
       'accessori di chi lavora per la pubblica amministrazione: personale '
       'scolastico e sanitario, forze dell’ordine, dipendenti di ministeri, '
       'Regioni ed enti locali. La dinamica dipende dagli organici e dai '
       'rinnovi contrattuali, che si concentrano in singoli esercizi e '
       'producono scalini nella serie storica anziché una crescita regolare.',
 'P2': 'Beni e servizi acquistati per il funzionamento corrente: farmaci e '
       'prestazioni sanitarie comprate da strutture private accreditate, '
       'energia, manutenzioni, servizi informatici, affitti, forniture. La '
       'sanità ne assorbe la quota maggiore. Non comprende i beni durevoli, che '
       'sono investimenti, né il personale, che ha una voce propria.',
 'D9': 'Somme trasferite ad altri soggetti perché realizzino investimenti: '
       'contributi in conto capitale alle imprese, fondi per opere di enti '
       'terzi, ripiani di perdite. Dal 2021 comprende i crediti d’imposta per '
       'la riqualificazione edilizia, che i conti nazionali registrano per '
       'intero nell’anno in cui maturano anziché nell’anno in cui sono '
       'utilizzati: da soli hanno alterato sensibilmente il profilo della voce.',
 'D4': 'Gli interessi pagati sui titoli di Stato e sugli altri debiti pubblici. '
       'L’importo dipende dallo stock di debito accumulato e dai tassi ai quali '
       'è stato emesso, quindi è poco comprimibile nel breve periodo: il debito '
       'si rinnova per scadenze, e una variazione dei tassi si trasmette alla '
       'spesa nell’arco di anni. Il rimborso del capitale non è compreso: nei '
       'conti nazionali è un’operazione finanziaria, non una spesa.',
 'P5': 'Opere e beni durevoli che restano nella disponibilità della pubblica '
       'amministrazione: strade, ferrovie, scuole, ospedali, attrezzature, '
       'software. È la componente storicamente più compressa nelle fasi di '
       'correzione dei conti, perché è la più facile da rinviare, ed è anche la '
       'più esposta ai tempi di realizzazione delle opere: quanto è stanziato e '
       'quanto è speso nello stesso anno raramente coincidono.',
 'D632': 'Prestazioni che il cittadino riceve senza pagarle, ma che la pubblica '
         'amministrazione acquista da produttori privati e paga per suo conto: '
         'assistenza sanitaria convenzionata, farmaci erogati dalle farmacie, '
         'visite ed esami in strutture accreditate. È la voce che misura quanta '
         'parte del servizio pubblico passa attraverso il mercato.',
 'D3': 'Somme versate a chi produce per contenere i prezzi di vendita o '
       'sostenere l’occupazione: sgravi contributivi, compensazioni ai gestori '
       'del trasporto pubblico locale, sostegni all’agricoltura e all’energia. '
       'Agiscono sul costo di produzione, e quindi sui prezzi finali: non sono '
       'trasferimenti alle famiglie, anche quando ne beneficiano di riflesso.',
 'D7': 'Trasferimenti correnti che non sono prestazioni sociali: le risorse '
       'proprie versate al bilancio dell’Unione europea, i contributi alle '
       'organizzazioni internazionali, la cooperazione allo sviluppo, i '
       'trasferimenti alle istituzioni senza scopo di lucro. La contribuzione '
       'al bilancio europeo ne è la componente maggiore.',
 'D29_D5_D8': 'Imposte che la pubblica amministrazione versa a se stessa — '
              'l’IRAP sulle retribuzioni pubbliche ne è l’esempio principale — '
              'e la rettifica contabile per la variazione dei diritti '
              'pensionistici. È una posta tecnica, necessaria a far quadrare i '
              'conti fra settori istituzionali: non corrisponde a un servizio '
              'erogato a qualcuno.',
 'NP': 'Acquisti al netto delle vendite di terreni, giacimenti, diritti di '
       'sfruttamento e licenze: attività che esistono senza essere state '
       'prodotte. Vi rientrano, per esempio, i proventi delle concessioni sulle '
       'frequenze. È una voce di importo marginale e può risultare negativa '
       'negli anni in cui le cessioni superano gli acquisti.',
}

# Le otto voci in cui la contabilità nazionale scompone le entrate
# totali, con i sottolivelli che si ricavano dalla stessa tabella. Il
# terzo campo è la voce Eurostat da cui si prende l'importo; «residuo»
# significa «quel che resta della voce sopra tolti i fratelli», che è un
# resto vero, non una voce inventata per far quadrare il totale.
ENTRATE = [
 ('dirette', 'Imposte su redditi e patrimonio', 'D5REC', [
    ('persone', 'Imposte sul reddito delle persone', 'D51A_C1REC'),
    ('societa', 'Imposte sul reddito delle società', 'D51B_C2REC'),
    ('altre',   'Altre imposte correnti', 'residuo'),
 ]),
 ('indirette', 'Imposte su consumi e produzione', 'D2REC', [
    ('iva',        'IVA', 'D211REC'),
    ('prodotti',   'Altre imposte sui prodotti', 'D21REC-D211REC'),
    ('produzione', 'Imposte sulla produzione', 'D29REC'),
 ]),
 ('contributi', 'Contributi sociali', 'D61REC', [
    ('datori',     'A carico dei datori di lavoro', 'D611REC'),
    ('lavoratori', 'A carico di lavoratori e autonomi', 'D613REC'),
    ('altri',      'Altri contributi sociali', 'residuo'),
 ]),
 ('vendite', 'Vendite di beni e servizi', 'P11_P12_P131', []),
 ('trasferimenti', 'Altri trasferimenti correnti', 'D7REC', []),
 ('capitale', 'Trasferimenti in conto capitale', 'D9REC', []),
 ('rendite', 'Redditi da capitale', 'D4REC', []),
 ('sussidi', 'Contributi alla produzione ricevuti', 'D39REC', []),
]

DESCR_ENTRATA = {
 'dirette': 'Imposte che colpiscono il reddito prodotto e il patrimonio '
            'posseduto, versate da persone fisiche e società. Insieme ai '
            'contributi sociali costituiscono la parte prevalente del prelievo. '
            'La componente principale, l’IRPEF, è progressiva: l’aliquota '
            'cresce al crescere del reddito, a differenza di quanto avviene per '
            'le imposte sui consumi.',
 'dirette/persone': 'Soprattutto l’IRPEF, con le addizionali regionali e '
                    'comunali, più le imposte sostitutive sui redditi da '
                    'capitale e sui regimi forfetari. È la voce singola più '
                    'rilevante del gettito complessivo. La base imponibile è '
                    'concentrata su lavoro dipendente e pensioni, che '
                    'dichiarano la quota largamente maggioritaria del reddito '
                    'imponibile complessivo.',
 'dirette/societa': 'L’IRES e le altre imposte sugli utili delle società di '
                    'capitali. Il gettito è più volatile di quello sulle '
                    'persone fisiche perché segue l’andamento dei profitti: si '
                    'contrae rapidamente nelle recessioni e recupera con '
                    'altrettanta velocità nelle riprese.',
 'dirette/altre': 'Imposte correnti che non colpiscono il reddito: bollo auto, '
                  'canone per il servizio pubblico radiotelevisivo, imposte '
                  'patrimoniali minori e altri prelievi ricorrenti sul possesso '
                  'di beni. Voce eterogenea e di importo contenuto rispetto '
                  'alle due precedenti.',
 'indirette': 'Imposte che colpiscono il consumo, la produzione e il possesso '
              'di beni, non il reddito di chi le paga. Sono incorporate nei '
              'prezzi, quindi meno visibili al contribuente, e pesano '
              'proporzionalmente di più sui redditi bassi, che destinano al '
              'consumo una quota maggiore di quanto guadagnano.',
 'indirette/iva': 'L’imposta sul valore aggiunto, la più rilevante fra le '
                  'imposte sui consumi. Si applica con aliquote differenziate — '
                  'ordinaria, ridotte e minima — a seconda del bene o del '
                  'servizio. Il gettito segue da vicino i consumi delle '
                  'famiglie, quindi reagisce rapidamente sia ai cicli economici '
                  'sia all’inflazione.',
 'indirette/prodotti': 'Accise su carburanti, energia elettrica, gas, alcolici '
                       'e tabacchi, imposta di registro e di bollo, prelievo su '
                       'lotto e giochi, dazi doganali. Le accise sui prodotti '
                       'energetici ne sono la componente maggiore e hanno un '
                       'gettito poco sensibile al prezzo, perché sono '
                       'commisurate alle quantità vendute e non al valore.',
 'indirette/produzione': 'Imposte che gravano sull’attività produttiva e sui '
                         'beni impiegati, indipendentemente dal profitto '
                         'realizzato: l’IRAP e le imposte sugli immobili, IMU '
                         'in testa, ne sono le componenti principali. L’IRAP '
                         'concorre a finanziare la sanità regionale, l’IMU i '
                         'bilanci comunali.',
 'contributi': 'Quanto datori di lavoro e lavoratori versano per pensioni, '
               'malattia, infortuni e disoccupazione. In senso tecnico non sono '
               'imposte, perché danno diritto a una prestazione futura; '
               'concorrono però al prelievo complessivo sul lavoro, ed è la '
               'somma di imposte e contributi a determinare la differenza fra '
               'costo del lavoro per l’impresa e retribuzione netta per il '
               'lavoratore.',
 'contributi/datori': 'La parte a carico del datore di lavoro, versata in '
                      'aggiunta alla retribuzione lorda. È la componente '
                      'maggiore del prelievo contributivo e quella su cui '
                      'agiscono gli interventi di riduzione del cuneo fiscale, '
                      'perché incide direttamente sul costo del lavoro.',
 'contributi/lavoratori': 'La quota trattenuta in busta paga ai dipendenti e '
                          'quella versata dai lavoratori autonomi alle '
                          'rispettive gestioni. Per il dipendente è la '
                          'differenza fra retribuzione lorda e imponibile '
                          'fiscale: si paga prima ancora che si calcoli '
                          'l’IRPEF.',
 'contributi/altri': 'Comprende i contributi figurativi, accreditati sulla '
                     'posizione previdenziale senza un versamento effettivo — '
                     'periodi di disoccupazione indennizzata, maternità, cassa '
                     'integrazione — e altre poste minori. Non corrispondono a '
                     'un incasso di cassa: figurano in entrata e, per pari '
                     'importo, in uscita.',
 'vendite': 'Quanto la pubblica amministrazione incassa cedendo beni e servizi: '
            'ticket sanitari, rette di asili e mense, trasporto scolastico, '
            'ingressi a musei, canoni e concessioni, diritti amministrativi. '
            'Sono entrate a fronte di una controprestazione, quindi non fanno '
            'parte del prelievo obbligatorio e non entrano nel calcolo della '
            'pressione fiscale.',
 'trasferimenti': 'Trasferimenti correnti provenienti dall’esterno della '
                  'pubblica amministrazione: fondi europei di parte corrente, '
                  'risarcimenti assicurativi, contributi da famiglie e imprese, '
                  'cooperazione internazionale in entrata.',
 'capitale': 'Trasferimenti destinati al finanziamento di investimenti, in '
             'larga parte di provenienza europea: dal 2021 la componente '
             'principale sono le sovvenzioni del PNRR. Comprende anche le '
             'imposte in conto capitale, cioè successioni, donazioni e i '
             'prelievi straordinari sul patrimonio.',
 'rendite': 'Interessi, dividendi e canoni che rendono le attività finanziarie '
            'e i beni patrimoniali pubblici: partecipazioni societarie, '
            'depositi, immobili, concessioni demaniali. È una voce contenuta, '
            'di un ordine di grandezza inferiore agli interessi che la stessa '
            'pubblica amministrazione paga sul debito.',
 'sussidi': 'Contributi alla produzione che la pubblica amministrazione riceve '
            'invece di erogare, nei casi in cui un ente pubblico opera come '
            'produttore di mercato e beneficia di un sostegno. Voce di importo '
            'marginale, presente per completezza della classificazione.',
}

NOTE_DIVISIONE = {
 '01': 'Il funzionamento generale dell’amministrazione: organi costituzionali, '
       'servizi fiscali, rete diplomatica, servizi comuni a più ministeri e '
       'ricerca di base. Comprende anche le transazioni sul debito pubblico, '
       'che ne sono la componente maggiore: sono gli interessi sui titoli di '
       'Stato, una spesa determinata dallo stock di debito e dai tassi di '
       'mercato, non da decisioni annuali di bilancio.',
 '02': 'Forze armate, missioni internazionali, ricerca e approvvigionamenti '
       'militari, difesa civile. La voce è dominata dalle retribuzioni del '
       'personale, che assorbono una quota molto superiore a quella degli '
       'investimenti in mezzi e infrastrutture. Gli impegni assunti in sede '
       'NATO si riferiscono a un perimetro diverso da questo, che segue le '
       'regole della classificazione COFOG.',
 '03': 'Polizia di Stato, Carabinieri, Guardia di finanza, vigili del fuoco, '
       'tribunali e istituti penitenziari. È una funzione a forte intensità di '
       'personale: la spesa dipende soprattutto dagli organici e dai rinnovi '
       'contrattuali. La giustizia vi compare per il costo del servizio, non '
       'per i suoi risultati: i tempi dei processi non si leggono in questa '
       'cifra.',
 '04': 'Il sostegno pubblico alle attività produttive: trasporti e '
       'infrastrutture — di gran lunga la componente maggiore — energia, '
       'agricoltura, industria, comunicazioni e politiche del lavoro. Vi '
       'confluiscono incentivi, contributi e crediti d’imposta alle imprese, '
       'insieme alla spesa per la rete stradale e ferroviaria. È la divisione '
       'più sensibile ai cicli della programmazione europea, PNRR compreso.',
 '05': 'Raccolta e trattamento dei rifiuti, depurazione delle acque reflue, '
       'riduzione dell’inquinamento, tutela della biodiversità e del paesaggio. '
       'È in larga parte spesa dei Comuni, finanziata anche dalle tariffe sui '
       'servizi ambientali. Non contiene tutta la spesa per il clima: la '
       'classificazione segue la finalità immediata del servizio, quindi gli '
       'interventi su energia o trasporti restano nelle rispettive divisioni.',
 '06': 'Edilizia residenziale pubblica, urbanistica e sviluppo del territorio, '
       'servizio idrico, illuminazione stradale. Dal 2021 la divisione include '
       'i crediti d’imposta per la riqualificazione edilizia, che i conti '
       'nazionali registrano per intero come spesa nell’anno di maturazione: è '
       'la ragione dell’impennata e del successivo rientro degli importi, non '
       'un cambiamento delle politiche abitative.',
 '07': 'Il Servizio sanitario nazionale: ospedali, assistenza territoriale e '
       'specialistica, farmaci, prevenzione, ricerca sanitaria. Il '
       'finanziamento è quasi interamente statale e passa dal Fondo sanitario '
       'nazionale; l’erogazione è quasi interamente regionale, attraverso '
       'aziende sanitarie e ospedaliere. Aprendo la funzione si vede la '
       'ripartizione fra i due livelli. La spesa sanitaria privata delle '
       'famiglie non è compresa.',
 '08': 'Attività ricreative e sportive, musei, biblioteche e archivi, '
       'spettacolo, editoria, servizi religiosi. È in buona parte spesa di '
       'Comuni e Regioni. Comprende i trasferimenti al concessionario del '
       'servizio pubblico radiotelevisivo, che nei conti nazionali figurano '
       'come spesa mentre il canone figura fra le entrate tributarie.',
 '09': 'Scuola dell’infanzia, primaria e secondaria, istruzione universitaria, '
       'formazione professionale, e i servizi ausiliari come mense e trasporto '
       'scolastico. Le retribuzioni del personale docente e non docente ne '
       'assorbono la parte largamente prevalente, il che rende la spesa poco '
       'flessibile nel breve periodo. La ricerca universitaria non '
       'riconducibile alla didattica è classificata sotto ricerca di base, in '
       'un’altra divisione.',
 '10': 'Pensioni di vecchiaia, ai superstiti e di invalidità, indennità di '
       'disoccupazione, assegni alle famiglie, contrasto alla povertà, edilizia '
       'sociale. È la funzione più rilevante della spesa pubblica italiana, con '
       'ampio margine sulla seconda, e la componente decisiva sono le pensioni. '
       'Il sistema previdenziale è a ripartizione: la spesa dipende dal '
       'rapporto fra chi lavora e chi è in quiescenza prima ancora che dalle '
       'regole di calcolo degli assegni.',
}

# Le descrizioni dei gruppi COFOG stanno già nel compilatore del bilancio
# dello Stato: si riusano, tranne quelle che raccontano la voce dal punto
# di vista del solo bilancio statale e qui sarebbero sbagliate.
try:
    from costruisci_rendiconto import DESCR_GRUPPO_COFOG as _DESCR_GRUPPI
    DESCR_GRUPPI = dict(_DESCR_GRUPPI)
except Exception:
    DESCR_GRUPPI = {}

# Due gruppi vanno riscritti per questa vista: nel bilancio dello Stato
# comprendono flussi che la contabilità nazionale non conta come spesa.
DESCR_GRUPPI.update({
 '01.07': 'Gli interessi pagati sul debito pubblico: cedole dei titoli di '
          'Stato, interessi sui prestiti e oneri connessi. L\u2019importo dipende '
          'dallo stock di debito accumulato e dai tassi ai quali è stato '
          'emesso, quindi si muove con ritardo rispetto alle decisioni di '
          'politica monetaria: il debito si rinnova per scadenze, e un rialzo '
          'dei tassi si trasmette alla spesa nell\u2019arco di anni. Il rimborso '
          'del capitale non è compreso: nei conti nazionali è un\u2019operazione '
          'finanziaria, non una spesa.',
 '01.08': 'I trasferimenti a carattere generale fra livelli di governo che '
          'restano dopo il consolidamento, cioè quelli non destinati a una '
          'funzione specifica: fondi perequativi, compartecipazioni al gettito, '
          'contributi al riequilibrio dei bilanci locali. I trasferimenti '
          'finalizzati a una politica — il Fondo sanitario nazionale, per '
          'esempio — sono già contati sotto quella politica, una volta sola.',
})

# ── lettura delle tabelle JSON-stat ──────────────────────────

class Tabella:
    """Accesso per etichette a un cubo JSON-stat di Eurostat."""

    def __init__(self, percorso):
        with open(percorso, encoding='utf-8') as f:
            d = json.load(f)
        self.ids = d['id']
        self.size = d['size']
        self.valori = d['value']
        self.indice = {k: d['dimension'][k]['category']['index'] for k in self.ids}
        self.aggiornato = d.get('updated', '')
        passo = [1] * len(self.size)
        for i in range(len(self.size) - 2, -1, -1):
            passo[i] = passo[i + 1] * self.size[i + 1]
        self.passo = passo

    def __call__(self, **coord):
        pos = [0] * len(self.size)
        for k, v in coord.items():
            idx = self.indice.get(k)
            if idx is None or v not in idx:
                return None
            pos[self.ids.index(k)] = idx[v]
        chiave = sum(a * s for a, s in zip(pos, self.passo))
        return self.valori.get(str(chiave))

    def valori_di(self, dimensione):
        idx = self.indice[dimensione]
        return sorted(idx, key=lambda c: idx[c])


TABELLE = ('spesa.json', 'trasferimenti.json', 'economica.json',
           'aggregati.json', 'debito.json', 'pil.json', 'popolazione.json')

def carica():
    manca = [n for n in TABELLE if not os.path.exists(os.path.join(EUROSTAT, n))]
    if manca:
        raise SystemExit('Mancano %s in data/eurostat/. Esegui prima '
                         'python3 scarica_eurostat.py' % ', '.join(manca))
    return {n.split('.')[0]: Tabella(os.path.join(EUROSTAT, n)) for n in TABELLE}


# ── consolidamento ───────────────────────────────────────────

def euro(mln):
    """Eurostat pubblica in milioni con un decimale: la precisione vera è
    di centomila euro, e qui non se ne inventa altra."""
    return int(round(mln * 1e6)) if mln is not None else None


def uscite_verso_altri(t, sottosettore, cofog, anno):
    """Trasferimenti che questo sottosettore versa agli altri due, sulla
    stessa funzione: la parte da togliere per non contarla due volte."""
    totale = 0.0
    for voce in ('D4', 'D7', 'D9'):
        for altro in SOTTOSETTORI:
            if altro == sottosettore:
                continue
            v = t['trasferimenti'](sector=sottosettore, cofog99=cofog,
                                   na_item='%s_%s' % (voce, altro), time=anno)
            if v:
                totale += v
    return totale


def netto(t, sottosettore, cofog, anno):
    """Spesa del sottosettore al netto di quel che gira agli altri livelli.
    Sommata sui tre sottosettori dà esattamente il totale consolidato."""
    lordo = t['spesa'](sector=sottosettore, cofog99=cofog, na_item='TE', time=anno)
    if lordo is None:
        return None
    return lordo - uscite_verso_altri(t, sottosettore, cofog, anno)


def totale(t, cofog, anno):
    return t['spesa'](sector='S13', cofog99=cofog, na_item='TE', time=anno)


def verifica(t, anni, codici):
    """L'identità di consolidamento su ogni cella: se non torna, meglio
    fermarsi che pubblicare numeri che non chiudono."""
    controllate = fuori = 0
    for anno in anni:
        for c in codici:
            atteso = totale(t, c, anno)
            if atteso is None:
                continue
            somma = 0.0
            for s in SOTTOSETTORI:
                v = netto(t, s, c, anno)
                if v is not None:
                    somma += v
            controllate += 1
            if abs(somma - atteso) > max(0.5, abs(atteso) * 1e-4):
                fuori += 1
                if fuori <= 5:
                    print('  scarto %s %s: totale %.1f, somma dei netti %.1f'
                          % (anno, c, atteso, somma))
    if fuori:
        raise SystemExit('Il consolidamento non torna su %d celle su %d.'
                         % (fuori, controllate))
    print('  consolidamento verificato: %d celle, nessuno scarto' % controllate)


def verifica_economica(t, anni, codici):
    controllate = fuori = 0
    for anno in anni:
        for c in codici:
            atteso = totale(t, c, anno)
            if atteso is None:
                continue
            somma = sum(t['economica'](cofog99=c, na_item=v, time=anno) or 0.0
                        for v, _ in ECONOMICHE)
            controllate += 1
            if abs(somma - atteso) > max(0.5, abs(atteso) * 1e-4):
                fuori += 1
                if fuori <= 5:
                    print('  scarto economico %s %s: %.1f vs %.1f'
                          % (anno, c, atteso, somma))
    if fuori:
        raise SystemExit('La classificazione economica non chiude su %d celle '
                         'su %d.' % (fuori, controllate))
    print('  classificazione economica verificata: %d celle, nessuno scarto'
          % controllate)


# ── costruzione degli alberi ─────────────────────────────────

def cod_divisione(gf):
    return gf[2:4]

def cod_gruppo(gf):
    return gf[2:4] + '.' + gf[4:6]


def nodo(ident, cod, nome, importo, figli=None, descrizione=''):
    n = {'id': ident, 'cod': cod, 'nome': nome, 'importo': int(round(importo))}
    if descrizione:
        n['descrizione'] = descrizione
    figli = [f for f in (figli or []) if f['importo'] != 0]
    if figli:
        figli.sort(key=lambda x: -x['importo'])
        n['figli'] = figli
    return n


def divisioni_presenti(t):
    return [c for c in t['spesa'].valori_di('cofog99') if len(c) == 4 and c != 'TOTAL']


def gruppi_di(t, divisione):
    return [c for c in t['spesa'].valori_di('cofog99')
            if len(c) == 6 and c[:4] == divisione]


def foglie_sottosettore(t, cofog, anno, prefisso):
    figli = []
    for s in SOTTOSETTORI:
        v = netto(t, s, cofog, anno)
        if v is None:
            continue
        figli.append(nodo(prefisso + '-' + s, s, NOMI_SOTTOSETTORE[s], euro(v),
                          descrizione=DESCR_SOTTOSETTORE[s]))
    return figli


def albero_cosa(t, anno, con_gruppi):
    """Divisione COFOG -> gruppo -> chi la eroga."""
    out = []
    for gf in divisioni_presenti(t):
        v = totale(t, gf, anno)
        if v is None:
            continue
        cd = cod_divisione(gf)
        ident = 'cosa-' + cd
        if con_gruppi:
            figli = []
            for gg in gruppi_di(t, gf):
                vg = totale(t, gg, anno)
                if vg is None:
                    continue
                cg = cod_gruppo(gg)
                idg = ident + '-' + gg[4:6]
                figli.append(nodo(idg, cg, GRUPPI.get(cg, gg), euro(vg),
                                  foglie_sottosettore(t, gg, anno, idg),
                                  DESCR_GRUPPI.get(cg, '')))
        else:
            figli = foglie_sottosettore(t, gf, anno, ident)
        out.append(nodo(ident, cd, DIVISIONI.get(cd, gf), euro(v), figli,
                        NOTE_DIVISIONE.get(cd, '')))
    out.sort(key=lambda x: -x['importo'])
    return out


def albero_chi(t, anno, con_gruppi):
    """Sottosettore -> divisione COFOG -> gruppo."""
    out = []
    for s in SOTTOSETTORI:
        v = netto(t, s, 'TOTAL', anno)
        if v is None:
            continue
        ident = 'chi-' + s
        divisioni = []
        for gf in divisioni_presenti(t):
            vd = netto(t, s, gf, anno)
            if vd is None:
                continue
            cd = cod_divisione(gf)
            idd = ident + '-' + cd
            gruppi = []
            if con_gruppi:
                for gg in gruppi_di(t, gf):
                    vg = netto(t, s, gg, anno)
                    if vg is None:
                        continue
                    cg = cod_gruppo(gg)
                    gruppi.append(nodo(idd + '-' + gg[4:6], cg,
                                       GRUPPI.get(cg, gg), euro(vg), None,
                                       DESCR_GRUPPI.get(cg, '')))
            divisioni.append(nodo(idd, cd, DIVISIONI.get(cd, gf), euro(vd),
                                  gruppi, NOTE_DIVISIONE.get(cd, '')))
        out.append(nodo(ident, s, NOMI_SOTTOSETTORE[s], euro(v), divisioni,
                        DESCR_SOTTOSETTORE[s]))
    out.sort(key=lambda x: -x['importo'])
    return out


def albero_come(t, anno):
    """Voce economica SEC 2010 -> divisione COFOG."""
    out = []
    for voce, nome in ECONOMICHE:
        v = t['economica'](cofog99='TOTAL', na_item=voce, time=anno)
        if v is None:
            continue
        ident = 'come-' + voce
        figli = []
        for gf in divisioni_presenti(t):
            vd = t['economica'](cofog99=gf, na_item=voce, time=anno)
            if vd is None:
                continue
            cd = cod_divisione(gf)
            figli.append(nodo(ident + '-' + cd, cd, DIVISIONI.get(cd, gf),
                              euro(vd), None, NOTE_DIVISIONE.get(cd, '')))
        out.append(nodo(ident, voce, nome, euro(v), figli,
                        DESCR_ECONOMICA.get(voce, '')))
    out.sort(key=lambda x: -x['importo'])
    return out


def voce_entrata(t, formula, anno):
    """Legge una voce delle entrate. Le formule sono di due tipi soli:
    un codice Eurostat, oppure una differenza fra due codici — mai una
    somma di comodo."""
    if '-' in formula:
        a, b = formula.split('-')
        va = t['aggregati'](sector='S13', na_item=a, time=anno)
        vb = t['aggregati'](sector='S13', na_item=b, time=anno)
        if va is None:
            return None
        return va - (vb or 0.0)
    return t['aggregati'](sector='S13', na_item=formula, time=anno)


def albero_entrate(t, anno):
    """Tipo di entrata -> dettaglio."""
    out = []
    for cod, nome, formula, figli_def in ENTRATE:
        v = voce_entrata(t, formula, anno)
        if v is None:
            continue
        ident = 'origine-' + cod
        figli = []
        noti = 0.0
        for fcod, fnome, fformula in figli_def:
            if fformula == 'residuo':
                continue
            fv = voce_entrata(t, fformula, anno)
            if fv is None:
                continue
            noti += fv
            figli.append(nodo(ident + '-' + fcod, cod + '/' + fcod, fnome, euro(fv),
                              None, DESCR_ENTRATA.get(cod + '/' + fcod, '')))
        for fcod, fnome, fformula in figli_def:
            if fformula != 'residuo' or not figli:
                continue
            resto = v - noti
            if resto <= 0:
                continue
            figli.append(nodo(ident + '-' + fcod, cod + '/' + fcod, fnome,
                              euro(resto), None,
                              DESCR_ENTRATA.get(cod + '/' + fcod, '')))
        out.append(nodo(ident, cod, nome, euro(v), figli,
                        DESCR_ENTRATA.get(cod, '')))
    out.sort(key=lambda x: -x['importo'])
    return out


def verifica_entrate(t, anni):
    """Le otto voci devono dare il totale delle entrate, e i sottolivelli
    non devono sfondare la voce che li contiene."""
    fuori = 0
    for anno in anni:
        tr = t['aggregati'](sector='S13', na_item='TR', time=anno)
        if tr is None:
            continue
        somma = sum(voce_entrata(t, f, anno) or 0.0 for _, _, f, _ in ENTRATE)
        if abs(somma - tr) > max(0.5, abs(tr) * 1e-4):
            fuori += 1
            print('  scarto entrate %s: totale %.1f, somma delle voci %.1f'
                  % (anno, tr, somma))
        for cod, _, formula, figli_def in ENTRATE:
            v = voce_entrata(t, formula, anno)
            noti = sum(voce_entrata(t, f, anno) or 0.0
                       for _, _, f in figli_def if f != 'residuo')
            if v is not None and noti - v > max(0.5, abs(v) * 1e-4):
                fuori += 1
                print('  i dettagli di %s sfondano la voce nel %s: %.1f > %.1f'
                      % (cod, anno, noti, v))
    if fuori:
        raise SystemExit('Le entrate non chiudono su %d controlli.' % fuori)
    print('  entrate verificate: %d anni, nessuno scarto' % len(anni))


def verifica_saldo(t, anni):
    """Entrate meno uscite deve fare il saldo pubblicato: è la sottrazione
    che il lettore fa a mente guardando la pagina."""
    fuori = 0
    for anno in anni:
        tr = t['aggregati'](sector='S13', na_item='TR', time=anno)
        te = t['aggregati'](sector='S13', na_item='TE', time=anno)
        b9 = t['aggregati'](sector='S13', na_item='B9', time=anno)
        if tr is None or te is None or b9 is None:
            continue
        if abs((tr - te) - b9) > 0.5:
            fuori += 1
            print('  il saldo %s non torna: %.1f invece di %.1f' % (anno, tr - te, b9))
    if fuori:
        raise SystemExit('Il saldo non torna su %d anni.' % fuori)
    print('  saldo verificato: entrate − uscite = indebitamento netto, %d anni'
          % len(anni))


# ── serie storiche ───────────────────────────────────────────

def raccogli(nodi, prefisso, anno, magazzino):
    for n in nodi:
        k = prefisso + '/' + n['cod']
        magazzino.setdefault(k, {})[anno] = n['importo']
        raccogli(n.get('figli') or [], k, anno, magazzino)


def timbra(nodi, prefisso, magazzino, anni):
    for n in nodi:
        k = prefisso + '/' + n['cod']
        serie = magazzino.get(k)
        if serie:
            n['storico'] = [serie.get(a) for a in anni]
        timbra(n.get('figli') or [], k, magazzino, anni)


def spoglia(nodi):
    for n in nodi:
        n.pop('cod', None)
        spoglia(n.get('figli') or [])
    return nodi


# ── impaginazione ────────────────────────────────────────────

FONTE_URL = ('https://ec.europa.eu/eurostat/databrowser/view/gov_10a_exp/'
             'default/table?lang=it')


def impagina(anno, alberi, tot, anni, totali, pil, popolazione,
             trasferimenti_interni, ultimo_anno, con_gruppi, bilancio):
    # Il totale della spesa per funzione è quello che Eurostat pubblica
    # come tale, non la somma delle parti: le celle sono arrotondate a
    # centomila euro ciascuna.
    quota_pil = (tot / pil * 100) if pil else None

    nota_gruppi = ('' if con_gruppi else
                   ' Il dettaglio per gruppo COFOG è trasmesso dall’Italia solo '
                   'dal %d: per il %d l’albero si ferma alla divisione e sotto '
                   'compaiono direttamente i livelli di governo. Nessuna stima, '
                   'nessuna interpolazione.' % (PRIMO_ANNO_GRUPPI, anno))

    # Le due tabelle Eurostat hanno calendari diversi: quando i totali
    # della spesa non coincidono lo si scrive, non lo si nasconde.
    scarto = bilancio['uscite'] - tot
    nota_scarto = ''
    if abs(scarto) >= 1e8:
        nota_scarto = (
            ' Un’ultima avvertenza. Gli aggregati e la ripartizione per funzione '
            'sono pubblicati in due tabelle distinte, con calendari di aggiornamento '
            'diversi: per il %d differiscono di %s sul totale della spesa, lo %s per '
            'cento. Le tre cifre in cima provengono dagli aggregati, che contengono '
            'il saldo ufficiale e rendono coerente la sottrazione; l’albero della '
            'spesa proviene dalla tabella per funzione, l’unica che riporti le '
            'funzioni.'
            % (anno, milioni(abs(scarto)),
               ('%.3f' % (abs(scarto) / bilancio['uscite'] * 100)).replace('.', ',')))

    nota_metodo = (
        'Gli importi sono spesa ed entrate delle amministrazioni pubbliche '
        '(settore S13) in contabilità nazionale SEC 2010, criterio della '
        'competenza economica: non sono impegni, pagamenti o stanziamenti di '
        'bilancio. La spesa non comprende il rimborso del capitale del debito, che '
        'nei conti nazionali è un’operazione finanziaria e non una spesa: è la '
        'ragione principale per cui questa cifra è più bassa di quella del bilancio '
        'dello Stato. Il saldo è l’indebitamento netto pubblicato da Eurostat e '
        'coincide con entrate meno uscite. '
        'Il consolidamento merita una precisazione. La somma delle spese dichiarate '
        'dai tre livelli di governo darebbe %s nel %d, %s in più del totale: i '
        'trasferimenti da un livello all’altro — dallo Stato alle Regioni per la '
        'sanità, dallo Stato all’INPS — comparirebbero due volte, come spesa di chi '
        'eroga e di chi riceve. Qui sono sottratti a chi li eroga, funzione per '
        'funzione, così ogni euro è contato una volta sola e i tre alberi della '
        'spesa chiudono sullo stesso totale al centesimo. '
        'Eurostat pubblica in milioni di euro con un decimale: la precisione degli '
        'importi è di centomila euro. Il dato è disponibile con circa un anno di '
        'ritardo sulla chiusura dell’esercizio; l’ultimo anno con la ripartizione '
        'per funzione è il %d.%s%s'
        % (miliardi(tot + trasferimenti_interni), anno,
           miliardi(trasferimenti_interni), ultimo_anno, nota_gruppi, nota_scarto))

    come_leggere = (
        'Le percentuali sono riferite alla voce che contiene, non al totale '
        'generale: 12% significa il 12% del livello superiore. Gli importi sono di '
        'contabilità nazionale, non stanziamenti di bilancio.')

    # Il racconto della fascia: la cifra, e che cosa vuol dire, in parole.
    saldo = bilancio['saldo']
    pezzi = []
    if saldo < 0:
        pezzi.append('Le uscite superano le entrate di %s: è l’indebitamento netto '
                     'del %d%s.'
                     % (miliardi_precisi(-saldo), anno,
                        (', pari al %s per cento del PIL'
                         % ('%.1f' % (-saldo / pil * 100)).replace('.', ',')) if pil else ''))
    else:
        pezzi.append('Le entrate superano le uscite di %s: è l’avanzo del %d%s.'
                     % (miliardi_precisi(saldo), anno,
                        (', pari al %s per cento del PIL'
                         % ('%.1f' % (saldo / pil * 100)).replace('.', ',')) if pil else ''))
    if bilancio.get('debito'):
        pezzi.append('A fine anno il debito pubblico ammonta a %s%s.'
                     % (miliardi_precisi(bilancio['debito']),
                        (', il %d per cento del PIL' % round(bilancio['debito'] / pil * 100))
                        if pil else ''))
    racconto = ' '.join(pezzi)

    lato_uscite = {
        'id': 'uscite',
        'nome': 'Uscite',
        'etichetta': 'Le uscite',
        'importo': bilancio['uscite'],
        'storico': bilancio['storico_uscite'],
        'etichetta_totale': 'della spesa pubblica',
        'titolo': 'La spesa pubblica nel %d' % anno,
        'titolo_display': {'prima': 'La spesa', 'corsivo': 'pubblica',
                           'dopo': 'nel %d' % anno},
        'sottotitolo': (
            'La spesa dell’intera pubblica amministrazione nel %d: Stato, Regioni, '
            'Comuni, INPS e INAIL. I trasferimenti fra enti sono eliminati, quindi '
            'ogni euro è contato una volta sola.' % anno),
        'apertura': (
            'La stessa spesa si può leggere in tre modi: per finalità, per livello '
            'di governo che la eroga, per natura economica. Scegli una voce e la '
            'barra si ridisegna su quella, scomponendola nelle sue parti.'),
    }
    lato_entrate = {
        'id': 'entrate',
        'nome': 'Entrate',
        'etichetta': 'Le entrate',
        'importo': bilancio['entrate'],
        'storico': bilancio['storico_entrate'],
        'etichetta_totale': 'delle entrate pubbliche',
        'titolo': 'Le entrate pubbliche nel %d' % anno,
        'titolo_display': {'prima': 'Le entrate', 'corsivo': 'pubbliche',
                           'dopo': 'nel %d' % anno},
        'sottotitolo': (
            'Le entrate dell’intera pubblica amministrazione nel %d. Imposte e '
            'contributi sociali ne costituiscono circa nove decimi; il resto sono '
            'vendite di servizi, redditi patrimoniali e trasferimenti '
            'dall’Unione europea.' % anno),
        'apertura': (
            'Tre voci — imposte dirette, imposte indirette, contributi sociali — '
            'coprono la quasi totalità del gettito. Aprendole si arriva a IRPEF, '
            'IRES, IVA, accise e ai contributi divisi fra datori di lavoro e '
            'lavoratori.'),
    }

    sezioni = [
        {'id': 'cosa', 'lato': 'uscite', 'nome': 'A cosa serve',
         'etichetta': 'A cosa serve',
         'titolo': 'La spesa pubblica %d per finalità' % anno, 'importo': tot,
         'descrizione': 'La spesa raggruppata per scopo, indipendentemente da chi '
                        'la eroga: è la classificazione COFOG delle Nazioni Unite, '
                        'adottata da tutti i paesi europei. Aprendo una funzione e '
                        'poi un suo gruppo si arriva al livello di governo che la '
                        'eroga materialmente.',
         'figli': alberi['cosa']},
        {'id': 'chi', 'lato': 'uscite', 'nome': 'Chi spende',
         'etichetta': 'Chi spende',
         'titolo': 'La spesa pubblica %d per livello di governo' % anno,
         'importo': tot,
         'descrizione': 'La stessa cifra ripartita per livello di governo, al netto '
                        'dei trasferimenti verso gli altri due: misura chi eroga la '
                        'spesa, non chi la finanzia. La distinzione conta: la '
                        'sanità è finanziata dallo Stato ed erogata dalle Regioni.',
         'figli': alberi['chi']},
        {'id': 'come', 'lato': 'uscite', 'nome': 'Come si spende',
         'etichetta': 'Come si spende',
         'titolo': 'La spesa pubblica %d per natura' % anno, 'importo': tot,
         'descrizione': 'La stessa cifra ripartita per natura economica: '
                        'prestazioni versate alle persone, retribuzioni, acquisti, '
                        'interessi, investimenti. È la lettura che dice quanto la '
                        'spesa sia rigida, cioè quanta parte non è comprimibile nel '
                        'breve periodo.',
         'figli': alberi['come']},
        {'id': 'origine', 'lato': 'entrate', 'nome': 'Da dove vengono',
         'etichetta': 'Da dove vengono',
         'titolo': 'Le entrate pubbliche %d per tipo' % anno,
         'importo': bilancio['entrate'],
         'descrizione': 'Le entrate ripartite per tipo di prelievo. Le prime tre '
                        'voci — imposte dirette, imposte indirette e contributi '
                        'sociali — costituiscono il prelievo obbligatorio e valgono '
                        'circa nove decimi del totale. Il resto è quanto la '
                        'pubblica amministrazione incassa vendendo servizi o '
                        'riceve dall’esterno.',
         'figli': alberi['origine']},
    ]

    return {
      'meta': {
        'vista': 'pa',
        'ente': 'Conti nazionali delle amministrazioni pubbliche',
        'titolo': lato_uscite['titolo'],
        'titolo_display': lato_uscite['titolo_display'],
        'anno': anno,
        'anni': anni,
        'totale_storico': totali,
        'anni_previsione': [],
        'sottotitolo': lato_uscite['sottotitolo'],
        'apertura': lato_uscite['apertura'],
        'lati': [lato_entrate, lato_uscite],
        'lato_predefinito': 'uscite',
        'saldo': {
            'nome': 'Saldo',
            'etichetta': 'Indebitamento netto' if saldo < 0 else 'Avanzo',
            'importo': bilancio['saldo'],
            'storico': bilancio['storico_saldo'],
        },
        'debito': ({'importo': bilancio['debito']} if bilancio.get('debito') else None),
        'racconto': racconto,
        'popolazione': popolazione,
        'pil': pil,
        'quota_pil': round(quota_pil, 1) if quota_pil else None,
        'etichetta_importo': 'Importo',
        'etichetta_totale': 'della spesa pubblica',
        'vista_nota': ('Il perimetro è l’intera pubblica amministrazione — Stato, '
                       'Regioni, Comuni, enti previdenziali — con i trasferimenti '
                       'fra enti eliminati. Contabilità nazionale SEC 2010, dal %d '
                       'al %d, dati Eurostat su trasmissione Istat.'
                       % (anni[0], ultimo_anno)),
        'portale': {'nome': 'Eurostat',
                    'url': 'https://ec.europa.eu/eurostat/web/main/data/database'},
        'fonte_link_testo': 'Apri le tabelle gov_10a_exp e gov_10a_main su Eurostat',
        'descrizioni': ('Le descrizioni delle voci sono sintesi redazionali di testi '
                        'ufficiali: la classificazione COFOG delle Nazioni Unite, il '
                        'regolamento SEC 2010 sui conti nazionali e il manuale '
                        'Eurostat sulla spesa pubblica per funzione. Sono '
                        'spiegazioni redazionali, non fonti: i numeri provengono '
                        'dalle tabelle indicate sopra.'),
        'come_leggere': come_leggere,
        'fonte_nome': ('Eurostat: «Spesa delle amministrazioni pubbliche per funzione '
                       '(COFOG)», tabella gov_10a_exp, e «Aggregati di contabilità '
                       'nazionale delle amministrazioni pubbliche», tabella '
                       "gov_10a_main, dati trasmessi dall'Istat secondo il SEC 2010. "
                       'Debito da gov_10dd_edpt1, PIL da nama_10_gdp, popolazione da '
                       'demo_gind.'),
        'fonte_url': FONTE_URL,
        'nota_metodo': nota_metodo,
      },
      'sezioni': sezioni,
    }

def miliardi(v):
    return '%s miliardi' % format(int(round(v / 1e9)), ',d').replace(',', '.')


def miliardi_precisi(v):
    """Sopra i cento miliardi i centesimi sono rumore."""
    mld = v / 1e9
    if abs(mld) >= 100:
        return '%s miliardi' % format(int(round(mld)), ',d').replace(',', '.')
    return ('%.2f miliardi' % mld).replace('.', ',')


def milioni(v):
    return ('%.0f milioni' % (v / 1e6)).replace('.', ',')


# ── ponte fra le due viste ───────────────────────────────────

def codici_cofog_stato(sezione):
    """Estrae dai JSON del bilancio dello Stato gli importi delle divisioni
    e dei gruppi COFOG, con gli stessi identificativi della vista pubblica."""
    fuori = {}
    for div in sezione.get('figli') or []:
        if not div['id'].startswith('cosa-') or div['id'].endswith('-zero'):
            continue
        fuori[div['id']] = div['importo']
        for gru in div.get('figli') or []:
            if gru['id'].endswith('-zero'):
                continue
            fuori[gru['id']] = gru['importo']
    return fuori


def scrivi_ponte(anni_pa, per_anno_pa):
    """Mette in fila, per ogni funzione COFOG, la spesa pubblica complessiva
    e quella che passa dal bilancio dello Stato. Sono due misure diverse e
    non si sottraggono: il ponte serve a passare da una vista all'altra."""
    stato = {}
    anni_stato = []
    for percorso in sorted(glob.glob(os.path.join(ASSETS, 'data_[0-9][0-9][0-9][0-9].json'))):
        with open(percorso, encoding='utf-8') as f:
            d = json.load(f)
        anno = d['meta']['anno']
        sez = [s for s in d['sezioni'] if s['id'] == 'cosa']
        if not sez:
            continue
        anni_stato.append(anno)
        for ident, importo in codici_cofog_stato(sez[0]).items():
            stato.setdefault(ident, {})[anno] = importo
    anni_stato.sort()

    ponte = {
        'anni_pa': anni_pa,
        'anni_stato': anni_stato,
        'pa': {k: [v.get(a) for a in anni_pa] for k, v in sorted(per_anno_pa.items())},
        'stato': {k: [v.get(a) for a in anni_stato] for k, v in sorted(stato.items())},
    }
    percorso = os.path.join(ASSETS, 'ponte.json')
    with open(percorso, 'w', encoding='utf-8') as f:
        json.dump(ponte, f, ensure_ascii=False, separators=(',', ':'))
    print('  scritto assets/ponte.json (%d funzioni, %d anni pubblici, '
          '%d anni di bilancio)' % (len(ponte['pa']), len(anni_pa), len(anni_stato)))


# ── main ─────────────────────────────────────────────────────

def main():
    t = carica()
    print('Tabelle Eurostat caricate (aggiornamento %s).'
          % t['spesa'].aggiornato[:10])

    disponibili = [int(a) for a in t['spesa'].valori_di('time')
                   if a.isdigit() and int(a) >= PRIMO_ANNO]
    anni = sorted(a for a in disponibili
                  if totale(t, 'TOTAL', str(a)) is not None)
    if not anni:
        raise SystemExit('Nessun anno con dati nella tabella della spesa.')
    ultimo = anni[-1]
    print('Anni con dati: %d–%d (%d anni).' % (anni[0], ultimo, len(anni)))

    codici = [c for c in t['spesa'].valori_di('cofog99')]
    anni_s = [str(a) for a in anni]
    verifica(t, anni_s, codici)
    verifica_economica(t, anni_s, codici)
    verifica_entrate(t, anni_s)
    verifica_saldo(t, anni_s)

    totali = [euro(totale(t, 'TOTAL', str(a))) for a in anni]

    # La fascia del bilancio viene tutta dalla tabella degli aggregati,
    # così entrate meno uscite fa esattamente il saldo pubblicato.
    def agg(voce, a):
        return euro(t['aggregati'](sector='S13', na_item=voce, time=str(a)))
    storico = {v: [agg(v, a) for a in anni] for v in ('TR', 'TE', 'B9')}
    debito = {a: euro(t['debito'](na_item='GD', time=str(a))) for a in anni}

    # PIL e popolazione: servono a dare una misura alla cifra, e mancano
    # solo se Eurostat non li pubblica per quell'anno.
    pil = {a: euro(t['pil'](na_item='B1GQ', unit='CP_MEUR', time=str(a))) for a in anni}
    pop = {}
    for a in anni:
        v = t['popolazione'](indic_de='AVG', time=str(a))
        pop[a] = int(round(v)) if v else None

    # Costruzione anno per anno, poi le serie storiche in un secondo giro.
    per_anno, magazzino = {}, {}
    for a in anni:
        anno = str(a)
        con_gruppi = a >= PRIMO_ANNO_GRUPPI
        alberi = {
            'cosa': albero_cosa(t, anno, con_gruppi),
            'chi': albero_chi(t, anno, con_gruppi),
            'come': albero_come(t, anno),
            'origine': albero_entrate(t, anno),
        }
        for sez, nodi in alberi.items():
            raccogli(nodi, sez, a, magazzino)
        per_anno[a] = alberi

    # il ponte fra le viste guarda solo l'albero per finalità
    ponte_pa = {}
    for a, alberi in per_anno.items():
        for div in alberi['cosa']:
            ponte_pa.setdefault(div['id'], {})[a] = div['importo']
            for gru in div.get('figli') or []:
                if gru['id'].startswith('cosa-'):
                    ponte_pa.setdefault(gru['id'], {})[a] = gru['importo']

    os.makedirs(ASSETS, exist_ok=True)
    ultimo_file = None
    for a in anni:
        alberi = per_anno[a]
        for sez, nodi in alberi.items():
            timbra(nodi, sez, magazzino, anni)
            spoglia(nodi)
        lordo = sum(t['spesa'](sector=s, cofog99='TOTAL', na_item='TE', time=str(a)) or 0.0
                    for s in SOTTOSETTORI)
        interni = euro(lordo - totale(t, 'TOTAL', str(a)))
        bilancio = {
            'entrate': agg('TR', a), 'uscite': agg('TE', a), 'saldo': agg('B9', a),
            'debito': debito.get(a),
            'storico_entrate': storico['TR'], 'storico_uscite': storico['TE'],
            'storico_saldo': storico['B9'],
        }
        dati = impagina(a, alberi, euro(totale(t, 'TOTAL', str(a))), anni,
                        totali, pil.get(a), pop.get(a), interni, ultimo,
                        a >= PRIMO_ANNO_GRUPPI, bilancio)
        percorso = os.path.join(ASSETS, 'pa_%d.json' % a)
        with open(percorso, 'w', encoding='utf-8') as f:
            json.dump(dati, f, ensure_ascii=False, separators=(',', ':'))
        ultimo_file = percorso
        print('  %d  uscite %13d €   entrate %13d €   saldo %13d €   %.0f KB'
              % (a, bilancio['uscite'], bilancio['entrate'], bilancio['saldo'],
                 os.path.getsize(percorso) / 1e3))

    if ultimo_file:
        with open(ultimo_file, encoding='utf-8') as f:
            copia = f.read()
        with open(os.path.join(ASSETS, 'pa.json'), 'w', encoding='utf-8') as f:
            f.write(copia)
        print('  assets/pa.json = pa_%d.json' % ultimo)

    scrivi_ponte(anni, ponte_pa)


if __name__ == '__main__':
    main()

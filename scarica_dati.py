#!/usr/bin/env python3
"""
Scarica i dati della pagina dal portale OpenBDAP della Ragioneria generale
dello Stato (bdap-opendata.rgs.mef.gov.it), in modo ripetibile:

    python3 scarica_dati.py              # tutto quello che manca in data/
    python3 scarica_dati.py --solo 2026  # un solo anno
    python3 scarica_dati.py --forza      # riscarica anche i file presenti

Per ogni anno scarica:
  - rendiconto_YYYY.csv  dal dataset "Rendiconto pubblicato triennio
    G8 OD action plan Capitolo" (consuntivo, con ripartizioni COFOG);
  - previsione_YYYY.csv  dal dataset "Legge di Bilancio Pubblicata
    Elaborabile Spese Capitolo" (previsione, quando esiste).

Il portale è un Drupal che consegna il file CSV attraverso tre passaggi
(pagina dataset → form "Pagina download" → URL di export): lo script li
fa tutti, con cookie e token del form. Nessuna dipendenza esterna.
"""

import argparse, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

BASE = 'https://bdap-opendata.rgs.mef.gov.it'
UA = {'User-Agent': 'Mozilla/5.0 (script di scarico dati pubblici)'}
DEST = os.environ.get('DATA_DIR',
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))

SLUG_RENDICONTO = '%d-rendiconto-pubblicato-triennio-g8-od-action-plan-capitolo'
SLUG_PREVISIONE = '%d-legge-di-bilancio-pubblicata-elaborabile-spese-capitolo'

ANNI = list(range(2000, 2028))


def richiesta(url, dati=None, cookie=None):
    """GET o POST (dati = dict), con eventuale cookie jar in formato semplice."""
    req = urllib.request.Request(url, headers=dict(UA))
    if cookie:
        req.add_header('Cookie', cookie)
    corpo = urllib.parse.urlencode(dati).encode() if dati else None
    if corpo:
        req.data = corpo
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read(), r.headers


def cookie_di_risposta(headers):
    crudo = headers.get('Set-Cookie', '')
    if ';' in crudo:
        nome_val = crudo.split(';')[0]
        return nome_val.strip()
    return ''


def url_export(percorso_dataset):
    """Dalla pagina del dataset arriva all'URL finale del CSV."""
    try:
        html, _ = richiesta(percorso_dataset)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

    # 1. link download.php?_url=<pagina download>
    m = re.search(r'href="([^"]*download\.php\?_url=[^"]+)"', html.decode('utf-8', 'replace'))
    if not m:
        raise SystemExit('Nessun link di download in %s' % percorso_dataset)
    href = m.group(1).replace('&amp;', '&')
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    pagina = q['_url'][0]

    # 2. pagina "Pagina download": serve il form_build_id e un cookie
    corpo, headers = richiesta(pagina)
    cookie = cookie_di_risposta(headers)
    pagina_html = corpo.decode('utf-8', 'replace')
    campi = {}
    for nome in ('mid', 'nid', 'fid', 'form_build_id'):
        mm = re.search(r'name="%s" value="([^"]*)"' % nome, pagina_html)
        if mm:
            campi[nome] = mm.group(1)
    if 'form_build_id' not in campi:
        raise SystemExit('Form non trovato in %s' % pagina)
    campi['export_type'] = 'csv'
    campi['filters'] = ''
    campi['op'] = 'Scarica'
    campi['form_id'] = 'metadata_download_form'

    # 3. POST del form: risponde JSON con l'URL di export
    corpo, _ = richiesta(pagina, dati=campi, cookie=cookie)
    risposta = json.loads(corpo.decode('utf-8', 'replace'))
    if 'URL' not in risposta:
        raise SystemExit('Risposta inattesa: %s' % risposta)
    return risposta['URL'], cookie


def scarica(anno):
    # prima il rendiconto; se per quell'anno non c'è ancora, la previsione
    for slug, nome in ((SLUG_RENDICONTO, 'rendiconto_%d.csv' % anno),
                       (SLUG_PREVISIONE, 'previsione_%d.csv' % anno)):
        sorgente = '%s/content/%s' % (BASE, slug % anno)
        dest = os.path.join(DEST, nome)
        if os.path.exists(dest) and not FORZA:
            print('%s: già presente, salto (usa --forza per riscaricare)' % nome)
            return

        print('%s: cerco il file…' % nome)
        esito = url_export(sorgente)
        if esito is None:
            print('  pagina inesistente, provo la prossima sorgente')
            continue
        url, cookie = esito
        print('  scarico %s' % url)
        corpo, headers = richiesta(url, cookie=cookie)
        tipo = headers.get('Content-Type', '')
        if 'csv' not in tipo and not corpo[:2000].lstrip().startswith(b'"'):
            anteprima = corpo[:300].decode('utf-8', 'replace')
            raise SystemExit('  Il file non sembra un CSV (%s): %s' % (tipo, anteprima))
        os.makedirs(DEST, exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(corpo)
        print('  scritto %s (%.1f MB) — fonte: %s'
              % (dest, len(corpo) / 1e6, sorgente))
        return
    print('Nessuna sorgente disponibile per il %d.' % anno)


def main():
    global FORZA
    ap = argparse.ArgumentParser(description='Scarica i dati dal portale OpenBDAP.')
    ap.add_argument('--solo', type=int, help='un solo anno, es. 2026')
    ap.add_argument('--forza', action='store_true', help='riscarica anche i file presenti')
    ap.add_argument('--no-compila', action='store_true',
                    help='scarica soltanto, senza rilanciare il compilatore')
    arg = ap.parse_args()
    FORZA = arg.forza

    anni = [arg.solo] if arg.solo else ANNI
    for i, a in enumerate(anni):
        if i:
            time.sleep(2)   # garbo verso il portale
        try:
            scarica(a)
        except SystemExit as e:
            print(e)
    print('\nFonte dei dati: %s e pagine annue collegate.' % BASE)

    if arg.no_compila:
        return
    # elaborazione in coda: la pagina legge solo i JSON in assets/
    print('\n─ elaborazione (costruisci_rendiconto.py) ─')
    compilatore = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'costruisci_rendiconto.py')
    esito = os.spawnl(os.P_WAIT, sys.executable, sys.executable, compilatore, DEST)
    if esito != 0:
        print('Il compilatore è fallito (uscita %d): i JSON non sono stati aggiornati.' % esito)
        sys.exit(esito)


main()

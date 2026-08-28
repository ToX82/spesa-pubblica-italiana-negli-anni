#!/usr/bin/env python3
"""
Scarica da Eurostat i dati della spesa delle amministrazioni pubbliche
italiane (Stato, Regioni, Comuni, enti previdenziali) e ricompila i JSON
della vista «Tutta la spesa pubblica».

    python3 scarica_eurostat.py              # scarica quel che manca + compila
    python3 scarica_eurostat.py --forza      # riscarica tutto
    python3 scarica_eurostat.py --no-compila # solo scaricamento

I file grezzi (formato JSON-stat) finiscono in data/eurostat/ e restano
nel repository: chi clona può ricompilare senza rete.

Le tabelle scaricate sono cinque:

  spesa.json         gov_10a_exp, na_item=TE — la spesa totale per
                     settore (S13 e i tre sottosettori) e per funzione
                     COFOG, dal 1995.
  trasferimenti.json gov_10a_exp, le voci D4/D7/D9 «di cui verso il
                     sottosettore X» — servono a consolidare: senza,
                     i trasferimenti fra Stato e Regioni si contano due
                     volte.
  economica.json     gov_10a_exp, le undici voci della classificazione
                     economica SEC 2010 (stipendi, acquisti, pensioni,
                     interessi, investimenti…) per S13.
  aggregati.json     gov_10a_main — entrate totali e le otto voci in cui
                     si scompongono, con i sottolivelli (IRPEF, IRES,
                     IVA, contributi), più spesa totale e indebitamento
                     netto. È la tabella degli aggregati: arriva prima di
                     quella per funzione e contiene il saldo ufficiale.
  debito.json        gov_10dd_edpt1 — debito pubblico consolidato, lo
                     stock che il saldo alimenta ogni anno.
  pil.json           nama_10_gdp, B1GQ a prezzi correnti — per esprimere
                     la spesa in percentuale del PIL.
  popolazione.json   demo_gind, popolazione media annua (fonte Istat) —
                     per la spesa per abitante.
"""

import json, os, sys, urllib.request, urllib.error

BASE = ('https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/'
        '%s?format=JSON&lang=EN&geo=IT')

# I tre sottosettori che l'Italia trasmette: Stato centrale, enti
# territoriali, enti di previdenza. S1312 (governi federati) non esiste.
SOTTOSETTORI = ['S1311', 'S1313', 'S1314']

# Le undici voci in cui la contabilità nazionale scompone la spesa
# totale: sommate danno TE al centesimo, per ogni funzione e ogni anno.
ECONOMICHE = ['P2', 'D1', 'D29_D5_D8', 'D3', 'D4', 'D62', 'D632', 'D7',
              'P5', 'NP', 'D9']

# Le otto voci in cui si scompongono le entrate totali (sommate danno TR
# al centesimo), i loro sottolivelli, e i tre aggregati del saldo.
ENTRATE = ['P11_P12_P131', 'D2REC', 'D39REC', 'D4REC', 'D5REC', 'D61REC',
           'D7REC', 'D9REC']
ENTRATE_DETTAGLIO = ['D51A_C1REC', 'D51B_C2REC', 'D21REC', 'D211REC',
                     'D29REC', 'D611REC', 'D613REC']
AGGREGATI = ['TR', 'TE', 'B9']

def voci_trasferimento():
    return ['%s_%s' % (d, s) for d in ('D4', 'D7', 'D9') for s in SOTTOSETTORI]

TABELLE = {
    'spesa.json': BASE % 'gov_10a_exp' + '&unit=MIO_EUR&na_item=TE',
    'trasferimenti.json': BASE % 'gov_10a_exp' + '&unit=MIO_EUR'
        + ''.join('&na_item=' + v for v in voci_trasferimento()),
    'economica.json': BASE % 'gov_10a_exp' + '&unit=MIO_EUR&sector=S13'
        + ''.join('&na_item=' + v for v in ECONOMICHE),
    'aggregati.json': BASE % 'gov_10a_main' + '&unit=MIO_EUR&sector=S13'
        + ''.join('&na_item=' + v for v in AGGREGATI + ENTRATE + ENTRATE_DETTAGLIO),
    'debito.json': BASE % 'gov_10dd_edpt1' + '&unit=MIO_EUR&sector=S13&na_item=GD',
    'pil.json': BASE % 'nama_10_gdp' + '&unit=CP_MEUR&na_item=B1GQ',
    'popolazione.json': BASE % 'demo_gind' + '&indic_de=AVG',
}


def scarica(url, destinazione):
    richiesta = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; spesa-pubblica/1.0)',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(richiesta, timeout=180) as r:
        grezzo = r.read()
    dati = json.loads(grezzo.decode('utf-8'))
    if 'value' not in dati or not dati['value']:
        raise SystemExit('Risposta senza dati da %s' % url)
    # riscritto compatto: gli originali arrivano con molta indentazione
    with open(destinazione, 'w', encoding='utf-8') as f:
        json.dump(dati, f, ensure_ascii=False, separators=(',', ':'))
    return len(dati['value'])


def main():
    qui = os.path.dirname(os.path.abspath(__file__))
    cartella = os.path.join(qui, 'data', 'eurostat')
    os.makedirs(cartella, exist_ok=True)
    forza = '--forza' in sys.argv

    for nome, url in TABELLE.items():
        percorso = os.path.join(cartella, nome)
        if os.path.exists(percorso) and not forza:
            print('%-20s già presente (--forza per riscaricarlo)' % nome)
            continue
        print('%-20s scarico…' % nome, end=' ', flush=True)
        try:
            n = scarica(url, percorso)
        except urllib.error.URLError as e:
            raise SystemExit('\nScaricamento fallito (%s). Riprova più tardi.' % e)
        print('%d valori, %.0f KB' % (n, os.path.getsize(percorso) / 1e3))

    if '--no-compila' in sys.argv:
        return
    print()
    os.execv(sys.executable, [sys.executable,
                              os.path.join(qui, 'costruisci_spesa_pa.py')])


if __name__ == '__main__':
    main()

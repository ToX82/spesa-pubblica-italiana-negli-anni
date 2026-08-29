/* =========================================================
   Dove vanno i soldi — due viste sulla stessa domanda:
   il bilancio dello Stato e la spesa di tutte le
   amministrazioni pubbliche.
   Nessuna dipendenza, nessuna compilazione.
   ========================================================= */
(function () {
  'use strict';

  // Le due viste del sito. Cambiano solo i file di dati: la pagina,
  // i comportamenti e i testi vengono tutti dal JSON caricato.
  var VISTE = {
    pa:    { prefisso: 'pa',   nome: 'Tutta la spesa pubblica' },
    stato: { prefisso: 'data', nome: 'Il bilancio dello Stato' }
  };
  var PREDEFINITA = 'pa';   // senza ?vista= si apre la spesa pubblica
  var VISTA = (location.search.match(/[?&]vista=([a-z]+)/) || [])[1];
  if (!VISTE[VISTA]) VISTA = PREDEFINITA;

  function param(nome) {
    return (location.search.match(new RegExp('[?&]' + nome + '=([\\w-]+)')) || [])[1] || '';
  }

  var COLORI = ['--c1', '--c2', '--c3', '--c4', '--c5', '--c6', '--c7', '--c8',
                '--c9', '--c10', '--c11', '--c12', '--c13'];
  var MAX_FETTE = 13;   // fette disegnate nella barra prima di raggruppare
  var MAX_RIGHE = 24;   // voci mostrate prima di "mostra tutte"

  function maxFette() {
    return window.matchMedia && window.matchMedia('(max-width:640px)').matches
      ? 6 : MAX_FETTE;
  }

  var dom = {};
  ['sommario', 'cifra-totale', 'cifra-nota', 'briciole', 'barra',
   'barra-legenda', 'contesto', 'contesto-grafico', 'contesto-parole',
   'contesto-andamento', 'contesto-griglia', 'voce-testata', 'voce-titolo', 'testata-cifre',
   'nota-voce', 'voci', 'vuoto', 'fonte-nome', 'fonte-link', 'fonte-metodo', 'esplora-h',
   'scelta', 'scelta-involucro', 'titolo', 'apertura-testo', 'come-leggere',
   'contesto-ponte', 'fonte-portale', 'fonte-altra', 'fonte-descrizioni',
   'vista-nota', 'vista-altra', 'testata-contesto', 'conti', 'racconto',
   'tempo', 'tempo-grafico', 'tempo-legenda', 'anno-scelta', 'anno-prec', 'anno-succ'
  ].forEach(function (id) { dom[id] = document.getElementById(id); });

  var dati = null;
  var ponte = null;   // assets/ponte.json: le funzioni COFOG nelle due viste
  var tabBtns = [];
  var stato = { lato: null, sezione: null, percorso: [], aperta: null, tutte: false,
                andamento: 'euro' };   // come si legge il grafico: euro | quota

  /* ── Numeri ────────────────────────────────────────────── */

  var nf = new Intl.NumberFormat('it-IT');
  // it-IT non separa le migliaia sotto le cinque cifre: per gli importi
  // «5196 €» si legge peggio di «5.196 €», quindi si forza il gruppo.
  var nfMigliaia = nf;
  try { nfMigliaia = new Intl.NumberFormat('it-IT', { useGrouping: 'always' }); }
  catch (e) { /* motori più vecchi: resta il formato predefinito */ }
  var nf1 = new Intl.NumberFormat('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var nf2 = new Intl.NumberFormat('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function euroBreve(v) {
    var s = v < 0 ? '−' : ''; v = Math.abs(v);
    if (v >= 1e9) return s + nf2.format(v / 1e9) + ' mld €';
    if (v >= 1e6) return s + nf1.format(v / 1e6) + ' mln €';
    if (v >= 1e3) return s + nf.format(Math.round(v / 1e3)) + ' mila €';
    return s + nf.format(v) + ' €';
  }

  function euroPieno(v) { return nf.format(v) + ' €'; }

  function perc(parte, tutto) {
    if (!tutto) return '—';
    var p = (parte / tutto) * 100;
    if (p > 0 && p < 0.1) return '< 0,1%';
    return (p >= 10 ? nf1.format(p) : nf2.format(p)) + '%';
  }

  function perAbitante(v) {
    if (!dati.meta.popolazione) return null;
    var q = v / dati.meta.popolazione;
    // sopra i mille euro i decimali sono rumore
    return (q >= 1000 ? nfMigliaia.format(Math.round(q))
          : q >= 10 ? nf1.format(q) : nf2.format(q)) + ' €';
  }

  function quotaPil(v) {
    if (!dati.meta.pil) return null;
    var q = (v / dati.meta.pil) * 100;
    if (q > 0 && q < 0.05) return '< 0,05% del PIL';
    return (q >= 10 ? nf1.format(q) : nf2.format(q)) + '% del PIL';
  }

  /* ── I due lati del bilancio ───────────────────────────── */

  // La vista della spesa pubblica ha due lati, entrate e uscite, con il
  // saldo come risultato. Quella del bilancio dello Stato ne ha uno solo:
  // dove meta.lati manca, tutto il resto continua a funzionare uguale.
  function lati() { return dati.meta.lati || null; }

  function latoCorrente() {
    var L = lati();
    if (!L) return {
      id: null,
      importo: sezioneCorrente().importo,
      storico: dati.meta.totale_storico,
      etichetta_totale: dati.meta.etichetta_totale
    };
    return L.filter(function (l) { return l.id === stato.lato; })[0] || L[0];
  }

  function latoPredefinito() {
    var L = lati();
    if (!L) return null;
    var id = dati.meta.lato_predefinito;
    return L.filter(function (l) { return l.id === id; })[0] ? id : L[0].id;
  }

  function sezioniDelLato() {
    return dati.sezioni.filter(function (s) {
      return !s.lato || !stato.lato || s.lato === stato.lato;
    });
  }

  function sezionePredefinita() {
    var s = sezioniDelLato()[0];
    return s ? s.id : (dati.sezioni[0] || {}).id;
  }

  /* ── Albero ────────────────────────────────────────────── */

  function sezioneCorrente() {
    return dati.sezioni.filter(function (s) { return s.id === stato.sezione; })[0]
        || sezioniDelLato()[0] || dati.sezioni[0];
  }

  function catena() {
    var out = [sezioneCorrente()];
    for (var i = 0; i < stato.percorso.length; i++) {
      var figli = out[out.length - 1].figli || [];
      var trovato = figli.filter(function (f) { return f.id === stato.percorso[i]; })[0];
      if (!trovato) { stato.percorso = stato.percorso.slice(0, i); break; }
      out.push(trovato);
    }
    return out;
  }

  function haFigli(n) { return !!(n.figli && n.figli.length); }

  /* ── Serie storiche ───────────────────────────────────── */

  var SVG_NS = 'http://www.w3.org/2000/svg';

  function svgEl(tag, attrs) {
    var el = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  function serieStorico(nodo) {
    var ann = dati.meta.anni;
    if (!ann || !nodo || !nodo.storico) return null;
    var p = [];
    for (var i = 0; i < ann.length; i++) {
      var v = nodo.storico[i];
      if (v !== null && v !== undefined) p.push({ anno: ann[i], valore: v, i: i });
    }
    return p.length >= 2 ? p : null;
  }

  function ePrevisione(anno) {
    var p = dati.meta.anni_previsione;
    return !!(p && p.indexOf(anno) >= 0);
  }

  // Segmenti di percorso: solidi fra consuntivi, in tratteggio verso
  // e fra gli anni di previsione. I vuoti (anni mancanti) restano vuoti.
  function percorsiStorico(p, x, y) {
    var out = { solido: '', tratteggio: '' };
    for (var j = 1; j < p.length; j++) {
      if (p[j].anno - p[j - 1].anno !== 1) continue;
      var d = ' M' + x(p[j - 1]).toFixed(1) + ' ' + y(p[j - 1].valore).toFixed(1) +
              ' L' + x(p[j]).toFixed(1) + ' ' + y(p[j].valore).toFixed(1);
      if (ePrevisione(p[j].anno)) out.tratteggio += d;
      else out.solido += d;
    }
    return out;
  }

  // Piccola linea dentro la riga dell'elenco: la series completa,
  // con un punto sull'anno di questa pagina.
  function scia(nodo) {
    var p = serieStorico(nodo);
    if (!p) return null;
    var W = 104, H = 26, P = 3;
    var min = Infinity, max = -Infinity;
    p.forEach(function (q) {
      if (q.valore < min) min = q.valore;
      if (q.valore > max) max = q.valore;
    });
    if (max === min) max = min + 1;
    var nSlot = dati.meta.anni.length;
    function x(q) { return P + (q.i / (nSlot - 1)) * (W - 2 * P); }
    function y(v) { return H - P - ((v - min) / (max - min)) * (H - 2 * P); }
    var svg = svgEl('svg', { 'class': 'spark', viewBox: '0 0 ' + W + ' ' + H, 'aria-hidden': 'true' });
    var percorsi = percorsiStorico(p, x, y);
    if (percorsi.solido) svg.appendChild(svgEl('path', {
      d: percorsi.solido, fill: 'none', stroke: 'currentColor',
      'stroke-width': 1.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'
    }));
    if (percorsi.tratteggio) svg.appendChild(svgEl('path', {
      d: percorsi.tratteggio, fill: 'none', stroke: 'currentColor',
      'stroke-width': 1.5, 'stroke-dasharray': '3 3', 'stroke-linecap': 'round', opacity: .8
    }));
    var qui = p[p.length - 1];
    for (var j = 0; j < p.length; j++) if (p[j].anno === dati.meta.anno) qui = p[j];
    svg.appendChild(svgEl('circle', ePrevisione(qui.anno)
      ? { cx: x(qui).toFixed(1), cy: y(qui.valore).toFixed(1), r: 2.2,
          fill: 'var(--carta)', stroke: 'currentColor', 'stroke-width': 1.4 }
      : { cx: x(qui).toFixed(1), cy: y(qui.valore).toFixed(1), r: 2.2, fill: 'currentColor' }));
    var host = document.createElement('span');
    host.className = 'voce-trenda';
    host.appendChild(svg);
    host.addEventListener('mouseenter', function () {
      mostraTip(host, qui.anno + ' · ' + euroBreve(qui.valore));
    });
    host.addEventListener('mouseleave', nascondiTip);
    return host;
  }

  // Il totale su cui si misura la quota: quello del lato aperto
  // (entrate o uscite) dove i lati esistono, altrimenti il totale
  // generale della vista.
  function totaleStorico() {
    return latoCorrente().storico || dati.meta.totale_storico;
  }

  // I decimali si decidono una volta per grafico, sulla scala della
  // serie: «dal 9,88% al 13,2%» si legge male, «dal 9,9% al 13,2%» no.
  function pctBreve(v, dec) {
    return (dec === 2 ? nf2 : nf1).format(v) + '%';
  }

  // Punti percentuali: la differenza fra due quote non è una
  // variazione percentuale, e chiamarla così sarebbe sbagliato.
  function punti(v, dec) {
    return (v > 0 ? '+' : v < 0 ? '−' : '') +
      (dec === 2 ? nf2 : nf1).format(Math.abs(v)) + ' punti';
  }

  // Le due letture dell'andamento. In euro si vede quanto si spende;
  // in quota si vede quanto pesa, ed è una domanda diversa: una voce
  // può crescere di anno in anno e perdere terreno lo stesso.
  var MODI = [
    { id: 'euro',  nome: 'Valore',  spiega: 'Importi in euro, anno per anno' },
    { id: 'quota', nome: 'Quota %', spiega: 'Peso della voce sul totale, anno per anno' }
  ];

  function sceltaModo(modo) {
    var box = document.createElement('div');
    box.className = 'andamento-modo';
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', 'Come leggere l’andamento');
    MODI.forEach(function (m) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'andamento-modo-voce' + (m.id === modo ? ' andamento-modo-qui' : '');
      b.textContent = m.nome;
      b.title = m.spiega;
      b.setAttribute('aria-pressed', m.id === modo ? 'true' : 'false');
      b.addEventListener('click', function () {
        if (stato.andamento === m.id) return;
        stato.andamento = m.id;
        ridisegnaAndamenti();
      });
      box.appendChild(b);
    });
    return box;
  }

  // Il modo è una preferenza di lettura, non uno stato della voce:
  // vale per tutti i grafici aperti, che si ridisegnano insieme.
  function ridisegnaAndamenti() {
    nascondiTip();
    var attivo = document.activeElement;
    var figure = [].slice.call(document.querySelectorAll('.andamento'));
    figure.forEach(function (vecchia) {
      if (!vecchia.parentNode || !vecchia.datiNodo) return;
      var bottoni = [].slice.call(vecchia.querySelectorAll('.andamento-modo-voce'));
      var iFuoco = bottoni.indexOf(attivo);
      var nuova = graficoAndamento(vecchia.datiNodo, vecchia.datiLarghezza);
      if (!nuova) return;
      vecchia.parentNode.replaceChild(nuova, vecchia);
      if (iFuoco >= 0) {
        var b = nuova.querySelectorAll('.andamento-modo-voce')[iFuoco];
        if (b) b.focus();
      }
    });
  }

  // Grafico d'andamento: anni sull'asse, importi (o quote) sull'altro,
  // vuoti dove la voce non esisteva. Lo snippet va nel blocco di
  // contesto e nelle schede.
  function graficoAndamento(nodo, larghezza) {
    var grezza = serieStorico(nodo);
    if (!grezza) return null;
    var ann = dati.meta.anni, ts = totaleStorico();

    // La quota vuole importo e totale dello stesso anno: dove il totale
    // manca il punto non si può calcolare e l'anno resta vuoto.
    var quote = [];
    if (ts) grezza.forEach(function (q) {
      if (ts[q.i]) quote.push({ anno: q.anno, i: q.i, valore: (q.valore / ts[q.i]) * 100, euro: q.valore });
    });
    var quotaPossibile = quote.length >= 2;
    var modo = (stato.andamento === 'quota' && quotaPossibile) ? 'quota' : 'euro';
    var p = modo === 'quota' ? quote : grezza.map(function (q) {
      return { anno: q.anno, i: q.i, valore: q.valore, euro: q.valore };
    });

    var W = larghezza || 560;
    var H = larghezza ? (larghezza < 620 ? 190 : 250) : 176;
    var ML = 52, MR = 16, MT = 18, MB = 34;
    var iw = W - ML - MR, ih = H - MT - MB;
    var vmin = Infinity, vmax = -Infinity;
    p.forEach(function (q) {
      if (q.valore < vmin) vmin = q.valore;
      if (q.valore > vmax) vmax = q.valore;
    });
    if (vmax === vmin) vmax = vmin + (modo === 'quota' ? 0.1 : 1);
    var pad = (vmax - vmin) * 0.1;
    var lo = vmin - pad, hi = vmax + pad;
    function x(q) { return ML + (q.i / (ann.length - 1)) * iw; }
    function y(v) { return MT + ih - ((v - lo) / (hi - lo)) * ih; }

    var primo = p[0], ultimo = p[p.length - 1];
    var pct = primo.valore ? ((ultimo.valore - primo.valore) / primo.valore) * 100 : null;
    var divisore = Math.abs(vmax) >= 1e9 ? 1e9 : 1e6;
    var dec = Math.abs(vmax) >= 10 ? 1 : 2;

    function segna(v) { return modo === 'quota' ? pctBreve(v, dec) : euroBreve(v); }
    function segnaAsse(v) {
      return modo === 'quota' ? pctBreve(v, dec) : nf.format(Math.round(v / divisore));
    }

    var fig = document.createElement('figure');
    fig.className = 'andamento';
    // servono a ridisegnare lo stesso grafico quando cambia il modo
    fig.datiNodo = nodo;
    fig.datiLarghezza = larghezza;
    if (quotaPossibile) fig.appendChild(sceltaModo(modo));

    var svg = svgEl('svg', {
      viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img'
    });
    svg.setAttribute('aria-label', (modo === 'quota' ? 'Quota ' + etichettaTotale() + ' dal ' : 'Andamento dal ') +
      primo.anno + ' al ' + ultimo.anno +
      ': da ' + segna(primo.valore) + ' a ' + segna(ultimo.valore) +
      (modo === 'quota' ? ', ' + punti(ultimo.valore - primo.valore, dec)
        : pct !== null ? ', ' + (pct > 0 ? '+' : '−') + nf1.format(Math.abs(pct)) + '%' : '') + '.');

    [vmax, (vmax + vmin) / 2, vmin].forEach(function (v, i) {
      svg.appendChild(svgEl('line', {
        x1: ML, x2: W - MR, y1: y(v).toFixed(1), y2: y(v).toFixed(1),
        stroke: 'var(--filo)', 'stroke-width': 1
      }));
      if (i !== 1) {
        var t = svgEl('text', { x: ML - 8, y: (y(v) + 3.5).toFixed(1), 'text-anchor': 'end', 'class': 'asse' });
        t.textContent = segnaAsse(v);
        svg.appendChild(t);
      }
    });

    var salto = Math.max(1, Math.ceil(ann.length / 16));
    var fisse = [0, ann.length - 1];
    var iQui = ann.indexOf(dati.meta.anno);
    if (iQui >= 0) fisse.push(iQui);
    var etichette = {};
    fisse.forEach(function (i) { etichette[i] = true; });
    for (var k = salto; k < ann.length - 1; k += salto) {
      var libera = fisse.every(function (j) {
        return Math.abs(k - j) >= salto;
      });
      if (libera) etichette[k] = true;
    }
    ann.forEach(function (a, i) {
      if (!etichette[i]) return;
      var t = svgEl('text', {
        x: (ML + (i / (ann.length - 1)) * iw).toFixed(1), y: H - 12,
        'text-anchor': 'middle', 'class': 'asse' + (a === dati.meta.anno ? ' asse-qui' : '')
      });
      t.textContent = a;
      svg.appendChild(t);
    });

    var percorsi = percorsiStorico(p, x, y);
    if (percorsi.solido) svg.appendChild(svgEl('path', {
      d: percorsi.solido, fill: 'none', stroke: 'var(--inchiostro)',
      'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'
    }));
    if (percorsi.tratteggio) svg.appendChild(svgEl('path', {
      d: percorsi.tratteggio, fill: 'none', stroke: 'var(--inchiostro)',
      'stroke-width': 2, 'stroke-dasharray': '5 4', 'stroke-linecap': 'round', opacity: .8
    }));
    p.forEach(function (q) {
      var corrente = q.anno === dati.meta.anno;
      if (corrente) {
        svg.appendChild(svgEl('circle', {
          cx: x(q).toFixed(1), cy: y(q.valore).toFixed(1),
          r: 3.5, fill: 'var(--accento)'
        }));
      } else if (ePrevisione(q.anno)) {
        svg.appendChild(svgEl('circle', {
          cx: x(q).toFixed(1), cy: y(q.valore).toFixed(1), r: 2.4,
          fill: 'var(--superficie)', stroke: 'var(--inchiostro)', 'stroke-width': 1.4
        }));
      } else {
        svg.appendChild(svgEl('circle', {
          cx: x(q).toFixed(1), cy: y(q.valore).toFixed(1), r: 2.2, fill: 'var(--inchiostro)'
        }));
      }
    });
    var tx = x(ultimo), anchor = tx > W - 100 ? 'end' : 'start';
    var vt = svgEl('text', {
      x: (tx + (anchor === 'end' ? -9 : 9)).toFixed(1), y: (y(ultimo.valore) - 8).toFixed(1),
      'text-anchor': anchor, 'class': 'valore'
    });
    vt.textContent = segna(ultimo.valore);
    svg.appendChild(vt);

    var passo = iw / (ann.length - 1);
    ann.forEach(function (a, i) {
      var q = null;
      for (var j = 0; j < p.length; j++) if (p[j].anno === a) q = p[j];
      if (!q) return;
      var rect = svgEl('rect', {
        x: (ML + i * passo - passo / 2).toFixed(1), y: MT,
        width: (passo + 1).toFixed(1), height: ih, fill: 'transparent'
      });
      var testo = modo === 'quota'
        ? a + ' · ' + pctBreve(q.valore, dec) + ' ' + etichettaTotale() + ' · ' + euroBreve(q.euro)
        : a + ' · ' + euroBreve(q.valore) +
          (ts && ts[i] ? ' · ' + perc(q.valore, ts[i]) + ' ' + etichettaTotale() : '');
      rect.addEventListener('mouseenter', function () { mostraTip(rect, testo); });
      rect.addEventListener('mouseleave', nascondiTip);
      svg.appendChild(rect);
    });

    fig.appendChild(svg);
    var cap = document.createElement('figcaption');
    var testo;
    if (modo === 'quota') {
      testo = 'Quota ' + etichettaTotale() + ' ' + primo.anno + '–' + ultimo.anno + ': ' +
        'dal ' + pctBreve(primo.valore, dec) + ' al ' + pctBreve(ultimo.valore, dec) +
        ' (' + punti(ultimo.valore - primo.valore, dec) + ')';
    } else {
      testo = 'Andamento ' + primo.anno + '–' + ultimo.anno + ': ' +
        (pct === null ? euroBreve(ultimo.valore)
          : (pct > 0 ? '+' : '−') + nf1.format(Math.abs(pct)) + '% (' +
            euroBreve(primo.valore) + ' → ' + euroBreve(ultimo.valore) + ')') +
        ' · importi in ' + (divisore === 1e9 ? 'miliardi' : 'milioni') + ' di €';
    }
    if (p.length < ann.length) testo += ' · anni con dato: ' + p.length + ' su ' + ann.length;
    var conPrevisione = p.some(function (q) { return ePrevisione(q.anno); });
    if (conPrevisione) {
      testo += ' · in tratteggio: ' +
        p.filter(function (q) { return ePrevisione(q.anno); })
         .map(function (q) { return q.anno; }).join(', ') + ', previsione';
    }
    cap.textContent = testo;
    fig.appendChild(cap);
    return fig;
  }

  /* ── Il ponte fra le due viste ─────────────────────────── */

  function etichettaTotale() {
    return latoCorrente().etichetta_totale || dati.meta.etichetta_totale
        || 'della spesa dello Stato';
  }

  // Le divisioni e i gruppi COFOG hanno lo stesso identificativo nelle
  // due viste (cosa-07, cosa-07-03): assets/ponte.json tiene in fila i
  // due importi, anno per anno. Sono misure diverse e non si sottraggono.
  function ponteDi(nodo) {
    if (!ponte || !nodo || !/^cosa-\d\d(-\d\d)?$/.test(nodo.id)) return null;
    var altra = VISTA === 'pa' ? 'stato' : 'pa';
    var anni = ponte['anni_' + altra];
    var serie = (ponte[altra] || {})[nodo.id];
    if (!anni || !serie) return null;
    var i = anni.indexOf(dati.meta.anno);
    if (i < 0 || serie[i] === null || serie[i] === undefined) return null;
    return { vista: altra, valore: serie[i] };
  }

  function bloccoPonte(nodo) {
    var p = ponteDi(nodo);
    if (!p) return null;

    var box = document.createElement('aside');
    box.className = 'ponte';

    var testa = document.createElement('p');
    testa.className = 'ponte-testa';
    var forte = document.createElement('strong');
    forte.textContent = euroBreve(p.valore);

    if (p.vista === 'stato') {
      testa.appendChild(document.createTextNode('Nel bilancio dello Stato la stessa ' +
        'funzione vale '));
      testa.appendChild(forte);
      testa.appendChild(document.createTextNode(' di impegni nel ' + dati.meta.anno + '.'));
    } else {
      testa.appendChild(document.createTextNode('Includendo Regioni, Comuni ed ' +
        'enti previdenziali, la stessa funzione vale '));
      testa.appendChild(forte);
      testa.appendChild(document.createTextNode(' nel ' + dati.meta.anno + '.'));
    }
    box.appendChild(testa);

    var nota = document.createElement('p');
    nota.className = 'ponte-nota';
    nota.textContent = p.vista === 'stato'
      ? 'Le due cifre non sono confrontabili per differenza. Il bilancio dello Stato ' +
        'adotta la competenza giuridica e include voci che i conti nazionali non ' +
        'registrano come spesa: il rimborso del capitale del debito e i trasferimenti ' +
        'agli altri enti. Serve a individuare i ministeri e i capitoli che stanno ' +
        'dietro alla funzione, non a calcolarne una quota.'
      : 'Le due cifre non sono confrontabili per differenza. I conti nazionali ' +
        'escludono il rimborso del capitale del debito e registrano una volta sola i ' +
        'trasferimenti fra enti: il bilancio dello Stato non è una quota di questa ' +
        'cifra, è un’altra misura della stessa funzione.';
    box.appendChild(nota);

    var a = document.createElement('a');
    a.className = 'ponte-vai';
    a.href = indirizzo(p.vista, dati.meta.anno, nodo.id);
    a.textContent = p.vista === 'stato'
      ? 'Apri la funzione nel bilancio dello Stato'
      : 'Apri la funzione in tutta la spesa pubblica';
    box.appendChild(a);
    return box;
  }

  /* ── Indirizzi condivisibili ───────────────────────────── */

  function indirizzo(vista, anno, voce) {
    var q = [];
    if (vista !== PREDEFINITA) q.push('vista=' + vista);
    if (anno) q.push('anno=' + anno);
    if (voce) q.push('voce=' + voce);
    return location.pathname + (q.length ? '?' + q.join('&') : '');
  }

  function voceCorrente() {
    if (stato.aperta) return stato.aperta;
    if (stato.percorso.length) return stato.percorso[stato.percorso.length - 1];
    var L = lati();
    var radice = L ? (dati.sezioni.filter(function (s) {
      return s.lato === dati.meta.lato_predefinito;
    })[0] || dati.sezioni[0]).id : dati.sezioni[0].id;
    return stato.sezione === radice ? '' : stato.sezione;
  }

  function segnaUrl(push) {
    if (!window.history || !history.replaceState) return;
    var url = indirizzo(VISTA, dati.meta.anno, voceCorrente());
    if (url === location.pathname + location.search) return;
    history[push ? 'pushState' : 'replaceState'](null, '', url);
  }

  // Ritrova un nodo dal suo identificativo, in qualsiasi sezione:
  // serve agli indirizzi condivisibili e al ponte fra le viste.
  function cerca(nodo, id, cammino) {
    var figli = nodo.figli || [];
    for (var i = 0; i < figli.length; i++) {
      var f = figli[i];
      if (f.id === id)
        return haFigli(f) ? { percorso: cammino.concat([f.id]), foglia: null }
                          : { percorso: cammino, foglia: f.id };
      if (haFigli(f)) {
        var r = cerca(f, id, cammino.concat([f.id]));
        if (r) return r;
      }
    }
    return null;
  }

  function vaiA(id) {
    if (!id) return false;
    for (var i = 0; i < dati.sezioni.length; i++) {
      var sez = dati.sezioni[i];
      if (sez.id === id) {
        if (sez.lato) stato.lato = sez.lato;
        stato.sezione = id; stato.percorso = []; stato.aperta = null; stato.tutte = false;
        return true;
      }
      var r = cerca(sez, id, []);
      if (r) {
        if (sez.lato) stato.lato = sez.lato;
        stato.sezione = sez.id;
        stato.percorso = r.percorso; stato.aperta = r.foglia; stato.tutte = false;
        return true;
      }
    }
    return false;
  }

  /* ── Disegno ───────────────────────────────────────────── */

  function disegna() {
    var cat = catena();
    var nodo = cat[cat.length - 1];
    var radice = cat[0];
    var figli = (nodo.figli || []).slice().sort(function (a, b) { return b.importo - a.importo; });

    dom['esplora-h'].textContent = radice.titolo ||
      (radice.domanda ? radice.domanda + ' i soldi' : 'Esplora il bilancio');
    briciole(cat);
    testataVoce(nodo, radice, cat);
    contesto(nodo, radice, cat);
    barra(nodo, figli);
    elenco(nodo, figli);
    costruisciConti();
  }

  function briciole(cat) {
    dom.briciole.textContent = '';
    cat.forEach(function (nodo, i) {
      if (i > 0) {
        var sep = document.createElement('span');
        sep.className = 'briciola-sep'; sep.textContent = '›';
        dom.briciole.appendChild(sep);
      }
      var etichetta = i === 0 ? 'Tutte le voci' : nodo.nome;
      if (i === cat.length - 1) {
        var qui = document.createElement('span');
        qui.className = 'briciola-qui';
        qui.setAttribute('aria-current', 'true');
        qui.textContent = etichetta;
        dom.briciole.appendChild(qui);
      } else {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'briciola'; b.textContent = etichetta;
        b.addEventListener('click', function () {
          stato.percorso = stato.percorso.slice(0, i);
          stato.aperta = null; stato.tutte = false; disegna(); segnaUrl(true);
        });
        dom.briciole.appendChild(b);
      }
    });
  }

  function coloreDi(i, n) {
    return i < Math.min(maxFette(), n) ? 'var(' + COLORI[i % COLORI.length] + ')' : 'var(--resto)';
  }

  function barra(nodo, figli) {
    dom.barra.textContent = '';
    delete dom.barra.dataset.attiva;

    if (!nodo.importo) {
      dom.barra.dataset.vuota = 'si';
    } else if (!figli.length) {
      delete dom.barra.dataset.vuota;
      var piena = document.createElement('div');
      piena.className = 'fetta fetta-resto'; piena.style.width = '100%';
      piena.style.setProperty('--fetta-colore', 'var(--c5)');
      piena.setAttribute('aria-hidden', 'true');
      dom.barra.appendChild(piena);
    } else {
      delete dom.barra.dataset.vuota;
      // Alcune voci possono essere negative — gli acquisti netti di beni
      // non prodotti lo sono quando le vendite superano gli acquisti. Una
      // larghezza negativa non esiste: la barra si misura sulla somma
      // delle sole voci positive, le altre restano nell'elenco.
      var base = figli.reduce(function (a, f) {
        return a + Math.max(0, f.importo);
      }, 0) || nodo.importo;
      figli.slice(0, maxFette()).forEach(function (f, i) {
        if (f.importo <= 0) return;
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'fetta';
        b.style.setProperty('--fetta-colore', coloreDi(i, figli.length));
        b.style.width = ((f.importo / base) * 100) + '%';
        b.dataset.id = f.id;
        var etichetta = f.nome + ' — ' + euroBreve(f.importo) + ' (' + perc(f.importo, nodo.importo) + ')' +
          (haFigli(f) ? ' · apri il dettaglio' : '');
        b.dataset.tip = etichetta;
        b.setAttribute('aria-label', etichetta);
        b.addEventListener('click', function () { attiva(f); });
        b.addEventListener('mouseenter', function () { evidenzia(f.id); mostraTip(b, etichetta); });
        b.addEventListener('focus', function () { evidenzia(f.id); mostraTip(b, etichetta); });
        b.addEventListener('mouseleave', spegni);
        b.addEventListener('blur', spegni);
        dom.barra.appendChild(b);
      });
      var resto = figli.slice(maxFette());
      if (resto.length) {
        var somma = resto.reduce(function (a, f) {
          return a + Math.max(0, f.importo);
        }, 0);
        var r = document.createElement('div');
        r.className = 'fetta fetta-resto';
        r.style.setProperty('--fetta-colore', 'var(--resto)');
        r.style.width = ((somma / base) * 100) + '%';
        var etichettaResto = 'Altre ' + resto.length + ' voci — ' + euroBreve(somma);
        r.dataset.tip = etichettaResto;
        r.setAttribute('aria-hidden', 'true');
        r.addEventListener('mouseenter', function () { spegni(); mostraTip(r, etichettaResto); });
        r.addEventListener('mouseleave', nascondiTip);
        dom.barra.appendChild(r);
      }
    }

    var etich = document.getElementById('composizione-etichetta');
    if (etich) etich.textContent = haFigli(nodo)
      ? 'Che cosa c’è dentro' : 'Dettaglio';

    dom['barra-legenda'].textContent = '';
    var negative = figli.filter(function (f) { return f.importo < 0; }).length;
    var sx = document.createElement('span');
    sx.textContent = !nodo.importo ? 'nessun importo per il ' + dati.meta.anno
      : figli.length ? figli.length + (figli.length === 1 ? ' voce' : ' voci')
        + (negative ? ', di cui ' + negative + (negative === 1 ? ' negativa' : ' negative')
           + ' — non disegnate nella barra' : '')
      : 'voce non suddivisa';
    var dx = document.createElement('span');
    dx.className = 'barra-totale';
    dx.textContent = euroPieno(nodo.importo);
    dom['barra-legenda'].appendChild(sx);
    dom['barra-legenda'].appendChild(dx);
  }

  function evidenzia(id) {
    dom.barra.dataset.attiva = 'si';
    var trovata = null;
    Array.prototype.forEach.call(dom.barra.children, function (el) {
      if (el.dataset.id === id) { el.dataset.evidenzia = 'si'; trovata = el; }
      else delete el.dataset.evidenzia;
    });
    return trovata;
  }
  function spegni() {
    delete dom.barra.dataset.attiva;
    Array.prototype.forEach.call(dom.barra.children, function (el) { delete el.dataset.evidenzia; });
    nascondiTip();
  }

  /* ── Suggerimento flottante ───────────────────────────── */

  var tip = document.createElement('div');
  tip.className = 'suggerimento';
  tip.setAttribute('role', 'tooltip');
  tip.setAttribute('aria-hidden', 'true');
  document.body.appendChild(tip);

  function mostraTip(el, testo) {
    tip.textContent = testo;
    var r = el.getBoundingClientRect();
    var metaLarghezza = Math.min(170, window.innerWidth / 2 - 12);
    var x = Math.min(Math.max(r.left + r.width / 2, metaLarghezza + 12),
                     window.innerWidth - metaLarghezza - 12);
    var sopra = r.top > 110;
    tip.style.left = Math.round(x) + 'px';
    tip.style.top = Math.round(sopra ? r.top - 10 : r.bottom + 10) + 'px';
    tip.style.transform = 'translate(-50%,' + (sopra ? '-100%' : '0') + ')';
    tip.style.opacity = '1';
  }

  function nascondiTip() { tip.style.opacity = '0'; }

  // collega una riga dell'elenco alla sua fetta: se la barra è in vista,
  // l'etichetta appare sulla fetta, non sulla riga (che già mostra tutto).
  function legaTip(id) {
    var fetta = evidenzia(id);
    if (!fetta || !fetta.dataset.id) return;
    var r = fetta.getBoundingClientRect();
    if (r.top < 0 || r.bottom > window.innerHeight || r.width === 0) return;
    mostraTip(fetta, fetta.dataset.tip || fetta.getAttribute('aria-label') || '');
  }

  // Il pannello risponde a quattro domande, in quest'ordine: che cosa
  // sto guardando, che cos'è, come è andata, di che cosa è fatto. Prima
  // la barra stava in cima, staccata dal suo elenco: erano la stessa
  // informazione a due risoluzioni, separate da tutto il resto.
  function testataVoce(nodo, radice, cat) {
    var profondo = cat.length > 1;
    dom['voce-testata'].hidden = !profondo;
    if (!profondo) return;
    dom['voce-titolo'].textContent = nodo.nome;
    var pezzi = [euroBreve(nodo.importo)];
    if (radice.importo)
      pezzi.push(perc(nodo.importo, radice.importo) + ' ' + etichettaTotale());
    var pa = perAbitante(nodo.importo);
    if (pa) pezzi.push(pa + ' per abitante');
    dom['testata-cifre'].textContent = pezzi.join('  ·  ');
  }

  function contesto(nodo, radice, cat) {
    var profondo = cat.length > 1;
    dom['contesto-grafico'].textContent = '';
    dom['contesto-ponte'].textContent = '';

    dom['nota-voce'].textContent = nodo.descrizione || '';
    dom['contesto-parole'].hidden = !nodo.descrizione;

    var pon = profondo ? bloccoPonte(nodo) : null;
    if (pon) dom['contesto-ponte'].appendChild(pon);
    if (pon && nodo.descrizione) dom['contesto-griglia'].dataset.due = 'si';
    else delete dom['contesto-griglia'].dataset.due;

    var g = null;
    if (profondo) {
      var pannello = document.getElementById('pannello');
      var largo = pannello ? pannello.clientWidth : 0;
      g = graficoAndamento(nodo, largo > 320 ? largo : null);
    }
    if (g) dom['contesto-grafico'].appendChild(g);
    dom['contesto-andamento'].hidden = !g;

    dom.contesto.hidden = !(nodo.descrizione || pon || g);
  }

  function elenco(nodo, figli) {
    dom.voci.textContent = '';

    if (!figli.length) {
      dom.voci.hidden = true;
      dom.vuoto.hidden = false;
      dom.vuoto.textContent = 'Questa voce non ha un livello di dettaglio ' +
        'ulteriore: ' + euroPieno(nodo.importo) + ' in tutto.';
      return;
    }
    dom.voci.hidden = false;
    dom.vuoto.hidden = true;

    var massimo = figli[0].importo || 1;
    var mostrati = stato.tutte ? figli : figli.slice(0, MAX_RIGHE);
    mostrati.forEach(function (f, i) { dom.voci.appendChild(riga(f, i, figli.length, nodo, massimo)); });

    if (mostrati.length < figli.length) {
      var li = document.createElement('li');
      li.className = 'voce voce-altre';
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'mostra-tutte';
      b.textContent = 'Mostra le altre ' + (figli.length - mostrati.length) + ' voci';
      b.addEventListener('click', function () { stato.tutte = true; disegna(); });
      li.appendChild(b);
      dom.voci.appendChild(li);
    }
  }

  function riga(f, i, tot, padre, massimo) {
    var li = document.createElement('li');
    li.className = 'voce entra';
    li.style.animationDelay = Math.min(i * 22, 240) + 'ms';
    li.dataset.aperta = stato.aperta === f.id ? 'si' : 'no';
    li.style.setProperty('--voce-colore', coloreDi(i, tot));

    var apribile = haFigli(f);

    var testa = document.createElement('button');
    testa.type = 'button'; testa.className = 'voce-testa';
    if (!apribile) testa.setAttribute('aria-expanded', stato.aperta === f.id ? 'true' : 'false');

    var tacca = document.createElement('span');
    tacca.className = 'voce-tacca';

    var corpo = document.createElement('span');
    corpo.className = 'voce-corpo';

    var nome = document.createElement('span');
    nome.className = 'voce-nome';
    nome.textContent = f.nome;
    corpo.appendChild(nome);

    if (f.importo > 0) {
      var misura = document.createElement('span');
      misura.className = 'voce-misura';
      var riemp = document.createElement('i');
      riemp.style.width = Math.max((f.importo / massimo) * 100, 0.5) + '%';
      misura.appendChild(riemp);
      corpo.appendChild(misura);
    }

    // Le righe che scendono di livello lo dicevano, le foglie no: non si
    // capiva né che si potessero aprire né quale fosse aperta.
    var piu = document.createElement('span');
    if (apribile) {
      piu.className = 'voce-piu';
      piu.textContent = f.figli.length + (f.figli.length === 1 ? ' voce dentro' : ' voci dentro');
    } else {
      piu.className = 'voce-piu voce-piu-scheda';
      piu.textContent = stato.aperta === f.id ? 'Chiudi il dettaglio' : 'Apri il dettaglio';
    }
    corpo.appendChild(piu);

    var cifre = document.createElement('span');
    cifre.className = 'voce-cifre';
    var euro = document.createElement('span');
    euro.className = 'voce-euro';
    euro.textContent = euroBreve(f.importo);
    var quota = document.createElement('span');
    quota.className = 'voce-quota';
    quota.textContent = perc(f.importo, padre.importo);
    cifre.appendChild(euro); cifre.appendChild(quota);

    var linea = scia(f);
    testa.appendChild(tacca); testa.appendChild(corpo);
    if (linea) testa.appendChild(linea);
    testa.appendChild(cifre);
    testa.addEventListener('click', function () { attiva(f); });
    testa.addEventListener('mouseenter', function () { legaTip(f.id); });
    testa.addEventListener('focus', function () { legaTip(f.id); });
    testa.addEventListener('mouseleave', spegni);
    testa.addEventListener('blur', spegni);
    li.appendChild(testa);

    if (!apribile) li.appendChild(scheda(f, padre));
    return li;
  }

  // La scheda della foglia ha gli stessi blocchi del pannello: a sinistra
  // che cos'è, a destra i numeri, sotto l'andamento a tutta larghezza.
  // Prima stava tutta stretta in metà pagina, con il grafico piccolo e
  // l'altra metà vuota.
  function scheda(f, padre) {
    var box = document.createElement('div');
    box.className = 'voce-scheda';

    var griglia = document.createElement('div');
    griglia.className = 'scheda-griglia';

    var parole = document.createElement('div');
    parole.className = 'scheda-parole';
    if (f.descrizione) {
      var p = document.createElement('p');
      p.textContent = f.descrizione;
      parole.appendChild(p);
    }
    griglia.appendChild(parole);

    var numeri = document.createElement('div');
    numeri.className = 'scheda-numeri';
    var titolo = document.createElement('h5');
    titolo.className = 'blocco-etichetta';
    titolo.textContent = 'I numeri';
    numeri.appendChild(titolo);

    var dl = document.createElement('dl');
    dato(dl, dati.meta.etichetta_importo || 'Importo esatto', euroPieno(f.importo));
    var radice = sezioneCorrente();
    if (radice && radice.importo)
      dato(dl, 'Quota del totale', perc(f.importo, radice.importo));
    var pa = perAbitante(f.importo);
    if (pa) dato(dl, 'Per abitante', pa);
    var pil = quotaPil(f.importo);
    if (pil) dato(dl, 'Quota del PIL', pil.replace(' del PIL', ''));
    numeri.appendChild(dl);
    griglia.appendChild(numeri);
    box.appendChild(griglia);

    // il grafico si disegna sulla larghezza dell'elenco, meno il rientro
    // della scheda: la scheda non è ancora nel documento e non si misura
    var largo = dom.voci ? dom.voci.clientWidth - 34 : 0;
    var g = graficoAndamento(f, largo > 320 ? largo : null);
    if (g) {
      var blocco = document.createElement('div');
      blocco.className = 'scheda-andamento';
      var et = document.createElement('h5');
      et.className = 'blocco-etichetta';
      et.textContent = 'Andamento';
      blocco.appendChild(et);
      blocco.appendChild(g);
      box.appendChild(blocco);
    }

    var pon = bloccoPonte(f);
    if (pon) box.appendChild(pon);
    return box;
  }

  function dato(dl, etichetta, valore) {
    var box = document.createElement('div');
    box.className = 'dato';
    var dt = document.createElement('dt'); dt.textContent = etichetta;
    var dd = document.createElement('dd'); dd.textContent = valore;
    box.appendChild(dt); box.appendChild(dd);
    dl.appendChild(box);
  }

  function attiva(nodo) {
    if (haFigli(nodo)) {
      stato.percorso = stato.percorso.concat([nodo.id]);
      stato.aperta = null; stato.tutte = false;
      spegni(); disegna(); segnaUrl(true);
      dom.briciole.scrollIntoView({ behavior: ridotto() ? 'auto' : 'smooth', block: 'start' });
    } else {
      stato.aperta = stato.aperta === nodo.id ? null : nodo.id;
      disegna(); segnaUrl(true);
    }
  }

  function ridotto() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /* ── La fascia del bilancio ────────────────────────────

     Entrate, uscite, saldo: tre cifre in fila, nell'ordine in cui si
     fa la sottrazione. Le prime due sono anche il comando che decide
     che cosa si esplora sotto — il controllo sta dove sta il
     significato, non in una barra a parte.
     ─────────────────────────────────────────────────────── */

  function contoNote(v) {
    var note = [];
    var pil = quotaPil(v);
    if (pil) note.push(pil);
    var pa = perAbitante(v);
    if (pa) note.push(pa + ' per abitante');
    return note;
  }

  // Sul saldo il segno lo porta già la cifra: la quota si scrive in
  // valore assoluto, e con un decimale come si legge sui giornali.
  function quotaPilSaldo(v) {
    if (!dati.meta.pil) return [];
    return [nf1.format(Math.abs(v / dati.meta.pil * 100)) + '% del PIL'];
  }

  function cartaConto(opz) {
    var el = document.createElement(opz.scegliibile ? 'button' : 'div');
    el.className = 'conto' + (opz.classe ? ' ' + opz.classe : '');
    if (opz.scegliibile) {
      el.type = 'button';
      el.setAttribute('aria-pressed', opz.attivo ? 'true' : 'false');
      el.addEventListener('click', opz.azione);
    }
    var nome = document.createElement('span');
    nome.className = 'conto-nome';
    nome.textContent = opz.nome;
    var cifra = document.createElement('span');
    cifra.className = 'conto-cifra';
    cifra.textContent = euroBreve(opz.importo);
    el.appendChild(nome);
    el.appendChild(cifra);
    (opz.note || []).forEach(function (t) {
      var note = document.createElement('span');
      note.className = 'conto-note';
      note.textContent = t;
      el.appendChild(note);
    });
    return el;
  }

  function costruisciConti() {
    dom.conti.textContent = '';
    var L = lati();

    if (!L) {
      // bilancio dello Stato: una cifra sola, e resta l'eroe della pagina
      dom.conti.dataset.uno = 'si';
      var radice = sezioneCorrente();
      var pezzi = [];
      var pil = quotaPil(radice.importo);
      if (pil) pezzi.push(pil);
      var pa = perAbitante(radice.importo);
      if (pa) pezzi.push(pa + ' per abitante');
      var ts = dati.meta.totale_storico, ann = dati.meta.anni;
      if (ts && ann && ann.length > 1) {
        var iQui = ann.indexOf(dati.meta.anno), iPrimo = -1;
        for (var i = 0; i <= iQui; i++) if (ts[i] != null) { iPrimo = i; break; }
        if (iPrimo >= 0 && iPrimo < iQui && ts[iPrimo]) {
          var pd = ((ts[iQui] - ts[iPrimo]) / ts[iPrimo]) * 100;
          pezzi.push((pd > 0 ? '+' : '−') + nf1.format(Math.abs(pd)) + '% dal ' + ann[iPrimo]);
          if (ePrevisione(dati.meta.anno))
            pezzi.push(ann[iQui] + ' a stanziamenti, non impegni');
        }
      }
      pezzi.push(euroPieno(radice.importo));
      dom.conti.appendChild(cartaConto({
        nome: radice.titolo || 'Totale', importo: radice.importo,
        note: [pezzi.join('  ·  ')], classe: 'conto-solo'
      }));
      dom.racconto.hidden = true;
      return;
    }

    delete dom.conti.dataset.uno;
    L.forEach(function (l) {
      dom.conti.appendChild(cartaConto({
        nome: l.nome, importo: l.importo, note: contoNote(l.importo),
        scegliibile: true, attivo: l.id === stato.lato,
        azione: function () { cambiaLato(l.id); }
      }));
    });

    var saldo = dati.meta.saldo;
    if (saldo) {
      dom.conti.appendChild(cartaConto({
        nome: saldo.etichetta || saldo.nome, importo: saldo.importo,
        note: quotaPilSaldo(saldo.importo),
        classe: 'conto-saldo' + (saldo.importo < 0 ? ' conto-saldo-rosso' : '')
      }));
    }

    dom.racconto.textContent = dati.meta.racconto || '';
    dom.racconto.hidden = !dati.meta.racconto;
  }

  function cambiaLato(id) {
    if (stato.lato === id) return;
    stato.lato = id;
    stato.percorso = []; stato.aperta = null; stato.tutte = false;
    stato.sezione = sezionePredefinita();
    testataDelLato();
    costruisciTab();
    sincronizzaTab();
    costruisciConti();
    spegni(); disegna(); segnaUrl(true);
  }

  // Titolo, sommario e testo d'apertura appartengono al lato: passando
  // alle entrate cambia la pagina, non solo l'albero.
  function testataDelLato() {
    var m = dati.meta, l = latoCorrente();
    var titolo = l.titolo || m.titolo;
    document.title = titolo + ' — Dove vanno i soldi';
    dom.sommario.textContent = l.sottotitolo || m.sottotitolo || '';
    dom['apertura-testo'].textContent = l.apertura || m.apertura || '';
    dom['testata-contesto'].textContent = VISTE[VISTA].nome + ' · ' + m.anno;

    dom.titolo.textContent = '';
    var t = l.titolo_display || m.titolo_display || { prima: titolo, corsivo: '', dopo: '' };
    if (t.prima) dom.titolo.appendChild(document.createTextNode(t.prima + ' '));
    if (t.corsivo) {
      var em = document.createElement('em');
      em.textContent = t.corsivo;
      dom.titolo.appendChild(em);
      if (t.dopo) dom.titolo.appendChild(document.createTextNode(' '));
    }
    if (t.dopo) dom.titolo.appendChild(document.createTextNode(t.dopo));
  }

  /* ── Il tempo ──────────────────────────────────────────

     Trent'anni non stanno in una fila di link, e una fila di link non
     dice niente. Qui l'anno si sceglie sulla linea del totale: si vede
     dove si è, e come è andata. Il menù e le frecce fanno la stessa
     cosa da tastiera e sul telefono.
     ─────────────────────────────────────────────────────── */

  // Le colonne del tempo raccontano tutto il bilancio, non il lato
  // aperto: l'altezza è il più grande fra entrate e uscite, la parte
  // piena il più piccolo, e il cappello vuoto è il divario.
  function serieTempo() {
    var L = lati();
    if (!L || L.length < 2) return { a: dati.meta.totale_storico || [], b: null };
    return { a: L[0].storico || [], b: L[1].storico || [],
             nomeA: L[0].nome, nomeB: L[1].nome };
  }

  function costruisciTempo() {
    var ann = dati.meta.anni, serie = serieTempo();
    dom.tempo.hidden = !(ann && ann.length > 1);
    if (dom.tempo.hidden) return;

    var sel = dom['anno-scelta'];
    sel.textContent = '';
    ann.forEach(function (a) {
      var o = document.createElement('option');
      o.value = a;
      o.textContent = a + (ePrevisione(a) ? ' · previsione' : '');
      if (a === dati.meta.anno) o.selected = true;
      sel.appendChild(o);
    });

    var i = ann.indexOf(dati.meta.anno);
    freccia(dom['anno-prec'], i > 0 ? ann[i - 1] : null);
    freccia(dom['anno-succ'], i >= 0 && i < ann.length - 1 ? ann[i + 1] : null);

    dom['tempo-grafico'].textContent = '';
    var g = lineaDelTempo(ann, serie);
    if (g) dom['tempo-grafico'].appendChild(g);

    dom['tempo-legenda'].textContent = '';
    dom['tempo-legenda'].hidden = !serie.b;
    if (serie.b) {
      [['tempo-segno-pieno', 'entrate'],
       ['tempo-segno-vuoto', 'disavanzo']].forEach(function (par) {
        var sp = document.createElement('span');
        sp.className = 'tempo-voce-legenda';
        var q = document.createElement('i');
        q.className = par[0];
        sp.appendChild(q);
        sp.appendChild(document.createTextNode(par[1]));
        dom['tempo-legenda'].appendChild(sp);
      });
    }
  }

  var attesaRidisegno = null;
  window.addEventListener('resize', function () {
    if (!dati) return;
    clearTimeout(attesaRidisegno);
    attesaRidisegno = setTimeout(function () {
      costruisciTempo();
      disegna();
    }, 180);
  });

  function freccia(el, anno) {
    if (!el) return;
    if (anno) {
      el.href = indirizzo(VISTA, anno, voceCorrente());
      el.removeAttribute('aria-disabled');
      el.setAttribute('title', 'Anno ' + anno);
      el.dataset.anno = anno;
    } else {
      el.removeAttribute('href');
      el.setAttribute('aria-disabled', 'true');
      el.setAttribute('title', '');
      delete el.dataset.anno;
    }
  }

  function lineaDelTempo(ann, serie) {
    var W = Math.max(280, dom['tempo-grafico'].clientWidth || 900);
    var stretto = W < 560;
    var H = stretto ? 96 : 132, ML = 4, MR = 4;
    var MT = stretto ? 10 : 14, MB = stretto ? 24 : 28;
    var iw = W - ML - MR, ih = H - MT - MB;
    var base = MT + ih;
    var a = serie.a || [], b = serie.b;

    var max = 0, quanti = 0;
    ann.forEach(function (anno, i) {
      var va = a[i], vb = b ? b[i] : null;
      if (va === null || va === undefined) return;
      quanti++;
      var alto = (vb === null || vb === undefined) ? va : Math.max(va, vb);
      if (alto > max) max = alto;
    });
    if (quanti < 2) return null;

    var passo = iw / ann.length;
    var larghezza = Math.max(2, Math.min(30, passo * 0.68));
    function xc(i) { return ML + passo * (i + 0.5); }
    function alt(v) { return Math.max(1.5, (v / max) * ih); }

    var svg = svgEl('svg', {
      'class': 'tempo-svg', width: W, height: H,
      viewBox: '0 0 ' + W + ' ' + H, role: 'img'
    });
    svg.setAttribute('aria-label', b
      ? 'Entrate e uscite pubbliche anno per anno dal ' + ann[0] + ' al ' +
        ann[ann.length - 1] + ': la colonna è la spesa, la parte piena le entrate, '
        + 'il vuoto in cima il disavanzo.'
      : 'Il totale anno per anno dal ' + ann[0] + ' al ' + ann[ann.length - 1] +
        ', in colonne: la più alta è ' + euroBreve(max) + '.');

    var iQui = ann.indexOf(dati.meta.anno);

    // Base a zero, quindi i rapporti fra gli anni sono quelli veri.
    var colonne = {};
    ann.forEach(function (anno, i) {
      var va = a[i];
      if (va === null || va === undefined) return;
      var vb = b ? b[i] : null;
      var haDue = vb !== null && vb !== undefined;
      var alto = haDue ? Math.max(va, vb) : va;
      var dentro = haDue ? Math.min(va, vb) : alto;
      var qui = anno === dati.meta.anno;
      var prev = ePrevisione(anno);
      var gruppo = svgEl('g', { 'class': 'tempo-gruppo' });

      // il cappello: la parte scoperta è il divario dell'anno
      if (haDue && alto > dentro) {
        var hAlto = alt(alto), hDentro = alt(dentro);
        gruppo.appendChild(svgEl('rect', {
          x: (xc(i) - larghezza / 2).toFixed(1), y: (base - hAlto).toFixed(1),
          width: larghezza.toFixed(1), height: (hAlto - hDentro).toFixed(1),
          rx: larghezza > 6 ? 1.5 : 0,
          'class': 'tempo-cappello' + (qui ? ' tempo-cappello-qui' : '')
        }));
      }
      var h = alt(dentro);
      var classe = 'tempo-barra';
      if (qui) classe += ' tempo-barra-qui';
      if (prev) classe += ' tempo-barra-prevista';
      var barra = svgEl('rect', {
        x: (xc(i) - larghezza / 2).toFixed(1), y: (base - h).toFixed(1),
        width: larghezza.toFixed(1), height: h.toFixed(1),
        rx: larghezza > 6 ? 1.5 : 0, 'class': classe
      });
      gruppo.appendChild(barra);
      colonne[anno] = barra;
      svg.appendChild(gruppo);
    });

    svg.appendChild(svgEl('line', {
      x1: ML, x2: W - MR, y1: base + .5, y2: base + .5, 'class': 'tempo-asse'
    }));

    // Etichette: i multipli di cinque danno il ritmo del decennio; poi
    // gli estremi e l'anno scelto, che non si toglie mai.
    var minSpazio = stretto ? 34 : 42;
    var scritte = {};
    [0, ann.length - 1].forEach(function (i) { scritte[i] = true; });
    if (iQui >= 0) scritte[iQui] = true;
    ann.forEach(function (anno, i) {
      if (anno % 5 !== 0) return;
      var vicino = Object.keys(scritte).some(function (j) {
        return Math.abs(xc(i) - xc(+j)) < minSpazio;
      });
      if (!vicino) scritte[i] = true;
    });

    var yTesto = H - (stretto ? 7 : 9);
    ann.forEach(function (anno, i) {
      if (!scritte[i]) return;
      // agli estremi l'etichetta si aggancia al bordo invece di centrarsi
      // sulla colonna: centrata, l'ultimo anno sborda dal riquadro
      var t = svgEl('text', {
        x: xc(i).toFixed(1), y: yTesto,
        'text-anchor': i === 0 ? 'start' : i === ann.length - 1 ? 'end' : 'middle',
        'class': 'tempo-anno' + (i === iQui ? ' tempo-anno-qui' : '')
      });
      t.textContent = anno;
      svg.appendChild(t);
    });

    // Bersagli: tutta l'altezza, così si clicca anche sopra le colonne basse
    ann.forEach(function (anno, i) {
      var r = svgEl('rect', {
        x: (ML + passo * i).toFixed(1), y: 0,
        width: passo.toFixed(1), height: (H - 4).toFixed(1),
        'class': 'tempo-colpo', 'aria-hidden': 'true'
      });
      var va = a[i], vb = b ? b[i] : null;
      var etichetta;
      if (va === null || va === undefined) {
        etichetta = anno + ' · dato non disponibile';
      } else if (vb !== null && vb !== undefined) {
        var sal = (dati.meta.saldo && dati.meta.saldo.storico || [])[i];
        etichetta = anno + ' · ' + (serie.nomeA || 'A').toLowerCase() + ' ' +
          euroBreve(va) + ' · ' + (serie.nomeB || 'B').toLowerCase() + ' ' +
          euroBreve(vb);
        if (sal !== null && sal !== undefined)
          etichetta += ' · ' + (sal < 0 ? 'disavanzo ' : 'avanzo ') +
            euroBreve(Math.abs(sal));
      } else {
        etichetta = anno + ' · ' + euroBreve(va);
      }
      if (ePrevisione(anno)) etichetta += ' · previsione';
      r.addEventListener('mouseenter', function () {
        if (colonne[anno]) colonne[anno].dataset.sfiorata = 'si';
        mostraTip(r, etichetta);
      });
      r.addEventListener('mouseleave', function () {
        if (colonne[anno]) delete colonne[anno].dataset.sfiorata;
        nascondiTip();
      });
      r.addEventListener('click', function () {
        nascondiTip();
        caricaAnno(anno, voceCorrente(), true);
      });
      svg.appendChild(r);
    });

    return svg;
  }

  /* ── Caricamento di un anno ────────────────────────────── */

  var caricando = false;

  function caricaAnno(anno, voce, push) {
    anno = parseInt(anno, 10);
    if (caricando || !anno || anno === dati.meta.anno) return;
    caricando = true;
    document.documentElement.dataset.caricando = 'si';
    fetch('assets/' + VISTE[VISTA].prefisso + '_' + anno + '.json')
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        applica(d, voce);
        if (push !== false) segnaUrl(true);
      })
      .catch(function () {
        // l'anno non c'è in questa vista: ci pensa il caricamento normale
        location.href = indirizzo(VISTA, anno, voce);
      })
      .then(function () {
        caricando = false;
        delete document.documentElement.dataset.caricando;
      });
  }

  /* ── Applicazione dei dati ─────────────────────────────── */

  function applica(d, voce) {
    var sezionePrima = stato.sezione;
    dati = d;
    var m = d.meta;

    dom['fonte-nome'].textContent = m.fonte_nome;
    dom['fonte-metodo'].textContent = m.nota_metodo;
    dom['fonte-link'].href = m.fonte_url;
    if (m.fonte_link_testo) dom['fonte-link'].textContent = m.fonte_link_testo;
    if (m.descrizioni) dom['fonte-descrizioni'].textContent = m.descrizioni;
    if (m.come_leggere) dom['come-leggere'].textContent = m.come_leggere;
    if (m.vista_nota) dom['vista-nota'].textContent = m.vista_nota;
    dom['testata-contesto'].textContent = VISTE[VISTA].nome + ' · ' + m.anno;

    if (m.portale) {
      dom['fonte-portale'].href = m.portale.url;
      dom['fonte-portale'].textContent = '';
      dom['fonte-portale'].appendChild(document.createTextNode(m.portale.nome));
      var nascosta = document.createElement('span');
      nascosta.className = 'visually-hidden';
      nascosta.textContent = ', il portale dei dati (si apre in un nuovo tab)';
      dom['fonte-portale'].appendChild(nascosta);
    }

    var altra = VISTA === 'pa' ? 'stato' : 'pa';

    dom['vista-altra'].textContent = '';
    var invito = document.createElement('a');
    invito.href = indirizzo(altra, m.anno, '');
    invito.className = 'vista-altra-link';
    if (altra === 'stato') {
      dom['vista-altra'].appendChild(document.createTextNode(
        'Per il dettaglio per ministero, missione e capitolo: '));
      invito.textContent = 'apri il bilancio dello Stato';
    } else {
      dom['vista-altra'].appendChild(document.createTextNode(
        'Per il perimetro completo, con Regioni, Comuni ed enti previdenziali: '));
      invito.textContent = 'torna a tutta la spesa pubblica';
    }
    dom['vista-altra'].appendChild(invito);

    dom['fonte-altra'].textContent = '';
    var linkAltra = document.createElement('a');
    linkAltra.href = indirizzo(altra, m.anno, '');
    linkAltra.textContent = VISTE[altra].nome;
    dom['fonte-altra'].appendChild(linkAltra);
    dom['fonte-altra'].appendChild(document.createTextNode(altra === 'stato'
      ? ' — la stessa domanda sul solo bilancio statale, ma scendendo fino al '
        + 'ministero, alla missione e al programma.'
      : ' — la stessa domanda su tutta la pubblica amministrazione, in contabilità '
        + 'nazionale, con entrate e saldo.'));

    // Il lato prima di tutto: da lì dipendono sezioni, testata e cifre.
    if (!lati()) stato.lato = null;
    else if (!stato.lato ||
             !lati().filter(function (l) { return l.id === stato.lato; })[0])
      stato.lato = latoPredefinito();

    // Se la voce chiesta non c'è in questo anno si torna alla radice, ma
    // si resta nello stesso lato e nella stessa chiave di lettura.
    if (!voce || !vaiA(voce)) {
      stato.percorso = []; stato.aperta = null; stato.tutte = false;
      var resta = sezioniDelLato().filter(function (s) { return s.id === sezionePrima; })[0];
      stato.sezione = resta ? sezionePrima : sezionePredefinita();
    }

    testataDelLato();
    costruisciTab();
    sincronizzaTab();
    costruisciTempo();
    spegni();
    disegna();
  }

  function costruisciTab() {
    dom.scelta.textContent = '';
    tabBtns = [];
    sezioniDelLato().forEach(function (sez) {
      var li = document.createElement('li');
      li.className = 'nav-item';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'nav-link';
      btn.id = 'tab-' + sez.id;
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-controls', 'pannello');
      btn.textContent = sez.etichetta || sez.nome;
      btn.addEventListener('click', function () { attivaTab(sez.id); });
      li.appendChild(btn);
      dom.scelta.appendChild(li);
      tabBtns.push(btn);
    });
    dom['scelta-involucro'].hidden = tabBtns.length < 2;
  }

  function attivaTab(id) {
    if (stato.sezione === id) return;
    stato.sezione = id;
    stato.percorso = []; stato.aperta = null; stato.tutte = false;
    sincronizzaTab();
    spegni(); disegna(); segnaUrl(true);
  }

  function sincronizzaTab() {
    tabBtns.forEach(function (b) {
      var on = b.id === 'tab-' + stato.sezione;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.setAttribute('tabindex', on ? '0' : '-1');
      b.classList.toggle('active', on);
    });
    var pannello = document.getElementById('pannello');
    if (pannello) pannello.setAttribute('aria-labelledby', 'tab-' + stato.sezione);
  }

  /* ── Avvio ─────────────────────────────────────────────── */

  function inizializza(d) {
    applica(d, param('voce'));
    segnaUrl(false);

    dom.scelta.addEventListener('keydown', function (e) {
      var i = tabBtns.indexOf(document.activeElement);
      if (i < 0) return;
      var j = null;
      if (e.key === 'ArrowRight') j = (i + 1) % tabBtns.length;
      else if (e.key === 'ArrowLeft') j = (i - 1 + tabBtns.length) % tabBtns.length;
      else if (e.key === 'Home') j = 0;
      else if (e.key === 'End') j = tabBtns.length - 1;
      if (j === null) return;
      e.preventDefault();
      tabBtns[j].focus();
      attivaTab(tabBtns[j].id.replace(/^tab-/, ''));
    });

    dom['anno-scelta'].addEventListener('change', function () {
      caricaAnno(this.value, voceCorrente(), true);
    });
    [dom['anno-prec'], dom['anno-succ']].forEach(function (el) {
      el.addEventListener('click', function (e) {
        if (!el.dataset.anno) { e.preventDefault(); return; }
        e.preventDefault();
        caricaAnno(el.dataset.anno, voceCorrente(), true);
      });
    });

    window.addEventListener('popstate', function () {
      var anno = parseInt(param('anno'), 10);
      var voce = param('voce');
      if (anno && anno !== dati.meta.anno) { caricaAnno(anno, voce, false); return; }
      if (!voce || !vaiA(voce)) {
        stato.lato = latoPredefinito();
        stato.percorso = []; stato.aperta = null; stato.tutte = false;
        stato.sezione = sezionePredefinita();
      }
      testataDelLato(); costruisciTab(); sincronizzaTab(); spegni(); disegna();
    });
  }

  function fallito(err) {
    dom.voci.hidden = true;
    dom.barra.hidden = true;
    dom.vuoto.hidden = false;
    dom.vuoto.textContent = '';
    dom.vuoto.appendChild(document.createTextNode(
      'I dati non sono stati caricati. Se la pagina è stata aperta con un doppio clic, il ' +
      'browser le impedisce di leggere i file in assets/: è una restrizione del browser, non ' +
      'un errore del sito. Avvia un server dalla cartella del progetto con '));
    var code = document.createElement('code');
    code.textContent = 'python3 -m http.server 8000';
    dom.vuoto.appendChild(code);
    dom.vuoto.appendChild(document.createTextNode(' e apri http://localhost:8000'));
    if (window.console) console.error(err);
  }

  var base = 'assets/' + VISTE[VISTA].prefisso;
  var mAnno = param('anno');
  var sorgente = /^\d{4}$/.test(mAnno) ? base + '_' + mAnno + '.json' : base + '.json';

  // Il ponte è facoltativo: se manca, le due viste restano semplicemente
  // separate e il resto della pagina funziona uguale.
  var attesaPonte = fetch('assets/ponte.json')
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; });

  fetch(sorgente)
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .catch(function () {
      // anno richiesto non disponibile in questa vista: torna all'ultimo
      return fetch(base + '.json').then(function (r) { return r.json(); });
    })
    .then(function (d) {
      return attesaPonte.then(function (pp) { ponte = pp; return d; });
    })
    .then(inizializza)
    .catch(fallito);

})();

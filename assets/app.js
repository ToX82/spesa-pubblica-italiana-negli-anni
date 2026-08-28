/* =========================================================
   Bilancio di previsione 2026 — Presidenza del Consiglio
   Nessuna dipendenza, nessuna compilazione.
   ========================================================= */
(function () {
  'use strict';

  var COLORI = ['--c1', '--c2', '--c3', '--c4', '--c5', '--c6', '--c7', '--c8',
                '--c9', '--c10', '--c11', '--c12', '--c13'];
  var MAX_FETTE = 13;   // fette disegnate nella barra prima di raggruppare
  var MAX_RIGHE = 24;   // voci mostrate prima di "mostra tutte"

  function maxFette() {
    return window.matchMedia && window.matchMedia('(max-width:640px)').matches
      ? 6 : MAX_FETTE;
  }

  var dom = {};
  ['occhiello', 'sommario', 'cifra-totale', 'cifra-nota', 'briciole', 'barra',
   'barra-legenda', 'contesto', 'contesto-fetta', 'contesto-testo', 'contesto-grafico',
   'nota-voce', 'voci', 'vuoto', 'fonte-nome', 'fonte-link', 'fonte-metodo', 'esplora-h',
   'scelta', 'scelta-involucro', 'titolo', 'apertura-testo', 'anni', 'come-leggere'
  ].forEach(function (id) { dom[id] = document.getElementById(id); });

  var dati = null;
  var stato = { sezione: 'uscite', percorso: [], aperta: null, tutte: false };

  /* ── Numeri ────────────────────────────────────────────── */

  var nf = new Intl.NumberFormat('it-IT');
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
    return (q >= 10 ? nf1.format(q) : nf2.format(q)) + ' €';
  }

  /* ── Albero ────────────────────────────────────────────── */

  function sezioneCorrente() {
    return dati.sezioni.filter(function (s) { return s.id === stato.sezione; })[0] || dati.sezioni[0];
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

  // Grafico d'andamento: anni sull'asse, importi sull'altro, vuoti dove
  // la voce non esisteva. Lo snippet va nel blocco di contesto e nelle schede.
  function graficoAndamento(nodo) {
    var p = serieStorico(nodo);
    if (!p) return null;
    var ann = dati.meta.anni, ts = dati.meta.totale_storico;
    var W = 560, H = 176, ML = 52, MR = 16, MT = 18, MB = 34;
    var iw = W - ML - MR, ih = H - MT - MB;
    var vmin = Infinity, vmax = -Infinity;
    p.forEach(function (q) {
      if (q.valore < vmin) vmin = q.valore;
      if (q.valore > vmax) vmax = q.valore;
    });
    if (vmax === vmin) vmax = vmin + 1;
    var pad = (vmax - vmin) * 0.1;
    var lo = vmin - pad, hi = vmax + pad;
    function x(q) { return ML + (q.i / (ann.length - 1)) * iw; }
    function y(v) { return MT + ih - ((v - lo) / (hi - lo)) * ih; }

    var primo = p[0], ultimo = p[p.length - 1];
    var pct = primo.valore ? ((ultimo.valore - primo.valore) / primo.valore) * 100 : null;
    var divisore = Math.abs(vmax) >= 1e9 ? 1e9 : 1e6;

    var fig = document.createElement('figure');
    fig.className = 'andamento';
    var svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' });
    svg.setAttribute('aria-label', 'Andamento dal ' + primo.anno + ' al ' + ultimo.anno +
      ': da ' + euroBreve(primo.valore) + ' a ' + euroBreve(ultimo.valore) +
      (pct !== null ? ', ' + (pct > 0 ? '+' : '−') + nf1.format(Math.abs(pct)) + '%' : '') + '.');

    [vmax, (vmax + vmin) / 2, vmin].forEach(function (v, i) {
      svg.appendChild(svgEl('line', {
        x1: ML, x2: W - MR, y1: y(v).toFixed(1), y2: y(v).toFixed(1),
        stroke: 'var(--filo)', 'stroke-width': 1
      }));
      if (i !== 1) {
        var t = svgEl('text', { x: ML - 8, y: (y(v) + 3.5).toFixed(1), 'text-anchor': 'end', 'class': 'asse' });
        t.textContent = nf.format(Math.round(v / divisore));
        svg.appendChild(t);
      }
    });

    ann.forEach(function (a, i) {
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
    vt.textContent = euroBreve(ultimo.valore);
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
      var testo = a + ' · ' + euroBreve(q.valore) +
        (ts && ts[i] ? ' · ' + perc(q.valore, ts[i]) + ' della spesa dello Stato' : '');
      rect.addEventListener('mouseenter', function () { mostraTip(rect, testo); });
      rect.addEventListener('mouseleave', nascondiTip);
      svg.appendChild(rect);
    });

    fig.appendChild(svg);
    var cap = document.createElement('figcaption');
    var testo = 'Andamento ' + primo.anno + '–' + ultimo.anno + ': ' +
      (pct === null ? euroBreve(ultimo.valore)
        : (pct > 0 ? '+' : '−') + nf1.format(Math.abs(pct)) + '% (' +
          euroBreve(primo.valore) + ' → ' + euroBreve(ultimo.valore) + ')') +
      ' · importi in ' + (divisore === 1e9 ? 'miliardi' : 'milioni') + ' di €';
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

  /* ── Disegno ───────────────────────────────────────────── */

  function disegna() {
    var cat = catena();
    var nodo = cat[cat.length - 1];
    var radice = cat[0];
    var figli = (nodo.figli || []).slice().sort(function (a, b) { return b.importo - a.importo; });

    dom['esplora-h'].textContent = radice.titolo ||
      (radice.domanda ? radice.domanda + ' i soldi' : 'Esplora il bilancio');
    briciole(cat);
    barra(nodo, figli);
    contesto(nodo, radice, cat);
    elenco(nodo, figli);
    apertura(radice);
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
          stato.aperta = null; stato.tutte = false; disegna();
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
      figli.slice(0, maxFette()).forEach(function (f, i) {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'fetta';
        b.style.setProperty('--fetta-colore', coloreDi(i, figli.length));
        b.style.width = ((f.importo / nodo.importo) * 100) + '%';
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
        var somma = resto.reduce(function (a, f) { return a + f.importo; }, 0);
        var r = document.createElement('div');
        r.className = 'fetta fetta-resto';
        r.style.setProperty('--fetta-colore', 'var(--resto)');
        r.style.width = ((somma / nodo.importo) * 100) + '%';
        var etichettaResto = 'Altre ' + resto.length + ' voci — ' + euroBreve(somma);
        r.dataset.tip = etichettaResto;
        r.setAttribute('aria-hidden', 'true');
        r.addEventListener('mouseenter', function () { spegni(); mostraTip(r, etichettaResto); });
        r.addEventListener('mouseleave', nascondiTip);
        dom.barra.appendChild(r);
      }
    }

    dom['barra-legenda'].textContent = '';
    var sx = document.createElement('span');
    sx.textContent = !nodo.importo ? 'nessun importo per il ' + dati.meta.anno
      : figli.length ? figli.length + (figli.length === 1 ? ' voce' : ' voci')
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

  function contesto(nodo, radice, cat) {
    var profondo = cat.length > 1;
    dom.contesto.hidden = !profondo;
    dom['contesto-grafico'].textContent = '';
    if (profondo) {
      var q = (nodo.importo / radice.importo) * 100;
      dom['contesto-fetta'].style.width = Math.max(q, 0.35) + '%';
      dom['contesto-testo'].textContent =
        nodo.nome + ': ' + perc(nodo.importo, radice.importo) + ' del totale, pari a ' +
        euroBreve(nodo.importo) + '.';
      var g = graficoAndamento(nodo);
      if (g) dom['contesto-grafico'].appendChild(g);
    }
    dom['nota-voce'].textContent = nodo.descrizione || '';
    dom['nota-voce'].hidden = !nodo.descrizione;
  }

  function elenco(nodo, figli) {
    dom.voci.textContent = '';

    if (!figli.length) {
      dom.voci.hidden = true;
      dom.vuoto.hidden = false;
      dom.vuoto.textContent = 'In questa chiave di lettura la voce non è divisa ' +
        'ulteriormente: ' + euroPieno(nodo.importo) + ' complessivi.';
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

    if (apribile) {
      var piu = document.createElement('span');
      piu.className = 'voce-piu';
      piu.textContent = f.figli.length + (f.figli.length === 1 ? ' voce dentro' : ' voci dentro');
      corpo.appendChild(piu);
    }

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

  function scheda(f, padre) {
    var box = document.createElement('div');
    box.className = 'voce-scheda';
    if (f.descrizione) {
      var p = document.createElement('p');
      p.textContent = f.descrizione;
      box.appendChild(p);
    }
    var dl = document.createElement('dl');
    dato(dl, 'Importo esatto', euroPieno(f.importo));
    var pa = perAbitante(f.importo);
    if (pa) dato(dl, 'Per abitante', pa);
    dato(dl, 'Quota della voce superiore', perc(f.importo, padre.importo));
    box.appendChild(dl);
    var g = graficoAndamento(f);
    if (g) box.appendChild(g);
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
      spegni(); disegna();
      dom.briciole.scrollIntoView({ behavior: ridotto() ? 'auto' : 'smooth', block: 'start' });
    } else {
      stato.aperta = stato.aperta === nodo.id ? null : nodo.id;
      disegna();
    }
  }

  function ridotto() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function apertura(radice) {
    dom['cifra-totale'].textContent = euroBreve(radice.importo);
    var pezzi = [euroPieno(radice.importo)];
    var pa = perAbitante(radice.importo);
    if (pa) pezzi.push(pa + ' per abitante');
    var prev = dati.meta.totale_2025;
    if (prev) {
      var p = ((radice.importo - prev) / prev) * 100;
      pezzi.push((p > 0 ? '+' : '−') + nf1.format(Math.abs(p)) + '% sul 2025');
    }
    var ts = dati.meta.totale_storico, ann = dati.meta.anni;
    if (ts && ann && ann.length > 1) {
      var iQui = ann.indexOf(dati.meta.anno);
      var iPrimo = -1;
      for (var i = 0; i <= iQui; i++) if (ts[i] != null) { iPrimo = i; break; }
      if (iPrimo >= 0 && iPrimo < iQui && ts[iPrimo]) {
        var pd = ((ts[iQui] - ts[iPrimo]) / ts[iPrimo]) * 100;
        pezzi.push((pd > 0 ? '+' : '−') + nf1.format(Math.abs(pd)) + '% dal ' + ann[iPrimo]);
        // l'ultimo tratto mescola le misure se l'anno è di previsione:
        // si dice, altrimenti il +x% sembra un confronto fra uguali
        if (ePrevisione(dati.meta.anno))
          pezzi.push(ann[iQui] + ' a stanziamenti, non impegni');
      }
    }
    dom['cifra-nota'].textContent = pezzi.join('  ·  ');
  }

  /* ── Avvio ─────────────────────────────────────────────── */

  function inizializza(d) {
    dati = d;
    var m = d.meta;
    document.title = m.titolo + ' — ' + m.ente;
    dom.occhiello.textContent = m.ente;
    dom.sommario.textContent = m.sottotitolo;

    // Titolo composto: la parte centrale va in evidenza.
    dom.titolo.textContent = '';
    var t = m.titolo_display || { prima: m.titolo, corsivo: '', dopo: '' };
    if (t.prima) dom.titolo.appendChild(document.createTextNode(t.prima + ' '));
    if (t.corsivo) {
      var em = document.createElement('em');
      em.textContent = t.corsivo;
      dom.titolo.appendChild(em);
      if (t.dopo) dom.titolo.appendChild(document.createTextNode(' '));
    }
    if (t.dopo) dom.titolo.appendChild(document.createTextNode(t.dopo));

    dom['apertura-testo'].textContent = m.apertura ||
      'Una cifra così grande non dice quasi nulla da sola. Qui sotto puoi aprirla: ogni ' +
      'volta che scegli una voce, la barra si ridisegna su quella voce e ti mostra come è ' +
      'fatta dentro.';
    dom['fonte-nome'].textContent = m.fonte_nome;
    dom['fonte-metodo'].textContent = m.nota_metodo;
    dom['fonte-link'].href = m.fonte_url;
    if (dom['come-leggere'] && m.come_leggere)
      dom['come-leggere'].textContent = m.come_leggere;

    stato.sezione = d.sezioni[0].id;

    var ann = d.meta.anni;
    dom.anni.textContent = '';
    if (ann && ann.length > 1) {
      dom.anni.hidden = false;
      var etichetta = document.createElement('span');
      etichetta.className = 'anni-etichetta';
      etichetta.textContent = 'Anni';
      dom.anni.appendChild(etichetta);
      ann.forEach(function (a) {
        if (a === d.meta.anno) {
          var qui = document.createElement('span');
          qui.setAttribute('aria-current', 'page');
          qui.textContent = a;
          dom.anni.appendChild(qui);
        } else {
          var l = document.createElement('a');
          l.href = '?anno=' + a;
          l.textContent = a;
          dom.anni.appendChild(l);
        }
      });
    } else {
      dom.anni.hidden = true;
    }

    // schede di chiave di lettura: stile nav-tabs di Bootstrap Italia,
    // con gestione completa da tastiera (frecce, Home/End) perché il
    // pannello è unico e ridisegnato
    dom.scelta.textContent = '';
    var tabBtns = [];
    d.sezioni.forEach(function (sez, i) {
      var li = document.createElement('li');
      li.className = 'nav-item';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'nav-link' + (i === 0 ? ' active' : '');
      btn.id = 'tab-' + sez.id;
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', i === 0 ? 'true' : 'false');
      btn.setAttribute('tabindex', i === 0 ? '0' : '-1');
      btn.setAttribute('aria-controls', 'pannello');
      btn.textContent = sez.etichetta || sez.domanda || sez.nome;
      btn.addEventListener('click', function () { attivaTab(btn, sez); });
      li.appendChild(btn);
      dom.scelta.appendChild(li);
      tabBtns.push(btn);
    });
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
      attivaTab(tabBtns[j], d.sezioni[j]);
    });
    function attivaTab(btn, sez) {
      if (stato.sezione === sez.id) return;
      stato.sezione = sez.id;
      stato.percorso = []; stato.aperta = null; stato.tutte = false;
      tabBtns.forEach(function (b) {
        var on = b === btn;
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        b.setAttribute('tabindex', on ? '0' : '-1');
        b.classList.toggle('active', on);
      });
      var pannello = document.getElementById('pannello');
      if (pannello) pannello.setAttribute('aria-labelledby', 'tab-' + sez.id);
      spegni(); disegna();
    }
    dom['scelta-involucro'].hidden = d.sezioni.length < 2;
    var pannelloIniziale = document.getElementById('pannello');
    if (pannelloIniziale)
      pannelloIniziale.setAttribute('aria-labelledby', 'tab-' + d.sezioni[0].id);

    disegna();
  }

  function fallito(err) {
    dom.voci.hidden = true;
    dom.barra.hidden = true;
    dom.vuoto.hidden = false;
    dom.vuoto.textContent = '';
    dom.vuoto.appendChild(document.createTextNode(
      'I dati non sono stati caricati. Aperta con un doppio clic, la pagina non può leggere ' +
      'assets/data.json: è una restrizione del browser. Avvia un server dalla cartella del progetto con '));
    var code = document.createElement('code');
    code.textContent = 'python3 -m http.server 8000';
    dom.vuoto.appendChild(code);
    dom.vuoto.appendChild(document.createTextNode(' e apri http://localhost:8000'));
    if (window.console) console.error(err);
  }

  var mAnno = (location.search.match(/[?&]anno=(\d{4})/) || [])[1];
  var sorgente = mAnno ? 'assets/data_' + mAnno + '.json' : 'assets/data.json';

  fetch(sorgente)
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .catch(function () {
      // anno richiesto non disponibile: torna all'ultimo pubblicato
      return fetch('assets/data.json').then(function (r) { return r.json(); });
    })
    .then(inizializza)
    .catch(fallito);

})();

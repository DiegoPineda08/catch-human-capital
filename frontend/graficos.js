/* Gráficos SVG sin dependencias: barras, barras horizontales, líneas, área, pastel, dispersión, histograma y caja.
   Todos los valores dibujados vienen de los registros que calculó el servidor; no se transforman. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const ETIQUETAS = ['rango', 'nombre', 'grupo', 'periodo', 'indicador', 'variable', 'entidad', 'pais', 'columna', 'metrica', 'categoria', 'anio'];
  const VALORES = ['valor', 'conteo', 'y', 'rho', 'mediana', 'proporcion', 'promedio', 'total'];
  const PALETA = ['var(--accent)', '#e07b39', '#2a9d8f', '#8a63d2', '#d1495b', '#6c8a2b', '#3d7ab8', '#b07d10'];

  function el(tag, attrs, padre) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (padre) padre.appendChild(n);
    return n;
  }
  function texto(padre, x, y, t, extra) {
    const n = el('text', Object.assign({ x, y }, extra || {}), padre);
    n.textContent = t;
    return n;
  }
  const esNum = v => typeof v === 'number' && isFinite(v);
  function fmt(v, unidad) {
    if (!esNum(v)) return String(v);
    if (unidad === 'proporcion') return (v * 100).toFixed(1) + '%';
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(1) + ' M';
    if (a >= 1e4) return Math.round(v).toLocaleString('es');
    if (a >= 100) return v.toFixed(0);
    return Number(v.toPrecision(3)).toString();
  }

  /* Decide qué columnas usar y el tipo natural del gráfico. */
  function analizar(nombre, filas) {
    filas = (filas || []).filter(f => f && typeof f === 'object');
    if (!filas.length) return null;
    const claves = Object.keys(filas[0]);
    if (claves.includes('q1') && claves.includes('q3')) return { tipo: 'caja', filas, etiqueta: claves.find(k => !esNum(filas[0][k])) || 'metrica' };
    const valor = VALORES.find(k => claves.includes(k) && filas.some(f => esNum(f[k])));
    if (!valor) return null;
    let serie = null, x = null;
    if (claves.includes('anio') && claves.includes('pais')) { x = 'anio'; serie = 'pais'; }
    else if (claves.includes('periodo') && claves.includes('indicador')) { x = 'periodo'; serie = 'indicador'; }
    const etiqueta = x || ETIQUETAS.find(k => claves.includes(k) && k !== valor) || claves.find(k => k !== valor);
    const temporal = !!x || /tendencia|evol/.test(nombre) || etiqueta === 'periodo';
    if (claves.includes('desde') && claves.includes('hasta')) return { tipo: 'barras', filas, valor, etiqueta: 'rango', agrupado: true };
    if (claves.includes('x') && valor === 'y') return { tipo: 'dispersion', filas, valor, etiqueta: 'entidad', unidad: null };
    return { tipo: temporal ? 'lineas' : 'barras', filas, valor, etiqueta, serie, unidad: valor === 'rho' ? 'rho' : null };
  }

  function escalaY(min, max) {
    if (min === max) { min -= 1; max += 1; }
    const paso = Math.pow(10, Math.floor(Math.log10((max - min) / 4)));
    const mult = [1, 2, 2.5, 5, 10].find(m => (max - min) / (paso * m) <= 5) || 10;
    const p = paso * mult;
    const lo = Math.floor(min / p) * p, hi = Math.ceil(max / p) * p;
    const ticks = []; for (let v = lo; v <= hi + p / 2; v += p) ticks.push(+v.toFixed(10));
    return { lo, hi, ticks };
  }

  function lienzo(alto) {
    const svg = el('svg', { viewBox: `0 0 640 ${alto}`, role: 'img' });
    return svg;
  }

  function ejes(svg, esc, area, unidad) {
    const { x0, x1, y0, y1 } = area;
    esc.ticks.forEach(t => {
      const y = y1 - (t - esc.lo) / (esc.hi - esc.lo) * (y1 - y0);
      el('line', { x1: x0, x2: x1, y1: y, y2: y, stroke: 'var(--grid)', 'stroke-width': 1 }, svg);
      texto(svg, x0 - 6, y + 4, fmt(t, unidad), { 'text-anchor': 'end' });
    });
  }

  function barras(info, unidad, horizontal) {
    const filas = info.filas.slice(0, 30);
    if (horizontal) {
      const alto = 30 + filas.length * 26;
      const svg = lienzo(alto);
      const vals = filas.map(f => f[info.valor]);
      const max = Math.max(0, ...vals), min = Math.min(0, ...vals);
      const x0 = 170, x1 = 600;
      const esc = v => x0 + (v - min) / ((max - min) || 1) * (x1 - x0);
      filas.forEach((f, i) => {
        const y = 14 + i * 26, v = f[info.valor];
        const a = esc(Math.min(0, v)), b = esc(Math.max(0, v));
        const r = el('rect', { x: a, y, width: Math.max(1, b - a), height: 18, rx: 3, fill: PALETA[0] }, svg);
        el('title', {}, r).textContent = `${f[info.etiqueta]}: ${fmt(v, unidad)}`;
        texto(svg, x0 - 8, y + 13, String(f[info.etiqueta]).slice(0, 24), { 'text-anchor': 'end' });
        texto(svg, b + 4, y + 13, fmt(v, unidad));
      });
      return svg;
    }
    const svg = lienzo(300);
    const vals = filas.map(f => f[info.valor]);
    const esc = escalaY(Math.min(0, ...vals), Math.max(0, ...vals));
    const area = { x0: 60, x1: 625, y0: 16, y1: 240 };
    ejes(svg, esc, area, unidad);
    const ancho = (area.x1 - area.x0) / filas.length;
    const y = v => area.y1 - (v - esc.lo) / (esc.hi - esc.lo) * (area.y1 - area.y0);
    filas.forEach((f, i) => {
      const v = f[info.valor], x = area.x0 + i * ancho + ancho * 0.15;
      const top = y(Math.max(0, v)), base = y(Math.min(0, v));
      const r = el('rect', { x, y: top, width: ancho * 0.7, height: Math.max(1, base - top), rx: 3, fill: PALETA[0] }, svg);
      el('title', {}, r).textContent = `${f[info.etiqueta]}: ${fmt(v, unidad)}`;
      if (filas.length <= 12) texto(svg, x + ancho * 0.35, top - 4, fmt(v, unidad), { 'text-anchor': 'middle' });
      const etq = String(f[info.etiqueta]);
      texto(svg, x + ancho * 0.35, 256, etq.length > 12 ? etq.slice(0, 11) + '…' : etq,
        (filas.length > 8 || filas.some(f => String(f[info.etiqueta]).length > 10)) ? { 'text-anchor': 'end', transform: `rotate(-35 ${x + ancho * 0.35} 256)` } : { 'text-anchor': 'middle' });
    });
    return svg;
  }

  function lineas(info, unidad, rellenar) {
    const svg = lienzo(300);
    const series = {};
    info.filas.forEach(f => { const s = info.serie ? f[info.serie] : 'valor'; (series[s] = series[s] || []).push(f); });
    const xs = [...new Set(info.filas.map(f => f[info.etiqueta]))];
    if (xs.every(esNum)) xs.sort((a, b) => a - b);
    const vals = info.filas.map(f => f[info.valor]);
    const esc = escalaY(Math.min(...vals, rellenar ? 0 : Infinity), Math.max(...vals));
    const area = { x0: 60, x1: 625, y0: 16, y1: 240 };
    ejes(svg, esc, area, unidad);
    const px = v => area.x0 + (xs.length === 1 ? 0.5 : xs.indexOf(v) / (xs.length - 1)) * (area.x1 - area.x0);
    const py = v => area.y1 - (v - esc.lo) / (esc.hi - esc.lo) * (area.y1 - area.y0);
    const salto = Math.ceil(xs.length / 10);
    xs.forEach((x, i) => { if (i % salto === 0) texto(svg, px(x), 258, String(x).slice(0, 10), { 'text-anchor': 'middle' }); });
    Object.entries(series).forEach(([nombre, filas], k) => {
      filas = filas.slice().sort((a, b) => xs.indexOf(a[info.etiqueta]) - xs.indexOf(b[info.etiqueta]));
      const d = filas.map((f, i) => `${i ? 'L' : 'M'}${px(f[info.etiqueta]).toFixed(1)},${py(f[info.valor]).toFixed(1)}`).join(' ');
      const color = PALETA[k % PALETA.length];
      if (rellenar && filas.length) el('path', { d: `${d} L${px(filas[filas.length - 1][info.etiqueta])},${area.y1} L${px(filas[0][info.etiqueta])},${area.y1} Z`, fill: color, opacity: 0.15 }, svg);
      el('path', { d, fill: 'none', stroke: color, 'stroke-width': 2 }, svg);
      filas.forEach(f => {
        const c = el('circle', { cx: px(f[info.etiqueta]), cy: py(f[info.valor]), r: 4, fill: color, stroke: 'var(--surface)', 'stroke-width': 2 }, svg);
        el('title', {}, c).textContent = `${info.serie ? nombre + ' · ' : ''}${f[info.etiqueta]}: ${fmt(f[info.valor], unidad)}`;
      });
    });
    if (info.serie) Object.keys(series).forEach((n, k) => {
      el('rect', { x: 70 + k * 130, y: 280, width: 10, height: 10, fill: PALETA[k % PALETA.length], rx: 2 }, svg);
      texto(svg, 84 + k * 130, 289, String(n).slice(0, 18));
    });
    return svg;
  }

  function pastel(info, unidad) {
    const filas = info.filas.filter(f => f[info.valor] > 0).slice(0, 8);
    const total = filas.reduce((s, f) => s + f[info.valor], 0);
    const svg = lienzo(260);
    let ang = -Math.PI / 2;
    filas.forEach((f, i) => {
      const a = f[info.valor] / total * Math.PI * 2;
      const x1 = 130 + 110 * Math.cos(ang), y1 = 130 + 110 * Math.sin(ang);
      ang += a;
      const x2 = 130 + 110 * Math.cos(ang), y2 = 130 + 110 * Math.sin(ang);
      const p = el('path', { d: `M130,130 L${x1},${y1} A110,110 0 ${a > Math.PI ? 1 : 0} 1 ${x2},${y2} Z`, fill: PALETA[i % PALETA.length], stroke: 'var(--surface)', 'stroke-width': 2 }, svg);
      el('title', {}, p).textContent = `${f[info.etiqueta]}: ${fmt(f[info.valor], unidad)}`;
      el('rect', { x: 280, y: 30 + i * 26, width: 12, height: 12, rx: 2, fill: PALETA[i % PALETA.length] }, svg);
      texto(svg, 300, 41 + i * 26, `${String(f[info.etiqueta]).slice(0, 26)} — ${fmt(f[info.valor], unidad)} (${(f[info.valor] / total * 100).toFixed(1)}% del total)`);
    });
    return svg;
  }

  function caja(info) {
    const svg = lienzo(70 + info.filas.length * 40);
    const min = Math.min(...info.filas.map(f => f.min)), max = Math.max(...info.filas.map(f => f.max));
    const x = v => 160 + (v - min) / ((max - min) || 1) * 440;
    info.filas.forEach((f, i) => {
      const y = 30 + i * 40;
      texto(svg, 150, y + 14, String(f[info.etiqueta] || '').slice(0, 20), { 'text-anchor': 'end' });
      el('line', { x1: x(f.min), x2: x(f.max), y1: y + 10, y2: y + 10, stroke: 'var(--fg-faint)' }, svg);
      el('rect', { x: x(f.q1), y, width: Math.max(2, x(f.q3) - x(f.q1)), height: 20, fill: 'var(--accent-bg)', stroke: 'var(--accent)' }, svg);
      el('line', { x1: x(f.mediana), x2: x(f.mediana), y1: y, y2: y + 20, stroke: 'var(--accent)', 'stroke-width': 3 }, svg);
      const t = el('title', {}, svg.lastChild); t.textContent = `mín ${fmt(f.min)} · Q1 ${fmt(f.q1)} · mediana ${fmt(f.mediana)} · Q3 ${fmt(f.q3)} · máx ${fmt(f.max)}`;
    });
    texto(svg, 160, 20 + info.filas.length * 40 + 24, fmt(min)); texto(svg, 600, 20 + info.filas.length * 40 + 24, fmt(max), { 'text-anchor': 'end' });
    return svg;
  }

  function dispersion(info, unidad) {
    const numericas = Object.keys(info.filas[0]).filter(k => k !== info.valor && info.filas.every(f => esNum(f[k])));
    if (!numericas.length) return null;
    const kx = numericas.includes('x') ? 'x' : numericas[0];
    const svg = lienzo(292);
    const ys = info.filas.map(f => f[info.valor]), xs = info.filas.map(f => f[kx]);
    const ey = escalaY(Math.min(...ys), Math.max(...ys)), ex = escalaY(Math.min(...xs), Math.max(...xs));
    const area = { x0: 60, x1: 625, y0: 16, y1: 240 };
    ejes(svg, ey, area, unidad);
    info.filas.forEach(f => {
      const c = el('circle', { cx: area.x0 + (f[kx] - ex.lo) / (ex.hi - ex.lo) * (area.x1 - area.x0), cy: area.y1 - (f[info.valor] - ey.lo) / (ey.hi - ey.lo) * (area.y1 - area.y0), r: 5, fill: PALETA[0], opacity: .8 }, svg);
      el('title', {}, c).textContent = `${f[info.etiqueta]}: ${kx} ${fmt(f[kx])}, ${info.valor} ${fmt(f[info.valor], unidad)}`;
    });
    ex.ticks.forEach(t => texto(svg, area.x0 + (t - ex.lo) / (ex.hi - ex.lo) * (area.x1 - area.x0), 256, fmt(t), { 'text-anchor': 'middle' }));
    const f0 = info.filas[0];
    texto(svg, 340, 282, f0.eje_x || kx, { 'text-anchor': 'middle' });
    texto(svg, 14, 128, f0.eje_y || info.valor, { 'text-anchor': 'middle', transform: 'rotate(-90 14 128)' });
    return svg;
  }

  function histograma(info, unidad) {
    const vals = info.filas.map(f => f[info.valor]).filter(esNum);
    const min = Math.min(...vals), max = Math.max(...vals);
    const k = Math.min(12, Math.max(4, Math.ceil(Math.sqrt(vals.length))));
    const ancho = (max - min) / k || 1;
    const cubos = Array.from({ length: k }, (_, i) => ({ rango: `${fmt(min + i * ancho, unidad)}–${fmt(min + (i + 1) * ancho, unidad)}`, conteo: 0 }));
    vals.forEach(v => { cubos[Math.min(k - 1, Math.floor((v - min) / ancho))].conteo++; });
    return barras({ filas: cubos, valor: 'conteo', etiqueta: 'rango' }, null, false);
  }

  const TIPOS = { barras: 'Barras', barras_h: 'Barras horizontales', lineas: 'Líneas', area: 'Área', pastel: 'Pastel', dispersion: 'Dispersión', histograma: 'Histograma', caja: 'Caja' };

  /* Dibuja dentro de `contenedor`. Respeta el tipo pedido si es posible; si no, lo dice. */
  function dibujar(contenedor, nombre, filas, pedido, unidad) {
    const info = analizar(nombre, filas);
    contenedor.innerHTML = '';
    if (!info) return false;
    const natural = info.tipo;
    let tipo = pedido && pedido !== 'auto' ? ({ lineas: 'lineas', barras: 'barras', pastel: 'pastel', dispersion: 'dispersion', histograma: 'histograma', caja: 'caja', area: 'area', calor: 'barras' }[pedido] || natural) : natural;
    if (natural === 'caja') tipo = 'caja';
    if (info.agrupado && pedido === 'histograma') tipo = 'histograma';
    if (natural === 'dispersion' && pedido !== 'dispersion') tipo = 'dispersion';
    const barra = document.createElement('div');
    barra.className = 'barra-graf';
    const sel = document.createElement('select');
    sel.style.width = 'auto';
    Object.entries(TIPOS).forEach(([k, v]) => { if (natural === 'caja' ? k === 'caja' : k !== 'caja') sel.add(new Option(v, k, false, k === tipo)); });
    const titulo = document.createElement('span');
    titulo.className = 'etiqueta';
    titulo.textContent = `Datos: ${nombre} · ${info.filas.length} registros`;
    barra.append(sel, titulo);
    const lienzoDiv = document.createElement('div');
    const nota = document.createElement('div');
    nota.className = 'etiqueta';
    contenedor.append(barra, lienzoDiv, nota);
    const pintar = t => {
      lienzoDiv.innerHTML = ''; nota.textContent = '';
      let svg = null;
      const u = info.unidad || unidad;
      if (t === 'caja') svg = caja(info);
      else if (t === 'lineas' || t === 'area') svg = lineas(info, u, t === 'area');
      else if (t === 'pastel') svg = info.filas.some(f => f[info.valor] < 0) ? null : pastel(info, u);
      else if (t === 'dispersion') svg = dispersion(info, u);
      else if (t === 'histograma') svg = info.agrupado ? barras(info, u, false) : histograma(info, u);   // agrupado = ya viene en intervalos
      else svg = barras(info, u, t === 'barras_h' || (t === 'barras' && info.filas.length > 14));
      if (!svg) { nota.textContent = `Un gráfico de ${TIPOS[t].toLowerCase()} no es adecuado para estos datos; muestro ${TIPOS[natural].toLowerCase()}.`; svg = natural === 'lineas' ? lineas(info, u) : barras(info, u); }
      svg.setAttribute('aria-label', `Gráfico de ${TIPOS[t]} de ${nombre}`);
      lienzoDiv.appendChild(svg);
    };
    sel.onchange = () => pintar(sel.value);
    pintar(tipo);
    return true;
  }

  window.DinamoGraficos = { dibujar, analizar };
})();

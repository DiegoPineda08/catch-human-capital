/* DINAMO Analytics — interfaz Fase 1 sobre el diseño PRO MAX.
   Habla con el servidor local (dinamo/servidor). Reglas: subir un archivo NO dispara análisis,
   IA, gráficos, investigación ni voz. Ninguna clave de API vive en el navegador. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const S = { conversaciones: [], actual: null, estado: null, vista: 'chat', motorWeb: null, cargandoWeb: false,
              enviando: false, paises: null, invModo: 'web', invResultado: null, nav: 0 };
  const pref = (k, d) => { try { return localStorage.getItem('dinamo.' + k) ?? d; } catch (e) { return d; } };
  const guardar = (k, v) => { try { localStorage.setItem('dinamo.' + k, v); } catch (e) { /* sin almacenamiento */ } };

  // ------------------------------------------------------------------ utilidades
  const esc = t => String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function toast(msg) {
    const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg;
    $('#toasts').appendChild(t); setTimeout(() => t.remove(), 3600);
  }
  async function api(ruta, op = {}) {
    const cab = Object.assign({ 'X-DINAMO': '1' }, op.headers || {});
    if (op.json !== undefined) { cab['Content-Type'] = 'application/json'; op.body = JSON.stringify(op.json); }
    const r = await fetch(ruta, Object.assign({}, op, { headers: cab }));
    if (op.crudo) return r;
    let d = null; try { d = await r.json(); } catch (e) { /* vacío */ }
    if (!r.ok) throw new Error((d && d.error) || `Error ${r.status}`);
    return d;
  }
  function fmtValor(e) {
    const v = e.valor;
    if (typeof v !== 'number') return String(v);
    switch (e.unidad) {
      case 'proporcion': return (v * 100).toFixed(1) + '%';
      case 'diferencia_proporcion': return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + ' pp';
      case 'cambio_relativo': return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
      case 'moneda': return '$' + Math.round(v).toLocaleString('es');
      case 'rho': return (v >= 0 ? '+' : '') + v.toFixed(2);
      case 'porcentaje': return v.toLocaleString('es', { maximumFractionDigits: 1 }) + '%';
      default: return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('es') : Number(v.toPrecision(4)).toString();
    }
  }
  const SVG = {
    ojo: '<svg class="i" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    voz: '<svg class="i" viewBox="0 0 24 24"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15 9a5 5 0 0 1 0 6"/></svg>',
    copiar: '<svg class="i" viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>',
    flecha: '<svg class="i flecha" viewBox="0 0 24 24"><path d="M7 17 17 7M8 7h9v9"/></svg>',
    nube: '<svg class="i" viewBox="0 0 24 24"><path d="M7 18a5 5 0 0 1-.5-10A6 6 0 0 1 18 9a4.5 4.5 0 0 1 0 9"/><path d="M12 12v8M9 15l3-3 3 3"/></svg>',
    borrar: '<svg class="i" viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
  };

  // ------------------------------------------------------------------ markdown seguro + citas
  function enLinea(t, malas) {
    t = esc(t)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (m, x, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${x}</a>`);
    return t.replace(/\[(E|W|C):([^\]]+)\]/g, (m, k, id) => {
      const clave = `${k}:${id}`, mala = malas.has(clave) ? ' mala' : '';
      const et = k === 'W' ? 'W' + id : k === 'E' ? 'dato' : 'doc';
      return `<button class="ref ${k.toLowerCase()}${mala}" data-ref="${esc(clave)}" title="${mala ? 'Cita no verificada' : 'Ver origen'}: ${esc(clave)}">${et}</button>`;
    });
  }
  function markdown(texto, malas = new Set()) {
    let html = '', lista = null, tabla = [];
    const cerrar = () => { if (lista) { html += `</${lista}>`; lista = null; } };
    const volcar = () => {
      if (!tabla.length) return;
      const filas = tabla.filter(f => !/^\s*\|?\s*:?-{2,}/.test(f)).map(f => f.trim().replace(/^\||\|$/g, '').split('|'));
      html += '<div class="tabla-wrap"><table class="t">' + filas.map((c, i) => '<tr>' + c.map(x => `<${i ? 'td' : 'th'}>${enLinea(x.trim(), malas)}</${i ? 'td' : 'th'}>`).join('') + '</tr>').join('') + '</table></div>';
      tabla = [];
    };
    for (const l of String(texto || '').split('\n')) {
      if (/^\s*\|.*\|\s*$/.test(l)) { cerrar(); tabla.push(l); continue; } else volcar();
      let m;
      if ((m = l.match(/^#{1,6}\s+(.*)/))) { cerrar(); html += `<h3>${enLinea(m[1], malas)}</h3>`; }
      else if ((m = l.match(/^\s*[-*•]\s+(.*)/))) { if (lista !== 'ul') { cerrar(); html += '<ul>'; lista = 'ul'; } html += `<li>${enLinea(m[1], malas)}</li>`; }
      else if ((m = l.match(/^\s*\d+[.)]\s+(.*)/))) { if (lista !== 'ol') { cerrar(); html += '<ol>'; lista = 'ol'; } html += `<li>${enLinea(m[1], malas)}</li>`; }
      else if (!l.trim()) cerrar();
      else { cerrar(); html += `<p>${enLinea(l, malas)}</p>`; }
    }
    cerrar(); volcar();
    return html;
  }
  const citasMalas = m => { const s = new Set(); (m.verificacion || []).forEach(p => (p.match(/[EWC]:[^,\s]+/g) || []).forEach(c => s.add(c))); return s; };
  const textoPlano = t => String(t || '').replace(/\[(E|W|C):[^\]]+\]/g, '').replace(/[#*`|>_]/g, '').replace(/\s+/g, ' ').trim();

  // ------------------------------------------------------------------ tema y acento
  function aplicarTema() {
    const tema = pref('tema', matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    document.documentElement.dataset.theme = tema;
    $('#txtTema').textContent = tema === 'dark' ? 'Oscuro' : 'Claro';
    const acento = pref('acento', 'azul');
    document.documentElement.dataset.accent = acento;
    $$('.acentos button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.acento === acento)));
  }
  $('#btnTema').onclick = () => { guardar('tema', document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'); aplicarTema(); };
  $$('.acentos button').forEach(b => b.onclick = () => { guardar('acento', b.dataset.acento); aplicarTema(); });

  // ------------------------------------------------------------------ estado del servidor e IA
  async function cargarEstado(forzar) {
    try {
      S.estado = await api('/api/estado' + (forzar ? '?forzar=1' : ''));
      $('#bannerServidor').hidden = true;
      $('#estadoServidor').innerHTML = '<span class="punto on"></span><span>Servidor local conectado</span>';
    } catch (e) {
      $('#bannerServidor').hidden = false;
      $('#bannerServidor').textContent = 'No hay conexión con el servidor de DINAMO. Ábrelo con INICIAR_DINAMO.bat (o «python -m dinamo.servidor») y recarga esta página.';
      $('#estadoServidor').innerHTML = '<span class="punto"></span><span>Servidor sin conexión</span>';
      return;
    }
    pintarIA();
  }
  function pintarIA() {
    const e = S.estado; if (!e) return;
    let txt, on = true;
    if (e.llm) txt = `${e.llm.etiqueta} · ${e.llm.modelo}${e.llm.nube ? ' (nube)' : ''}`;
    else if (S.motorWeb) txt = 'IA del navegador (local)';
    else { txt = S.cargandoWeb ? 'Descargando IA del navegador…' : 'Sin modelo: cálculos y fuentes sin redactar'; on = false; }
    $('#estadoLLM').innerHTML = `<span class="punto ${on ? 'on' : ''}"></span><span>IA: ${esc(txt)}</span>`;
    $('#railAIStatus').textContent = e.llm ? (e.llm.nube ? 'Nube · ' + e.llm.etiqueta : 'Local · ' + e.llm.etiqueta) : S.motorWeb ? 'WebLLM local' : 'Sin modelo';
    $('#btnWebLLM').hidden = !!e.llm || !!S.motorWeb || S.cargandoWeb;
    $('#avatarBadge').textContent = on ? 'IA lista para conversar' : 'Sin modelo de lenguaje';
    $('#privacidad').textContent = $('#privacidad').title = (S.motorWeb && !e.llm ? 'La IA del navegador redacta en tu equipo. ' : e.privacidad + ' ') + e.investigacion;
  }
  const MODELO_WEB = 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC';
  async function activarWebLLM() {
    if (!('gpu' in navigator)) { toast('Este navegador no tiene WebGPU: usa Chrome o Edge recientes, o configura un modelo en el servidor.'); return; }
    S.cargandoWeb = true; pintarIA();
    try {
      const webllm = await import('https://esm.run/@mlc-ai/web-llm@0.2.81');
      S.motorWeb = await webllm.CreateMLCEngine(MODELO_WEB, { initProgressCallback: p => {
        $('#estadoLLM').innerHTML = `<span class="punto"></span><span>Descargando IA: ${Math.round((p.progress || 0) * 100)}%</span>`; } });
      guardar('webllm', '1'); toast('IA del navegador lista.');
    } catch (e) { S.motorWeb = null; toast('No se pudo activar la IA del navegador: ' + (e.message || e)); }
    S.cargandoWeb = false; pintarIA();
  }
  $('#btnWebLLM').onclick = activarWebLLM;
  $('#estadoLLM').onclick = $('#btnAjustes').onclick = () => irA('integraciones');

  // ------------------------------------------------------------------ perfil (cambia el tono, nunca los números)
  function perfil() { try { return JSON.parse(pref('perfil', '{}')); } catch (e) { return {}; } }
  function pintarPerfil() {
    const p = perfil();
    $('#nombrePerfil').textContent = p.nombre || 'Tu perfil';
    $('#subPerfil').textContent = p.rol || 'Añadir nombre y rol';
    $('#avatarPerfil').textContent = (p.nombre || 'DINAMO Analytics').split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
  }
  $('#btnPerfil').onclick = () => {
    const p = perfil();
    const m = modal('Tu perfil', `<div class="perfil-preview"><span class="perfil-avatar">${esc($('#avatarPerfil').textContent)}</span>
      <div class="etiqueta">DINAMO adapta el tono de las respuestas a tu rol. Nunca cambia las cifras. Se guarda sólo en este navegador.</div></div>
      <form class="formulario" id="fPerfil"><label>Nombre<input name="nombre" maxlength="48" value="${esc(p.nombre || '')}"></label>
      <label>Rol<input name="rol" maxlength="60" placeholder="Ej.: Gerente de RR. HH." value="${esc(p.rol || '')}"></label>
      <label>Nivel de detalle<select name="nivel"><option value="general">General</option><option value="directivo">Directivo (conclusión y acción)</option><option value="analista">Analista (método y muestra)</option></select></label>
      <button class="btn primario">Guardar</button></form>`);
    m.querySelector('[name=nivel]').value = p.nivel || 'general';
    m.querySelector('#fPerfil').onsubmit = e => { e.preventDefault(); const f = e.target;
      guardar('perfil', JSON.stringify({ nombre: f.nombre.value.trim(), rol: f.rol.value.trim(), nivel: f.nivel.value })); pintarPerfil(); cerrarModal(); };
  };
  function modal(titulo, html) {
    cerrarModal();
    const f = document.createElement('div'); f.className = 'modal-fondo'; f.id = 'modalFondo';
    f.innerHTML = `<div class="modal" role="dialog" aria-modal="true"><div class="modal-head"><h3>${esc(titulo)}</h3><button class="icon-btn" data-cerrar aria-label="Cerrar">✕</button></div><div class="modal-cuerpo">${html}</div></div>`;
    f.addEventListener('click', e => { if (e.target === f || e.target.closest('[data-cerrar]')) cerrarModal(); });
    document.body.appendChild(f);
    return f;
  }
  function cerrarModal() { const f = $('#modalFondo'); if (f) f.remove(); }
  document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarModal(); });

  // ------------------------------------------------------------------ conversaciones
  async function cargarConversaciones() {
    S.conversaciones = (await api('/api/conversaciones')).conversaciones;
    $('#badgeHist').textContent = S.conversaciones.length;
    const c = $('#recientes'); c.innerHTML = '';
    if (!S.conversaciones.length) { c.innerHTML = '<div class="recientes-vacio">Aún no hay conversaciones.</div>'; return; }
    S.conversaciones.slice(0, 30).forEach(x => {
      const b = document.createElement('button');
      b.className = 'reciente' + (S.actual && S.actual.id === x.id ? ' activo' : '');
      b.textContent = x.titulo; b.title = x.titulo;
      b.onclick = () => { abrir(x.id); irA('chat'); };
      c.appendChild(b);
    });
  }
  async function nueva() {
    S.nav++;
    S.actual = await api('/api/conversaciones', { method: 'POST', json: {} });
    guardar('actual', S.actual.id);
    await cargarConversaciones(); pintarTodo(); irA('chat'); $('#entrada').focus();
  }
  async function abrir(id) {
    const turno = ++S.nav;
    let c;
    try { c = await api('/api/conversaciones/' + id); } catch (e) { toast(e.message); return; }
    if (turno !== S.nav) return;              // el usuario abrió otra conversación mientras cargaba
    S.actual = c; guardar('actual', id);
    await cargarConversaciones(); pintarTodo();
    if (S.vista !== 'chat') pintarVista(S.vista);
  }
  async function recargar() { if (S.actual) S.actual = await api('/api/conversaciones/' + S.actual.id); }
  $('#btnNueva').onclick = nueva;

  function pintarTodo() {
    $('#tituloConv').textContent = S.actual ? S.actual.titulo : 'Nueva conversación';
    pintarHilo(); pintarRail();
    const ult = S.actual && [...S.actual.mensajes].reverse().find(m => m.rol === 'asistente');
    pintarFuentes(ult);
  }

  // ------------------------------------------------------------------ hilo de mensajes
  const EJEMPLOS = ['Calcula la rotación, la retención y el ausentismo por mes', '¿Hay anomalías en las bajas?',
    'Compara el desempleo de México, Colombia y España', 'Busca artículos científicos sobre rotación voluntaria',
    'Investiga en internet buenas prácticas de onboarding'];
  function pintarHilo() {
    const h = $('#hilo'); h.innerHTML = '';
    if (!S.actual || !S.actual.mensajes.length) { h.appendChild(bienvenida()); return; }
    S.actual.mensajes.forEach(m => h.appendChild(nodoMensaje(m)));
    desplazar();
  }
  function bienvenida() {
    const d = document.createElement('div'); d.className = 'bienvenida';
    d.innerHTML = `<h2>Del dato a la decisión, <em>con evidencia</em>.</h2>
      <p class="lead">Pregunta sobre tus archivos, pide una investigación con fuentes o simplemente conversa. Lo que subas se guarda en este chat y sólo se analiza cuando preguntas.</p>
      <div class="zona-carga" id="zonaBienvenida" role="button" tabindex="0">${SVG.nube}<div class="grande">Arrastra archivos o haz clic</div><div class="formatos">Excel · CSV · PDF · TXT · Markdown</div></div>
      <div class="pasos">
        <div class="paso"><span class="num">01</span><b>Calcula con Python</b><span>Rotación, ausentismo, rankings, anomalías: cifras reproducibles.</span></div>
        <div class="paso"><span class="num">02</span><b>Investiga con fuentes</b><span>Web, artículos y Banco Mundial, con el estado de lectura de cada fuente.</span></div>
        <div class="paso"><span class="num">03</span><b>Explica y cita</b><span>La IA redacta; cada cifra lleva su origen y se verifica.</span></div>
      </div>
      <div class="sigue"><div class="sigue-label">Puedes empezar por</div>${EJEMPLOS.map(e => `<button class="sugerencia" data-ej="${esc(e)}">${esc(e)} ${SVG.flecha}</button>`).join('')}</div>`;
    const z = d.querySelector('#zonaBienvenida');
    z.onclick = () => $('#inputArchivos').click();
    z.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#inputArchivos').click(); } };
    d.querySelectorAll('.sugerencia').forEach(b => b.onclick = () => { $('#entrada').value = b.dataset.ej; autoAltura(); $('#entrada').focus(); });
    return d;
  }
  function desplazar() { const v = $('#mensajes'); v.scrollTop = v.scrollHeight; }
  function nodoMensaje(m) {
    if (m.rol === 'usuario') {
      const d = document.createElement('div'); d.className = 'burbuja-usuario';
      d.innerHTML = `<div class="txt">${esc(m.mostrar || m.texto)}</div>`; return d;
    }
    if (m.rol === 'sistema') { const d = document.createElement('div'); d.className = 'sistema'; d.textContent = m.texto; return d; }
    const a = document.createElement('article'); a.className = 'capitulo'; a.dataset.id = m.id || '';
    a.innerHTML = '<div class="cap-head"></div><div class="relato"></div>';
    a.querySelector('.relato').innerHTML = markdown(m.texto, citasMalas(m));
    decorar(a, m);
    return a;
  }
  function etiquetaModelo(m) {
    if (!m.modelo) return '';
    if (m.modelo.proveedor === 'ninguno') return 'sin modelo de lenguaje';
    if (m.modelo.proveedor === 'navegador') return 'IA del navegador';
    return (m.modelo.etiqueta || m.modelo.proveedor) + (m.modelo.modelo ? ' · ' + m.modelo.modelo : '');
  }
  function decorar(a, m) {
    const plan = m.plan || {};
    const pasos = (plan.pasos || []).map(p => p.herramienta.replace(/_/g, ' '));
    const tag = m.tipo === 'aclaracion' ? 'Necesito un dato' : (m.fuentes || []).length ? 'Investigación' : (m.evidencias || []).length ? 'Análisis' : 'Respuesta';
    const head = a.querySelector('.cap-head');
    head.innerHTML = `<span class="cap-tag">${tag}</span><span class="cap-fuente" title="${esc(plan.razon || '')}">${esc([etiquetaModelo(m), pasos.length ? pasos.join(' → ') : 'conocimiento general'].filter(Boolean).join(' · '))}</span>
      <div class="cap-acciones"><button class="icon-btn" data-acc="origen" title="Ver cálculos y fuentes">${SVG.ojo}</button><button class="icon-btn" data-acc="voz" title="Escuchar">${SVG.voz}</button><button class="icon-btn" data-acc="copiar" title="Copiar">${SVG.copiar}</button></div>`;
    head.querySelector('[data-acc=origen]').onclick = () => pintarFuentes(m, true);
    head.querySelector('[data-acc=voz]').onclick = () => hablar(m.texto);
    head.querySelector('[data-acc=copiar]').onclick = () => navigator.clipboard.writeText(m.texto).then(() => toast('Copiado'), () => toast('No se pudo copiar'));
    a.querySelectorAll('.extra').forEach(x => x.remove());
    const ev = m.evidencias || [];
    if (ev.length) {   // tarjetas KPI con los primeros cálculos, como en el diseño original
      const k = document.createElement('div'); k.className = 'kpis extra';
      k.innerHTML = ev.slice(0, 4).map(e => `<div class="kpi"><div class="k-et" title="${esc(e.descripcion)}">${esc(e.descripcion.length > 46 ? e.descripcion.slice(0, 45) + '…' : e.descripcion)}</div><div class="k-val">${esc(fmtValor(e))}</div><div class="k-nota">n=${e.n} · ${esc(e.skill.replace(/_/g, ' '))}</div></div>`).join('');
      a.querySelector('.relato').before(k);
    }
    const extra = document.createElement('div'); extra.className = 'extra'; extra.style.cssText = 'display:flex;flex-direction:column;gap:12px';
    if ((m.opciones || []).length) {
      const s = document.createElement('div'); s.className = 'sigue';
      s.innerHTML = '<div class="sigue-label">Elige una opción</div>';
      m.opciones.forEach(o => { const b = document.createElement('button'); b.className = 'sugerencia'; b.innerHTML = esc(o) + SVG.flecha; b.onclick = () => enviar(o); s.appendChild(b); });
      extra.appendChild(s);
    }
    const datos = m.datos || {};
    const nombres = Object.keys(datos).filter(k => window.DinamoGraficos.analizar(k, datos[k]));
    if (nombres.length) {
      const g = document.createElement('div'); g.className = 'grafica-bloque';
      const unidad = ev.some(e => e.unidad === 'proporcion') ? 'proporcion' : null;
      const top = document.createElement('div'); top.className = 'grafica-top';
      top.innerHTML = '<span class="grafica-titulo">Gráfica de los datos calculados</span>';
      const sel = document.createElement('select'); sel.className = 'seg-select'; nombres.forEach(n => sel.add(new Option(n.replace(/_/g, ' '), n)));
      if (nombres.length > 1) top.appendChild(sel);
      const area = document.createElement('div');
      const pintar = () => window.DinamoGraficos.dibujar(area, sel.value, datos[sel.value], m.grafico, unidad);
      sel.onchange = pintar;
      g.append(top, area);
      if (m.grafico || nombres.some(n => /tendencia|indicador_pais|histograma|dispersion/.test(n))) { extra.appendChild(g); pintar(); }
      else { const w = document.createElement('div'); w.className = 'chips-accion'; const b = document.createElement('button'); b.className = 'chip-accion'; b.textContent = '📊 Ver gráfica'; b.onclick = () => { w.replaceWith(g); pintar(); }; w.appendChild(b); extra.appendChild(w); }
    }
    if ((m.verificacion || []).length) extra.insertAdjacentHTML('beforeend', `<div class="aviso-caja"><b>Verificación automática:</b> ${m.verificacion.map(esc).join(' · ')}</div>`);
    if ((m.advertencias || []).length) extra.insertAdjacentHTML('beforeend', `<details class="fuentes"><summary>Advertencias (${m.advertencias.length})</summary><ul>${m.advertencias.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>`);
    if ((m.sugerencias || []).length) {
      const s = document.createElement('div'); s.className = 'sigue';
      s.innerHTML = '<div class="sigue-label">Puedes seguir con</div>';
      m.sugerencias.slice(0, 3).forEach(x => { const b = document.createElement('button'); b.className = 'sugerencia'; b.innerHTML = esc(x) + SVG.flecha; b.onclick = () => enviar(x); s.appendChild(b); });
      extra.appendChild(s);
    }
    a.appendChild(extra);
    a.querySelectorAll('.ref').forEach(b => b.onclick = () => mostrarCita(m, b.dataset.ref));
  }

  // ------------------------------------------------------------------ enviar (respuesta en streaming)
  async function enviar(forzado, mostrar) {
    if (S.enviando) return;
    const entrada = $('#entrada');
    const texto = (forzado ?? entrada.value).trim();
    if (!texto) return;
    if (!S.actual) await nueva();
    irA('chat');
    entrada.value = ''; autoAltura();
    S.enviando = true; actualizarEnviar();
    const h = $('#hilo');
    if (!S.actual.mensajes.length) h.innerHTML = '';
    h.appendChild(nodoMensaje({ rol: 'usuario', texto, mostrar }));
    const pensando = document.createElement('div'); pensando.className = 'pensando';
    pensando.innerHTML = '<div class="paso-p activo"><span class="ic"></span><span>Entendiendo la pregunta…</span></div>';
    h.appendChild(pensando); desplazar();
    const art = document.createElement('article'); art.className = 'capitulo'; art.hidden = true;
    art.innerHTML = '<div class="cap-head"><span class="cap-tag">Respuesta</span><span class="cap-fuente">redactando…</span></div><div class="relato cursor"></div>';
    h.appendChild(art);
    const relato = art.querySelector('.relato');
    let acumulado = '', final = null;
    const pintar = () => { art.hidden = false; relato.innerHTML = markdown(acumulado); desplazar(); };
    const paso = (txt, estado = 'activo') => {
      pensando.querySelectorAll('.paso-p.activo').forEach(p => p.className = 'paso-p hecho');
      const p = document.createElement('div'); p.className = 'paso-p ' + estado; p.innerHTML = `<span class="ic"></span><span>${esc(txt)}</span>`;
      pensando.appendChild(p); desplazar(); return p;
    };
    try {
      const r = await api(`/api/conversaciones/${S.actual.id}/mensajes`, { method: 'POST', crudo: true,
        json: { texto, llm_navegador: !!S.motorWeb, perfil: perfil() } });
      if (!r.ok) { let d = {}; try { d = await r.json(); } catch (e) { /* */ } throw new Error(d.error || 'Error ' + r.status); }
      const lector = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      for (;;) {
        const { value, done } = await lector.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf('\n')) >= 0) {
          const linea = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
          if (!linea) continue;
          const ev = JSON.parse(linea);
          if (ev.tipo === 'plan') paso(ev.plan.pasos.length ? `Plan: ${ev.plan.pasos.map(x => x.herramienta.replace(/_/g, ' ')).join(' → ')}` : 'Respuesta conversacional, sin herramientas', 'hecho');
          else if (ev.tipo === 'contexto') paso(ev.mensaje, 'hecho');
          else if (ev.tipo === 'herramienta') {
            if (ev.estado === 'inicio') paso(ev.etiqueta + '…');
            else { const u = [...pensando.querySelectorAll('.paso-p')].pop(); const x = ev.resultado;
              if (u) { u.className = 'paso-p hecho'; u.lastChild.textContent = u.lastChild.textContent.replace('…', '') + ` — ${x.evidencias} cálculos, ${x.fuentes} fuentes, ${x.fragmentos} fragmentos`; } }
          } else if (ev.tipo === 'texto') { acumulado = ev.reemplazar ? ev.delta : acumulado + ev.delta; pintar(); }
          else if (ev.tipo === 'necesita_llm') {
            paso('Redactando con la IA del navegador…');
            acumulado = await redactarEnNavegador(ev, t => { acumulado = t; pintar(); });
            final = (await api(`/api/conversaciones/${S.actual.id}/mensajes/${ev.mensaje_id}/completar`, { method: 'POST', json: { texto: acumulado } })).mensaje;
          } else if (ev.tipo === 'final') final = ev.mensaje;
          else if (ev.tipo === 'error') { art.hidden = false; relato.innerHTML = `<div class="error-caja">${esc(ev.mensaje)}</div>`; }
        }
      }
    } catch (e) { art.hidden = false; relato.innerHTML = `<div class="error-caja">No se pudo completar la respuesta: ${esc(e.message)}</div>`; }
    relato.classList.remove('cursor');
    pensando.querySelectorAll('.paso-p.activo').forEach(p => p.className = 'paso-p hecho');
    await recargar();
    if (final) {
      const m = S.actual.mensajes.find(x => x.id === final.id) || final;
      art.hidden = false; art.dataset.id = m.id;
      relato.innerHTML = markdown(m.texto, citasMalas(m));
      decorar(art, m);
      pintarFuentes(m);
      if ($('#avatarAutoRead').checked) hablar(m.texto);
    }
    $('#tituloConv').textContent = S.actual.titulo;
    pintarRail(); cargarConversaciones();
    S.enviando = false; actualizarEnviar(); desplazar();
  }
  async function redactarEnNavegador(ev, avance) {
    if (!S.motorWeb) return ev.respaldo;
    let t = '';
    try {
      const flujo = await S.motorWeb.chat.completions.create({ messages: ev.mensajes, stream: true, temperature: 0.3, max_tokens: 900 });
      for await (const c of flujo) { t += c.choices[0]?.delta?.content || ''; avance(t); }
    } catch (e) { toast('La IA del navegador falló; muestro el material verificado.'); return ev.respaldo; }
    return t.trim() || ev.respaldo;
  }

  // ------------------------------------------------------------------ compositor
  const entrada = $('#entrada');
  function autoAltura() { entrada.style.height = 'auto'; entrada.style.height = Math.min(180, entrada.scrollHeight) + 'px'; actualizarEnviar(); }
  function actualizarEnviar() { $('#btnEnviar').disabled = S.enviando || !entrada.value.trim(); }
  entrada.addEventListener('input', autoAltura);
  entrada.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); enviar(); } });
  $('#btnEnviar').onclick = () => enviar();
  ['#btnAdjuntar', '#railUploadBtn', '#btnSubirDatos'].forEach(s => $(s).onclick = () => $('#inputArchivos').click());
  $('#inputArchivos').onchange = e => { subir([...e.target.files]); e.target.value = ''; };

  async function subir(archivos) {
    if (!archivos.length) return;
    if (!S.actual) await nueva();
    for (const f of archivos) {
      const chip = document.createElement('div'); chip.className = 'ctx-chip';
      chip.innerHTML = `<span class="est leyendo"></span><span>${esc(f.name)}</span>`;
      $('#ctxChips').appendChild(chip);
      try {
        const r = await api(`/api/conversaciones/${S.actual.id}/archivos`, { method: 'POST', body: f,
          headers: { 'X-Nombre-Archivo': encodeURIComponent(f.name), 'Content-Type': 'application/octet-stream' } });
        const a = r.archivo;
        const det = a.tablas.length ? a.tablas.map(t => `${t.filas} filas`).join(', ') : `${a.fragmentos_texto} fragmentos`;
        chip.innerHTML = `<span class="est"></span><span title="Listo. No se analizó: pregunta cuando quieras.">${esc(a.nombre)} · ${esc(det)} · listo</span>`;
      } catch (e) { chip.innerHTML = `<span class="est error"></span><span title="${esc(e.message)}">${esc(f.name)}: ${esc(e.message)}</span>`; }
      setTimeout(() => chip.remove(), 10000);
    }
    await recargar(); pintarRail();
    if (S.vista === 'datos') pintarVista('datos');
  }
  let arrastre = 0;
  document.addEventListener('dragenter', e => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { arrastre++; mostrarSoltar(true); } });
  document.addEventListener('dragleave', () => { arrastre = Math.max(0, arrastre - 1); if (!arrastre) mostrarSoltar(false); });
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', e => { e.preventDefault(); arrastre = 0; mostrarSoltar(false); if (e.dataTransfer.files.length) subir([...e.dataTransfer.files]); });
  function mostrarSoltar(on) {
    let s = $('#capaSoltar');
    if (on && !s) { s = document.createElement('div'); s.className = 'soltar'; s.id = 'capaSoltar'; s.innerHTML = '<div>Suelta para agregar al chat (no se analiza hasta que preguntes)</div>'; document.body.appendChild(s); }
    if (!on && s) s.remove();
  }

  // Dictado: rellena el cuadro; nunca envía solo. Independiente de la voz del avatar.
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  let dictado = null;
  if (!Reconocimiento) $('#btnDictar').hidden = true;
  $('#btnDictar').onclick = () => {
    if (dictado) { dictado.stop(); return; }
    dictado = new Reconocimiento(); dictado.lang = 'es-MX'; dictado.interimResults = true;
    const base = entrada.value ? entrada.value + ' ' : '';
    const est = $('#estadoDictado');
    dictado.onresult = e => { entrada.value = base + [...e.results].map(r => r[0].transcript).join(''); autoAltura(); };
    dictado.onend = () => { dictado = null; $('#btnDictar').classList.remove('escuchando'); $('#btnDictar').setAttribute('aria-pressed', 'false'); est.hidden = false; est.textContent = 'Dictado terminado. Revisa el texto y pulsa Enviar.'; };
    dictado.onerror = e => { est.hidden = false; est.textContent = 'Dictado no disponible: ' + e.error; };
    $('#btnDictar').classList.add('escuchando'); $('#btnDictar').setAttribute('aria-pressed', 'true');
    est.hidden = false; est.textContent = 'Escuchando… (el navegador puede usar su servicio de voz en línea)';
    dictado.start();
  };

  // ------------------------------------------------------------------ avatar y voz (sin sincronización labial)
  const AVATARES = { sofia: { nombre: 'Sofía', src: 'img/sofia.webp' }, mateo: { nombre: 'Mateo', src: 'img/mateo.webp' } };
  const panel = $('#avatarAsistentePanel');
  function ponerAvatar(id) {
    const a = AVATARES[id] || AVATARES.sofia;
    $('#avatarCharacter').src = a.src; $('#avatarCharacter').alt = `${a.nombre}, avatar de DINAMO`;
    $('#avatarNombreAsistente').textContent = `${a.nombre} · Asistente`;
    $$('.assistant-avatar-option').forEach(b => { const on = b.dataset.assistantAvatar === id; b.classList.toggle('activo', on); b.setAttribute('aria-pressed', String(on)); });
    guardar('avatar', id);
  }
  $$('.assistant-avatar-option').forEach(b => b.onclick = () => ponerAvatar(b.dataset.assistantAvatar));
  const esMovil = () => matchMedia('(max-width: 850px)').matches;
  function mostrarAvatar(on) {
    const v = $('#vista-chat');
    if (esMovil()) v.classList.toggle('avatar-mobile-open', on);
    v.classList.toggle('avatar-panel-off', !on);
    $('#btnAvatarPanelToggle').setAttribute('aria-expanded', String(on));
    if (!esMovil()) guardar('avatarVisible', on ? '1' : '0');
  }
  $('#btnAvatarPanelToggle').onclick = () => { const v = $('#vista-chat'); mostrarAvatar(esMovil() ? !v.classList.contains('avatar-mobile-open') : v.classList.contains('avatar-panel-off')); };
  $('#btnAvatarClose').onclick = () => mostrarAvatar(false);
  function cargarVoces() {
    if (!('speechSynthesis' in window)) { $('#avatarVoice').innerHTML = '<option>Voz no disponible</option>'; return; }
    const voces = speechSynthesis.getVoices().filter(v => v.lang.toLowerCase().startsWith('es'));
    const p = pref('voz', '');
    $('#avatarVoice').innerHTML = voces.map(v => `<option value="${esc(v.name)}" ${v.name === p ? 'selected' : ''}>${esc(v.name)} · ${esc(v.lang)}</option>`).join('') || '<option value="">Voz por defecto</option>';
  }
  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = cargarVoces;
  cargarVoces();
  $('#avatarVoice').onchange = e => guardar('voz', e.target.value);
  $('#avatarRate').oninput = e => { $('#avatarRateValue').textContent = Number(e.target.value).toFixed(2).replace('.', ',') + '×'; guardar('vel', e.target.value); };
  $('#avatarAutoRead').onchange = e => guardar('leerAuto', e.target.checked ? '1' : '0');
  function estadoVoz(hablando, pausado) {
    panel.classList.toggle('hablando', hablando); panel.classList.toggle('pausado', !!pausado);
    $('#avatarEstado').textContent = pausado ? 'En pausa' : hablando ? 'Leyendo la respuesta…' : 'Lista para ayudarte';
    if (!hablando) $('#avatarSubtitulo').hidden = true;
  }
  function hablar(texto) {
    if (!('speechSynthesis' in window)) { toast('Este navegador no tiene voz sintetizada.'); return; }
    speechSynthesis.cancel();
    const plano = textoPlano(texto).slice(0, 3000);
    const u = new SpeechSynthesisUtterance(plano);
    const voz = speechSynthesis.getVoices().find(v => v.name === $('#avatarVoice').value);
    if (voz) u.voice = voz; u.lang = voz ? voz.lang : 'es-MX';
    u.rate = Number($('#avatarRate').value);
    u.onstart = () => estadoVoz(true);
    u.onboundary = e => { const s = $('#avatarSubtitulo'); s.hidden = false; s.textContent = plano.slice(Math.max(0, e.charIndex - 40), e.charIndex + 80); };
    u.onend = u.onerror = () => estadoVoz(false);
    speechSynthesis.speak(u);
  }
  $('#btnAvatarSpeak').onclick = () => { const m = S.actual && [...S.actual.mensajes].reverse().find(x => x.rol === 'asistente' && x.texto); if (m) hablar(m.texto); else toast('Aún no hay respuestas para leer.'); };
  $('#btnAvatarPause').onclick = () => { if (!('speechSynthesis' in window)) return; if (speechSynthesis.paused) { speechSynthesis.resume(); estadoVoz(true); } else if (speechSynthesis.speaking) { speechSynthesis.pause(); estadoVoz(true, true); } };
  $('#btnAvatarStop').onclick = () => { if ('speechSynthesis' in window) speechSynthesis.cancel(); estadoVoz(false); };

  // ------------------------------------------------------------------ panel derecho
  const tipoArchivo = n => { const e = n.split('.').pop().toLowerCase(); return ['csv', 'xlsx', 'xlsm', 'xls'].includes(e) ? ['t-tabla', e.toUpperCase()] : e === 'pdf' ? ['t-pdf', 'PDF'] : ['t-txt', e.toUpperCase().slice(0, 4)]; };
  function pintarRail() {
    const arch = (S.actual && S.actual.archivos) || [];
    $('#railDocCount').textContent = arch.length; $('#badgeDatos').textContent = arch.length; $('#railReadyCount').textContent = `${arch.length} / ${arch.length}`;
    $('#badgeInv').textContent = ((S.actual && S.actual.investigaciones) || []).length;
    $('#railStatus').textContent = arch.length ? 'Listos · sin analizar' : 'Sin archivos';
    const l = $('#railDocsList'); l.innerHTML = '';
    if (!arch.length) l.innerHTML = '<div class="rail-empty">Sube un archivo: se guarda sin analizarse hasta que preguntes.</div>';
    arch.forEach(a => {
      const d = document.createElement('div'); d.className = 'rail-doc';
      const det = a.tablas.length ? a.tablas.map(t => `${t.filas} filas × ${t.columnas} col.`).join(', ') : `${a.fragmentos_texto} fragmentos de texto`;
      d.innerHTML = `<span class="rail-doc-icon">${esc(tipoArchivo(a.nombre)[1])}</span><span class="rail-doc-text"><b title="${esc(a.nombre)}">${esc(a.nombre)}</b><small>${esc(det)}</small></span><span class="rail-doc-state" title="Listo"></span>`;
      d.style.cursor = 'pointer'; d.onclick = () => irA('datos');
      l.appendChild(d);
    });
    pintarMemoria(); pintarPais();
  }
  function pintarMemoria() {
    const c = $('#railMemoria'); const mem = (S.actual && S.actual.memoria) || [];
    c.innerHTML = mem.length ? '' : '<div class="rail-empty">Escribe «Recuerda que…» o pulsa ＋. Sólo vale para este chat.</div>';
    mem.forEach(x => {
      const d = document.createElement('div'); d.className = 'rail-item';
      d.innerHTML = `<div>${esc(x.hecho)}</div>`;
      const b = document.createElement('button'); b.className = 'rail-mini'; b.textContent = '✕'; b.title = 'Olvidar';
      b.onclick = async () => { await api(`/api/conversaciones/${S.actual.id}/memoria/${x.id}`, { method: 'DELETE' }); await recargar(); pintarMemoria(); };
      d.appendChild(b); c.appendChild(d);
    });
  }
  $('#btnRecordar').onclick = () => {
    if (!S.actual) return;
    const c = $('#railMemoria'); if (c.querySelector('form')) return;
    const f = document.createElement('form'); f.style.cssText = 'display:flex;gap:6px;margin-bottom:6px';
    f.innerHTML = '<input class="rail-input" placeholder="Ej.: la meta de rotación es 3%" aria-label="Dato a recordar"><button class="btn mini primario">OK</button>';
    f.onsubmit = async e => { e.preventDefault(); const v = f.querySelector('input').value.trim(); if (!v) return; await api(`/api/conversaciones/${S.actual.id}/memoria`, { method: 'POST', json: { hecho: v } }); await recargar(); pintarMemoria(); };
    c.prepend(f); f.querySelector('input').focus();
  };
  async function pintarPais() {
    if (!S.paises) { try { S.paises = await api('/api/paises'); } catch (e) { return; } }
    const act = (S.actual && S.actual.preferencias && S.actual.preferencias.pais_referencia) || '';
    $('#railPais').textContent = act ? S.paises.paises[act] : 'Sin definir';
    $('#selPaisRef').innerHTML = `<option value="">Elegir país de referencia (sugerido: ${esc(S.paises.paises[S.paises.referencia_sugerida])})</option>` +
      Object.entries(S.paises.paises).map(([k, v]) => `<option value="${k}" ${k === act ? 'selected' : ''}>${esc(v)}</option>`).join('');
  }
  $('#selPaisRef').onchange = async e => { if (!S.actual) await nueva(); await api(`/api/conversaciones/${S.actual.id}/preferencias`, { method: 'POST', json: { pais_referencia: e.target.value } }); await recargar(); pintarPais(); toast('País de referencia actualizado'); };
  $$('[data-prompt]').forEach(b => b.onclick = () => enviar(b.dataset.prompt));
  $$('[data-ir]').forEach(b => b.onclick = () => irA(b.dataset.ir));
  $$('[data-inv]').forEach(b => b.onclick = () => { S.invModo = b.dataset.inv; S.invResultado = null; irA('investigacion'); });
  $('#btnIrInvestigacion').onclick = () => irA('investigacion');

  const claseLectura = e => e === 'leída' || e === 'datos oficiales' ? 'ok' : e === 'no se pudo leer' ? 'error' : 'aviso';
  function pintarFuentes(m, enfocar) {
    const c = $('#railFuentes');
    if (!m) { c.innerHTML = '<div class="rail-empty">Aquí verás los cálculos y las fuentes de cada respuesta.</div>'; return; }
    const ev = m.evidencias || [], fu = m.fuentes || [], docs = (m.contexto || []).filter(x => x.tipo === 'documento');
    let html = '';
    if (ev.length) html += ev.slice(0, 30).map(e => `<div class="rail-item" id="ev-${esc(e.id)}"><div><b>${esc(fmtValor(e))}</b> · ${esc(e.descripcion)}<small>n=${e.n} · ${esc(e.metodo)}</small></div></div>`).join('');
    if (docs.length) html += docs.map(x => `<div class="rail-item"><div><b>${esc(x.fuente)}</b><small>${esc(x.texto.slice(0, 180))}…</small></div></div>`).join('');
    if (fu.length) html += fu.map(f => `<div class="rail-item" id="fu-${esc(f.id)}"><div><span class="ref w">${esc(f.id)}</span> <a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">${esc(f.titulo)}</a>
      <small><span class="insignia">${esc(f.tipo)}</span> <span class="insignia ${claseLectura(f.estado)}">${esc(f.estado)}</span> ${esc(f.dominio)}${f.fecha_publicacion ? ' · publ. ' + esc(f.fecha_publicacion) : ''}</small></div></div>`).join('');
    c.innerHTML = html || '<div class="rail-empty">Esta respuesta no usó cálculos ni fuentes: es conocimiento general.</div>';
    if (enfocar) c.closest('.rail-card').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  function mostrarCita(m, clave) {
    pintarFuentes(m, true);
    const id = clave.startsWith('E:') ? 'ev-' + clave.slice(2) : clave.startsWith('W:') ? 'fu-' + clave : null;
    const n = id && document.getElementById(id);
    if (n && n.offsetParent) { n.scrollIntoView({ block: 'center', behavior: 'smooth' }); n.style.background = 'var(--accent-bg)'; setTimeout(() => n.style.background = '', 1600); }
    else if (n) {
      const e = (m.evidencias || []).find(x => 'E:' + x.id === clave), f = (m.fuentes || []).find(x => x.id === clave);
      toast(e ? `${e.descripcion}: ${fmtValor(e)} (n=${e.n}; ${e.metodo})` : f ? `${f.titulo} — ${f.estado}` : clave);
    } else toast(clave.startsWith('C:') ? 'Fragmento del documento ' + clave.slice(2) : 'Esta cita no corresponde a ningún cálculo o fuente verificada.');
  }

  // ------------------------------------------------------------------ cabecera
  $('#tituloConv').onclick = () => {
    if (!S.actual) return;
    const h = $('#tituloConv'); const inp = document.createElement('input'); inp.className = 'titulo-input'; inp.value = S.actual.titulo;
    h.replaceWith(inp); inp.focus(); inp.select();
    let hecho = false;
    const fin = async ok => { if (hecho) return; hecho = true; inp.replaceWith(h);
      if (ok && inp.value.trim()) { await api(`/api/conversaciones/${S.actual.id}/titulo`, { method: 'POST', json: { titulo: inp.value } }); S.actual.titulo = inp.value.trim(); h.textContent = S.actual.titulo; cargarConversaciones(); } };
    inp.onkeydown = e => { if (e.key === 'Enter') fin(true); if (e.key === 'Escape') fin(false); };
    inp.onblur = () => fin(true);
  };
  $('#btnExportar').onclick = () => {
    if (!S.actual) return;
    const md = [`# ${S.actual.titulo}`, `Exportado de DINAMO Analytics · ${new Date().toLocaleString('es')}`, ''];
    S.actual.mensajes.forEach(m => {
      md.push(m.rol === 'usuario' ? `**Tú:** ${m.texto}` : `**DINAMO:**\n\n${m.texto}`);
      if ((m.fuentes || []).length) md.push('\nFuentes:\n' + m.fuentes.map(f => `- [${f.id}] ${f.titulo} — ${f.url} (${f.estado}; consultado ${f.fecha_consulta})`).join('\n'));
      if ((m.evidencias || []).length) md.push('\nCálculos:\n' + m.evidencias.map(e => `- [E:${e.id}] ${e.descripcion}: ${fmtValor(e)} (n=${e.n}; ${e.metodo})`).join('\n'));
      md.push('');
    });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([md.join('\n')], { type: 'text/markdown' }));
    a.download = (S.actual.titulo.replace(/[^\wáéíóúñ ]+/gi, '').slice(0, 50) || 'conversacion') + '.md';
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };
  $('#btnMenu').onclick = () => { $('#sidebar').classList.add('abierta'); $('#fondoMovil').classList.add('on'); };
  $('#fondoMovil').onclick = () => { $('#sidebar').classList.remove('abierta'); $('#fondoMovil').classList.remove('on'); };

  // ------------------------------------------------------------------ vistas
  function irA(v) {
    S.vista = v;
    $$('.nav-item').forEach(b => b.classList.toggle('activo', b.dataset.vista === v));
    $$('.vista').forEach(x => x.hidden = x.id !== 'vista-' + v);
    $('#sidebar').classList.remove('abierta'); $('#fondoMovil').classList.remove('on');
    if (v !== 'chat') pintarVista(v);
  }
  $$('.nav-item').forEach(b => b.onclick = () => irA(b.dataset.vista));
  function pintarVista(v) { ({ datos: vistaDatos, investigacion: vistaInvestigacion, historial: vistaHistorial, integraciones: vistaIntegraciones }[v] || (() => {}))(); }

  // ---- Datos y limpieza
  function vistaDatos() {
    const c = $('#datosCuerpo'); const arch = (S.actual && S.actual.archivos) || [];
    if (!arch.length) {
      c.innerHTML = `<div class="vacio"><h3>Todavía no hay archivos en este chat</h3><p>Se guardan sin analizarse. Puedes revisar su calidad y limpiarlos con tu aprobación.</p>
        <div class="zona-carga" id="zonaDatos" style="width:min(520px,100%)">${SVG.nube}<div class="grande">Arrastra archivos o haz clic</div><div class="formatos">Excel · CSV · PDF · TXT · Markdown</div></div></div>`;
      $('#zonaDatos').onclick = () => $('#inputArchivos').click(); return;
    }
    const total = arch.reduce((s, a) => s + a.tablas.reduce((x, t) => x + t.filas, 0), 0);
    c.innerHTML = `<div class="resumen-datos"><span><b>${arch.length}</b> archivos</span><span><b>${total.toLocaleString('es')}</b> filas</span><span>El original nunca se modifica: la limpieza crea un archivo nuevo.</span></div><div class="grid-archivos" id="gridArchivos"></div><div id="histLimpieza"></div>`;
    const g = $('#gridArchivos');
    arch.forEach(a => {
      const [cls, et] = tipoArchivo(a.nombre);
      const d = document.createElement('div'); d.className = 'archivo-card';
      d.innerHTML = `<div class="ac-top"><div class="tipo-icono ${cls}">${esc(et)}</div><div style="min-width:0"><div class="ac-nombre">${esc(a.nombre)}</div>
        <div class="ac-meta">${a.tablas.length ? a.tablas.map(t => `${t.filas} filas × ${t.columnas} columnas`).join(' · ') : a.fragmentos_texto + ' fragmentos de texto'}</div></div></div>
        <div><span class="ac-estado listo">● Listo · sin analizar</span></div><div class="ac-acciones"></div>`;
      const acc = d.querySelector('.ac-acciones');
      a.tablas.forEach(t => { const b = document.createElement('button'); b.className = 'btn mini'; b.textContent = 'Vista previa'; b.onclick = () => vistaPrevia(t.tabla); acc.appendChild(b); });
      if (cls === 't-tabla') { const b = document.createElement('button'); b.className = 'btn mini'; b.textContent = 'Revisar calidad'; b.onclick = () => proponerLimpieza(a.nombre); acc.appendChild(b); }
      const q = document.createElement('button'); q.className = 'btn mini peligro'; q.textContent = 'Quitar';
      q.onclick = async () => { await api(`/api/conversaciones/${S.actual.id}/archivos/${encodeURIComponent(a.nombre)}`, { method: 'DELETE' }); await recargar(); pintarRail(); vistaDatos(); };
      acc.appendChild(q); g.appendChild(d);
    });
    const hist = S.actual.limpieza || [];
    if (hist.length) $('#histLimpieza').innerHTML = '<div class="sigue-label" style="margin:6px 0">Registro de limpiezas</div>' + hist.map(r => `<div class="resultado"><h4>${esc(r.origen)} → ${esc(r.resultado)}</h4><div class="meta">${esc(new Date(r.fecha).toLocaleString('es'))}</div>
      <div class="etiqueta">${r.registro.map(x => esc(`${x.detalle} (${x.columna || 'tabla'}: ${x.filas_cambiadas} filas)`)).join('<br>')}</div>
      <div class="chips-accion"><a class="chip-accion" href="/api/conversaciones/${S.actual.id}/descargas/archivos/${encodeURIComponent(r.resultado)}">⤓ CSV limpio</a><a class="chip-accion" href="/api/conversaciones/${S.actual.id}/descargas/scripts/${encodeURIComponent(r.script)}">⤓ Script de Python</a></div></div>`).join('');
  }
  async function vistaPrevia(tabla) {
    const m = modal('Vista previa: ' + tabla, '<p class="etiqueta">Cargando…</p>');
    try {
      const v = await api(`/api/conversaciones/${S.actual.id}/tablas/${encodeURIComponent(tabla)}/vista?filas=30`);
      const cols = v.columnas.map(c => c.nombre);
      m.querySelector('.modal-cuerpo').innerHTML = `<div class="perfil-cols">${v.columnas.map(c => `<div class="perfil-col"><b>${esc(c.nombre)}</b><span class="tipo">${esc(c.rol)}</span> <span class="det">${esc(c.unidad)}</span></div>`).join('')}</div>
        <p class="etiqueta">Primeras ${v.filas.length} de ${v.total_filas} filas.</p>
        <div class="tabla-wrap"><table class="t"><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${v.filas.map(f => '<tr>' + cols.map(c => `<td class="${typeof f[c] === 'number' ? 'num' : ''}">${esc(f[c] ?? '')}</td>`).join('') + '</tr>').join('')}</tbody></table></div>`;
    } catch (e) { m.querySelector('.modal-cuerpo').innerHTML = `<div class="error-caja">${esc(e.message)}</div>`; }
  }
  async function proponerLimpieza(archivo) {
    const m = modal('Revisión de calidad: ' + archivo, '<p class="etiqueta">Revisando…</p>');
    const cuerpo = m.querySelector('.modal-cuerpo');
    let p;
    try { p = await api(`/api/conversaciones/${S.actual.id}/limpieza/proponer`, { method: 'POST', json: { archivo } }); }
    catch (e) { cuerpo.innerHTML = `<div class="error-caja">${esc(e.message)}</div>`; return; }
    if (!p.problemas.length) { cuerpo.innerHTML = '<p><span class="insignia ok">No se detectaron problemas de calidad.</span></p>'; return; }
    cuerpo.innerHTML = `<p class="etiqueta">${p.filas} filas × ${p.columnas} columnas. Marca lo que apruebas; lo demás no se toca. Los valores faltantes no se rellenan salvo que lo elijas.</p><div class="caja-borde" id="listaProb"></div>
      <div class="acciones-resp"><button class="btn primario" id="btnAplicar">Aplicar cambios aprobados</button><span class="etiqueta">Se crea un archivo nuevo; el original queda intacto.</span></div><div id="resLimpieza"></div>`;
    const caja = cuerpo.querySelector('#listaProb');
    p.problemas.forEach(x => {
      const ops = [x.accion, ...x.alternativas].filter(Boolean);
      const d = document.createElement('div'); d.className = 'problema'; d.dataset.id = x.id;
      d.innerHTML = `<input type="checkbox" ${x.accion ? 'checked' : ''} ${ops.length ? '' : 'disabled'} aria-label="Aprobar ${esc(x.id)}">
        <div class="cuerpo-p"><b>${esc(x.tipo)}</b>${x.columna ? ' · <code>' + esc(x.columna) + '</code>' : ''} <span class="insignia">${x.filas_afectadas} filas</span><br>${esc(x.descripcion)}
        ${x.ejemplos.length ? `<br><span class="etiqueta">Ejemplos: ${esc(JSON.stringify(x.ejemplos).slice(0, 160))}</span>` : ''}
        ${ops.length ? `<br><select class="seg-select" style="margin-top:6px">${ops.map(o => `<option value="${o}">${esc(o.replace(/_/g, ' '))}</option>`).join('')}</select>` : '<br><span class="etiqueta">Sólo informativo: no se propone cambio automático.</span>'}</div>`;
      caja.appendChild(d);
    });
    cuerpo.querySelector('#btnAplicar').onclick = async () => {
      const aprobadas = {};
      caja.querySelectorAll('.problema').forEach(d => { const c = d.querySelector('input'), s = d.querySelector('select'); if (c.checked && s) aprobadas[d.dataset.id] = s.value; });
      const res = cuerpo.querySelector('#resLimpieza');
      if (!Object.keys(aprobadas).length) { res.innerHTML = '<p class="etiqueta">No aprobaste ningún cambio.</p>'; return; }
      try {
        const r = await api(`/api/conversaciones/${S.actual.id}/limpieza/aplicar`, { method: 'POST', json: { archivo, aprobadas } });
        const a = r.comparacion.antes, b = r.comparacion.despues;
        res.innerHTML = `<div class="sigue-label">Antes / después</div><div class="tabla-wrap"><table class="t"><tr><th></th><th>Antes</th><th>Después</th></tr>
          <tr><td>Filas</td><td class="num">${a.filas}</td><td class="num">${b.filas}</td></tr><tr><td>Columnas</td><td class="num">${a.columnas}</td><td class="num">${b.columnas}</td></tr>
          <tr><td>Filas duplicadas</td><td class="num">${a.duplicados}</td><td class="num">${b.duplicados}</td></tr></table></div>
          <p>Nuevo archivo <b>${esc(r.resultado)}</b> agregado al chat.</p>
          <div class="chips-accion"><a class="chip-accion" href="/api/conversaciones/${S.actual.id}/descargas/archivos/${encodeURIComponent(r.resultado)}">⤓ CSV limpio</a><a class="chip-accion" href="/api/conversaciones/${S.actual.id}/descargas/scripts/${encodeURIComponent(r.script)}">⤓ Script de Python</a></div>
          <details class="fuentes"><summary>Registro de cambios</summary><ul>${r.registro.map(x => `<li>${esc(x.detalle)} — ${esc(x.columna || 'tabla')}: ${x.filas_cambiadas} filas</li>`).join('')}</ul></details>`;
        await recargar(); pintarRail(); vistaDatos();
      } catch (e) { res.innerHTML = `<div class="error-caja">${esc(e.message)}</div>`; }
    };
  }

  // ---- Investigación (sección única)
  const MODOS = [['web', 'Web general'], ['academico', 'Artículos científicos'], ['noticias', 'Noticias'], ['estadisticas', 'Estadísticas oficiales'], ['tecnica', 'Documentación técnica'], ['guardadas', 'Guardadas']];
  async function vistaInvestigacion() {
    const c = $('#invCuerpo');
    if (!S.paises) { try { S.paises = await api('/api/paises'); } catch (e) { /* */ } }
    c.innerHTML = `<div class="pestanas" role="tablist">${MODOS.map(([k, v]) => `<button role="tab" data-modo="${k}" aria-selected="${k === S.invModo}">${v}</button>`).join('')}</div><div id="invForm"></div><div id="invRes" style="display:flex;flex-direction:column;gap:12px"></div>`;
    c.querySelectorAll('.pestanas button').forEach(b => b.onclick = () => { S.invModo = b.dataset.modo; S.invResultado = null; vistaInvestigacion(); });
    const form = $('#invForm');
    if (!S.actual) { form.innerHTML = '<p class="etiqueta">Crea o abre una conversación para guardar tus investigaciones.</p>'; return; }
    if (S.invModo === 'guardadas') return pintarGuardadas();
    if (S.invModo === 'estadisticas' && S.paises) {
      const ref = (S.actual.preferencias || {}).pais_referencia;
      form.innerHTML = `<form class="formulario"><label>Indicador<select name="indicador">${Object.entries(S.paises.indicadores).map(([k, v]) => `<option value="${k}">${esc(v.nombre)}</option>`).join('')}</select></label>
        <label>Países (Ctrl/Cmd para varios)<select name="paises" multiple size="5">${Object.entries(S.paises.paises).map(([k, v]) => `<option value="${k}" ${k === (ref || S.paises.referencia_sugerida) ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></label>
        <button class="btn primario">Consultar Banco Mundial</button></form><p class="etiqueta">País de referencia del chat: ${ref ? esc(S.paises.paises[ref]) : 'sin definir (México es sólo una sugerencia)'}; cámbialo en el panel derecho.</p>`;
    } else {
      const ph = { web: 'Ej.: buenas prácticas para reducir la rotación en manufactura', academico: 'Ej.: voluntary employee turnover predictors (mejor en inglés)', noticias: 'Ej.: reforma laboral 40 horas México', tecnica: 'Ej.: pandas groupby named aggregation' }[S.invModo];
      form.innerHTML = `<form class="formulario"><label>Consulta<input type="search" name="consulta" placeholder="${esc(ph)}" required></label><button class="btn primario">Investigar</button></form>`;
    }
    form.querySelector('form').onsubmit = async e => {
      e.preventDefault();
      const f = e.target, btn = f.querySelector('button'), txt = btn.textContent;
      btn.disabled = true; btn.innerHTML = '<span class="dinamo-spinning"></span> Buscando y leyendo…';
      const cuerpo = { modo: S.invModo };
      if (S.invModo === 'estadisticas') { cuerpo.indicador = f.indicador.value; cuerpo.paises = [...f.paises.selectedOptions].map(o => o.value); cuerpo.consulta = ''; }
      else cuerpo.consulta = f.consulta.value;
      try { S.invResultado = await api(`/api/conversaciones/${S.actual.id}/investigacion`, { method: 'POST', json: cuerpo }); await recargar(); pintarRail(); pintarInvestigacion(S.invResultado); }
      catch (err) { $('#invRes').innerHTML = `<div class="error-caja">${esc(err.message)}</div>`; }
      btn.disabled = false; btn.textContent = txt;
    };
    if (S.invResultado) pintarInvestigacion(S.invResultado);
  }
  function pintarInvestigacion(inv) {
    const c = $('#invRes'); c.innerHTML = '';
    const cab = document.createElement('div'); cab.className = 'acciones-resp'; cab.style.alignItems = 'center';
    cab.innerHTML = `<span class="etiqueta">«${esc(inv.consulta || inv.pregunta)}» · ${esc(inv.fecha)} · vía ${esc((inv.proveedores || []).join(', ') || '—')}</span> ${Object.entries(inv.resumen_lectura || {}).map(([k, v]) => `<span class="insignia ${claseLectura(k)}">${v} ${esc(k)}</span>`).join(' ')}`;
    if (inv.fuentes.length) {
      const usar = document.createElement('button'); usar.className = 'btn mini primario'; usar.textContent = 'Analizar en la conversación';
      usar.onclick = () => enviar(`Analiza los hallazgos de esta investigación y dime qué implican para mí [investigacion:${inv.id}]`, `Analiza los hallazgos de la investigación «${inv.consulta || inv.pregunta}»`);
      const g = document.createElement('button'); g.className = 'btn mini'; g.textContent = inv.guardada ? '★ Guardada' : '☆ Guardar';
      g.onclick = async () => { const r = await api(`/api/conversaciones/${S.actual.id}/investigaciones/${inv.id}/guardar`, { method: 'POST', json: { guardada: !inv.guardada } }); inv.guardada = r.guardada; g.textContent = inv.guardada ? '★ Guardada' : '☆ Guardar'; await recargar(); };
      cab.append(usar, g);
    }
    c.appendChild(cab);
    (inv.avisos || []).forEach(a => c.insertAdjacentHTML('beforeend', `<div class="aviso-caja">${esc(a)}</div>`));
    if (inv.modo === 'estadisticas') {
      const filas = inv.fuentes.flatMap(f => (f.datos || []).map(d => ({ pais: f.titulo.split(' — ').pop(), anio: d.anio, valor: d.valor })));
      if (filas.length) { const g = document.createElement('div'); g.className = 'grafica-bloque'; c.appendChild(g); window.DinamoGraficos.dibujar(g, inv.fuentes[0].titulo.split(' — ')[0], filas, 'lineas'); }
    }
    inv.fuentes.forEach(f => {
      const t = document.createElement('article'); t.className = 'resultado';
      const extracto = (f.pasajes || []).length ? f.pasajes.slice(0, 2).map(p => `<blockquote>${esc(p.slice(0, 500))}</blockquote>`).join('') : f.fragmento ? `<blockquote>${esc(f.fragmento.slice(0, 500))}</blockquote>` : '';
      const ult = (f.datos || []).length ? f.datos[f.datos.length - 1] : null;
      t.innerHTML = `<div class="meta"><span class="ref w">${esc(f.id)}</span><span class="insignia">${esc(f.tipo)}</span><span class="insignia ${claseLectura(f.estado)}">${esc(f.estado)}</span><span>${esc(f.dominio)}</span>
          <span>${f.fecha_publicacion ? 'publicado ' + esc(f.fecha_publicacion) : 'fecha de publicación no disponible'}</span><span>consultado ${esc(f.fecha_consulta)}</span>${f.citas != null ? `<span>${f.citas} citas</span>` : ''}</div>
        <h4><a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">${esc(f.titulo)}</a></h4>
        ${(f.autores || []).length ? `<div class="etiqueta">${esc(f.autores.slice(0, 4).join(', '))}${f.medio ? ' · ' + esc(f.medio) : ''}</div>` : f.medio ? `<div class="etiqueta">${esc(f.medio)}</div>` : ''}
        ${extracto}${ult ? `<p class="etiqueta">Último dato: ${esc(ult.anio)} = ${esc(ult.valor.toLocaleString('es'))}</p>` : ''}<div class="etiqueta">${esc(f.justificacion)}${f.motivo ? ' · ' + esc(f.motivo) : ''}</div>`;
      c.appendChild(t);
    });
    if (!inv.fuentes.length && !(inv.avisos || []).length) c.insertAdjacentHTML('beforeend', '<p class="etiqueta">Sin resultados.</p>');
  }
  function pintarGuardadas() {
    const c = $('#invRes'); const todas = (S.actual.investigaciones || []).slice().reverse(); const g = todas.filter(i => i.guardada);
    c.innerHTML = `<p class="etiqueta">${g.length} guardadas · ${todas.length} investigaciones en este chat.</p><div class="lista-hist"></div>`;
    (g.length ? g : todas).forEach(i => {
      const d = document.createElement('div'); d.className = 'hist-item';
      d.innerHTML = `<div class="hist-cuerpo"><div class="hist-titulo">${i.guardada ? '★ ' : ''}${esc(i.consulta || i.pregunta)}</div><div class="hist-meta"><span>${esc(i.modo)}</span><span>${esc(i.fecha)}</span><span>${i.fuentes.length} fuentes</span></div></div>`;
      d.onclick = () => { S.invModo = i.modo; S.invResultado = i; vistaInvestigacion(); };
      c.querySelector('.lista-hist').appendChild(d);
    });
  }

  // ---- Historial
  async function vistaHistorial() {
    await cargarConversaciones();
    const c = $('#histCuerpo');
    if (!S.conversaciones.length) { c.innerHTML = '<div class="vacio"><h3>Sin conversaciones todavía</h3></div>'; return; }
    c.innerHTML = '<div class="lista-hist"></div>';
    const l = c.querySelector('.lista-hist');
    S.conversaciones.forEach(x => {
      const d = document.createElement('div'); d.className = 'hist-item' + (S.actual && S.actual.id === x.id ? ' actual' : '');
      d.innerHTML = `<div class="hist-cuerpo"><div class="hist-titulo">${esc(x.titulo)}</div><div class="hist-meta"><span>${x.mensajes} mensajes</span><span>${x.archivos} archivos</span><span>${esc(new Date(x.actualizada).toLocaleString('es'))}</span></div></div><div class="hist-acc"></div>`;
      d.onclick = e => { if (!e.target.closest('.hist-acc')) { abrir(x.id); irA('chat'); } };
      const del = document.createElement('button'); del.className = 'icon-btn'; del.title = 'Eliminar conversación'; del.innerHTML = SVG.borrar;
      del.onclick = () => {
        const acc = d.querySelector('.hist-acc');
        acc.innerHTML = '<span class="confirmar">¿Eliminar? <button class="btn mini peligro">Sí</button><button class="btn mini">No</button></span>';
        const [si, no] = acc.querySelectorAll('button');
        si.onclick = async () => { await api('/api/conversaciones/' + x.id, { method: 'DELETE' }); if (S.actual && S.actual.id === x.id) { S.actual = null; pintarTodo(); } vistaHistorial(); };
        no.onclick = vistaHistorial;
      };
      d.querySelector('.hist-acc').appendChild(del); l.appendChild(d);
    });
  }

  // ---- Integraciones
  async function vistaIntegraciones(comprobar) {
    const c = $('#intCuerpo');
    c.innerHTML = '<p class="etiqueta">«Disponible» sólo aparece tras una comprobación que respondió bien. Las claves se configuran en el archivo .env del servidor y nunca llegan al navegador.</p><div id="tablaInt"><p class="etiqueta">Cargando…</p></div>';
    try {
      const d = await api('/api/integraciones' + (comprobar ? '?comprobar=1' : ''));
      const cls = { 'disponible': 'ok', 'limitada': 'aviso', 'sin conexión': 'error', 'error': 'error' };
      $('#tablaInt').innerHTML = `<div class="tabla-wrap" style="max-height:none"><table class="t"><thead><tr><th>Servicio</th><th>Categoría</th><th>Estado</th><th class="wrap">Detalle</th><th>Envía datos fuera</th><th class="wrap">Costo / límite</th></tr></thead><tbody>
        ${d.integraciones.map(i => `<tr><td>${esc(i.nombre)}</td><td>${esc(i.categoria)}</td><td><span class="insignia ${cls[i.estado] || ''}">${esc(i.estado)}</span></td><td class="wrap">${esc(i.detalle)}</td><td>${i.envia_datos_fuera ? 'Sí' : 'No'}</td><td class="wrap">${esc(i.costo)}</td></tr>`).join('')}</tbody></table></div>`;
      if (comprobar) await cargarEstado(true);
    } catch (e) { $('#tablaInt').innerHTML = `<div class="error-caja">${esc(e.message)}</div>`; }
  }
  $('#btnComprobar').onclick = async () => { const b = $('#btnComprobar'); b.disabled = true; await vistaIntegraciones(true); b.disabled = false; };

  // Gancho para pruebas automáticas (simular la IA del navegador sin descargar un modelo).
  window.__dinamoPruebas = { ponerMotor: m => { S.motorWeb = m; pintarIA(); } };

  // ------------------------------------------------------------------ inicio
  (async () => {
    aplicarTema(); pintarPerfil();
    ponerAvatar(pref('avatar', 'sofia'));
    $('#avatarRate').value = pref('vel', '1'); $('#avatarRateValue').textContent = Number($('#avatarRate').value).toFixed(2).replace('.', ',') + '×';
    $('#avatarAutoRead').checked = pref('leerAuto', '0') === '1';
    if (pref('avatarVisible', '1') === '0' && !esMovil()) mostrarAvatar(false);
    pintarHilo();
    await cargarEstado();
    if (!S.estado) return;
    try {
      await cargarConversaciones();
      const ult = pref('actual', '');
      const ex = S.conversaciones.find(c => c.id === ult) || S.conversaciones[0];
      if (ex) await abrir(ex.id); else pintarTodo();
    } catch (e) { toast(e.message); }
    if (!S.estado.llm && pref('webllm', '0') === '1' && 'gpu' in navigator) activarWebLLM();
  })();
})();

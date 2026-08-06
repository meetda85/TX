/* =========================================================================
   Tiempo Extra · TWR MEX — interfaz
   ========================================================================= */

'use strict';

const estado = {
  anio: null,
  mes: null,
  cuadricula: null,
  config: null,
  vacantesPrevia: [],
  solicitudesPrevia: [],
};

const $  = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

const MESES = ['enero','febrero','marzo','abril','mayo','junio',
               'julio','agosto','septiembre','octubre','noviembre','diciembre'];

/* ---------------------------------------------------------------- API --- */

async function api(ruta, opciones = {}) {
  const resp = await fetch(ruta, {
    headers: { 'Content-Type': 'application/json' },
    ...opciones,
  });
  const datos = await resp.json().catch(() => ({ error: 'Respuesta ilegible del servidor' }));
  if (!resp.ok) throw new Error(datos.error || `Error ${resp.status}`);
  return datos;
}

const obtener = (ruta, params) =>
  api(ruta + (params ? '?' + new URLSearchParams(params) : ''));

const enviar = (ruta, cuerpo) =>
  api(ruta, { method: 'POST', body: JSON.stringify(cuerpo || {}) });

/* ------------------------------------------------------------- avisos --- */

function avisar(texto, tipo = 'ok', ms = 3800) {
  const el = document.createElement('div');
  el.className = `aviso ${tipo}`;
  el.textContent = texto;
  $('#avisos').append(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity .25s';
    setTimeout(() => el.remove(), 260);
  }, ms);
}

const fallar = (err) => avisar(err.message || String(err), 'error', 6000);

/* -------------------------------------------------------------- fecha --- */

const hoyISO = () => new Date().toISOString().slice(0, 10);

function fechaLarga(iso) {
  const [a, m, d] = iso.split('-').map(Number);
  return `${d} de ${MESES[m - 1]} de ${a}`;
}

/* ----------------------------------------------------- clasificación --- */

/** Familia visual de un código de turno (define el color de la celda). */
function familia(codigo) {
  if (!codigo) return 't-vacio';
  if (codigo === 'C' || codigo === 'a' || codigo === 'b') return 't-C';
  if (codigo === 'K' || codigo === 'x') return 't-K';
  if (codigo === 'O') return 't-O';
  if (codigo === 'f') return 't-f';
  if (codigo === '#' || codigo === '*#') return 't-descanso';
  if (codigo === '*') return 't-vaca';
  if (codigo === '+') return 't-recup';
  if (['A','M','Z','E','G'].includes(codigo)) return 't-otro';
  return 't-otro';
}

const esLaborable = (codigo) => !!(estado.config && estado.config.turnos[codigo]);

function descripcionCodigo(codigo) {
  if (!codigo) return 'Sin horario cargado';
  const cfg = estado.config;
  if (cfg && cfg.turnos[codigo]) return `${cfg.turnos[codigo].etiqueta} · ${cfg.turnos[codigo].descripcion}`;
  if (cfg && cfg.no_laborables[codigo]) return cfg.no_laborables[codigo];
  return `Código «${codigo}»`;
}

/* ==========================================================================
   CUADRÍCULA
   ========================================================================== */

async function cargarCuadricula() {
  try {
    estado.cuadricula = await obtener('/api/cuadricula', { anio: estado.anio, mes: estado.mes });
    pintarCuadricula();
  } catch (err) { fallar(err); }
}

function pintarCuadricula() {
  const datos = estado.cuadricula;
  if (!datos) return;

  $('#etiqueta-mes').textContent = `${MESES[estado.mes - 1]} ${estado.anio}`;

  const categoria = $('#filtro-categoria').value;
  const busqueda  = $('#filtro-texto').value.trim().toLowerCase();
  const soloTX    = $('#solo-tx').checked;
  const tope      = datos.max_dobles_consecutivas;

  let personas = datos.personas;
  if (categoria) personas = personas.filter(p => p.categoria === categoria);
  if (busqueda) {
    personas = personas.filter(p =>
      p.iniciales.toLowerCase().includes(busqueda) || p.nombre.toLowerCase().includes(busqueda));
  }
  if (soloTX) {
    personas = personas.filter(p => Object.values(p.celdas).some(c => c.tx.length));
  }

  const rejilla = $('#rejilla');
  rejilla.dataset.zoom = $('#zoom').value;
  rejilla.textContent = '';

  // --- Encabezado ---
  const cab = document.createElement('div');
  cab.className = 'fila-r fila-cab';
  cab.append(elem('div', 'celda-nombre', (n) => {
    n.innerHTML = '<div class="persona"><div class="datos"><div class="nom">Personal</div>'
                + `<div class="meta">${personas.length} de ${datos.personas.length}</div></div></div>`;
  }));
  for (const d of datos.dias) {
    cab.append(elem('div', `celda-cab${d.finde ? ' finde' : ''}${d.hoy ? ' hoy' : ''}`, (n) => {
      n.innerHTML = `<span class="num">${d.dia}</span>${d.dow}`;
    }));
  }
  cab.append(elem('div', 'celda-total', (n) => { n.textContent = 'TX mes'; }));
  rejilla.append(cab);

  // --- Filas por categoría ---
  const etiquetas = { SUPERVISOR: 'Supervisores', ATCO: 'ATCOs', AUX: 'Auxiliares' };
  let categoriaPrevia = null;

  for (const persona of personas) {
    if (persona.categoria !== categoriaPrevia) {
      categoriaPrevia = persona.categoria;
      const sec = document.createElement('div');
      sec.className = 'fila-r fila-seccion';
      sec.append(elem('div', 'celda-nombre', (n) => {
        n.textContent = etiquetas[persona.categoria] || persona.categoria;
      }));
      for (const _ of datos.dias) sec.append(elem('div', 'celda-dia'));
      sec.append(elem('div', 'celda-total'));
      rejilla.append(sec);
    }
    rejilla.append(filaPersona(persona, datos, tope));
  }

  if (!personas.length) {
    const vacio = document.createElement('div');
    vacio.className = 'vacio';
    vacio.textContent = datos.personas.length
      ? 'Ningún registro coincide con el filtro.'
      : 'Todavía no hay personal cargado. Ve a la pestaña Personal.';
    rejilla.append(vacio);
  }

  pintarLeyenda();
}

function elem(tipo, clase, fn) {
  const n = document.createElement(tipo);
  if (clase) n.className = clase;
  if (fn) fn(n);
  return n;
}

function filaPersona(persona, datos, tope) {
  const fila = document.createElement('div');
  fila.className = 'fila-r';

  fila.append(elem('div', 'celda-nombre', (n) => {
    n.innerHTML = `
      <div class="persona">
        <span class="siglas">${persona.iniciales}</span>
        <div class="datos">
          <div class="nom" title="${escapar(persona.nombre)}">${escapar(nombreCorto(persona.nombre))}</div>
          <div class="meta">${persona.no_empleado || ''}${persona.notas ? ' · ' + escapar(persona.notas) : ''}</div>
        </div>
      </div>`;
  }));

  for (const d of datos.dias) {
    fila.append(celdaDia(persona, d, tope));
  }

  const totalManual = persona.total_manual;
  fila.append(elem('div', 'celda-total', (n) => {
    const horas = totalManual ? totalManual.horas : persona.horas_sistema;
    n.innerHTML = `<div class="total-horas">${(horas || 0).toFixed(1)}</div>`
                + `<div class="total-nota">${totalManual ? 'capturado' : 'sistema'}</div>`;
  }));

  return fila;
}

function celdaDia(persona, dia, tope) {
  const celda = persona.celdas[dia.fecha] || { base: null, tx: [], doble: false, racha: 0 };
  const clases = ['celda-dia'];
  if (dia.finde) clases.push('finde');
  if (dia.hoy) clases.push('hoy');
  if (celda.doble) clases.push('doble');
  if (celda.doble && celda.racha === tope) clases.push('limite');
  if (celda.doble && celda.racha > tope) clases.push('excedida');
  if (celda.tx.length) {
    clases.push('con-tx');
    if (celda.tx.every(t => t.origen === 'HISTORICO')) clases.push('tx-historico');
    if (celda.tx.some(t => t.origen === 'ASIGNADO' && !t.acuse)) clases.push('sin-acuse');
  }

  const nodo = elem('div', clases.join(' '));
  nodo.dataset.persona = persona.id;
  nodo.dataset.fecha = dia.fecha;

  // Código principal y marca de tiempo extra
  const base = celda.base;
  const codigosTX = celda.tx.map(t => t.turno);
  let principal, marca = '';

  if (esLaborable(base)) {
    principal = base;
    if (codigosTX.length) marca = '+' + codigosTX.join('+');
  } else if (codigosTX.length) {
    principal = codigosTX[0];
    marca = codigosTX.length > 1 ? 'TX+' + codigosTX.slice(1).join('+') : 'TX';
  } else {
    principal = base || '·';
  }

  const clasesTurno = ['turno', familia(esLaborable(base) ? base : (codigosTX[0] || base))];
  nodo.append(elem('div', clasesTurno.join(' '), (n) => {
    n.innerHTML = escapar(principal) + (marca ? `<span class="tx-marca">${escapar(marca)}</span>` : '');
  }));

  if (celda.doble && celda.racha >= 2) {
    nodo.append(elem('span', 'contador-racha', (n) => { n.textContent = celda.racha; }));
  }

  nodo.title = tituloCelda(persona, dia, celda, tope);
  nodo.addEventListener('click', () => abrirModalCelda(persona.id, dia.fecha));
  return nodo;
}

function tituloCelda(persona, dia, celda, tope) {
  const lineas = [`${persona.iniciales} · ${fechaLarga(dia.fecha)}`, descripcionCodigo(celda.base)];
  for (const t of celda.tx) {
    const detalle = t.completo ? 'turno completo' : `${t.horas || '?'} h`;
    lineas.push(`TX ${t.turno} (${detalle}, ${t.ubicacion})${t.origen === 'HISTORICO' ? ' · histórico' : ''}`);
  }
  if (celda.doble) {
    lineas.push(`⚠ Jornada doble — ${celda.racha} seguida(s) de máximo ${tope}`);
    if (celda.racha > tope) lineas.push('🚫 Excede la regla de días consecutivos');
  }
  if (celda.horas) lineas.push(`${celda.horas} horas en el día`);
  return lineas.join('\n');
}

function nombreCorto(nombre) {
  const partes = nombre.split(/\s+/);
  return partes.length <= 2 ? nombre : partes.slice(0, 2).join(' ');
}

const escapar = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function pintarLeyenda() {
  const cfg = estado.config;
  if (!cfg) return;
  const partes = [];
  for (const c of ['C', 'K', 'O', 'f']) {
    const t = cfg.turnos[c];
    partes.push(`<span class="item"><span class="muestra ${familia(c)}">${c}</span>${t.inicio}-${t.fin}</span>`);
  }
  partes.push('<span class="separador"></span>');
  partes.push('<span class="item"><span class="muestra t-descanso">#</span>Descanso</span>');
  partes.push('<span class="item"><span class="muestra t-vaca">*</span>Vacaciones</span>');
  partes.push('<span class="item"><span class="muestra t-recup">+</span>Recuperación</span>');
  partes.push('<span class="separador"></span>');
  partes.push('<span class="item"><span class="muestra t-K" style="box-shadow:inset 0 -3px 0 var(--tx)">K</span>Con tiempo extra</span>');
  partes.push('<span class="item"><span class="muestra t-C" style="border:2.5px solid var(--aviso)">C</span>Jornada doble</span>');
  partes.push('<span class="item"><span class="muestra t-C" style="border:2.5px solid var(--alto)">C</span>Al límite / excede</span>');
  $('#leyenda').innerHTML = partes.join('');
}

/* ==========================================================================
   MODAL DE CELDA
   ========================================================================== */

function abrirModal(html) {
  $('#contenido-modal').innerHTML = html;
  $('#fondo-modal').hidden = false;
}
function cerrarModal() { $('#fondo-modal').hidden = true; }

async function abrirModalCelda(personaId, fecha) {
  const datos = estado.cuadricula;
  const persona = datos.personas.find(p => p.id === personaId);
  if (!persona) return;
  const celda = persona.celdas[fecha] || { base: null, tx: [], doble: false, racha: 0 };
  const cfg = estado.config;

  const opcionesBase = ['', ...Object.keys(cfg.turnos), ...Object.keys(cfg.no_laborables)]
    .map(c => `<option value="${escapar(c)}"${c === (celda.base || '') ? ' selected' : ''}>`
            + `${c ? escapar(c) + ' — ' + escapar(descripcionCodigo(c)) : '(sin horario)'}</option>`)
    .join('');

  const listaTX = celda.tx.length
    ? '<ul class="lista-tx">' + celda.tx.map(t => `
        <li>
          <span class="etiqueta t-${t.turno}">${t.turno}</span>
          <span class="crece">
            ${t.completo ? 'Turno completo' : `${t.horas || '?'} horas`} · ${t.ubicacion}
            ${t.origen === 'HISTORICO' ? ' · <i>histórico</i>' : ''}
            ${t.origen === 'ASIGNADO' && !t.acuse ? ' · <b style="color:var(--tx)">sin acuse</b>' : ''}
          </span>
          ${t.origen === 'ASIGNADO' && !t.acuse
            ? `<button class="btn chico" data-acuse="${t.id}">Acusar</button>` : ''}
          <button class="btn chico peligro" data-borrar="${t.id}">Quitar</button>
        </li>`).join('') + '</ul>'
    : '<p class="nota">Sin tiempo extra registrado este día.</p>';

  abrirModal(`
    <h3>${escapar(persona.iniciales)} · ${escapar(persona.nombre)}</h3>
    <p class="sub-modal">${fechaLarga(fecha)}${celda.doble ? ' · <b style="color:var(--aviso)">jornada doble</b>' : ''}</p>

    <label class="linea" style="margin-bottom:14px">Turno base del horario
      <select id="modal-base" style="flex:1">${opcionesBase}</select>
    </label>

    <h3 style="font-size:14px;margin-top:16px">Tiempo extra del día</h3>
    ${listaTX}

    <h3 style="font-size:14px;margin-top:18px">Anotar tiempo extra</h3>
    <div class="rejilla-turnos" id="modal-turnos">
      ${['C','K','O'].map(c => `
        <div class="opcion-turno ${familia(c)}" data-turno="${c}">
          ${c}<span class="h">${cfg.turnos[c].inicio}-${cfg.turnos[c].fin}</span>
        </div>`).join('')}
    </div>

    <div class="fila-controles">
      <label>Ubicación
        <select id="modal-ubicacion"><option value="TWR1">TWR 1</option><option value="T2">T2</option></select>
      </label>
      <label>Alcance
        <select id="modal-alcance">
          <option value="completo">Turno completo</option>
          <option value="parcial">Sólo unas horas</option>
        </select>
      </label>
      <label id="modal-horas-campo" hidden>Horas
        <input type="number" id="modal-horas" min="0.5" max="10" step="0.5" value="1" style="width:80px">
      </label>
      <label>Registro
        <select id="modal-origen">
          <option value="ASIGNADO">Asignación nueva</option>
          <option value="HISTORICO">Histórico (ya lo trabajó)</option>
        </select>
      </label>
    </div>

    <div id="modal-eval"></div>

    <div class="acciones-modal">
      <button class="btn" id="modal-cancelar">Cerrar</button>
      <button class="btn primario" id="modal-guardar" disabled>Anotar tiempo extra</button>
    </div>
  `);

  let turnoElegido = null;
  const eval_ = $('#modal-eval');
  const btnGuardar = $('#modal-guardar');

  $('#modal-base').addEventListener('change', async (e) => {
    try {
      await enviar('/api/horario', { persona_id: personaId, fecha, codigo: e.target.value });
      avisar('Turno base actualizado');
      await cargarCuadricula();
      if (turnoElegido) revisar();
    } catch (err) { fallar(err); }
  });

  $$('#modal-turnos .opcion-turno').forEach(op => {
    op.addEventListener('click', () => {
      $$('#modal-turnos .opcion-turno').forEach(o => o.classList.remove('sel'));
      op.classList.add('sel');
      turnoElegido = op.dataset.turno;
      revisar();
    });
  });

  $('#modal-alcance').addEventListener('change', (e) => {
    $('#modal-horas-campo').hidden = e.target.value !== 'parcial';
    if (turnoElegido) revisar();
  });

  async function revisar() {
    if (!turnoElegido) return;
    const completo = $('#modal-alcance').value === 'completo';
    try {
      const ev = await obtener('/api/evaluar', {
        persona_id: personaId, fecha, turno: turnoElegido, completo: completo ? 1 : 0,
      });
      eval_.innerHTML = bloqueEvaluacion(ev);
      btnGuardar.disabled = false;
      btnGuardar.textContent = ev.permitido ? 'Anotar tiempo extra' : 'Anotar de todos modos';
      btnGuardar.className = ev.permitido ? 'btn primario' : 'btn peligro';
    } catch (err) { fallar(err); }
  }

  btnGuardar.addEventListener('click', async () => {
    if (!turnoElegido) return;
    const completo = $('#modal-alcance').value === 'completo';
    try {
      const r = await enviar('/api/asignaciones', {
        persona_id: personaId, fecha, turno: turnoElegido,
        ubicacion: $('#modal-ubicacion').value,
        completo,
        horas: completo ? null : parseFloat($('#modal-horas').value),
        origen: $('#modal-origen').value,
        forzar: true,
      });
      avisar(r.forzado
        ? `Anotado ${turnoElegido} pese a la restricción — queda marcado en rojo`
        : `Tiempo extra ${turnoElegido} anotado`, r.forzado ? 'warn' : 'ok');
      cerrarModal();
      await cargarCuadricula();
    } catch (err) { fallar(err); }
  });

  $('#modal-cancelar').addEventListener('click', cerrarModal);

  $$('[data-borrar]').forEach(b => b.addEventListener('click', async () => {
    try {
      await enviar('/api/asignaciones/borrar', { id: Number(b.dataset.borrar) });
      avisar('Tiempo extra eliminado');
      cerrarModal();
      await cargarCuadricula();
    } catch (err) { fallar(err); }
  }));

  $$('[data-acuse]').forEach(b => b.addEventListener('click', async () => {
    try {
      await enviar('/api/asignaciones/acuse', { id: Number(b.dataset.acuse), acuse: true });
      avisar('Acuse registrado');
      cerrarModal();
      await cargarCuadricula();
    } catch (err) { fallar(err); }
  }));
}

function bloqueEvaluacion(ev) {
  const titulos = {
    OK: '✓ Se puede asignar',
    ADVERTENCIA: '⚠ Se puede, pero con cuidado',
    PROHIBIDO: '🚫 Prohibido por reglamento',
  };
  const motivos = ev.motivos.length
    ? '<ul>' + ev.motivos.map(m => `<li>${escapar(m.texto)}</li>`).join('') + '</ul>'
    : '';
  return `<div class="bloque-eval nivel-${ev.nivel}"><b>${titulos[ev.nivel]}</b>${motivos}</div>`;
}

/* ==========================================================================
   ASIGNAR
   ========================================================================== */

/** Extrae siglas de un texto suelto o de un mensaje pegado del grupo. */
function siglasDe(texto) {
  const limpio = texto.replace(/\b\d+\s*[CKOcko]\b/g, ' ')     // "13 K" no son siglas
                      .replace(/\b[CKOcko]\b/g, ' ');
  const halladas = limpio.toUpperCase().match(/\b[A-ZÁÉÍÓÚÑ]{2,3}\b/g) || [];
  const ruido = new Set(['TX','LOS','LAS','QUE','POR','DEL','CON','SUS','ACK','PLS','EN','Y','O']);
  return [...new Set(halladas.filter(s => !ruido.has(s)))].join(' ');
}

async function buscarCandidatos() {
  const fecha = $('#asig-fecha').value;
  if (!fecha) { avisar('Elige una fecha', 'warn'); return; }
  const params = {
    fecha,
    turno: $('#asig-turno').value,
    ubicacion: $('#asig-ubicacion').value,
  };
  const cat = $('#asig-categoria').value;
  if (cat) params.categoria = cat;

  const crudo = $('#asig-siglas').value.trim();
  if (crudo) params.siglas = siglasDe(crudo);

  try {
    const datos = await obtener('/api/candidatos', params);
    let resumen = `${fechaLarga(datos.fecha)} · turno ${datos.turno} (${datos.turno_desc})`;
    if (datos.siglas_desconocidas.length) {
      resumen += ` · sin registrar: ${datos.siglas_desconocidas.join(', ')}`;
    }
    $('#asig-resumen').textContent = resumen;
    pintarCandidatos(datos);
  } catch (err) { fallar(err); }
}

function pintarCandidatos(datos) {
  const cont = $('#lista-candidatos');
  if (!datos.candidatos.length) {
    cont.innerHTML = '<p class="vacio">No hay personal que coincida.</p>';
    return;
  }
  cont.innerHTML = datos.candidatos.map(c => `
    <div class="candidato nivel-${c.nivel}">
      <span class="siglas">${escapar(c.iniciales)}</span>
      <div class="quien">
        <div class="n">${escapar(nombreCorto(c.nombre))}</div>
        <div class="r">${escapar(c.base ? `Base: ${c.base} — ` : '')}${escapar(c.resumen)}</div>
      </div>
      <label class="acum-editable" title="Horas de tiempo extra ya trabajadas">
        <span>Horas</span>
        <input type="number" step="0.5" min="0" data-total="${c.id}"
               value="${c.acumulado_horas ?? ''}" placeholder="—"
               class="${c.acumulado_es_manual ? 'capturado' : ''}">
      </label>
      <button class="btn ${c.nivel === 'PROHIBIDO' ? 'peligro' : 'primario'} chico"
              data-asignar="${c.id}" data-nivel="${c.nivel}">
        ${c.nivel === 'PROHIBIDO' ? 'Forzar' : 'Asignar'}
      </button>
    </div>`).join('');

  // Captura del acumulado en línea: guarda al salir del campo o con Enter,
  // y reordena la lista para que quien menos lleva quede arriba.
  $$('[data-total]', cont).forEach(campo => {
    const guardar = async () => {
      if (campo.dataset.guardando) return;
      campo.dataset.guardando = '1';
      try {
        await enviar('/api/totales/uno', {
          persona_id: Number(campo.dataset.total),
          periodo: datos.periodo,
          horas: campo.value,
        });
        await buscarCandidatos();
        await cargarCuadricula();
      } catch (err) { fallar(err); }
      finally { delete campo.dataset.guardando; }
    };
    campo.addEventListener('change', guardar);
    campo.addEventListener('keydown', (e) => { if (e.key === 'Enter') campo.blur(); });
  });

  $$('[data-asignar]', cont).forEach(b => b.addEventListener('click', async () => {
    const prohibido = b.dataset.nivel === 'PROHIBIDO';
    if (prohibido && !confirm(
      'Esta asignación rompe la regla de días consecutivos.\n\n¿Registrarla de todos modos?')) return;
    try {
      const r = await enviar('/api/asignaciones', {
        persona_id: Number(b.dataset.asignar),
        fecha: datos.fecha, turno: datos.turno, ubicacion: datos.ubicacion,
        forzar: prohibido,
      });
      if (r.bloqueado) { avisar(r.evaluacion.resumen, 'error', 6000); return; }
      avisar(r.forzado ? 'Asignado forzando la regla' : 'Asignado', r.forzado ? 'warn' : 'ok');
      await buscarCandidatos();
      await cargarCuadricula();
    } catch (err) { fallar(err); }
  }));
}

/* ==========================================================================
   PUBLICAR — captura de lugares y mensajes por grupo
   ========================================================================== */

const GRUPOS_ORDEN = ['SUPERVISOR', 'ATCO', 'AUX'];
const GRUPOS_TITULO = { SUPERVISOR: 'Supervisores', ATCO: 'ATCO (TWR)', AUX: 'Auxiliares' };

async function cargarMatriz() {
  const desde = $('#pub-desde').value || hoyISO();
  $('#pub-desde').value = desde;
  try {
    const datos = await obtener('/api/vacantes/matriz', { desde, dias: $('#pub-dias').value });
    pintarMatriz(datos);
    await cargarMensajesGrupo();
  } catch (err) { fallar(err); }
}

function pintarMatriz(datos) {
  const turnos = datos.turnos;
  const cabGrupos = GRUPOS_ORDEN.map(g =>
    `<th class="grupo-cab g-${g}" colspan="${turnos.length}">${GRUPOS_TITULO[g]}</th>`).join('');
  const cabTurnos = GRUPOS_ORDEN.map(g =>
    turnos.map((t, i) => `<th class="${i === turnos.length - 1 ? 'sep' : ''}">${t}</th>`).join('')).join('');

  const filas = datos.dias.map(d => {
    const celdas = GRUPOS_ORDEN.map(g => turnos.map((t, i) => {
      const valor = datos.cupos[`${d.fecha}|${g}|${t}`] || '';
      const etiqueta = `${GRUPOS_TITULO[g]} en turno ${t} el ${d.dia}`;
      return `<td class="${i === turnos.length - 1 ? 'sep' : ''}">
        <div class="paso">
          <button type="button" class="paso-btn" data-delta="-1" tabindex="-1"
                  aria-label="Un lugar menos de ${etiqueta}">−</button>
          <input type="number" class="cupo ${valor ? 'puesto' : ''}" min="0" max="20" placeholder="·"
                 value="${valor}" data-fecha="${d.fecha}" data-grupo="${g}" data-turno="${t}"
                 aria-label="Lugares de ${etiqueta}">
          <button type="button" class="paso-btn" data-delta="1" tabindex="-1"
                  aria-label="Un lugar más de ${etiqueta}">+</button>
        </div>
      </td>`;
    }).join('')).join('');

    const total = GRUPOS_ORDEN.reduce((suma, g) =>
      suma + turnos.reduce((s, t) => s + (datos.cupos[`${d.fecha}|${g}|${t}`] || 0), 0), 0);

    return `<tr class="${d.finde ? 'finde' : ''} ${d.hoy ? 'hoy' : ''}">
      <td class="dia-cel"><b>${d.dia}</b><small>${d.dow_largo.slice(0, 3)}</small></td>
      ${celdas}
      <td class="total-fila">${total || ''}</td>
    </tr>`;
  }).join('');

  const totalPorColumna = GRUPOS_ORDEN.map(g => turnos.map((t, i) => {
    const suma = datos.dias.reduce((s, d) => s + (datos.cupos[`${d.fecha}|${g}|${t}`] || 0), 0);
    return `<td class="${i === turnos.length - 1 ? 'sep' : ''}">${suma || ''}</td>`;
  }).join('')).join('');

  $('#pub-matriz').innerHTML = `<div class="matriz-envoltura"><table class="matriz">
    <thead>
      <tr><th class="dia-cab" rowspan="2">Día</th>${cabGrupos}<th rowspan="2">Total</th></tr>
      <tr>${cabTurnos}</tr>
    </thead>
    <tbody>${filas}
      <tr class="totales"><td class="dia-cel">Total</td>${totalPorColumna}
        <td class="total-fila">${datos.total_lugares || ''}</td></tr>
    </tbody>
  </table></div>`;

  $('#pub-conteo').textContent = datos.total_lugares
    ? `${datos.total_lugares} lugar(es) en el rango`
    : 'Todavía no hay lugares capturados';

  $$('#pub-matriz input.cupo').forEach(campo => {
    campo.addEventListener('change', () => fijarCupo(campo, campo.value));
    campo.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { campo.blur(); return; }
      // Como en una hoja de cálculo: las flechas mueven de casilla, y para
      // subir o bajar el número están los botones − y +.
      const paso = { ArrowUp: -1, ArrowDown: 1 }[e.key];
      if (!paso) return;
      e.preventDefault();
      const todos = $$('#pub-matriz input.cupo');
      const cols = GRUPOS_ORDEN.length * 3;
      const destino = todos[todos.indexOf(campo) + paso * cols];
      if (destino) { destino.focus(); destino.select(); }
    });
  });

  $$('#pub-matriz .paso-btn').forEach(boton => {
    boton.addEventListener('click', () => {
      const campo = $('input.cupo', boton.parentElement);
      const actual = Number(campo.value) || 0;
      fijarCupo(campo, actual + Number(boton.dataset.delta));
    });
  });
}

/** Fija los lugares de una casilla sin repintar la tabla entera.
 *
 *  Repintar en cada clic hacía perder el foco y el «+» se escapaba del cursor,
 *  así que la casilla y los totales se actualizan en el momento y el guardado
 *  viaja aparte.
 */
function fijarCupo(campo, valorCrudo) {
  const n = Math.max(0, Math.min(20, Number(valorCrudo) || 0));
  campo.value = n || '';
  campo.classList.toggle('puesto', n > 0);
  recalcularTotales();

  clearTimeout(fijarCupo._temporizador);
  fijarCupo._temporizador = setTimeout(async () => {
    try {
      await enviar('/api/vacantes/cupos', {
        cupos: [{
          fecha: campo.dataset.fecha,
          categoria: campo.dataset.grupo,
          turno: campo.dataset.turno,
          cupos: n,
        }],
      });
      await cargarMensajesGrupo();
    } catch (err) { fallar(err); await cargarMatriz(); }
  }, 180);
}

/** Recalcula los totales de la tabla leyendo lo que hay en pantalla. */
function recalcularTotales() {
  const filas = $$('#pub-matriz tbody tr:not(.totales)');
  const columnas = [];
  let general = 0;

  filas.forEach(fila => {
    let suma = 0;
    $$('input.cupo', fila).forEach((campo, indice) => {
      const n = Number(campo.value) || 0;
      suma += n;
      columnas[indice] = (columnas[indice] || 0) + n;
    });
    const celda = $('.total-fila', fila);
    if (celda) celda.textContent = suma || '';
    general += suma;
  });

  const pie = $('#pub-matriz tr.totales');
  if (pie) {
    $$('td', pie).slice(1, -1).forEach((celda, indice) => {
      celda.textContent = columnas[indice] || '';
    });
    const ultima = $('.total-fila', pie);
    if (ultima) ultima.textContent = general || '';
  }

  $('#pub-conteo').textContent = general
    ? `${general} lugar(es) en el rango`
    : 'Todavía no hay lugares capturados';
}

//: Qué hace cada ronda, en una línea, para mostrarlo en pantalla.
const EXPLICA_RONDA = {
  1: 'Ronda 1 · cada grupo ve sólo lo de su categoría.',
  2: 'Ronda 2 · lo que sobró de auxiliares sube también al grupo de torre.',
  3: 'Ronda 3 · lo sobrante sube todo lo que puede: lo de auxiliares llega hasta '
   + 'supervisores y lo de torre hasta supervisores. Lo de supervisor nunca baja.',
};

function pintarSelectorRonda() {
  const ronda = estado.ronda || 1;
  $$('.ronda-btn').forEach(b => b.classList.toggle('activa', Number(b.dataset.ronda) === ronda));
  const nota = $('#pub-explica-ronda');
  if (nota) nota.textContent = EXPLICA_RONDA[ronda];
}

async function cambiarRonda(ronda) {
  try {
    await enviar('/api/ajustes', { ronda });
    estado.ronda = ronda;
    pintarSelectorRonda();
    avisar(EXPLICA_RONDA[ronda], 'ok', 6000);
    await cargarMensajesGrupo();
    if ($('#vista-sugerencia').classList.contains('activa')) await cargarSugerencias();
    if ($('#vista-cierre').classList.contains('activa')) await cargarCierre();
  } catch (err) { fallar(err); }
}

async function cargarMensajesGrupo() {
  const { desde, hasta } = ventanaTrabajo();
  try {
    const datos = await obtener('/api/publicaciones', {
      desde, hasta, dia_semana: $('#pub-dia-semana').checked ? 1 : 0,
    });
    estado.ronda = datos.ronda;
    pintarSelectorRonda();

    const cont = $('#pub-mensajes');
    if (!datos.mensajes.length) {
      cont.innerHTML = '<p class="vacio">'
        + (datos.total_lugares === 0 && estado.ronda > 1
            ? 'Ya no queda nada por cubrir en este rango.'
            : 'Captura lugares arriba y aquí aparecen los mensajes.')
        + '</p>';
      return;
    }
    cont.innerHTML = datos.mensajes.map(m => `
      <div class="mensaje-caja g-${m.categoria}">
        <header>
          <b>${escapar(m.grupo)}</b>
          ${m.de_otra ? `<span class="escalado">${m.de_otra} de otra categoría</span>` : ''}
          <span class="cuantos">${m.lugares} lugar(es)</span>
        </header>
        <pre id="msj-${m.categoria}">${escapar(m.mensaje)}</pre>
        <footer><button class="btn chico" data-copiar="${m.categoria}">Copiar mensaje</button></footer>
      </div>`).join('');

    $$('[data-copiar]', cont).forEach(b => b.addEventListener('click', async () => {
      const texto = $(`#msj-${b.dataset.copiar}`).textContent;
      try {
        await navigator.clipboard.writeText(texto);
        avisar(`Mensaje de ${GRUPOS_TITULO[b.dataset.copiar]} copiado`);
      } catch {
        const rango = document.createRange();
        rango.selectNodeContents($(`#msj-${b.dataset.copiar}`));
        getSelection().removeAllRanges();
        getSelection().addRange(rango);
        avisar('Selecciónalo y copia con Ctrl+C', 'warn');
      }
    }));
  } catch (err) { fallar(err); }
}

/* ==========================================================================
   2 · SOLICITUDES — captura manual, persona por persona
   ========================================================================== */

/** Rango de trabajo: el mismo que se está publicando. */
function ventanaTrabajo() {
  const desde = $('#pub-desde').value || hoyISO();
  const dias = Number($('#pub-dias').value || 14);
  const hasta = new Date(new Date(desde + 'T12:00:00').getTime() + (dias - 1) * 864e5)
    .toISOString().slice(0, 10);
  return { desde, hasta };
}

async function cargarSiglasConocidas() {
  try {
    const datos = await obtener('/api/personas');
    $('#lista-siglas').innerHTML = datos.personas
      .map(p => `<option value="${escapar(p.iniciales)}">${escapar(p.nombre)}</option>`).join('');
    estado.personas = datos.personas;
  } catch (err) { fallar(err); }
}

function mostrarQuienEs() {
  const siglas = $('#sol-siglas').value.trim().toUpperCase();
  const quien = (estado.personas || []).find(p => p.iniciales.toUpperCase() === siglas);
  const nodo = $('#sol-quien');
  if (!siglas) { nodo.textContent = ''; return; }
  if (quien) {
    nodo.innerHTML = `<b>${escapar(quien.nombre)}</b> · ${quien.categoria}`;
    nodo.style.color = '';
  } else {
    nodo.textContent = `No hay nadie con las siglas ${siglas}. Dalo de alta en Personal.`;
    nodo.style.color = 'var(--alto)';
  }
}

async function agregarSolicitud() {
  const siglas = $('#sol-siglas').value.trim().toUpperCase();
  const texto = $('#sol-texto').value.trim();
  if (!siglas) { avisar('Escribe las siglas', 'warn'); $('#sol-siglas').focus(); return; }
  if (!texto) { avisar('Escribe qué días pidió', 'warn'); $('#sol-texto').focus(); return; }

  try {
    const r = await enviar('/api/peticiones/agregar', {
      iniciales: siglas, texto, referencia: ventanaTrabajo().desde,
    });
    const resumen = r.agregadas
      .map(a => `${Number(a.fecha.slice(8))}${a.turno}`).join(', ');
    avisar(`${r.iniciales}: ${resumen}`);
    $('#sol-siglas').value = '';
    $('#sol-texto').value = '';
    $('#sol-quien').textContent = '';
    $('#sol-siglas').focus();
    await cargarSolicitudes();
  } catch (err) { fallar(err); }
}

async function cargarSolicitudes() {
  const { desde, hasta } = ventanaTrabajo();
  try {
    const datos = await obtener('/api/peticiones', { desde, hasta });
    $('#sol-conteo').textContent = datos.total_personas
      ? `${datos.total_personas} persona(s), ${datos.total_peticiones} solicitud(es)`
      : 'Todavía no hay solicitudes capturadas.';

    const cont = $('#sol-lista');
    if (!datos.personas.length) {
      cont.innerHTML = '<p class="vacio">Captura la primera a la izquierda.</p>';
      return;
    }

    const titulos = { SUPERVISOR: 'Supervisores', ATCO: 'ATCO (TWR)', AUX: 'Auxiliares' };
    const porCategoria = {};
    for (const p of datos.personas) (porCategoria[p.categoria] ||= []).push(p);

    cont.innerHTML = GRUPOS_ORDEN.filter(g => porCategoria[g]).map(g => `
      <div class="grupo-solicitudes">
        <h3>${titulos[g]} · ${porCategoria[g].length}</h3>
        ${porCategoria[g].map(p => `
          <div class="persona-solicitud">
            <span class="siglas">${escapar(p.iniciales)}</span>
            <div class="fichas">
              ${p.peticiones.map(q => `
                <span class="ficha t-${q.turno}">
                  ${Number(q.fecha.slice(8))} ${q.turno}
                  <button data-quitar-pet="${q.id}" title="Quitar" aria-label="Quitar">×</button>
                </span>`).join('')}
            </div>
          </div>`).join('')}
      </div>`).join('');

    $$('[data-quitar-pet]', cont).forEach(b => b.addEventListener('click', async () => {
      try {
        await enviar('/api/peticiones/borrar', { id: Number(b.dataset.quitarPet) });
        await cargarSolicitudes();
      } catch (err) { fallar(err); }
    }));
  } catch (err) { fallar(err); }
}

/* ==========================================================================
   3 · HORAS TRABAJADAS
   ========================================================================== */

async function cargarHoras() {
  const { desde, hasta } = ventanaTrabajo();
  const periodo = $('#horas-periodo').value || desde.slice(0, 7);
  $('#horas-periodo').value = periodo;

  try {
    const datos = await obtener('/api/resumen', { desde, hasta, periodo });
    const cont = $('#horas-tabla');
    if (!datos.personas.length) {
      cont.innerHTML = '<p class="vacio">Nadie ha pedido nada todavía. Vuelve al paso 2.</p>';
      $('#horas-aviso').textContent = '';
      return;
    }

    const titulos = { SUPERVISOR: 'Supervisores', ATCO: 'ATCO (TWR)', AUX: 'Auxiliares' };
    let categoriaPrevia = null;
    const filas = datos.personas.map(p => {
      const encabezado = p.categoria !== categoriaPrevia
        ? `<tr class="fila-grupo"><td colspan="4">${titulos[p.categoria] || p.categoria}</td></tr>`
        : '';
      categoriaPrevia = p.categoria;
      return encabezado + `<tr data-persona="${p.persona_id}">
        <td><span class="etiqueta">${escapar(p.iniciales)}</span></td>
        <td>${escapar(p.nombre)}</td>
        <td>${p.dias.map(d => `<span class="etiqueta t-${d.slice(-1)}">${escapar(d)}</span>`).join(' ')}</td>
        <td style="width:130px"><input type="number" step="0.5" min="0" class="horas-capt"
              value="${p.horas ?? ''}" placeholder="—"
              aria-label="Horas trabajadas de ${escapar(p.iniciales)}"></td>
      </tr>`;
    }).join('');

    cont.innerHTML = `<div class="envoltura-tabla"><table class="datos">
      <thead><tr><th>Siglas</th><th>Nombre</th><th>Qué pidió</th><th>Horas trabajadas</th></tr></thead>
      <tbody>${filas}</tbody></table></div>`;

    $('#horas-aviso').textContent = datos.sin_horas.length
      ? `Faltan las horas de: ${datos.sin_horas.join(', ')}`
      : 'Todas las horas están capturadas';
    $('#horas-aviso').style.color = datos.sin_horas.length ? 'var(--aviso)' : 'var(--ok)';

    $$('.horas-capt', cont).forEach(campo => {
      const guardar = async () => {
        const fila = campo.closest('tr');
        try {
          await enviar('/api/totales/uno', {
            persona_id: Number(fila.dataset.persona),
            periodo: $('#horas-periodo').value,
            horas: campo.value,
          });
          await cargarHoras();
        } catch (err) { fallar(err); }
      };
      campo.addEventListener('change', guardar);
      campo.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        const todos = $$('.horas-capt', cont);
        const siguiente = todos[todos.indexOf(campo) + 1];
        campo.blur();
        if (siguiente) setTimeout(() => { siguiente.focus(); siguiente.select(); }, 120);
      });
    });
  } catch (err) { fallar(err); }
}

/* ==========================================================================
   4 · SUGERENCIA
   ========================================================================== */

async function cargarSugerencias() {
  const { desde, hasta } = ventanaTrabajo();
  const periodo = $('#horas-periodo').value || desde.slice(0, 7);
  try {
    const datos = await obtener('/api/sugerencias', { desde, hasta, periodo });
    const soloPendientes = $('#sug-pendientes').checked;

    estado.ronda = datos.ronda;
    pintarSelectorRonda();
    $('#sug-conteo').textContent =
      `Ronda ${datos.ronda} · ${datos.total_asignados} de ${datos.total_lugares} lugar(es) asignado(s)`;

    const lugares = soloPendientes ? datos.lugares.filter(l => l.libres > 0) : datos.lugares;
    const cont = $('#sug-lista');
    if (!lugares.length) {
      cont.innerHTML = `<p class="vacio">${soloPendientes
        ? 'Todos los lugares están cubiertos.'
        : 'No hay lugares publicados. Vuelve al paso 1.'}</p>`;
      await cargarMensajesAsignacion();
      return;
    }

    cont.innerHTML = lugares.map(l => {
      const clase = l.sin_solicitudes ? 'vacio' : (l.libres > 0 ? 'pendiente' : 'completo');
      const estado_ = l.sin_solicitudes ? 'Nadie lo pidió'
        : l.libres > 0 ? `Faltan ${l.libres} de ${l.cupos}` : `Cubierto (${l.cupos})`;

      const lista = l.candidatos.length ? `<ol>${l.candidatos.map((c, i) => `
        <li class="${c.asignado ? 'ya' : (i === 0 && l.libres > 0 ? 'sugerido' : '')} n-${c.nivel}">
          <span class="puesto">${c.asignado ? '✓' : i + 1}</span>
          <span class="quien">${escapar(c.iniciales)}
            ${c.de_otra_categoria ? `<span class="otra-cat">${GRUPOS_TITULO[c.categoria]}</span>` : ''}
            <small>${escapar(nombreCorto(c.nombre))}</small>
            ${c.aviso ? `<em class="choque">${escapar(c.aviso)}</em>` : ''}</span>
          <span class="horas ${c.horas === null ? 'falta' : ''}">
            ${c.horas === null ? 'sin horas' : c.horas.toFixed(1)}
            ${c.horas === null ? '' : '<small>trabajadas</small>'}</span>
          <button class="btn chico ${c.asignado ? '' : (c.nivel === 'PROHIBIDO' ? 'peligro' : 'primario')}"
                  data-asig="${c.persona_id}" data-fecha="${l.fecha}" data-turno="${l.turno}"
                  data-nivel="${c.nivel}" ${c.asignado ? 'disabled' : ''}>
            ${c.asignado ? 'Asignado' : (c.nivel === 'PROHIBIDO' ? 'Forzar' : 'Asignar')}
          </button>
        </li>`).join('')}</ol>`
        : '<p class="sin-nadie">Nadie pidió este lugar.</p>';

      const abierto = l.abierto_a.length > 1
        ? `<span class="abierto-a">abierto a ${l.abierto_a.map(g => GRUPOS_TITULO[g]).join(' + ')}</span>`
        : '';

      return `<div class="lugar ${clase}">
        <header>
          <span class="cuando">${l.dia} ${l.turno}<small>${l.dow}</small></span>
          <span class="grupo-eti">${escapar(l.grupo)}</span>
          ${abierto}
          <span class="estado">${estado_}</span>
        </header>
        ${lista}
      </div>`;
    }).join('');

    $$('[data-asig]', cont).forEach(b => b.addEventListener('click', async () => {
      const prohibido = b.dataset.nivel === 'PROHIBIDO';
      const fila = b.closest('li');
      const motivo = $('.choque', fila)?.textContent.trim() || '';
      if (prohibido && !confirm(`${motivo}\n\n¿Asignarlo de todos modos?`)) return;
      try {
        const r = await enviar('/api/asignaciones', {
          persona_id: Number(b.dataset.asig),
          fecha: b.dataset.fecha,
          turno: b.dataset.turno,
          forzar: true,
        });
        // El motivo real viene del evaluador; no se supone cuál fue.
        avisar(r.forzado ? `Asignado. ${r.evaluacion.resumen}` : 'Asignado',
               r.forzado ? 'warn' : 'ok', r.forzado ? 7000 : 3500);
        await cargarSugerencias();
      } catch (err) { fallar(err); }
    }));

    await cargarMensajesAsignacion();
  } catch (err) { fallar(err); }
}

async function cargarMensajesAsignacion() {
  const { desde, hasta } = ventanaTrabajo();
  try {
    const datos = await enviar('/api/wa/generar', { desde, hasta });
    const cont = $('#sug-mensajes');
    if (!datos.asignacion) {
      cont.innerHTML = '<p class="vacio">Asigna a alguien y aquí sale el mensaje.</p>';
      return;
    }
    cont.innerHTML = `
      <div class="mensaje-caja">
        <header><b>Asignación</b><span class="cuantos">${datos.total} lugar(es)</span></header>
        <pre id="msj-asignacion">${escapar(datos.asignacion)}</pre>
        <footer><button class="btn chico" id="copiar-asignacion">Copiar mensaje</button></footer>
      </div>`;
    $('#copiar-asignacion').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText($('#msj-asignacion').textContent);
        avisar('Mensaje copiado');
      } catch { avisar('Selecciónalo y copia con Ctrl+C', 'warn'); }
    });
  } catch (err) { fallar(err); }
}

/* ==========================================================================
   5 · RESUMEN — qué quedó cubierto y qué sigue libre
   ========================================================================== */

async function cargarCierre() {
  const { desde, hasta } = ventanaTrabajo();
  try {
    const d = await obtener('/api/cierre', { desde, hasta });
    estado.ronda = d.ronda;
    pintarSelectorRonda();

    const avance = d.total_cupos ? Math.round(d.total_asignados / d.total_cupos * 100) : 0;
    const titulos = { SUPERVISOR: 'Supervisores', ATCO: 'ATCO (TWR)', AUX: 'Auxiliares' };

    const desglose = GRUPOS_ORDEN.filter(g => d.por_grupo[g].cupos).map(g => {
      const x = d.por_grupo[g];
      const pct = x.cupos ? Math.round(x.asignados / x.cupos * 100) : 0;
      return `<div class="reng"><b>${titulos[g]}</b>
        <span class="pista"><span style="width:${pct}%"></span></span>
        <span class="cuenta">${x.asignados}/${x.cupos}</span></div>`;
    }).join('');

    $('#cierre-tablero').innerHTML = `
      <div class="marcador total">
        <div class="cifra">${d.total_cupos}</div>
        <div class="etiqueta">Lugares publicados</div>
        <div class="detalle">Ronda ${d.ronda} · del ${fechaLarga(d.desde)} al ${fechaLarga(d.hasta)}</div>
      </div>
      <div class="marcador cubierto">
        <div class="cifra">${d.total_asignados}</div>
        <div class="etiqueta">Ya cubiertos</div>
        <div class="barra-avance"><span style="width:${avance}%"></span></div>
        <div class="detalle">${avance}% del total</div>
      </div>
      <div class="marcador libre ${d.total_libres ? '' : 'cero'}">
        <div class="cifra">${d.total_libres}</div>
        <div class="etiqueta">Siguen libres</div>
        <div class="detalle">${d.total_libres
          ? 'Falta asignarlos o republicarlos'
          : 'No falta nada por cubrir'}</div>
      </div>
      <div class="marcador">
        <div class="etiqueta">Por grupo</div>
        <div class="por-grupo">${desglose || '<div class="detalle">Sin lugares publicados</div>'}</div>
      </div>`;

    $('#cierre-pendientes').innerHTML = d.pendientes.length
      ? pintarDiasCierre(d.pendientes, false)
      : `<p class="vacio">${d.total_cupos
          ? '✓ Todos los lugares están cubiertos.'
          : 'No hay lugares publicados en este rango.'}</p>`;

    $('#cierre-cubiertos').innerHTML = d.cubiertos.length
      ? pintarDiasCierre(d.cubiertos, true)
      : '<p class="vacio">Todavía no se ha asignado ningún lugar.</p>';
  } catch (err) { fallar(err); }
}

/** Agrupa los lugares por día y los pinta como tarjetas. */
function pintarDiasCierre(lugares, cubierto) {
  const titulos = { SUPERVISOR: 'Supervisores', ATCO: 'ATCO (TWR)', AUX: 'Auxiliares' };
  const porDia = {};
  for (const l of lugares) (porDia[l.fecha] ||= []).push(l);

  return Object.keys(porDia).sort().map(fecha => {
    const delDia = porDia[fecha];
    const cupos = delDia.reduce((s, l) => s + l.cupos, 0);
    const libres = delDia.reduce((s, l) => s + l.libres, 0);

    const tarjetas = delDia.map(l => {
      const gente = l.asignados.length
        ? l.asignados.map(escapar).join(', ') : '';
      const falta = l.libres
        ? `<span class="falta-txt">${gente ? ' · ' : ''}faltan ${l.libres}</span>` : '';
      const abierto = !cubierto && l.abierto_a.length > 1
        ? `<div class="abierto">abierto a ${l.abierto_a.map(g => titulos[g]).join(' + ')}</div>` : '';
      return `<div class="lugar-chico ${cubierto ? 'ok' : 'falta'}">
        <span class="turno-eti t-${l.turno}">${l.turno}</span>
        <div class="quienes">
          <div class="grupo">${titulos[l.categoria]}</div>
          <div class="gente">${gente || (l.libres ? '' : '—')}${falta}</div>
          ${abierto}
        </div>
      </div>`;
    }).join('');

    return `<div class="dia-cierre">
      <header>
        <span class="fecha">${delDia[0].dia}<small>${delDia[0].dow}</small></span>
        <span class="cuenta" style="color:var(--${cubierto ? 'ok' : 'aviso'})">
          ${cubierto ? `${cupos} cubierto(s)` : `${libres} sin cubrir de ${cupos}`}</span>
      </header>
      <div class="tarjetas-lugar">${tarjetas}</div>
    </div>`;
  }).join('');
}

/* ==========================================================================
   CANDADO DEL PERSONAL
   ========================================================================== */

//: La clave vive sólo en memoria mientras la pestaña está abierta.
let claveEnMemoria = null;

function pintarCandado() {
  const abierto = Boolean(claveEnMemoria);
  $('#estado-candado').innerHTML = abierto
    ? '<span class="candado-abierto">✓ Desbloqueado. Ya puedes modificar el personal.</span>'
    : '<span class="candado-cerrado">Bajo llave. Sólo se puede consultar.</span>';
  $('#btn-desbloquear').textContent = abierto ? 'Bloquear' : 'Desbloquear';
  $('#clave-personal').disabled = abierto;
  $('#btn-nueva-persona').disabled = !abierto;
  $('#btn-cambiar-clave').disabled = !abierto;
  $$('[data-editar]').forEach(b => { b.disabled = !abierto; });
}

async function alternarCandado() {
  if (claveEnMemoria) {
    claveEnMemoria = null;
    $('#clave-personal').value = '';
    pintarCandado();
    avisar('Catálogo bloqueado de nuevo');
    return;
  }
  const clave = $('#clave-personal').value;
  if (!clave) { avisar('Escribe la clave', 'warn'); $('#clave-personal').focus(); return; }
  try {
    await enviar('/api/acceso/verificar', { clave });
    claveEnMemoria = clave;
    $('#clave-personal').value = '';
    pintarCandado();
    avisar('Desbloqueado');
  } catch (err) { fallar(err); $('#clave-personal').select(); }
}

function modalCambiarClave() {
  abrirModal(`
    <h3>Cambiar la clave</h3>
    <p class="sub-modal">Al menos 4 caracteres. Anótala en un lugar seguro: si se
      pierde, hay que borrar el ajuste directamente en la base de datos.</p>
    <label class="linea" style="margin-bottom:12px">Clave nueva
      <input type="password" id="clave-nueva" maxlength="64" autocomplete="new-password"
             style="flex:1"></label>
    <label class="linea" style="margin-bottom:12px">Repítela
      <input type="password" id="clave-repetir" maxlength="64" autocomplete="new-password"
             style="flex:1"></label>
    <div class="acciones-modal">
      <button class="btn" id="cc-cancelar">Cancelar</button>
      <button class="btn primario" id="cc-guardar">Cambiar</button>
    </div>`);

  $('#cc-cancelar').addEventListener('click', cerrarModal);
  $('#cc-guardar').addEventListener('click', async () => {
    const nueva = $('#clave-nueva').value;
    if (nueva !== $('#clave-repetir').value) {
      avisar('Las dos claves no coinciden', 'error');
      return;
    }
    try {
      await enviar('/api/acceso/cambiar', { clave: claveEnMemoria, clave_nueva: nueva });
      claveEnMemoria = nueva;
      avisar('Clave cambiada');
      cerrarModal();
    } catch (err) { fallar(err); }
  });
}

/* ==========================================================================
   VACANTES
   ========================================================================== */

async function leerPublicacion() {
  const texto = $('#texto-publicacion').value;
  if (!texto.trim()) { avisar('Pega primero el mensaje', 'warn'); return; }
  try {
    const datos = await enviar('/api/wa/publicacion', {
      texto, referencia: $('#fecha-publicacion').value || hoyISO(),
    });
    estado.vacantesPrevia = datos.vacantes;
    $('#btn-guardar-vacantes').disabled = !datos.vacantes.length;
    $('#previa-publicacion').innerHTML = datos.vacantes.length ? `
      <p class="nota"><b>${datos.total}</b> vacante(s) detectada(s):</p>
      <div class="envoltura-tabla"><table class="datos">
        <thead><tr><th>Fecha</th><th>Turno</th><th>Cupos</th><th>Ubicación</th><th>Categoría</th></tr></thead>
        <tbody>${datos.vacantes.map(v => `<tr>
          <td>${fechaLarga(v.fecha)}</td>
          <td><span class="etiqueta t-${v.turno}">${v.turno}</span></td>
          <td class="num">${v.cupos}</td><td>${v.ubicacion}</td>
          <td>${v.categoria || '—'}</td></tr>`).join('')}</tbody>
      </table></div>` : '<p class="vacio">No se reconoció ninguna vacante en ese texto.</p>';
  } catch (err) { fallar(err); }
}

async function guardarVacantes() {
  try {
    const r = await enviar('/api/vacantes/crear', { vacantes: estado.vacantesPrevia });
    avisar(`${r.creadas} vacante(s) guardada(s)`);
    $('#btn-guardar-vacantes').disabled = true;
    await cargarVacantes();
  } catch (err) { fallar(err); }
}

async function cargarVacantes() {
  try {
    const datos = await obtener('/api/vacantes');
    const cont = $('#tabla-vacantes');
    if (!datos.vacantes.length) {
      cont.innerHTML = '<p class="vacio">No hay vacantes registradas.</p>';
      return;
    }
    cont.innerHTML = `<div class="envoltura-tabla"><table class="datos">
      <thead><tr><th>Fecha</th><th>Turno</th><th>Cupos</th><th>Solicitan</th><th>Asignados</th><th></th></tr></thead>
      <tbody>${datos.vacantes.map(v => `<tr>
        <td>${fechaLarga(v.fecha)}</td>
        <td><span class="etiqueta t-${v.turno}">${v.turno}</span> ${v.ubicacion === 'T2' ? '<small>T2</small>' : ''}</td>
        <td class="num">${v.asignados.length}/${v.cupos}</td>
        <td>${v.solicitudes.map(s => `<span class="etiqueta">${escapar(s.iniciales)}</span>`).join(' ') || '—'}</td>
        <td>${v.asignados.map(a => `<span class="etiqueta ok">${escapar(a)}</span>`).join(' ') || '—'}</td>
        <td><button class="btn chico peligro" data-borrar-vacante="${v.id}">Quitar</button></td>
      </tr>`).join('')}</tbody></table></div>`;

    $$('[data-borrar-vacante]', cont).forEach(b => b.addEventListener('click', async () => {
      try {
        await enviar('/api/vacantes/borrar', { id: Number(b.dataset.borrarVacante) });
        await cargarVacantes();
      } catch (err) { fallar(err); }
    }));
  } catch (err) { fallar(err); }
}

/* ==========================================================================
   TOTALES
   ========================================================================== */

async function cargarTotales() {
  const periodo = $('#periodo-totales').value || `${estado.anio}-${String(estado.mes).padStart(2, '0')}`;
  $('#periodo-totales').value = periodo;
  try {
    const datos = await obtener('/api/totales', { periodo });
    $('#tabla-totales').innerHTML = `<div class="envoltura-tabla"><table class="datos">
      <thead><tr><th>Siglas</th><th>Nombre</th><th>Categoría</th>
        <th style="width:130px">Horas TX</th><th style="width:110px">Turnos</th>
        <th class="num">Sistema</th><th>Actualizado</th></tr></thead>
      <tbody>${datos.totales.map(t => `<tr data-persona="${t.id}">
        <td><span class="etiqueta">${escapar(t.iniciales)}</span></td>
        <td>${escapar(t.nombre)}</td>
        <td><small>${t.categoria}</small></td>
        <td><input type="number" step="0.5" min="0" class="horas" value="${t.horas ?? ''}" placeholder="—"></td>
        <td><input type="number" step="1" min="0" class="turnos" value="${t.turnos ?? ''}" placeholder="—"></td>
        <td class="num">${(t.horas_sistema || 0).toFixed(1)}</td>
        <td><small>${t.actualizado ? escapar(t.actualizado) : '—'}</small></td>
      </tr>`).join('')}</tbody></table></div>`;
  } catch (err) { fallar(err); }
}

async function guardarTotales() {
  const periodo = $('#periodo-totales').value;
  const totales = $$('#tabla-totales tr[data-persona]').map(tr => ({
    persona_id: Number(tr.dataset.persona),
    horas: $('.horas', tr).value,
    turnos: $('.turnos', tr).value,
  }));
  try {
    const r = await enviar('/api/totales/guardar', { periodo, totales });
    avisar(`${r.guardados} total(es) guardado(s)`);
    await cargarTotales();
    await cargarCuadricula();
  } catch (err) { fallar(err); }
}

/* ==========================================================================
   MENSAJES
   ========================================================================== */

async function leerSolicitudes() {
  const texto = $('#texto-solicitudes').value;
  if (!texto.trim()) { avisar('Pega primero el mensaje', 'warn'); return; }
  try {
    const datos = await enviar('/api/wa/solicitudes', {
      texto,
      referencia: $('#fecha-solicitudes').value || hoyISO(),
      iniciales: $('#solicitud-siglas').value,
    });
    estado.solicitudesPrevia = datos.solicitudes;
    $('#btn-guardar-solicitudes').disabled = !datos.solicitudes.length || !$('#solicitud-siglas').value.trim();
    $('#previa-solicitudes').innerHTML = datos.solicitudes.length
      ? `<p class="nota"><b>${datos.total}</b> solicitud(es): `
        + datos.solicitudes.map(s => `<span class="etiqueta t-${s.turno}">${
            Number(s.fecha.slice(8))}${s.turno}</span>`).join(' ') + '</p>'
      : '<p class="vacio">No se reconoció ninguna solicitud.</p>';
  } catch (err) { fallar(err); }
}

async function guardarSolicitudes() {
  const siglas = $('#solicitud-siglas').value.trim().toUpperCase();
  if (!siglas) { avisar('Escribe las siglas de quien pide', 'warn'); return; }
  try {
    const r = await enviar('/api/solicitudes', {
      solicitudes: estado.solicitudesPrevia.map(s => ({ ...s, iniciales: siglas })),
    });
    let msg = `${r.registradas} solicitud(es) registrada(s)`;
    if (r.sin_persona.length) msg += ` · siglas no encontradas: ${r.sin_persona.join(', ')}`;
    if (r.sin_vacante.length) msg += ` · sin vacante publicada: ${r.sin_vacante.join(', ')}`;
    avisar(msg, r.registradas ? 'ok' : 'warn', 6000);
    await cargarVacantes();
  } catch (err) { fallar(err); }
}

async function generarMensaje() {
  try {
    const datos = await enviar('/api/wa/generar', {
      desde: $('#gen-desde').value || hoyISO(),
      hasta: $('#gen-hasta').value || $('#gen-desde').value || hoyISO(),
    });
    const partes = [];
    if (datos.publicacion) partes.push(datos.publicacion);
    if (datos.asignacion) partes.push(datos.asignacion);
    $('#salida-mensaje').value = partes.join('\n\n---\n\n')
      || 'No hay asignaciones ni vacantes en ese rango.';
  } catch (err) { fallar(err); }
}

async function cargarExport(archivo) {
  $('#nombre-export').textContent = `Leyendo ${archivo.name}…`;
  const texto = await archivo.text();
  try {
    const previa = await enviar('/api/wa/export', { texto });
    $('#nombre-export').textContent = archivo.name;
    $('#previa-export').innerHTML = `
      <p class="nota">Se encontraron <b>${previa.total_asignaciones}</b> asignación(es) de tiempo extra
      y <b>${previa.total_publicaciones}</b> publicación(es) de disponibilidad.</p>
      ${previa.total_asignaciones ? `
        <div class="envoltura-tabla" style="max-height:280px"><table class="datos">
          <thead><tr><th>Siglas</th><th>Fecha</th><th>Turno</th><th>Publicó</th></tr></thead>
          <tbody>${previa.asignaciones.slice(-60).reverse().map(a => `<tr>
            <td><span class="etiqueta">${escapar(a.iniciales)}</span></td>
            <td>${a.fecha}</td>
            <td><span class="etiqueta t-${a.turno}">${a.turno}</span></td>
            <td><small>${escapar(a.supervisor || '')}</small></td></tr>`).join('')}</tbody>
        </table></div>
        <p class="nota">Se muestran las 60 más recientes.</p>
        <button class="btn primario" id="btn-aplicar-export">Cargar como histórico</button>` : ''}`;

    const btn = $('#btn-aplicar-export');
    if (btn) btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const r = await enviar('/api/wa/export', { texto, aplicar: true });
        let msg = `${r.aplicadas} asignación(es) cargada(s) como histórico`;
        if (r.siglas_desconocidas.length) {
          msg += ` · siglas sin persona registrada: ${r.siglas_desconocidas.join(', ')}`;
        }
        avisar(msg, 'ok', 8000);
        await cargarCuadricula();
      } catch (err) { fallar(err); } finally { btn.disabled = false; }
    });
  } catch (err) { fallar(err); $('#nombre-export').textContent = ''; }
}

/* ==========================================================================
   PERSONAL
   ========================================================================== */

async function cargarPersonal() {
  try {
    const datos = await obtener('/api/personas', { todas: 1 });
    $('#tabla-personal').innerHTML = `<div class="envoltura-tabla"><table class="datos">
      <thead><tr><th>Siglas</th><th>Nombre</th><th>No. empleado</th><th>Categoría</th><th>Estado</th><th></th></tr></thead>
      <tbody>${datos.personas.map(p => `<tr>
        <td><span class="etiqueta">${escapar(p.iniciales)}</span></td>
        <td>${escapar(p.nombre)}</td>
        <td>${escapar(p.no_empleado || '—')}</td>
        <td>${p.categoria}</td>
        <td>${p.activo ? '<span class="etiqueta ok">Activo</span>' : '<span class="etiqueta">Inactivo</span>'}</td>
        <td><button class="btn chico" data-editar='${escapar(JSON.stringify(p))}'>Editar</button></td>
      </tr>`).join('')}</tbody></table></div>`;

    $$('[data-editar]').forEach(b => b.addEventListener('click', () =>
      modalPersona(JSON.parse(b.dataset.editar))));
    pintarCandado();
  } catch (err) { fallar(err); }
}

function modalPersona(persona = {}) {
  const cats = ['SUPERVISOR', 'ATCO', 'AUX'];
  abrirModal(`
    <h3>${persona.id ? 'Editar' : 'Agregar'} persona</h3>
    <p class="sub-modal">Las siglas son la clave con que aparece en los mensajes del grupo.</p>
    <div class="campos">
      <label>Siglas <input type="text" id="p-siglas" maxlength="3" value="${escapar(persona.iniciales || '')}"></label>
      <label>No. empleado <input type="text" id="p-numero" value="${escapar(persona.no_empleado || '')}"></label>
    </div>
    <label class="linea" style="margin-bottom:12px">Nombre completo
      <input type="text" id="p-nombre" style="flex:1" value="${escapar(persona.nombre || '')}"></label>
    <div class="campos">
      <label>Categoría <select id="p-categoria">
        ${cats.map(c => `<option value="${c}"${c === persona.categoria ? ' selected' : ''}>${c}</option>`).join('')}
      </select></label>
      <label>Estado <select id="p-activo">
        <option value="1"${persona.activo !== 0 ? ' selected' : ''}>Activo</option>
        <option value="0"${persona.activo === 0 ? ' selected' : ''}>Inactivo</option>
      </select></label>
    </div>
    <div class="acciones-modal">
      <button class="btn" id="p-cancelar">Cancelar</button>
      <button class="btn primario" id="p-guardar">Guardar</button>
    </div>`);

  $('#p-cancelar').addEventListener('click', cerrarModal);
  $('#p-guardar').addEventListener('click', async () => {
    try {
      await enviar('/api/personas/guardar', {
        clave: claveEnMemoria,
        id: persona.id,
        iniciales: $('#p-siglas').value,
        nombre: $('#p-nombre').value,
        no_empleado: $('#p-numero').value,
        categoria: $('#p-categoria').value,
        activo: $('#p-activo').value === '1',
      });
      avisar('Guardado');
      cerrarModal();
      await cargarPersonal();
      await cargarCuadricula();
    } catch (err) { fallar(err); }
  });
}

/* ------------------------------------------------------- importadores --- */

const leerBase64 = (archivo) => new Promise((res, rej) => {
  const fr = new FileReader();
  fr.onload = () => res(String(fr.result).split(',', 2)[1]);
  fr.onerror = rej;
  fr.readAsDataURL(archivo);
});

async function importarHorario(archivo) {
  try {
    const b64 = await leerBase64(archivo);
    const previa = await enviar('/api/importar/horario', { nombre: archivo.name, contenido_b64: b64 });
    if (!previa.ok) { avisar(previa.error, 'error', 8000); return; }

    abrirModal(`
      <h3>Importar horario</h3>
      <p class="sub-modal">Se reconocieron <b>${previa.total_personas}</b> persona(s) y los días
        ${previa.dias_detectados[0]} al ${previa.dias_detectados.at(-1)}.</p>
      <div class="campos">
        <label>Mes que corresponde <input type="month" id="imp-periodo" value="${estado.anio}-${String(estado.mes).padStart(2,'0')}"></label>
        <label>Categoría por defecto <select id="imp-categoria">
          <option value="ATCO">ATCO</option><option value="SUPERVISOR">Supervisor</option><option value="AUX">Auxiliar</option>
        </select></label>
      </div>
      <div class="envoltura-tabla" style="max-height:260px"><table class="datos">
        <thead><tr><th>Siglas</th><th>Nombre</th><th>Días</th><th>Códigos raros</th></tr></thead>
        <tbody>${previa.personas.map(p => `<tr>
          <td><span class="etiqueta">${escapar(p.siglas)}</span></td>
          <td>${escapar(p.nombre)}</td>
          <td class="num">${Object.keys(p.dias).length}</td>
          <td>${p.codigos_desconocidos.length
            ? `<span class="etiqueta alto">${p.codigos_desconocidos.map(escapar).join(' ')}</span>` : '—'}</td>
        </tr>`).join('')}</tbody></table></div>
      <div class="acciones-modal">
        <button class="btn" id="imp-cancelar">Cancelar</button>
        <button class="btn primario" id="imp-aplicar">Importar</button>
      </div>`);

    $('#imp-cancelar').addEventListener('click', cerrarModal);
    $('#imp-aplicar').addEventListener('click', async () => {
      const [anio, mes] = $('#imp-periodo').value.split('-').map(Number);
      try {
        const r = await enviar('/api/importar/horario', {
          nombre: archivo.name, contenido_b64: b64, aplicar: true,
          anio, mes, categoria: $('#imp-categoria').value,
        });
        avisar(`${r.personas_creadas} persona(s) nueva(s), ${r.dias_escritos} día(s) de horario`, 'ok', 6000);
        cerrarModal();
        await cargarPersonal();
        await cargarCuadricula();
      } catch (err) { fallar(err); }
    });
  } catch (err) { fallar(err); }
}

async function importarConteo(archivo) {
  try {
    const b64 = await leerBase64(archivo);
    let previa = await enviar('/api/importar/conteo', { nombre: archivo.name, contenido_b64: b64 });

    const hojas = previa.hojas || [];
    // Se abre en la hoja que más días traiga; suele ser la del mes en curso.
    if (!previa.ok && hojas.length) {
      for (const h of hojas) {
        const intento = await enviar('/api/importar/conteo',
          { nombre: archivo.name, contenido_b64: b64, hoja: h });
        if (intento.ok) { previa = intento; break; }
      }
    }
    if (!previa.ok) { avisar(previa.error, 'error', 9000); return; }

    const pintar = (p) => {
      const dobles = (p.dobles || []).slice(0, 30);
      abrirModal(`
        <h3>Importar del libro de conteo</h3>
        <p class="sub-modal">
          Hoja <b>${escapar(p.hoja_leida || hojas[0] || '')}</b> ·
          ${p.total_personas} persona(s) · ${p.total_dias} día(s) con movimiento
          ${p.desde ? `· del ${p.desde} al ${p.hasta}` : ''}
        </p>
        ${p.aviso ? `<div class="bloque-eval nivel-ADVERTENCIA">⚠ ${escapar(p.aviso)}</div>` : ''}

        <div class="campos">
          <label>Hoja
            <select id="cont-hoja">
              ${hojas.map(h => `<option value="${escapar(h)}"${h === p.hoja_leida ? ' selected' : ''}>${escapar(h)}</option>`).join('')}
            </select>
          </label>
          <label>Periodo destino
            <input type="month" id="cont-periodo"
                   value="${p.desde ? p.desde.slice(0, 7) : `${estado.anio}-${String(estado.mes).padStart(2, '0')}`}">
          </label>
        </div>

        <div class="fila-controles">
          <label class="check"><input type="checkbox" id="cont-totales" checked> Totales acumulados</label>
          <label class="check"><input type="checkbox" id="cont-dias" checked> Detalle día por día</label>
          <label class="check"><input type="checkbox" id="cont-altas" checked> Dar de alta a quien falte</label>
          <label>Categoría de las altas
            <select id="cont-categoria">
              <option value="ATCO">ATCO</option>
              <option value="AUX">Auxiliar</option>
              <option value="SUPERVISOR">Supervisor</option>
            </select>
          </label>
        </div>

        ${dobles.length ? `
          <p class="nota"><b>${(p.dobles || []).length}</b> jornada(s) doble(s)
             detectada(s) (14 horas o más en un día). Estas alimentan la regla
             de días consecutivos:</p>
          <div class="envoltura-tabla" style="max-height:170px"><table class="datos">
            <thead><tr><th>Fecha</th><th>Siglas</th><th class="num">Horas</th></tr></thead>
            <tbody>${dobles.map(d => `<tr><td>${d.fecha}</td>
              <td><span class="etiqueta">${escapar(d.siglas)}</span></td>
              <td class="num">${d.horas}</td></tr>`).join('')}</tbody>
          </table></div>` : ''}

        <div class="envoltura-tabla" style="max-height:200px;margin-top:12px"><table class="datos">
          <thead><tr><th>Siglas</th><th class="num">Total acumulado</th></tr></thead>
          <tbody>${Object.entries(p.totales).map(([s, h]) => `<tr>
            <td><span class="etiqueta">${escapar(s)}</span></td>
            <td class="num">${h}</td></tr>`).join('')}</tbody>
        </table></div>

        <div class="acciones-modal">
          <button class="btn" id="cont-cancelar">Cancelar</button>
          <button class="btn primario" id="cont-aplicar">Importar</button>
        </div>`);

      $('#cont-cancelar').addEventListener('click', cerrarModal);

      $('#cont-hoja').addEventListener('change', async (e) => {
        const [anio, mes] = $('#cont-periodo').value.split('-').map(Number);
        try {
          const otra = await enviar('/api/importar/conteo', {
            nombre: archivo.name, contenido_b64: b64, hoja: e.target.value, anio, mes,
          });
          if (otra.ok) pintar(otra);
          else avisar(otra.error, 'warn', 7000);
        } catch (err) { fallar(err); }
      });

      $('#cont-aplicar').addEventListener('click', async () => {
        const [anio, mes] = $('#cont-periodo').value.split('-').map(Number);
        try {
          const r = await enviar('/api/importar/conteo', {
            nombre: archivo.name, contenido_b64: b64, aplicar: true,
            hoja: $('#cont-hoja').value,
            periodo: $('#cont-periodo').value,
            anio, mes,
            con_totales: $('#cont-totales').checked,
            con_dias: $('#cont-dias').checked,
            crear_personas: $('#cont-altas').checked,
            categoria: $('#cont-categoria').value,
          });
          let msg = `${r.totales_aplicados} total(es) y ${r.dias_aplicados} registro(s) diarios importados`;
          if (r.personas_creadas.length) {
            msg += ` · ${r.personas_creadas.length} alta(s) nueva(s): ${r.personas_creadas.join(', ')}`;
          }
          if (r.sin_persona.length) {
            msg += ` · siglas sin persona dada de alta: ${r.sin_persona.join(', ')}`;
          }
          avisar(msg, 'ok', 12000);
          if (r.personas_creadas.length) {
            avisar('Las altas nuevas quedaron sólo con siglas. '
                 + 'Complétales el nombre y la categoría en la pestaña Personal.', 'warn', 12000);
          }
          cerrarModal();
          await cargarTotales();
          await cargarPersonal();
          await cargarCuadricula();
        } catch (err) { fallar(err); }
      });
    };

    pintar(previa);
  } catch (err) { fallar(err); }
}

/* ==========================================================================
   LIMPIEZA PARA UNA ASIGNACIÓN NUEVA
   ========================================================================== */

async function modalLimpiar() {
  let previa;
  try { previa = await obtener('/api/limpiar/previa'); }
  catch (err) { fallar(err); return; }

  const cimiento = new Set(['personal', 'horario', 'historico']);
  const filas = previa.grupos.map(g => `
    <label class="grupo-limpiar ${g.por_defecto ? 'se-borra' : ''}
                  ${cimiento.has(g.clave) ? 'cimiento' : ''}
                  ${g.registros ? '' : 'vacio-ya'}">
      <input type="checkbox" data-grupo="${g.clave}" ${g.por_defecto ? 'checked' : ''}>
      <span class="nombre">${escapar(g.etiqueta)}</span>
      <span class="cuantos">${g.registros} registro(s)</span>
    </label>`).join('');

  abrirModal(`
    <h3>Empezar una asignación nueva</h3>
    <p class="sub-modal">
      Vacía lo de la semana pasada para arrancar de cero. Lo marcado se borra;
      lo demás se queda.
    </p>

    <div class="grupos-limpiar">${filas}</div>

    <p class="nota">
      El <b>catálogo de personal</b>, el <b>horario</b> y el <b>histórico del
      Excel</b> no se tocan: son el cimiento, no el ciclo. Las horas sí se
      limpian porque las vuelves a tomar del conteo cada semana, y una cifra
      vieja ordenaría mal la sugerencia sin que te dieras cuenta.
    </p>

    <label class="check" style="margin-bottom:6px">
      <input type="checkbox" id="lim-respaldo" checked>
      Sacar un respaldo antes de borrar
    </label>
    <label class="check">
      <input type="checkbox" id="lim-ronda" checked>
      Volver a la ronda 1
    </label>

    <div class="confirmar-limpiar">
      <label for="lim-palabra">Escribe ${escapar(previa.palabra)} para confirmar</label>
      <input type="text" id="lim-palabra" maxlength="10" autocomplete="off"
             placeholder="${escapar(previa.palabra)}">
    </div>

    <div class="acciones-modal">
      <button class="btn" id="lim-cancelar">Cancelar</button>
      <button class="btn peligro" id="lim-hacer" disabled>Limpiar</button>
    </div>`);

  const palabra = $('#lim-palabra');
  const botonHacer = $('#lim-hacer');

  const revisar = () => {
    const marcados = $$('[data-grupo]').filter(c => c.checked);
    botonHacer.disabled = !marcados.length
      || palabra.value.trim().toUpperCase() !== previa.palabra;
    botonHacer.textContent = marcados.length
      ? `Limpiar ${marcados.length} grupo(s)` : 'Nada marcado';
  };

  $$('[data-grupo]').forEach(casilla => casilla.addEventListener('change', () => {
    casilla.closest('label').classList.toggle('se-borra', casilla.checked);
    revisar();
  }));
  palabra.addEventListener('input', revisar);
  palabra.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !botonHacer.disabled) botonHacer.click();
  });
  revisar();
  setTimeout(() => palabra.focus(), 80);

  $('#lim-cancelar').addEventListener('click', cerrarModal);

  botonHacer.addEventListener('click', async () => {
    const grupos = $$('[data-grupo]').filter(c => c.checked).map(c => c.dataset.grupo);
    const cuerpo = {
      grupos,
      confirmacion: palabra.value,
      respaldar: $('#lim-respaldo').checked,
      volver_a_ronda_1: $('#lim-ronda').checked,
    };
    // Borrar al personal pide la misma clave que el catálogo.
    if (grupos.includes('personal')) {
      const clave = prompt('Borrar el catálogo de personal pide la clave:');
      if (clave === null) return;
      cuerpo.clave = clave;
    }

    botonHacer.disabled = true;
    try {
      const r = await enviar('/api/limpiar', cuerpo);
      cerrarModal();
      avisar(`Listo: ${r.total} registro(s) borrado(s). Ya puedes empezar de nuevo.`, 'ok', 7000);
      if (r.respaldo) {
        avisar(`Respaldo guardado en ${r.respaldo.split(/[/\\]/).pop()}`, 'ok', 9000);
      }
      estado.ronda = r.ronda;
      await cargarConfig();
      pintarSelectorRonda();
      await cargarMatriz();
      await cargarCuadricula();
      cambiarVista('publicar');
    } catch (err) { fallar(err); revisar(); }
  });
}

/* ==========================================================================
   AJUSTES Y ARRANQUE
   ========================================================================== */

function modalAjustes() {
  abrirModal(`
    <h3>Ajustes</h3>
    <p class="sub-modal">La regla principal es configurable por si cambia la normativa.</p>
    <label class="linea" style="margin-bottom:14px">
      Máximo de jornadas dobles consecutivas
      <input type="number" id="aj-tope" min="1" max="7" value="${estado.config.max_dobles_consecutivas}" style="width:80px">
    </label>
    <p class="nota">
      Con el valor en <b>2</b>, un tercer día doble seguido queda prohibido —
      que es la regla vigente en la torre.
    </p>
    <div class="bloque-eval nivel-OK" style="color:var(--tinta)">
      <b>Datos cargados</b>
      <ul>
        <li>${estado.config.conteos.personas} persona(s)</li>
        <li>${estado.config.conteos.dias_horario} día(s) de horario base</li>
        <li>${estado.config.conteos.asignaciones} registro(s) de tiempo extra</li>
      </ul>
    </div>
    <div class="acciones-modal">
      <button class="btn" id="aj-cancelar">Cerrar</button>
      <button class="btn primario" id="aj-guardar">Guardar</button>
    </div>`);

  $('#aj-cancelar').addEventListener('click', cerrarModal);
  $('#aj-guardar').addEventListener('click', async () => {
    try {
      await enviar('/api/ajustes', { max_dobles_consecutivas: $('#aj-tope').value });
      avisar('Ajustes guardados');
      cerrarModal();
      await cargarConfig();
      await cargarCuadricula();
    } catch (err) { fallar(err); }
  });
}

async function cargarConfig() {
  estado.config = await obtener('/api/estado');
}

//: Vistas que no tienen pestaña propia y viven bajo «Más…».
const VISTAS_SECUNDARIAS = ['cuadricula', 'asignar', 'vacantes', 'totales', 'mensajes'];

function cambiarVista(nombre) {
  const pestana = VISTAS_SECUNDARIAS.includes(nombre) ? 'mas' : nombre;
  $$('.pest').forEach(b => b.classList.toggle('activa', b.dataset.vista === pestana));
  $$('.vista').forEach(v => v.classList.toggle('activa', v.id === `vista-${nombre}`));

  if (nombre === 'publicar')    cargarMatriz();
  if (nombre === 'solicitudes') { cargarSiglasConocidas(); cargarSolicitudes(); $('#sol-siglas').focus(); }
  if (nombre === 'horas')       cargarHoras();
  if (nombre === 'sugerencia')  cargarSugerencias();
  if (nombre === 'cierre')      cargarCierre();
  if (nombre === 'vacantes')    cargarVacantes();
  if (nombre === 'totales')     cargarTotales();
  if (nombre === 'personal')    cargarPersonal();
  if (nombre === 'cuadricula')  cargarCuadricula();

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function moverMes(delta) {
  let m = estado.mes + delta, a = estado.anio;
  if (m < 1)  { m = 12; a--; }
  if (m > 12) { m = 1;  a++; }
  estado.mes = m; estado.anio = a;
  cargarCuadricula();
}

function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema;
  localStorage.setItem('tx-tema', tema);
}

async function iniciar() {
  aplicarTema(localStorage.getItem('tx-tema')
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro'));

  const hoy = new Date();
  estado.anio = hoy.getFullYear();
  estado.mes  = hoy.getMonth() + 1;

  for (const id of ['#asig-fecha', '#fecha-publicacion', '#fecha-solicitudes',
                    '#gen-desde', '#gen-hasta', '#pub-desde']) {
    $(id).value = hoyISO();
  }
  $('#periodo-totales').value = `${estado.anio}-${String(estado.mes).padStart(2, '0')}`;
  $('#horas-periodo').value = `${estado.anio}-${String(estado.mes).padStart(2, '0')}`;

  try {
    await cargarConfig();
  } catch (err) { fallar(err); return; }

  // Navegación
  $$('.pest').forEach(b => b.addEventListener('click', () => cambiarVista(b.dataset.vista)));
  // Los botones «Siguiente» y los atajos de «Más…»
  document.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-ir]');
    if (boton) cambiarVista(boton.dataset.ir);
  });

  // Paso 2 · solicitudes
  $('#sol-siglas').addEventListener('input', mostrarQuienEs);
  $('#sol-siglas').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); $('#sol-texto').focus(); }
  });
  $('#sol-texto').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); agregarSolicitud(); }
  });
  $('#sol-agregar').addEventListener('click', agregarSolicitud);

  // Paso 3 · horas
  $('#horas-periodo').addEventListener('change', cargarHoras);

  // Paso 4 · sugerencia
  $('#sug-pendientes').addEventListener('change', cargarSugerencias);
  $('#mes-ant').addEventListener('click', () => moverMes(-1));
  $('#mes-sig').addEventListener('click', () => moverMes(1));
  $('#mes-hoy').addEventListener('click', () => {
    const h = new Date();
    estado.anio = h.getFullYear(); estado.mes = h.getMonth() + 1;
    cargarCuadricula();
  });

  // Filtros
  for (const id of ['#filtro-categoria', '#filtro-texto', '#zoom', '#solo-tx']) {
    $(id).addEventListener('input', pintarCuadricula);
  }

  // Tema y ajustes
  $('#btn-tema').addEventListener('click', () =>
    aplicarTema(document.documentElement.dataset.tema === 'oscuro' ? 'claro' : 'oscuro'));
  $('#btn-ajustes').addEventListener('click', modalAjustes);
  $('#btn-limpiar-todo').addEventListener('click', modalLimpiar);

  // Modal
  $('#cerrar-modal').addEventListener('click', cerrarModal);
  $('#fondo-modal').addEventListener('click', (e) => { if (e.target.id === 'fondo-modal') cerrarModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') cerrarModal(); });

  // Asignar
  $('#btn-buscar-candidatos').addEventListener('click', buscarCandidatos);

  // Ronda de publicación
  $$('.ronda-btn').forEach(b =>
    b.addEventListener('click', () => cambiarRonda(Number(b.dataset.ronda))));
  estado.ronda = estado.config.ronda;
  pintarSelectorRonda();

  // Publicar
  $('#pub-desde').addEventListener('change', cargarMatriz);
  $('#pub-dias').addEventListener('change', cargarMatriz);
  $('#pub-dia-semana').addEventListener('change', cargarMensajesGrupo);
  $('#pub-refrescar').addEventListener('click', cargarMensajesGrupo);
  $('#pub-limpiar').addEventListener('click', async () => {
    const desde = $('#pub-desde').value;
    const dias = Number($('#pub-dias').value);
    const hasta = new Date(new Date(desde + 'T12:00:00').getTime() + (dias - 1) * 864e5)
      .toISOString().slice(0, 10);
    if (!confirm(`¿Borrar todos los lugares capturados del ${desde} al ${hasta}?`)) return;
    try {
      const r = await enviar('/api/vacantes/limpiar', { desde, hasta });
      avisar(`${r.borradas} registro(s) borrado(s)`);
      await cargarMatriz();
    } catch (err) { fallar(err); }
  });

  // Vacantes
  $('#btn-leer-publicacion').addEventListener('click', leerPublicacion);
  $('#btn-guardar-vacantes').addEventListener('click', guardarVacantes);

  // Totales
  $('#btn-guardar-totales').addEventListener('click', guardarTotales);
  $('#periodo-totales').addEventListener('change', cargarTotales);
  $('#btn-importar-conteo').addEventListener('click', () => $('#archivo-conteo').click());
  $('#archivo-conteo').addEventListener('change', (e) => {
    if (e.target.files[0]) importarConteo(e.target.files[0]);
    e.target.value = '';
  });

  // Mensajes
  $('#btn-leer-solicitudes').addEventListener('click', leerSolicitudes);
  $('#btn-guardar-solicitudes').addEventListener('click', guardarSolicitudes);
  $('#btn-generar').addEventListener('click', generarMensaje);
  $('#btn-copiar').addEventListener('click', async () => {
    const texto = $('#salida-mensaje').value;
    if (!texto) return;
    try { await navigator.clipboard.writeText(texto); avisar('Copiado'); }
    catch { $('#salida-mensaje').select(); avisar('Selecciona y copia con Ctrl+C', 'warn'); }
  });
  $('#btn-elegir-export').addEventListener('click', () => $('#archivo-export').click());
  $('#archivo-export').addEventListener('change', (e) => {
    if (e.target.files[0]) cargarExport(e.target.files[0]);
    e.target.value = '';
  });

  // Personal
  $('#btn-desbloquear').addEventListener('click', alternarCandado);
  $('#clave-personal').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); alternarCandado(); }
  });
  $('#btn-cambiar-clave').addEventListener('click', modalCambiarClave);
  pintarCandado();
  $('#btn-nueva-persona').addEventListener('click', () => modalPersona());
  $('#btn-importar-horario').addEventListener('click', () => $('#archivo-horario').click());
  $('#archivo-horario').addEventListener('change', (e) => {
    if (e.target.files[0]) importarHorario(e.target.files[0]);
    e.target.value = '';
  });
  $('#btn-sembrar').addEventListener('click', async () => {
    try {
      const r = await enviar('/api/sembrar', { forzar: true });
      avisar(r.ok ? `${r.personas_creadas} persona(s), ${r.dias_escritos} día(s) de horario` : r.motivo,
             r.ok ? 'ok' : 'warn');
      await cargarPersonal();
      await cargarCuadricula();
    } catch (err) { fallar(err); }
  });

  await cargarCuadricula();
  await cargarMatriz();

  if (estado.config.vacio) {
    avisar('Base vacía: usa «Cargar plantilla S-TWR agosto» en la pestaña Personal', 'warn', 9000);
  }
}

iniciar();

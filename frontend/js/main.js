import { api } from "./api.js";
import { createScene, view } from "./scene.js";
import { CyclotronView } from "./cyclotron.js";
import { ParticleView, TrajectoryLine } from "./particle.js";
import { bindControls, readRf, setPlayingUi, setStatus, showMessages, updateHud } from "./controls.js";

// ---------------- Configuración (Etapa 5: pasará al panel de parámetros) ----------------
const CONFIG = {
  particle: "proton",
  bMagnitude: 1.0,         // T
  bSign: +1,
  // Geometría física (SI). Se envía al backend y se devuelve para dibujarla: misma fuente.
  geometry: { dee_radius_m: 0.05, gap_m: 0.005, height_m: 0.02, stop_at_wall: true },
  stepsPerOrbit: 1000,     // Δt = Tc / stepsPerOrbit (resuelve el cruce del hueco)
  maxOrbits: 40,
  blockSteps: 500,         // pasos físicos por petición
  prefetchSteps: 1500,     // ventaja mínima de cálculo sobre la reproducción
  playbackStepsPerSecond: 600,   // SOLO velocidad visual de reproducción
};
const MAX_STEPS = CONFIG.stepsPerOrbit * CONFIG.maxOrbits;
const TERMINAL = new Set(["finished", "extracted", "lost", "error"]);
const END_LABEL = {
  finished: "Finalizada (máx. de pasos)", extracted: "Extraída",
  lost: "Perdida en la pared", error: "Error de cálculo",
};

// ---------------- Escena ----------------
const ctx = createScene(document.getElementById("viewport"));
const cyclotronView = new CyclotronView(ctx.scene);
const particleView = new ParticleView(ctx.scene);
const trajectory = new TrajectoryLine(ctx.scene, MAX_STEPS + 1);

// ---------------- Estado de la aplicación ----------------
const COLUMNS = ["step", "t", "position", "velocity", "speed", "kinetic_energy_j",
                 "lorentz_force_n", "e_field", "b_field", "electric_work_j",
                 "rf_signal_vm", "in_gap"];
const buf = Object.fromEntries(COLUMNS.map((k) => [k, []]));   // datos físicos del backend
let simId = null;
let meta = { fc: 0, frf: 0, e0: 0 };
let generation = 0;        // invalida respuestas de simulaciones anteriores
let pending = null;        // petición /step en curso
let fetching = false;
let finished = false;      // el backend ya no tiene más pasos
let finalState = null;     // estado terminal informado por el backend
let endShown = false;
let playing = false;
let started = false;
let playIndex = 0;         // índice (decimal) de la muestra que se reproduce
let lastTime = null;
let framed = false;        // la cámara se encuadra solo la primera vez

const messages = { warnings: [], runtime: [], error: null, info: null };
const lastIndex = () => buf.t.length - 1;

function renderMessages() {
  const items = [];
  if (messages.error) items.push({ kind: "error", text: messages.error });
  if (messages.info) items.push({ kind: "info", text: messages.info });
  for (const w of messages.runtime) items.push({ kind: "warn", text: w });
  for (const w of messages.warnings) items.push({ kind: "warn", text: w });
  showMessages(items);
}

function clearBuffer() {
  for (const k of COLUMNS) buf[k].length = 0;
  trajectory.clear();
}

function resetPlayback() {
  playing = false; started = false; finished = false; endShown = false;
  finalState = null; playIndex = 0;
  messages.warnings = []; messages.runtime = []; messages.error = null; messages.info = null;
  clearBuffer();
}

function noteState(state) {
  messages.runtime = state.runtime_warnings ?? [];
  if (TERMINAL.has(state.status)) {
    finished = true;
    finalState = state;
  }
}

function ingest(block) {
  if (block.step.length === 0) return;
  if (block.step[0] !== buf.step.length) {
    throw new Error("Bloque desalineado: se esperaba el paso " + buf.step.length);
  }
  for (const k of COLUMNS) for (const v of block[k]) buf[k].push(v);
  trajectory.addPoints(block.position);
}

function refreshUi() {
  setPlayingUi({ playing, started, canStart: !(finished && playIndex >= lastIndex()) });
}

// ---------------- Comunicación con el backend ----------------
async function newSimulation() {
  generation++;
  const gen = generation;
  await pending?.catch(() => {});
  if (gen !== generation) return;          // otra petición posterior tomó el relevo
  resetPlayback();
  setStatus("Calculando…");
  renderMessages();
  refreshUi();
  try {
    const rf = readRf();
    const bz = CONFIG.bMagnitude * CONFIG.bSign;
    const particle = { type: CONFIG.particle };
    const d = await api.derived({ particle, b_z_t: bz });
    const dt = d.cyclotron_period_s / CONFIG.stepsPerOrbit;
    // f_RF = fc cuando la razón es 1; si no, se envía f_RF = razón · fc (fc la calculó el backend)
    const electric = rf.ratio === 1
      ? { voltage_v: rf.voltageV, use_cyclotron_frequency: true, phase_deg: rf.phaseDeg }
      : { voltage_v: rf.voltageV, use_cyclotron_frequency: false,
          frequency_hz: rf.ratio * d.cyclotron_frequency_hz, phase_deg: rf.phaseDeg };
    const r = await api.createSimulation({
      particle, position_m: [0, 0, 0], velocity_ms: [0, 0, 0], b_z_t: bz,
      dt_s: dt, max_steps: MAX_STEPS, geometry: CONFIG.geometry, electric,
    });
    if (gen !== generation) return;
    simId = r.simulation_id;
    const el = r.derived.electric;
    meta = { fc: d.cyclotron_frequency_hz, frf: el?.rf_frequency_hz ?? 0, e0: el?.e0_v_per_m ?? 0 };
    ctx.fitToGeometry(r.geometry, !framed);
    framed = true;
    cyclotronView.build(r.geometry, CONFIG.bSign, Boolean(el));
    particleView.setVisualSize(r.geometry.dee_radius_m * view.scale);
    ingest(r.block);
    noteState(r.state);
    messages.warnings = r.warnings;
    setStatus("Listo");
  } catch (e) {
    simId = null;
    messages.error = e.message;
    setStatus("Error");
  }
  renderMessages();
  refreshUi();
}

async function resetSimulation() {
  if (!simId) return newSimulation();
  generation++;
  await pending?.catch(() => {});      // evita que un /step en vuelo desalinee el reinicio
  const warnings = messages.warnings;
  resetPlayback();
  messages.warnings = warnings;
  try {
    const r = await api.reset(simId);
    ingest(r.block);
    noteState(r.state);
    setStatus("Listo");
  } catch (e) {
    messages.error = e.message;
    setStatus("Error");
  }
  renderMessages();
  refreshUi();
}

async function fetchBlock() {
  const gen = generation;
  fetching = true;
  try {
    const r = await api.step(simId, CONFIG.blockSteps);
    if (gen !== generation) return;
    ingest(r.block);
    noteState(r.state);
    renderMessages();
  } catch (e) {
    if (gen === generation) {
      finished = true;
      messages.error = e.message;
      setStatus("Error");
      renderMessages();
    }
  } finally {
    fetching = false;
  }
}

function maybePrefetch() {
  if (!simId || fetching || finished) return;
  if (lastIndex() - playIndex < CONFIG.prefetchSteps) pending = fetchBlock();
}

// ---------------- Visualización de una muestra ----------------
function showSample(i) {
  if (i < 0 || i > lastIndex()) return;
  const sample = Object.fromEntries(COLUMNS.map((k) => [k, buf[k][i]]));
  particleView.setSample(sample.position, sample.velocity);
  if (meta.e0 > 0) cyclotronView.updateElectricField(sample.rf_signal_vm / meta.e0);
  trajectory.setVisibleCount(i + 1);
  updateHud(sample, { ...meta, shown: i, computed: lastIndex() });
}

function checkEnd() {
  if (endShown || !finished || playIndex < lastIndex() || !finalState) return;
  endShown = true;
  playing = false;
  setStatus(END_LABEL[finalState.status] ?? "Finalizada");
  if (finalState.stop_reason) messages.info = finalState.stop_reason;
  renderMessages();
  refreshUi();
}

// ---------------- Bucle de animación (independiente de los FPS) ----------------
function frame(now) {
  requestAnimationFrame(frame);
  const dtReal = lastTime === null ? 0 : Math.min((now - lastTime) / 1000, 0.1);
  lastTime = now;

  if (playing && lastIndex() >= 0) {
    playIndex = Math.min(playIndex + CONFIG.playbackStepsPerSecond * dtReal, lastIndex());
  }
  checkEnd();
  maybePrefetch();
  showSample(Math.floor(playIndex));
  ctx.controls.update();
  ctx.render();
}

// ---------------- Controles ----------------
bindControls({
  onStart: () => { if (!simId) return; playing = true; started = true; setStatus("Reproduciendo"); refreshUi(); },
  onPause: () => { playing = false; setStatus("En pausa"); refreshUi(); },
  onStep: () => {
    if (!simId) return;
    started = true;
    playIndex = Math.min(Math.floor(playIndex) + 1, lastIndex());
    setStatus("Paso a paso");
    refreshUi();
  },
  onReset: resetSimulation,
  onToggleTrajectory: (on) => trajectory.setVisible(on),
  onToggleAxes: (on) => { ctx.axes.visible = on; },
  onToggleArrow: (on) => particleView.setArrowVisible(on),
  onToggleFields: (on) => cyclotronView.setFieldVectorsVisible(on),
  onChamberOpacity: (a) => cyclotronView.setChamberOpacity(a),
  onDeeOpacity: (a) => cyclotronView.setDeeOpacity(a),
  onRate: (v) => { CONFIG.playbackStepsPerSecond = v; },
  onBSign: (s) => { CONFIG.bSign = s; newSimulation(); },
  onRfChange: () => newSimulation(),
});

newSimulation();
requestAnimationFrame(frame);
// Manejo del DOM: no contiene física ni lógica de simulación.
const $ = (id) => document.getElementById(id);
const sci = (x, d = 4) => x.toExponential(d);
const EV_PER_J = 1 / 1.602176634e-19;

export function bindControls(h) {
  $("btn-start").onclick = h.onStart;
  $("btn-pause").onclick = h.onPause;
  $("btn-step").onclick = h.onStep;
  $("btn-reset").onclick = h.onReset;
  $("chk-traj").onchange = (e) => h.onToggleTrajectory(e.target.checked);
  $("chk-axes").onchange = (e) => h.onToggleAxes(e.target.checked);
  $("chk-arrow").onchange = (e) => h.onToggleArrow(e.target.checked);
  $("chk-fields").onchange = (e) => h.onToggleFields(e.target.checked);
  $("rng-chamber").oninput = (e) => h.onChamberOpacity(Number(e.target.value));
  $("rng-dees").oninput = (e) => h.onDeeOpacity(Number(e.target.value));
  $("rng-rate").oninput = (e) => {
    $("rate-out").textContent = e.target.value;
    h.onRate(Number(e.target.value));
  };
  $("sel-bsign").onchange = (e) => h.onBSign(Number(e.target.value));
  // Los parámetros de RF cambian la física: al confirmarlos se recalcula desde t = 0.
  for (const id of ["inp-voltage", "inp-ratio", "inp-phase"]) $(id).onchange = h.onRfChange;
}

/** Lee los parámetros de RF del panel (única fuente de sus valores por defecto: el HTML). */
export function readRf() {
  const voltageKv = parseFloat($("inp-voltage").value);
  const ratio = parseFloat($("inp-ratio").value);
  const phaseDeg = parseFloat($("inp-phase").value);
  if (![voltageKv, ratio, phaseDeg].every(Number.isFinite)) {
    throw new Error("Los parámetros de radiofrecuencia deben ser números.");
  }
  return { voltageV: voltageKv * 1000, ratio, phaseDeg };
}

export function setStatus(text) {
  $("status-chip").textContent = text;
}

export function setPlayingUi({ playing, started, canStart }) {
  $("btn-start").textContent = started ? "Continuar" : "Iniciar";
  $("btn-start").disabled = playing || !canStart;
  $("btn-pause").disabled = !playing;
  $("btn-step").disabled = playing || !canStart;
}

/** items = [{ kind: "warn" | "error" | "info", text }] */
export function showMessages(items) {
  const box = $("messages");
  box.replaceChildren();
  for (const { kind, text } of items) {
    const div = document.createElement("div");
    div.className = `msg ${kind}`;
    div.textContent = text;       // textContent: nunca se interpreta como HTML
    box.appendChild(div);
  }
}

/** s = muestra del backend; meta = datos derivados y contadores. */
export function updateHud(s, meta) {
  const [x, y, z] = s.position;
  const [vx, vy, vz] = s.velocity;
  $("hud-t").textContent = `${sci(s.t)} s`;
  $("hud-pos").textContent = `X = ${sci(x, 3)}\nY = ${sci(y, 3)}\nZ = ${sci(z, 3)}`;
  $("hud-vel").textContent = `Vx = ${sci(vx, 3)}\nVy = ${sci(vy, 3)}\nVz = ${sci(vz, 3)}`;
  $("hud-speed").textContent = `${sci(s.speed)} m/s`;
  $("hud-force").textContent = `${sci(s.lorentz_force_n)} N`;
  $("hud-ke").textContent = `${sci(s.kinetic_energy_j)} J\n(${(s.kinetic_energy_j * EV_PER_J / 1e3).toFixed(3)} keV)`;
  $("hud-work").textContent = `${sci(s.electric_work_j)} J\n(${(s.electric_work_j * EV_PER_J / 1e3).toFixed(3)} keV)`;
  $("hud-b").textContent = `${sci(Math.hypot(...s.b_field), 3)} T`;
  $("hud-e").textContent = `${sci(Math.hypot(...s.e_field), 3)} V/m`;
  $("hud-rf").textContent = `${sci(s.rf_signal_vm, 3)} V/m`;
  $("hud-region").textContent = s.in_gap ? "Hueco (actúan E y B)" : "Dee (solo B)";
  $("hud-fc").textContent = `${(meta.fc / 1e6).toFixed(3)} MHz`;
  $("hud-frf").textContent = meta.frf > 0 ? `${(meta.frf / 1e6).toFixed(3)} MHz` : "–";
  $("hud-steps").textContent = `${meta.shown} / ${meta.computed}`;
}
// Gráficas científicas con Chart.js.
// Etapa 4: Gráfica 5 - Campo eléctrico y fase.
// Etapas 6+: Gráficas 1-4 (posición, velocidad, energía, trayectoria XY).

import { Chart, registerables } from "https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.esm.min.js";

Chart.register(...registerables);

const COLORS = {
  particle: "#4cc9ff",
  trajectory: "#ffb703",
  electric: "#ff5c5c",
  phase: "#4cf08a",
};

export class Charts {
  constructor() {
    this.chartEF = null; // Gráfica 5: Campo eléctrico vs tiempo
    this._rfPoints = []; // puntos (t, E) del campo RF
    this._crossPoints = []; // puntos (t, E) en cruces por el gap
  }

  // ---------- Gráfica 5: Campo eléctrico y fase ----------
  initEFChart(canvasId) {
    const ctx = document.getElementById(canvasId).getContext("2d");
    this.chartEF = new Chart(ctx, {
      type: "line",
      data: {
        datasets: [
          {
            label: "E(t) = E0·sin(2πft + φ) [V/m]",
            data: this._rfPoints,
            borderColor: COLORS.electric,
            backgroundColor: COLORS.electric + "33",
            fill: false,
            tension: 0.2,
            pointRadius: 0,
          },
          {
            label: "Cruces por el gap",
            data: this._crossPoints,
            borderColor: COLORS.phase,
            backgroundColor: COLORS.phase,
            showLine: false,
            pointRadius: 4,
            pointStyle: "cross",
          },
        ],
      },
      options: {
        responsive: true,
        animation: false,
        scales: {
          x: { type: "linear", title: { display: true, text: "Tiempo [s]" } },
          y: { title: { display: true, text: "Campo eléctrico [V/m]" } },
        },
        plugins: {
          title: { display: true, text: "Campo eléctrico RF y cruces por la separación central" },
          legend: { display: true },
        },
      },
    });
  }

  // Actualiza la gráfica 5 con los datos del bloque recibido
  updateEFChart(times, eFields, crossTimes, crossE) {
    if (!this.chartEF) return;

    // Serie completa del campo RF (muestras del backend)
    this._rfPoints = times.map((t, i) => ({ x: t, y: eFields[i] }));

    // Serie de cruces (cuando la partícula pasa por x ≈ 0)
    this._crossPoints = crossTimes.map((t, i) => ({ x: t, y: crossE[i] }));

    this.chartEF.update();
  }

  // Placeholder para gráficas 1-4 (Etapa 6)
  initPositionChart() {}
  initVelocityChart() {}
  initEnergyChart() {}
  initTrajectoryChart() {}
}
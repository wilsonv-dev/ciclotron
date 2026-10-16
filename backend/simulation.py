"""Estado de la simulación, avance por bloques y validación numérica."""
import math
import numpy as np

from fields import (RadioFrequencyGapField, UniformMagneticField, ZeroElectricField,
                    cyclotron_angular_frequency, cyclotron_frequency_hz, larmor_radius)
from integrator import boris_push
from models import MAX_BLOCK_STEPS, SimulationConfig
from particles import SPEED_OF_LIGHT, Particle, get_particle

THETA_WARN = 0.1        # rad/paso: por encima, precisión reducida (~63 pasos/órbita)
THETA_ERROR = 1.0       # rad/paso: por encima, configuración rechazada
V_FRAC_WARN = 0.1       # v/c: por encima, el modelo clásico deja de ser adecuado
GAP_STEPS_WARN = 10.0   # pasos para cruzar el hueco: por debajo, error de discretización notable
GAP_STEPS_ERROR = 1.0   # por debajo, la partícula puede "saltarse" el hueco sin sentir E
DETUNING_WARN = 0.01    # |f_RF/fc − 1| a partir del cual se avisa de falta de sincronización
TERMINAL = {"finished", "extracted", "lost", "error"}


class SimulationConfigError(ValueError):
    def __init__(self, messages: list[str]):
        super().__init__("; ".join(messages))
        self.messages = messages


def build_particle(spec) -> Particle:
    return get_particle(spec.type, spec.mass_kg, spec.charge_c)


def derived_quantities(p: Particle, bz: float, v_perp: float | None = None) -> dict:
    gyrates = bz != 0 and p.charge != 0
    wc = cyclotron_angular_frequency(p.charge, p.mass, bz)
    return {
        "model": "clásico no relativista",
        "cyclotron_angular_frequency_rad_s": wc,
        "cyclotron_frequency_hz": cyclotron_frequency_hz(p.charge, p.mass, bz),
        "cyclotron_period_s": 2 * math.pi / wc if gyrates else None,
        "larmor_radius_m": (larmor_radius(p.mass, v_perp, p.charge, bz)
                            if gyrates and v_perp is not None else None),
    }


def _analyze_electric(cfg: SimulationConfig, p: Particle, derived: dict,
                      errors: list, warnings: list) -> dict | None:
    """Valida el campo RF y calcula sus magnitudes derivadas."""
    el, geo = cfg.electric, cfg.geometry
    fc = derived["cyclotron_frequency_hz"]
    if el.use_cyclotron_frequency:
        if fc <= 0:
            errors.append("No existe frecuencia ciclotrónica (B = 0 o q = 0): desactive "
                          "use_cyclotron_frequency e indique frequency_hz.")
            return None
        f_rf = fc
    else:
        f_rf = el.frequency_hz

    e0 = el.voltage_v / geo.gap_m                       # E0 = V/g
    detuning = (f_rf / fc - 1.0) if fc > 0 else None
    info = {
        "voltage_v": el.voltage_v, "gap_m": geo.gap_m, "e0_v_per_m": e0,
        "rf_frequency_hz": f_rf, "rf_period_s": 1.0 / f_rf, "phase_deg": el.phase_deg,
        "detuning": detuning, "synchronized": detuning is not None and abs(detuning) <= DETUNING_WARN,
        "v_max_ms": None, "k_max_j": None, "v_max_over_c": None, "gap_transit_steps": None,
    }
    if detuning is not None and abs(detuning) > DETUNING_WARN:
        warnings.append(f"f_RF difiere de fc en {detuning:+.1%}: sin sincronización no se espera "
                        "aceleración eficiente (la partícula perderá la fase con el campo).")

    theta_rf = 2 * math.pi * f_rf * cfg.dt_s
    if theta_rf > THETA_ERROR:
        errors.append(f"Paso temporal demasiado grande para la RF: 2π·f_RF·Δt = {theta_rf:.2f} rad.")
    elif theta_rf > THETA_WARN:
        warnings.append(f"2π·f_RF·Δt = {theta_rf:.3f} rad: la señal RF se muestrea con pocos pasos.")

    if fc > 0:   # velocidad al llegar al radio R: v = |q|B R / m
        v_max = abs(p.charge) * abs(cfg.b_z_t) * geo.dee_radius_m / p.mass
        info.update(v_max_ms=v_max, k_max_j=0.5 * p.mass * v_max ** 2,
                    v_max_over_c=v_max / SPEED_OF_LIGHT)
        if v_max / SPEED_OF_LIGHT > V_FRAC_WARN:
            warnings.append(f"Alcanzar R exige v ≈ {v_max / SPEED_OF_LIGHT:.2f}c: el modelo clásico "
                            "dejará de ser válido (efectos relativistas) antes de llegar al borde.")
        v_ref = min(v_max, V_FRAC_WARN * SPEED_OF_LIGHT)
        steps = geo.gap_m / (v_ref * cfg.dt_s)
        info["gap_transit_steps"] = steps
        if steps < GAP_STEPS_ERROR:
            errors.append(f"Con Δt = {cfg.dt_s:.3e} s la partícula avanza más que la separación "
                          f"({geo.gap_m} m) en un paso a v = {v_ref:.2e} m/s: podría saltarse el campo "
                          "eléctrico. Reduzca Δt o aumente la separación.")
        elif steps < GAP_STEPS_WARN:
            warnings.append(f"Cruzar la separación a v = {v_ref:.1e} m/s toma solo {steps:.1f} pasos: "
                            f"la ganancia de energía por cruce tendrá un error de discretización "
                            f"≈ {1 / steps:.0%}. Reduzca Δt para mayor precisión.")
    return info


def analyze_config(cfg: SimulationConfig) -> dict:
    """Valida la configuración física/numérica. Devuelve errores, avisos y derivadas."""
    p = build_particle(cfg.particle)
    v = np.array(cfg.velocity_ms)
    speed = float(np.linalg.norm(v))
    v_perp = float(math.hypot(v[0], v[1]))   # perpendicular a B (B ∥ z)
    errors, warnings = [], []

    derived = derived_quantities(p, cfg.b_z_t, v_perp)
    derived["speed_over_c"] = speed / SPEED_OF_LIGHT

    if speed >= SPEED_OF_LIGHT:
        errors.append("La rapidez inicial es ≥ c: inválida incluso como aproximación.")
    elif speed / SPEED_OF_LIGHT > V_FRAC_WARN:
        warnings.append(f"v = {speed / SPEED_OF_LIGHT:.2f}c: el modelo clásico no relativista "
                        "deja de ser adecuado (la masa efectiva crece).")

    if derived["cyclotron_period_s"] is not None:
        wc = derived["cyclotron_angular_frequency_rad_s"]
        theta = wc * cfg.dt_s
        derived["steps_per_orbit"] = derived["cyclotron_period_s"] / cfg.dt_s
        if theta > THETA_ERROR:
            errors.append(f"Paso temporal demasiado grande: ωc·Δt = {theta:.2f} rad "
                          f"(máximo {THETA_ERROR}). Use Δt ≤ Tc/100 = "
                          f"{derived['cyclotron_period_s'] / 100:.3e} s.")
        elif theta > THETA_WARN:
            warnings.append(f"ωc·Δt = {theta:.3f} rad: pocos pasos por órbita "
                            f"({derived['steps_per_orbit']:.0f}); el radio tendrá un error "
                            f"de segundo orden ≈ {theta ** 2 / 8:.1%}.")

    derived["electric"] = (_analyze_electric(cfg, p, derived, errors, warnings)
                           if cfg.electric is not None else None)
    return {"errors": errors, "warnings": warnings, "derived": derived}


class Simulation:
    def __init__(self, cfg: SimulationConfig):
        report = analyze_config(cfg)
        if report["errors"]:
            raise SimulationConfigError(report["errors"])
        self.cfg = cfg
        self.particle = build_particle(cfg.particle)
        self.warnings = report["warnings"]
        self.derived = report["derived"]
        self.dt = cfg.dt_s
        self.geometry = cfg.geometry
        self.B_field = UniformMagneticField(cfg.b_z_t)
        if cfg.electric is not None:
            el = self.derived["electric"]
            self.E_field = RadioFrequencyGapField(
                cfg.electric.voltage_v, cfg.geometry.gap_m, el["rf_frequency_hz"],
                math.radians(cfg.electric.phase_deg), cfg.geometry.dee_radius_m,
                cfg.geometry.height_m / 2.0)
        else:
            self.E_field = ZeroElectricField()
        self.reset()

    # ---------- ciclo de vida ----------
    def reset(self):
        q, m = self.particle.charge, self.particle.mass
        self.step = 0
        self.t = 0.0
        self.work_e = 0.0                    # trabajo acumulado del campo eléctrico [J]
        self.stop_reason = None
        self.runtime_warnings = []
        self._warned_relativistic = False
        self.status = "ready"
        self.x = np.array(self.cfg.position_m, dtype=float)
        v0 = np.array(self.cfg.velocity_ms, dtype=float)
        E0 = self.E_field.at(self.x, 0.0)
        B0 = self.B_field.at(self.x, 0.0)
        # Boris necesita v(-1/2): se retrocede medio paso desde la v(0) dada.
        self.v_half = boris_push(v0, E0, B0, q, m, -self.dt / 2.0)
        self._h = {k: [] for k in ("step", "t", "position", "velocity", "speed",
                                   "kinetic_energy_j", "lorentz_force_n", "e_field", "b_field",
                                   "electric_work_j", "rf_signal_vm", "in_gap")}
        self._record()

    def _record(self):
        """Guarda la muestra en el instante t_n con velocidad sincronizada v(n)."""
        q, m = self.particle.charge, self.particle.mass
        E = self.E_field.at(self.x, self.t)
        B = self.B_field.at(self.x, self.t)
        v = boris_push(self.v_half, E, B, q, m, self.dt / 2.0)   # v(n-½) -> v(n)
        F = q * (E + np.cross(v, B))                              # F = q(E + v×B)
        speed = float(np.linalg.norm(v))
        h = self._h
        h["step"].append(self.step)
        h["t"].append(self.t)
        h["position"].append(self.x.tolist())
        h["velocity"].append(v.tolist())
        h["speed"].append(speed)
        h["kinetic_energy_j"].append(0.5 * m * float(np.dot(v, v)))   # K = ½m|v|²
        h["lorentz_force_n"].append(float(np.linalg.norm(F)))
        h["e_field"].append(E.tolist())
        h["b_field"].append(B.tolist())
        h["electric_work_j"].append(self.work_e)
        h["rf_signal_vm"].append(self.E_field.signal(self.t))
        h["in_gap"].append(bool(self.E_field.in_region(self.x)))
        # Límites del modelo clásico
        if speed >= SPEED_OF_LIGHT:
            self.status = "error"
            self.stop_reason = "La rapidez alcanzó c: el modelo clásico no relativista es inválido."
        elif speed / SPEED_OF_LIGHT > V_FRAC_WARN and not self._warned_relativistic:
            self._warned_relativistic = True
            self.runtime_warnings.append(
                f"v = {speed / SPEED_OF_LIGHT:.2f}c en t = {self.t:.3e} s: el modelo clásico "
                "ya no es adecuado (efectos relativistas ignorados).")

    # ---------- avance ----------
    def advance(self, n_steps: int) -> dict:
        """Calcula hasta n_steps pasos y devuelve solo las muestras nuevas."""
        if not isinstance(n_steps, int) or n_steps < 1:
            raise ValueError("n_steps debe ser un entero ≥ 1.")
        if n_steps > MAX_BLOCK_STEPS:
            raise ValueError(f"n_steps no puede superar {MAX_BLOCK_STEPS} por petición.")
        start = len(self._h["step"])
        if self.status in TERMINAL:
            return self.columns(start)
        q, m = self.particle.charge, self.particle.mass
        n = min(n_steps, self.cfg.max_steps - self.step)
        for _ in range(n):
            E = self.E_field.at(self.x, self.t)
            B = self.B_field.at(self.x, self.t)
            v_old = self.v_half
            self.v_half = boris_push(v_old, E, B, q, m, self.dt)   # v(n-½) -> v(n+½)
            # Trabajo del campo E en este paso: q E·(v(n-½)+v(n+½))/2 · Δt  (identidad exacta de Boris)
            self.work_e += q * float(np.dot(E, v_old + self.v_half)) * self.dt / 2.0
            self.x = self.x + self.v_half * self.dt                # x(n+1) = xₙ + v(n+½)Δt
            self.step += 1
            self.t = self.step * self.dt        # evita acumular error de suma
            if not np.all(np.isfinite(self.x)):
                self.status = "error"
                self.stop_reason = "El cálculo produjo valores no finitos."
                break
            self._record()
            if self.status == "error":
                break
            if self.geometry is not None:
                if abs(self.x[2]) > self.geometry.height_m / 2.0:
                    self.status = "lost"
                    self.stop_reason = "La partícula alcanzó la pared de la cámara (|z| > H/2)."
                    break
                if self.geometry.stop_at_wall and math.hypot(self.x[0], self.x[1]) >= self.geometry.dee_radius_m:
                    self._stop_at_radius()
                    break
        if self.status not in TERMINAL:
            self.status = "finished" if self.step >= self.cfg.max_steps else "ready"
        return self.columns(start)

    def _stop_at_radius(self):
        """La partícula llegó a r = R. Se distingue extracción de colisión por su energía:
        si K ≥ 50 % de K_R = (|q|BR)²/(2m) su radio de giro es ≈ R (haz en el borde);
        si no, la órbita se desplazó y la partícula choca con la pared a baja energía."""
        k = self._h["kinetic_energy_j"][-1]
        q, m, bz = self.particle.charge, self.particle.mass, self.cfg.b_z_t
        k_ref = (q * bz * self.geometry.dee_radius_m) ** 2 / (2 * m) if q * bz != 0 else None
        if k_ref is None or k / k_ref >= 0.5:
            self.status = "extracted"
            pct = f" ({k / k_ref:.0%} de la energía máxima teórica)" if k_ref else ""
            self.stop_reason = (f"La partícula alcanzó el radio de los dees con K = {k:.3e} J{pct}. "
                                "Extracción ideal: no se modela el deflector.")
        else:
            self.status = "lost"
            self.stop_reason = (f"La partícula chocó con la pared (r = R) con solo {k / k_ref:.0%} de "
                                "la energía de extracción: su órbita quedó desplazada.")

    # ---------- consulta ----------
    def columns(self, start: int = 0, stop: int | None = None) -> dict:
        return {k: v[start:stop] for k, v in self._h.items()}

    def state(self) -> dict:
        last = {k: v[-1] for k, v in self._h.items()}
        last.update(status=self.status, steps_computed=self.step,
                    max_steps=self.cfg.max_steps, stop_reason=self.stop_reason,
                    runtime_warnings=list(self.runtime_warnings))
        return last
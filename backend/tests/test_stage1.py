"""Etapas 3-4: geometría, campo eléctrico alterno en el hueco y aceleración."""
import math
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from fields import RadioFrequencyGapField, UniformMagneticField, cyclotron_angular_frequency
from integrator import boris_push
from main import app
from models import ElectricSpec, GeometrySpec, ParticleSpec, SimulationConfig
from particles import ELEMENTARY_CHARGE, PROTON_MASS, get_particle
from simulation import Simulation, SimulationConfigError

R, G, H = 0.05, 0.005, 0.02
WC = ELEMENTARY_CHARGE / PROTON_MASS                 # ωc del protón en 1 T
FC = WC / (2 * math.pi)
TC = 1 / FC
K_R = (ELEMENTARY_CHARGE * 1.0 * R) ** 2 / (2 * PROTON_MASS)   # energía con radio de giro R


def rf_cfg(ratio=1.0, phase=90.0, volts=1e4, spo=1000, orbits=40, velocity=(0, 0, 0), **geo):
    electric = (ElectricSpec(voltage_v=volts, phase_deg=phase) if ratio == 1.0 else
                ElectricSpec(voltage_v=volts, phase_deg=phase,
                             use_cyclotron_frequency=False, frequency_hz=ratio * FC))
    return SimulationConfig(
        particle=ParticleSpec(type="proton"), velocity_ms=list(velocity), b_z_t=1.0,
        dt_s=TC / spo, max_steps=spo * orbits,
        geometry=GeometrySpec(dee_radius_m=R, gap_m=G, height_m=H, **geo), electric=electric)


def run_until_stop(cfg):
    sim = Simulation(cfg)
    while sim.status == "ready":
        sim.advance(5000)
    return sim, {k: np.array(v) for k, v in sim.columns().items()}


# ---------- campo confinado al hueco ----------
def test_field_is_confined_to_gap():
    f = RadioFrequencyGapField(1e4, G, FC, math.pi / 2, R, H / 2)
    assert f.e0 == pytest.approx(1e4 / G)
    inside = f.at(np.array([0.0, 0.01, 0.0]), 0.0)
    assert inside[0] == pytest.approx(f.e0) and inside[1] == 0 and inside[2] == 0   # E(0) = E0 sin(90°)
    assert np.all(f.at(np.array([0.01, 0.0, 0.0]), 0.0) == 0)      # dentro de un dee
    assert np.all(f.at(np.array([-0.01, 0.0, 0.0]), 0.0) == 0)     # dentro del otro dee
    assert np.all(f.at(np.array([0.0, 0.06, 0.0]), 0.0) == 0)      # fuera del radio R
    assert np.all(f.at(np.array([0.0, 0.0, 0.02]), 0.0) == 0)      # fuera de la altura


def test_field_waveform():
    f = RadioFrequencyGapField(1e4, G, FC, 0.0, R, H / 2)
    p = np.zeros(3)
    assert f.at(p, 0.0)[0] == pytest.approx(0.0, abs=1e-6)
    assert f.at(p, TC / 4)[0] == pytest.approx(f.e0)
    assert f.at(p, TC / 2)[0] == pytest.approx(0.0, abs=1e-3 * f.e0)
    assert f.at(p, 3 * TC / 4)[0] == pytest.approx(-f.e0)


# ---------- trabajo del campo eléctrico (punto 7 de la validación) ----------
def test_boris_work_energy_identity_is_exact():
    """ΔK(v de medio paso) = Σ q E·(v_old+v_new)/2·Δt, con campos E y B arbitrarios."""
    p = get_particle("proton")
    rng = np.random.default_rng(1)
    E, B = rng.normal(size=3) * 1e5, rng.normal(size=3)
    dt = 1e-10
    v = rng.normal(size=3) * 1e5
    k0, work = 0.5 * p.mass * v @ v, 0.0
    for _ in range(500):
        v_new = boris_push(v, E, B, p.charge, p.mass, dt)
        work += p.charge * float(E @ (v + v_new)) * dt / 2
        v = v_new
    assert 0.5 * p.mass * v @ v - k0 == pytest.approx(work, rel=1e-9)


def test_simulation_energy_matches_electric_work():
    sim, h = run_until_stop(rf_cfg())
    K, W = h["kinetic_energy_j"], h["electric_work_j"]
    bound = ELEMENTARY_CHARGE * sim.E_field.e0 * h["speed"].max() * sim.dt   # error de extremos del paso
    assert np.max(np.abs(K - K[0] - W)) <= 1.5 * bound
    assert W[-1] == pytest.approx(K[-1] - K[0], rel=0.02)


def test_energy_constant_when_outside_gap():
    """Fuera del hueco solo actúa B: la energía no cambia entre muestras consecutivas."""
    _, h = run_until_stop(rf_cfg(spo=500))
    K, g = h["kinetic_energy_j"], h["in_gap"]
    free = ~g[:-1] & ~g[1:]
    assert free.sum() > 1000
    assert np.max(np.abs(np.diff(K)[free])) / K.max() < 1e-9


# ---------- sincronización ----------
def test_synchronized_particle_reaches_extraction():
    sim, h = run_until_stop(rf_cfg())
    assert sim.status == "extracted"
    assert 0.6 < h["kinetic_energy_j"][-1] / K_R < 1.05
    assert np.hypot(*h["position"][-1][:2]) >= R
    assert sim.step < 8000          # ~5 vueltas: la ganancia es sistemática


def test_unsynchronized_particle_does_not_gain_energy():
    sim, h = run_until_stop(rf_cfg(ratio=0.8, spo=500, orbits=30))
    assert h["kinetic_energy_j"].max() < 0.3 * K_R
    assert sim.status in ("lost", "finished")


def test_phase_changes_energy_gain():
    """Con f = fc, la fase φ cambia la energía tras 2 vueltas: φ = 90° gana ≈ 1.75 veces más que φ = 0°.
    Además, invertir el signo del campo (φ → φ + 180°) solo refleja el movimiento: misma energía."""
    def k_after(phase):
        sim = Simulation(rf_cfg(phase=phase, orbits=2))
        sim.advance(2000)
        return sim.columns()["kinetic_energy_j"][-1]
    k0, k90 = k_after(0.0), k_after(90.0)
    assert k90 > 1.5 * k0
    assert k_after(-90.0) == pytest.approx(k90, rel=1e-6)
    assert k_after(180.0) == pytest.approx(k0, rel=1e-6)


def test_zero_voltage_means_no_acceleration():
    sim = Simulation(rf_cfg(volts=0.0, velocity=(2e6, 0, 0), orbits=3))
    sim.advance(3000)
    K = np.array(sim.columns()["kinetic_energy_j"])
    assert np.max(np.abs(K - K[0])) / K[0] < 1e-9


# ---------- límites geométricos ----------
def test_particle_leaving_chamber_height_is_lost():
    sim, _ = run_until_stop(rf_cfg(velocity=(1e6, 0, 1e6), volts=0.0))
    assert sim.status == "lost" and "pared" in sim.stop_reason


def test_stop_at_wall_can_be_disabled():
    sim = Simulation(rf_cfg(stop_at_wall=False, orbits=12))
    sim.advance(5000); sim.advance(5000)
    assert sim.status != "extracted" and sim.step > 5400


# ---------- validación ----------
def test_electric_requires_geometry():
    with pytest.raises(ValidationError, match="geometría"):
        SimulationConfig(particle=ParticleSpec(type="proton"), velocity_ms=[0, 0, 0], b_z_t=1.0,
                         dt_s=1e-10, electric=ElectricSpec())


def test_frequency_options_are_exclusive():
    with pytest.raises(ValidationError):
        ElectricSpec(use_cyclotron_frequency=True, frequency_hz=1e7)
    with pytest.raises(ValidationError):
        ElectricSpec(use_cyclotron_frequency=False)
    with pytest.raises(ValidationError):
        ElectricSpec(voltage_v=-5.0)


def test_gap_must_be_smaller_than_radius():
    with pytest.raises(ValidationError):
        GeometrySpec(dee_radius_m=0.01, gap_m=0.02)


def test_sync_frequency_needs_magnetic_field():
    cfg = rf_cfg()
    cfg.b_z_t = 0.0
    with pytest.raises(SimulationConfigError, match="frecuencia ciclotrónica"):
        Simulation(cfg)


def test_timestep_too_coarse_for_the_gap_is_rejected():
    with pytest.raises(SimulationConfigError, match="saltarse"):
        Simulation(rf_cfg(spo=50))


def test_detuned_rf_gives_warning():
    sim = Simulation(rf_cfg(ratio=0.8))
    assert any("sincronización" in w for w in sim.warnings)
    assert not Simulation(rf_cfg()).derived["electric"]["detuning"]


def test_relativistic_warning_at_runtime():
    cfg = rf_cfg(velocity=(4e7, 0, 0), volts=0.0)    # 0.13c
    sim = Simulation(cfg)
    sim.advance(10)
    assert any("clásico" in w for w in sim.state()["runtime_warnings"])


# ---------- API ----------
client = TestClient(app)


def api_body():
    return {"particle": {"type": "proton"}, "velocity_ms": [0, 0, 0], "b_z_t": 1.0,
            "dt_s": TC / 1000, "max_steps": 20000,
            "geometry": {"dee_radius_m": R, "gap_m": G, "height_m": H},
            "electric": {"voltage_v": 1e4, "use_cyclotron_frequency": True, "phase_deg": 90}}


def test_api_returns_geometry_and_electric_derivatives():
    r = client.post("/api/simulations", json=api_body())
    assert r.status_code == 200
    d = r.json()
    assert d["geometry"]["gap_m"] == G
    assert d["derived"]["electric"]["rf_frequency_hz"] == pytest.approx(FC)
    assert d["derived"]["electric"]["e0_v_per_m"] == pytest.approx(1e4 / G)
    sid = d["simulation_id"]
    s = client.post(f"/api/simulations/{sid}/step", json={"n_steps": 500}).json()
    assert {"rf_signal_vm", "electric_work_j", "in_gap"} <= set(s["block"])
    assert len(s["block"]["t"]) == 500


def test_api_rejects_invalid_electric():
    body = api_body()
    body["electric"]["voltage_v"] = -1
    r = client.post("/api/simulations", json=body)
    assert r.status_code == 422 and "voltage_v" in r.text
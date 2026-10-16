"""API FastAPI. No contiene física: solo valida, delega y serializa."""
from collections import OrderedDict
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from models import DerivedRequest, SimulationConfig, StepRequest
from particles import PRESETS, ELEMENTARY_CHARGE, PROTON_MASS, ELECTRON_MASS, SPEED_OF_LIGHT
from simulation import (Simulation, SimulationConfigError, analyze_config,
                        build_particle, derived_quantities)

MAX_SIMULATIONS = 16
sims: "OrderedDict[str, Simulation]" = OrderedDict()

app = FastAPI(title="Simulador de ciclotrón", version="0.4.0-etapa4")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    detail = [{"campo": ".".join(str(p) for p in e["loc"][1:]), "mensaje": e["msg"]}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(SimulationConfigError)
async def config_handler(request: Request, exc: SimulationConfigError):
    return JSONResponse(status_code=422, content={"detail": [{"mensaje": m} for m in exc.messages]})


def _get(sim_id: str) -> Simulation:
    if sim_id not in sims:
        raise HTTPException(404, "Simulación no encontrada.")
    return sims[sim_id]


@app.get("/api/particles")
def list_particles():
    return {"particles": [{"id": k, "name": p.name, "mass_kg": p.mass, "charge_c": p.charge}
                          for k, p in PRESETS.items()],
            "constants": {"elementary_charge_c": ELEMENTARY_CHARGE,
                          "proton_mass_kg": PROTON_MASS,
                          "electron_mass_kg": ELECTRON_MASS,
                          "speed_of_light_m_s": SPEED_OF_LIGHT}}


@app.post("/api/derived")
def derived(req: DerivedRequest):
    return derived_quantities(build_particle(req.particle), req.b_z_t)


@app.post("/api/validate")
def validate(cfg: SimulationConfig):
    report = analyze_config(cfg)
    return {"valid": not report["errors"], **report}


@app.post("/api/simulations")
def create(cfg: SimulationConfig):
    sim = Simulation(cfg)                  # lanza SimulationConfigError si es inválida
    sim_id = uuid4().hex
    sims[sim_id] = sim
    while len(sims) > MAX_SIMULATIONS:     # descarta las más antiguas
        sims.popitem(last=False)
    return {"simulation_id": sim_id, "warnings": sim.warnings, "derived": sim.derived,
            "geometry": cfg.geometry.model_dump() if cfg.geometry else None,
            "block": sim.columns(), "state": sim.state()}


@app.post("/api/simulations/{sim_id}/step")
def step(sim_id: str, req: StepRequest):
    sim = _get(sim_id)
    try:
        block = sim.advance(req.n_steps)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"block": block, "state": sim.state()}


@app.get("/api/simulations/{sim_id}/state")
def state(sim_id: str):
    return _get(sim_id).state()


@app.post("/api/simulations/{sim_id}/reset")
def reset(sim_id: str):
    sim = _get(sim_id)
    sim.reset()
    return {"block": sim.columns(), "state": sim.state()}


# En la Etapa 2 se servirá el frontend desde aquí (solo si la carpeta existe).
_front = Path(__file__).resolve().parent.parent / "frontend"
if _front.is_dir():
    app.mount("/", StaticFiles(directory=_front, html=True), name="frontend")
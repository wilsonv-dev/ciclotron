"""Esquemas Pydantic (entrada/salida de la API) y límites de cálculo."""
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field, model_validator

MAX_TOTAL_STEPS = 500_000   # pasos máximos por simulación
MAX_BLOCK_STEPS = 5_000     # pasos máximos por petición

Finite = Annotated[float, Field(allow_inf_nan=False)]
Vec3 = Annotated[list[Finite], Field(min_length=3, max_length=3)]


class ParticleSpec(BaseModel):
    type: Literal["proton", "electron", "custom"]
    mass_kg: Optional[Finite] = None
    charge_c: Optional[Finite] = None

    @model_validator(mode="after")
    def _check(self):
        if self.type == "custom":
            if self.mass_kg is None or self.charge_c is None:
                raise ValueError("La partícula personalizada requiere mass_kg y charge_c.")
            if self.mass_kg <= 0:
                raise ValueError("mass_kg debe ser estrictamente positiva.")
        elif self.mass_kg is not None or self.charge_c is not None:
            raise ValueError("Las partículas predefinidas no admiten mass_kg ni charge_c.")
        return self


class GeometrySpec(BaseModel):
    """Geometría del ciclotrón (SI). Es la MISMA que dibuja el frontend."""
    dee_radius_m: Finite = Field(default=0.05, gt=0)    # radio R de los dees y de la zona activa
    gap_m: Finite = Field(default=0.005, gt=0)          # separación g entre los dees
    height_m: Finite = Field(default=0.02, gt=0)        # altura H de la cámara (eje z)
    stop_at_wall: bool = True                           # detener la partícula al llegar a R (extracción ideal)

    @model_validator(mode="after")
    def _check(self):
        if self.gap_m >= self.dee_radius_m:
            raise ValueError("gap_m debe ser menor que dee_radius_m.")
        return self


class ElectricSpec(BaseModel):
    """Campo eléctrico de radiofrecuencia en la separación: E(t) = (V/g) sin(2πft + φ)."""
    voltage_v: Finite = Field(default=10_000.0, ge=0)   # amplitud V entre los dees [V]
    frequency_hz: Optional[Finite] = Field(default=None, gt=0)
    use_cyclotron_frequency: bool = True                # f = fc = |q|B/(2πm)
    phase_deg: Finite = 90.0                            # φ [grados]

    @model_validator(mode="after")
    def _check(self):
        if self.use_cyclotron_frequency and self.frequency_hz is not None:
            raise ValueError("No indique frequency_hz si use_cyclotron_frequency es verdadero.")
        if not self.use_cyclotron_frequency and self.frequency_hz is None:
            raise ValueError("Indique frequency_hz o active use_cyclotron_frequency.")
        return self


class SimulationConfig(BaseModel):
    particle: ParticleSpec
    position_m: Vec3 = [0.0, 0.0, 0.0]
    velocity_ms: Vec3
    b_z_t: Finite                       # Bz con signo [T]
    dt_s: Finite = Field(gt=0)          # paso temporal [s]
    max_steps: int = Field(default=20_000, ge=1, le=MAX_TOTAL_STEPS)
    geometry: Optional[GeometrySpec] = None   # sin geometría: espacio sin paredes (Etapa 1)
    electric: Optional[ElectricSpec] = None   # sin campo eléctrico: solo magnético (Etapa 1)

    @model_validator(mode="after")
    def _check(self):
        if self.electric is not None and self.geometry is None:
            raise ValueError("El campo eléctrico requiere definir la geometría (geometry).")
        return self


class DerivedRequest(BaseModel):
    particle: ParticleSpec
    b_z_t: Finite


class StepRequest(BaseModel):
    n_steps: int = Field(ge=1, le=MAX_BLOCK_STEPS)
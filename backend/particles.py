"""Constantes físicas (SI, CODATA 2018/2022) y partículas predefinidas."""
import math
from dataclasses import dataclass

ELEMENTARY_CHARGE = 1.602176634e-19   # C
PROTON_MASS = 1.67262192369e-27       # kg
ELECTRON_MASS = 9.1093837139e-31      # kg
SPEED_OF_LIGHT = 299_792_458.0        # m/s


@dataclass(frozen=True)
class Particle:
    name: str
    mass: float    # kg, estrictamente positiva
    charge: float  # C, con signo

    def __post_init__(self):
        if not math.isfinite(self.mass) or self.mass <= 0:
            raise ValueError("La masa debe ser finita y estrictamente positiva (kg).")
        if not math.isfinite(self.charge):
            raise ValueError("La carga debe ser un valor finito (C).")


PRESETS = {
    "proton": Particle("Protón", PROTON_MASS, +ELEMENTARY_CHARGE),
    "electron": Particle("Electrón", ELECTRON_MASS, -ELEMENTARY_CHARGE),
}


def get_particle(kind: str, mass: float | None = None, charge: float | None = None) -> Particle:
    """Devuelve una partícula predefinida o una personalizada."""
    if kind in PRESETS:
        if mass is not None or charge is not None:
            raise ValueError("Las partículas predefinidas no admiten masa ni carga personalizadas.")
        return PRESETS[kind]
    if kind == "custom":
        if mass is None or charge is None:
            raise ValueError("La partícula personalizada requiere masa (kg) y carga (C).")
        return Particle("Personalizada", float(mass), float(charge))
    raise ValueError(f"Tipo de partícula desconocido: '{kind}'.")
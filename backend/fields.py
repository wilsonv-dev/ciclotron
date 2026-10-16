"""Campos electromagnéticos y fórmulas ciclotrónicas de referencia (SI)."""
import math
import numpy as np

_ZERO3 = np.zeros(3)


class UniformMagneticField:
    """B = (0, 0, Bz), uniforme y estático. El signo de Bz fija el sentido."""

    def __init__(self, bz_tesla: float):
        self._b = np.array([0.0, 0.0, float(bz_tesla)])

    def at(self, position: np.ndarray, t: float) -> np.ndarray:
        return self._b


class ZeroElectricField:
    """E = 0 en todo el espacio (Etapa 1: solo campo magnético)."""

    def at(self, position: np.ndarray, t: float) -> np.ndarray:
        return _ZERO3

    def signal(self, t: float) -> float:
        return 0.0

    def in_region(self, position: np.ndarray) -> bool:
        return False


class RadioFrequencyGapField:
    """Campo eléctrico alterno confinado a la separación entre los dees.

        E(x, t) = E0 · sin(2π f t + φ) · x̂      si |x| ≤ g/2, x²+y² ≤ R², |z| ≤ H/2
        E(x, t) = 0                              en cualquier otro punto (dentro de los dees, fuera)

    con E0 = V/g (aproximación de placas paralelas: campo uniforme en el hueco,
    sin efectos de borde). La separación es la franja |x| ≤ g/2.
    """

    def __init__(self, voltage_v: float, gap_m: float, frequency_hz: float, phase_rad: float,
                 radius_m: float, half_height_m: float):
        self.e0 = voltage_v / gap_m                 # E0 = V/g  [V/m]
        self.omega = 2.0 * math.pi * frequency_hz   # ω = 2πf   [rad/s]
        self.phase = phase_rad
        self.half_gap = gap_m / 2.0
        self.radius_sq = radius_m ** 2
        self.half_height = half_height_m

    def signal(self, t: float) -> float:
        """Amplitud instantánea del campo RF, E0 sin(ωt+φ), con independencia de la posición."""
        return self.e0 * math.sin(self.omega * t + self.phase)

    def in_region(self, position: np.ndarray) -> bool:
        x, y, z = position[0], position[1], position[2]
        return (abs(x) <= self.half_gap and x * x + y * y <= self.radius_sq
                and abs(z) <= self.half_height)

    def at(self, position: np.ndarray, t: float) -> np.ndarray:
        if self.in_region(position):
            return np.array([self.signal(t), 0.0, 0.0])
        return _ZERO3


def cyclotron_angular_frequency(charge: float, mass: float, b_mag: float) -> float:
    """ωc = |q|B/m  [rad/s]"""
    return abs(charge) * abs(b_mag) / mass


def cyclotron_frequency_hz(charge: float, mass: float, b_mag: float) -> float:
    """fc = |q|B/(2πm)  [Hz]"""
    return cyclotron_angular_frequency(charge, mass, b_mag) / (2.0 * math.pi)


def larmor_radius(mass: float, v_perp: float, charge: float, b_mag: float) -> float:
    """r = m·v⊥/(|q|B)  [m]. Exige q ≠ 0 y B ≠ 0."""
    return mass * v_perp / (abs(charge) * abs(b_mag))
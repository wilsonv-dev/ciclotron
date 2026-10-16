"""Integrador de Boris para una partícula cargada (modelo clásico)."""
import numpy as np


def boris_push(v: np.ndarray, E: np.ndarray, B: np.ndarray,
               q: float, m: float, dt: float) -> np.ndarray:
    """Avanza la velocidad un intervalo `dt` (puede ser negativo o un medio paso).

    Entrada:  v = v(n-1/2).  Salida: v(n+1/2). No modifica los arreglos de entrada.
    Orden: medio impulso E -> rotación magnética -> medio impulso E.
    """
    h = q * dt / (2.0 * m)                 # h = qΔt/2m
    v_minus = v + h * E                    # v⁻ = v + hE
    t = h * B                              # vector de rotación
    s = 2.0 * t / (1.0 + np.dot(t, t))     # s = 2t/(1+|t|²)
    v_prime = v_minus + np.cross(v_minus, t)
    v_plus = v_minus + np.cross(v_prime, s)
    return v_plus + h * E                  # v(n+½) = v⁺ + hE
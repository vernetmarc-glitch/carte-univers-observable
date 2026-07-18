"""Moteur de densité v3.2 — advection de Zel'dovich (matrice, bloc `zeldovich`).

SOURCE UNIQUE partagée par :
  - generate_layers.py            (textures de production density_l*.png, a=1)
  - generate_spacetime_frames.py  (frames temporelles st_*, format identique)

Tous les paramètres sont lus dans spacetime_matrix.json (variante Z2 validée
par Marc le 16/07). Déterministe : mêmes graines -> mêmes sorties, partout.
"""
import json
import math
import os
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
MATRIX_PATH = os.path.join(_HERE, "..", "app", "public", "data", "spacetime_matrix.json")

with open(MATRIX_PATH) as _f:
    _MATRIX = json.load(_f)
Z = _MATRIX["zeldovich"]

_CACHE = {}


def _kgrids(n):
    if n not in _CACHE:
        ky = np.fft.fftfreq(n)[:, None]
        kx = np.fft.rfftfreq(n)[None, :]
        k2 = ky ** 2 + kx ** 2
        _CACHE[n] = (ky, kx, k2, np.sqrt(k2))
    return _CACHE[n]


def displacement(delta, world_mpc):
    """Ψ̂ = i·k·δ̂/k², bande λ ∈ [lam_min_px, filament_max_scale_mpc comobiles],
    normalisé à déplacement rms = 1 px (l'amplitude est portée par S)."""
    n = delta.shape[0]
    ky, kx, k2, k = _kgrids(n)
    D = np.fft.rfft2(delta)
    k_cut = world_mpc / (Z["filament_max_scale_mpc"] * n)
    mask = (k >= k_cut) & (k <= 1.0 / max(Z["lam_min_px"], 2.0)) & (k2 > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        base = np.where(mask, D / k2, 0)
    px = np.fft.irfft2(1j * kx * base / (2 * np.pi), s=delta.shape)
    py = np.fft.irfft2(1j * ky * base / (2 * np.pi), s=delta.shape)
    # v3.3 : AUCUNE renormalisation par layer — Ψ brut (un même mode physique
    # déplace identiquement à tous les zooms) ; l'amplitude est portée par le
    # facteur de croissance G global (calibré sur l3 = Z2 validée).
    return px, py


def _bilinear(f, y, x):
    n = f.shape[0]
    y0 = np.floor(y).astype(int) % n
    x0 = np.floor(x).astype(int) % n
    y1, x1 = (y0 + 1) % n, (x0 + 1) % n
    fy, fx = y - np.floor(y), x - np.floor(x)
    return (f[y0, x0] * (1 - fy) * (1 - fx) + f[y1, x0] * fy * (1 - fx)
            + f[y0, x1] * (1 - fy) * fx + f[y1, x1] * fy * fx)


def _blur(f, sigma_px):
    if sigma_px <= 0:
        return f
    n = f.shape[0]
    _, _, k2, _ = _kgrids(n)
    G = np.exp(-2 * (math.pi * sigma_px) ** 2 * k2)
    return np.fft.irfft2(np.fft.rfft2(f) * G, s=f.shape)


def density_from_psi(psi, s_px, out_n):
    """Dépôt CIC d'une grille de masse advectée. S=0 -> exactement uniforme."""
    if s_px <= 1e-3:
        return np.ones((out_n, out_n))
    px, py = psi
    ng = Z["mass_grid"]
    step = out_n / ng
    qy, qx = np.mgrid[0:ng, 0:ng] * step
    qy, qx = qy.ravel(), qx.ravel()
    y = qy + s_px * _bilinear(py, qy, qx)
    x = qx + s_px * _bilinear(px, qy, qx)
    rho = np.zeros((out_n, out_n))
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    fy, fx = y - y0, x - x0
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            np.add.at(rho, ((y0 + dy) % out_n, (x0 + dx) % out_n), wy * wx)
    rho /= rho.mean()
    # le flou anti-crénelage peut créer de petits négatifs -> clip (ρ^shape)
    return np.clip(_blur(rho, Z["soft_px"]), 0, None)


def density_from_delta(delta, world_mpc, s_px):
    return density_from_psi(displacement(delta, world_mpc), s_px, delta.shape[0])


TARGET_MEAN = Z["exposure"]["target_mean_255"] / 255.0


def calibrate_growth(psi_l3):
    """G global : rms du déplacement de l3 = 11 px (reproduit la Z2 validée)."""
    px, py = psi_l3
    rms = math.sqrt(px.var() + py.var())
    return 11.0 / rms


def solve_alpha(rho, target=None):
    """α résolu pour que mean(tone) = target (v3.3 : ton maintenu par frame)."""
    target = TARGET_MEAN if target is None else target
    shape = Z["exposure"]["shape"]
    vg = Z["exposure"]["void_gamma"]
    rs = rho ** shape
    lo, hi = 1e-4, 6.0
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        if np.mean((1 - np.exp(-mid * rs)) ** vg) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def tone(rho, alpha):
    return (1 - np.exp(-alpha * rho ** Z["exposure"]["shape"])) ** Z["exposure"]["void_gamma"]


def dissolved_tone(alpha=None):
    """v3.3 : l'état dissous est PAR CONSTRUCTION au ton maintenu (38/255)."""
    return TARGET_MEAN


def store_computed(growth):
    """Écrit G et le ton maintenu dans matrix.computed.zeldovich."""
    with open(MATRIX_PATH) as f:
        m = json.load(f)
    m.setdefault("computed", {})["zeldovich"] = {
        "growth_G": round(growth, 6),
        "target_mean_255": Z["exposure"]["target_mean_255"],
        "dissolved_tone_255": Z["exposure"]["target_mean_255"],
        "provenance": "G calibré par generate_layers.py (rms l3 = 11 px, Z2 validée) ; "
                      "α résolu PAR FRAME (ton maintenu, v3.3)",
    }
    with open(MATRIX_PATH, "w") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
    return m["computed"]["zeldovich"]


def load_growth():
    with open(MATRIX_PATH) as f:
        m = json.load(f)
    zc = m.get("computed", {}).get("zeldovich")
    if not zc or "growth_G" not in zc:
        raise RuntimeError("G non calibré — lancer d'abord generate_layers.py")
    return zc["growth_G"]


def export_tone_png(t, path):
    from PIL import Image
    Image.fromarray(np.clip(t * 255, 0, 255).astype(np.uint8), mode="L").save(path)

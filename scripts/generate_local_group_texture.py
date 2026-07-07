"""
Génère une texture statique pour le layer "Groupe Local" — UNIQUEMENT pour
les galaxies PROCÉDURALES (non nommées, lointaines, ~90 galaxies de champ).
Les 8 galaxies réelles nommées (Andromède, M33, Nuages de Magellan...) sont
rendues séparément comme des sprites individuels (cf.
scripts/generate_simulated_textures.mjs, RealGalaxiesLayer.tsx).

Sortie : app/public/data/density_localgroup.png
Box : 4.8 Mpc de côté (max_mpc=2.4, cf. layerWeights.ts LAYER_EDGES_MPC[1])

7 juillet : chaque galaxie procédurale reçoit maintenant, en plus de son
halo+cœur d'origine, un halo "nuageux" (bruit de valeur multi-octaves,
même algorithme que celui utilisé pour la Voie lactée, cf.
generate_simulated_textures.mjs et l1b dans generate_layers.py), à travers
un masque ELLIPTIQUE d'orientation et d'aplatissement aléatoires (mais
déterministes par galaxie) — pour une variété visuelle cohérente avec le
traitement donné aux 8 galaxies réelles, sans prétendre connaître leur
vraie forme (elles sont procédurales, contrairement aux 8 réelles).
Calculé dans une fenêtre LOCALE autour de chaque position plutôt que sur
toute la texture 1024×1024, pour rester rapide (~90 petites fenêtres,
pas 90 champs de bruit pleine résolution).
"""

import numpy as np
from PIL import Image
from generate_local_group_catalog import build_catalog

N = 1024
MAX_MPC = 2.4
MARGIN_FACTOR = 1.5

AMPLITUDE = 3.5
HALO_SCALE = 0.85
CORE_SCALE = 1.1
# Taille du halo PROPORTIONNELLE au rayon assigné à chaque galaxie procédurale
# (plutôt qu'une taille unique pour toutes) — cohérent avec la correction
# apportée aux galaxies réelles. VISIBILITY_SCALE compense le fait que ces
# rayons (~0.0003-0.0015 Mpc) sont sous la taille d'un pixel à cette résolution.
VISIBILITY_SCALE = 22.0
MIN_SIZE_MPC = 0.006  # plancher pour rester visible même pour les plus petites

NEAR_MPC = 0.15
FAR_MPC = 1.0
PERIPHERAL_BOOST = 4.0

# Halo nuageux (cf. docstring du fichier) — amplitude volontairement plus
# faible que le halo/cœur d'origine : vient s'ajouter en complément, pas en
# remplacement, pour ne pas changer la luminosité globale déjà calibrée.
CLOUD_AMPLITUDE_FACTOR = 0.5  # relatif à peak_amp, comme HALO_SCALE/CORE_SCALE
CLOUD_SEMI_MAJOR_FACTOR = 2.6  # en multiple de size_mpc (le halo d'origine)
CLOUD_FLATTEN_MIN = 0.35
CLOUD_FLATTEN_MAX = 0.75
CLOUD_BASE_GRID = 5  # petit car la fenêtre locale est petite (peu de pixels)
CLOUD_SOFTNESS_FRAC = 0.3


def halo_distance_factor(distance_mpc):
    t = np.clip((distance_mpc - NEAR_MPC) / (FAR_MPC - NEAR_MPC), 0, 1)
    smooth = t * t * (3 - 2 * t)
    return 1.0 + (PERIPHERAL_BOOST - 1.0) * smooth


def value_noise_2d(h, w, grid_size, rng):
    """Bruit de valeur local (grille + interpolation smoothstep) — même
    algorithme que value_noise_field() dans generate_layers.py, mais pour
    une petite fenêtre h×w plutôt que le champ entier."""
    g = max(2, round(grid_size))
    grid = rng.random((g + 1, g + 1)) * 2 - 1
    ys = np.linspace(0, g, h, endpoint=False)
    xs = np.linspace(0, g, w, endpoint=False)
    gy0 = np.clip(np.floor(ys).astype(int), 0, g - 1)
    gx0 = np.clip(np.floor(xs).astype(int), 0, g - 1)
    fy = ys - np.floor(ys)
    fx = xs - np.floor(xs)
    sy = fy * fy * (3 - 2 * fy)
    sx = fx * fx * (3 - 2 * fx)
    v00 = grid[gy0[:, None], gx0[None, :]]
    v10 = grid[gy0[:, None], gx0[None, :] + 1]
    v01 = grid[gy0[:, None] + 1, gx0[None, :]]
    v11 = grid[gy0[:, None] + 1, gx0[None, :] + 1]
    a = v00 + (v10 - v00) * sx[None, :]
    b = v01 + (v11 - v01) * sx[None, :]
    return a + (b - a) * sy[:, None]


def multi_octave_cloud_2d(h, w, base_grid, rng):
    oct1 = value_noise_2d(h, w, base_grid, rng)
    oct2 = value_noise_2d(h, w, base_grid * 2.4, rng)
    oct3 = value_noise_2d(h, w, base_grid * 5.5, rng)
    c = oct1 * 0.55 + oct2 * 0.3 + oct3 * 0.15
    span = c.max() - c.min()
    return (c - c.min()) / span if span > 0 else np.zeros_like(c)


def add_cloud_halo(field, n, pixel_size_mpc, cx, cy, gx_mpc, gy_mpc, size_mpc, peak_amp, seed):
    """Ajoute un halo nuageux elliptique (orientation/aplatissement
    aléatoires déterministes par seed) dans une fenêtre locale autour de
    (gx_mpc, gy_mpc), directement dans `field` (in-place)."""
    rng = np.random.default_rng(seed)
    flatten = CLOUD_FLATTEN_MIN + rng.random() * (CLOUD_FLATTEN_MAX - CLOUD_FLATTEN_MIN)
    orientation = rng.random() * 2 * np.pi
    semi_major_mpc = size_mpc * CLOUD_SEMI_MAJOR_FACTOR
    semi_minor_mpc = semi_major_mpc * flatten

    reach_mpc = semi_major_mpc * (1 + CLOUD_SOFTNESS_FRAC) * 1.1
    reach_px = int(np.ceil(reach_mpc / pixel_size_mpc))
    px_center = cx + gx_mpc / pixel_size_mpc
    py_center = cy + gy_mpc / pixel_size_mpc
    x0 = int(np.floor(px_center - reach_px))
    x1 = int(np.ceil(px_center + reach_px))
    y0 = int(np.floor(py_center - reach_px))
    y1 = int(np.ceil(py_center + reach_px))
    cx0, cx1 = max(0, x0), min(n, x1)
    cy0, cy1 = max(0, y0), min(n, y1)
    if cx1 <= cx0 or cy1 <= cy0:
        return  # entierement hors champ

    h, w = cy1 - cy0, cx1 - cx0
    yy, xx = np.indices((h, w))
    x_mpc = (xx + cx0 - px_center) * pixel_size_mpc
    y_mpc = (yy + cy0 - py_center) * pixel_size_mpc
    # Rotation vers le repere de l'ellipse
    cos_o, sin_o = np.cos(orientation), np.sin(orientation)
    x_rot = x_mpc * cos_o + y_mpc * sin_o
    y_rot = -x_mpc * sin_o + y_mpc * cos_o
    ed = np.sqrt((x_rot / semi_major_mpc) ** 2 + (y_rot / semi_minor_mpc) ** 2)
    t = np.clip((1 - ed) / CLOUD_SOFTNESS_FRAC, 0, 1)
    mask = t * t * (3 - 2 * t)

    cloud = multi_octave_cloud_2d(h, w, CLOUD_BASE_GRID, rng)
    field[cy0:cy1, cx0:cx1] += cloud * mask * peak_amp * CLOUD_AMPLITUDE_FACTOR


def build_field(catalog, max_mpc, n, margin_factor=1.0):
    box_mpc = 2 * max_mpc * margin_factor
    pixel_size_mpc = box_mpc / n
    yy, xx = np.indices((n, n))
    cx, cy = n / 2, n / 2
    x_mpc = (xx - cx) * pixel_size_mpc
    y_mpc = (yy - cy) * pixel_size_mpc

    field = np.zeros((n, n))
    for i, gal in enumerate(catalog):
        if gal["isReal"]:
            continue  # rendues comme sprites individuels, cf. generate_simulated_textures.mjs
        if gal["distanceMpc"] > max_mpc * margin_factor * 1.05:
            continue
        angle_rad = np.radians(gal["angleDeg"])
        gx = np.cos(angle_rad) * gal["distanceMpc"]
        gy = np.sin(angle_rad) * gal["distanceMpc"]
        peak_amp = np.log(1 + gal["brightness"] * AMPLITUDE)
        halo_scale = HALO_SCALE * halo_distance_factor(gal["distanceMpc"])
        size_mpc = max(gal["radiusMpc"] * VISIBILITY_SCALE, MIN_SIZE_MPC)
        core_sigma_mpc = pixel_size_mpc * 1.5
        field += halo_scale * peak_amp * np.exp(-((x_mpc - gx) ** 2 + (y_mpc - gy) ** 2) / (2 * size_mpc ** 2))
        field += CORE_SCALE * peak_amp * np.exp(-((x_mpc - gx) ** 2 + (y_mpc - gy) ** 2) / (2 * core_sigma_mpc ** 2))
        add_cloud_halo(field, n, pixel_size_mpc, cx, cy, gx, gy, size_mpc, peak_amp, seed=7919 * (i + 1))
    return field


if __name__ == "__main__":
    catalog = build_catalog()
    field = build_field(catalog, MAX_MPC, N, margin_factor=MARGIN_FACTOR)

    VMAX_REFERENCE = 4.074
    norm = np.clip(field / VMAX_REFERENCE, 0, 1)
    img_data = (norm * 255).astype(np.uint8)
    out_path = "../app/public/data/density_localgroup.png"
    Image.fromarray(img_data, mode="L").save(out_path)
    print(f"Texture Groupe Local generee -> {out_path}")
    print(f"max brut: {field.max():.3f}, pixels satures (>0.99): {(norm>0.99).sum()}")

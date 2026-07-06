"""
Génère une texture statique pour le layer "Groupe Local" (halo+point par
galaxie), pour remplacer le calcul en direct (trop coûteux à chaque frame,
cf. retour utilisateur sur les lenteurs de zoom).

Contrairement à la version live précédente (sigma large ~0.59 Mpc, pensée
pour une seule échelle de vue), cette texture utilise un sigma BEAUCOUP plus
petit pour que chaque galaxie proche (Sagittaire, Nuages de Magellan...)
garde un halo distinct au lieu de fusionner en une seule tache.

Sortie : app/public/data/density_localgroup.png
Box : 4.8 Mpc de côté (max_mpc=2.4, cf. layerWeights.ts LAYER_EDGES_MPC[1])
"""

import numpy as np
from PIL import Image
from generate_local_group_catalog import build_catalog

N = 1024  # marge de securite supplementaire, en plus du fix DPR cote app
MAX_MPC = 2.4  # cf. layerWeights.ts : frontiere Groupe Local / L2 (frontiere LOGIQUE)
MARGIN_FACTOR = 1.5  # cf. generate_layers.py : meme marge, pour recadrage rectangulaire

SIZE_MPC = 0.02       # sigma du halo, calé sur le rayon reel de la Voie lactee (~0.016 Mpc)
AMPLITUDE = 3.5
HALO_SCALE = 0.85     # remonte (etait 0.55) pour mieux voir les galaxies, tout en restant petit
CORE_SCALE = 1.1


def build_field(catalog, max_mpc, n, margin_factor=1.0):
    box_mpc = 2 * max_mpc * margin_factor
    pixel_size_mpc = box_mpc / n
    core_sigma_mpc = pixel_size_mpc * 1.5
    yy, xx = np.indices((n, n))
    cx, cy = n / 2, n / 2
    x_mpc = (xx - cx) * pixel_size_mpc
    y_mpc = (yy - cy) * pixel_size_mpc

    field = np.zeros((n, n))
    for gal in catalog:
        if gal["distanceMpc"] > max_mpc * margin_factor * 1.05:
            continue
        angle_rad = np.radians(gal["angleDeg"])
        gx = np.cos(angle_rad) * gal["distanceMpc"]
        gy = np.sin(angle_rad) * gal["distanceMpc"]
        peak_amp = np.log(1 + gal["brightness"] * AMPLITUDE)
        field += HALO_SCALE * peak_amp * np.exp(-((x_mpc - gx) ** 2 + (y_mpc - gy) ** 2) / (2 * SIZE_MPC ** 2))
        field += CORE_SCALE * peak_amp * np.exp(-((x_mpc - gx) ** 2 + (y_mpc - gy) ** 2) / (2 * core_sigma_mpc ** 2))
    return field


if __name__ == "__main__":
    catalog = build_catalog()
    field = build_field(catalog, MAX_MPC, N, margin_factor=MARGIN_FACTOR)

    vmax = max(field.max(), 0.05)
    norm = np.clip(field / vmax, 0, 1)
    img_data = (norm * 255).astype(np.uint8)
    out_path = "../app/public/data/density_localgroup.png"
    Image.fromarray(img_data, mode="L").save(out_path)
    print(f"Texture Groupe Local generee -> {out_path}")
    print(f"max brut: {field.max():.3f}, pixels satures (>0.99): {(norm>0.99).sum()}")

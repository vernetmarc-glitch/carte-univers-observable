"""
Cuit une séquence de frames de fond filamenteux pour la dissolution
temporelle du Groupe Local (RealGalaxiesLayer), en utilisant EXACTEMENT la
même technique que la production pour l1b->l5 (generate_layers.py) :
recadrage d'un champ "maître" haute résolution (donne la croissance
d'échelle) + ajout d'un détail haute fréquence FRAÎCHEMENT régénéré à
pleine résolution d'affichage à chaque palier — pas un flou, pas un
recadrage seul (qui perd trop de résolution réelle, vérifié : variance du
laplacien qui s'effondre de 0.066 à ~0 sans le détail frais).

Retour du 10 juillet : aucun flou gaussien, aucune atténuation globale ne
doit servir de mécanisme de transition — seuls les PARAMÈTRES DE
GÉNÉRATION du champ (échelle du recadrage, amplitude avant la
transformation log-normale) doivent varier.

Sortie : app/public/data/bg_filament_f00.png ... f09.png (niveaux de gris,
512x512, non colorés — la palette/couleur reste une opération runtime,
comme tous les autres sprites/textures du projet).

Usage : node -e "" (non, Python) : python3 scripts/dev/generate_bg_filament_keyframes.py
"""
import sys
sys.path.insert(0, '..')
from generate_layers import generate_raw_field, normalize_variance, field_to_log_density
import numpy as np
from PIL import Image
from scipy.ndimage import zoom as ndi_zoom

N_MASTER = 4096
N_DISPLAY = 512
N_KEYFRAMES = 10
W_COARSE, W_DETAIL = 0.74, 0.67
OUT_DIR = "../../app/public/data"
# Echelle physique du champ maitre : cf. retour du 10 juillet — 200 Mpc
# etait sans rapport avec l'echelle reelle de la scene du Groupe Local
# (halfWidthMpc va de 0.3 a 2.5 Mpc), rendant le fond visuellement plat
# une fois recadre a cette echelle, et surtout jamais rattache au meme
# systeme de coordonnees que les galaxies. 5.0 Mpc (= 2x le halfWidthMpc
# max du curseur) donne un fond dont le cadrage complet correspond
# raisonnablement au champ affiche.
NATIVE_BOX_MPC = 5.0

master = normalize_variance(generate_raw_field(N_MASTER, NATIVE_BOX_MPC, seed=4242))
print(f"champ maître {N_MASTER}x{N_MASTER}, échelle native {NATIVE_BOX_MPC} Mpc généré")

log_d_ref = field_to_log_density(master[:N_DISPLAY, :N_DISPLAY] * 1.0)
VMIN, VMAX = np.percentile(log_d_ref, [1, 99.7])

zooms = np.linspace(1.0, 9.0, N_KEYFRAMES)
amps = np.linspace(1.0, 0.35, N_KEYFRAMES)  # reduit aussi l'amplitude (technique deja validee sur l2), EN PLUS du zoom

for i, (zoom, amp) in enumerate(zip(zooms, amps)):
    crop_px = max(int(round(N_DISPLAY / zoom)), 8)
    crop_px_master = max(int(round(crop_px * (N_MASTER / N_DISPLAY))), 8)
    start = (N_MASTER - crop_px_master) // 2
    crop = master[start:start+crop_px_master, start:start+crop_px_master]
    coarse_trend = ndi_zoom(crop, N_DISPLAY / crop_px_master, order=3)[:N_DISPLAY, :N_DISPLAY]
    if coarse_trend.shape != (N_DISPLAY, N_DISPLAY):
        pad = N_DISPLAY - coarse_trend.shape[0]
        coarse_trend = np.pad(coarse_trend, ((0, pad), (0, pad)), mode='edge')

    detail = generate_raw_field(N_DISPLAY, NATIVE_BOX_MPC / zoom, seed=7777 + i)
    combined = normalize_variance(coarse_trend) * W_COARSE + normalize_variance(detail) * W_DETAIL
    combined = combined * amp

    log_d = field_to_log_density(combined)
    norm = np.clip((log_d - VMIN) / (VMAX - VMIN), 0, 1)
    img = (norm * 255).astype(np.uint8)
    Image.fromarray(img, mode='L').save(f"{OUT_DIR}/bg_filament_f{i:02d}.png")
    print(f"frame {i}: zoom={zoom:.2f} amp={amp:.2f} -> bg_filament_f{i:02d}.png")

print("\nTerminé.")

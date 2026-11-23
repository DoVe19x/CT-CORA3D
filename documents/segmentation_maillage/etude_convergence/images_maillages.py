"""
images_maillages.py : image des deux familles de maillages du tibia (tétraèdres TetGen et hexaèdres voxels), avec
l'encastrement (gris) et la zone chargée (rouge) : tétraèdres TetGen (h = 4 mm), hexaèdres balayés (h = 3 mm),
hexaèdres voxels (h = 3 mm). Écrit ../images/maillages_tibia.png.
Usage : python images_maillages.py
"""
from pathlib import Path

import numpy as np
import pyvista as pv

import etude_convergence as C
import maillages as M

ICI = Path(__file__).resolve().parent


def grille(X, conn, type_vtk):
    cellules = np.hstack([np.full((len(conn), 1), conn.shape[1]), conn]).ravel()
    return pv.UnstructuredGrid(cellules, np.full(len(conn), type_vtk, np.uint8), X)


def main():
    pv.OFF_SCREEN = True
    s = M.lire_os(C.STL)
    x0, x1 = s.bounds[0], s.bounds[1]
    Xt, ct = M.tetraedres(s, 4.0)
    Xb, cb = M.balaye(s, 3.0)
    Xh, ch = M.voxels(s, 3.0)
    from PIL import Image
    vues = []
    for X, conn, typ in ((Xt, ct, pv.CellType.TETRA), (Xb, cb, pv.CellType.HEXAHEDRON), (Xh, ch, pv.CellType.HEXAHEDRON)):
        pl = pv.Plotter(off_screen=True, window_size=(2400, 700))
        pl.set_background("white")
        g = grille(X, conn, typ)
        centre = X[conn].mean(1)[:, 0]
        g.cell_data["zone"] = np.where(centre < x0 + C.ENCASTREMENT_MM, 0, np.where(centre > x1 - C.CHARGE_MM, 2, 1))
        pl.add_mesh(g.extract_surface(), scalars="zone", cmap=["#7f8c8d", "#efe6d2", "#c0392b"], show_edges=True,
                    edge_color="#5b4a2e", line_width=0.6, show_scalar_bar=False, clim=[0, 2])
        pl.view_xz()
        pl.reset_camera()
        pl.camera.zoom(1.5)
        im = Image.fromarray(pl.screenshot(return_img=True))
        pl.close()
        fond = np.asarray(im.convert("L")) < 250                # recadrage : on retire les marges blanches
        lignes, colonnes = np.nonzero(fond.any(1))[0], np.nonzero(fond.any(0))[0]
        vues.append(im.crop((max(colonnes[0] - 10, 0), max(lignes[0] - 10, 0), colonnes[-1] + 10, lignes[-1] + 10)))
        print(f"  {typ.name} : {len(X)} nœuds, {len(conn)} éléments")
    largeur = max(v.width for v in vues)
    image = Image.new("RGB", (largeur, sum(v.height for v in vues) + 40 * (len(vues) - 1)), "white")
    y = 0
    for v in vues:
        image.paste(v, ((largeur - v.width) // 2, y))
        y += v.height + 40
    image.save(ICI.parent / "images" / "maillages_tibia.png")
    print("  images/maillages_tibia.png")



def section_o(h=1.6):
    """Section du maillage balayé au milieu de l'os (grille en « O ») et vrai contour du STL : ../images/section_o.pdf."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    s = M.lire_os(C.STL)
    X, conn = M.balaye(s, h)
    xm = 0.5 * (s.bounds[0] + s.bounds[1])
    k = np.argmin(np.abs(np.unique(X[:, 0]) - xm))
    xk = np.unique(X[:, 0])[k]
    bas = conn[np.isclose(X[conn[:, 0], 0], xk)][:, :4]          # faces des hexaèdres posées sur cette tranche
    coupe = s.slice(normal="x", origin=(xk, 0, 0))
    fig, ax = plt.subplots(figsize=(3.4, 3.4))
    ax.add_collection(PolyCollection(X[bas][:, :, 1:], facecolor="#efe6d2", edgecolor="#5b4a2e", lw=0.5))
    p = np.asarray(coupe.points)[:, 1:]
    for a, b in coupe.lines.reshape(-1, 3)[:, 1:]:
        ax.plot(p[[a, b], 0], p[[a, b], 1], color="#c0392b", lw=1.4)
    ax.set_aspect("equal")
    ax.autoscale()
    ax.set_axis_off()
    fig.savefig(ICI.parent / "images" / "section_o.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  images/section_o.pdf ({len(bas)} quadrangles par section, x = {xk:.1f} mm)")



def geometrie_figee():
    """La géométrie figée de l'étude principale, maillée avec k = 1, 2 et 4 (C3D8) : ../images/figee_maillages.png."""
    from PIL import Image
    import etude_geometrie_figee as G
    pv.OFF_SCREEN = True
    s = M.lire_os(C.STL)
    vues = []
    for k in (1, 2, 4):
        X, conn = G.maillage_k(s, "C3D8", k)
        pl = pv.Plotter(off_screen=True, window_size=(2400, 700))
        pl.set_background("white")
        pl.add_mesh(grille(X, conn, pv.CellType.HEXAHEDRON).extract_surface(), color="#efe6d2", show_edges=True,
                    edge_color="#5b4a2e", line_width=0.6)
        pl.view_xz()
        pl.reset_camera()
        pl.camera.zoom(1.5)
        im = Image.fromarray(pl.screenshot(return_img=True))
        pl.close()
        fond = np.asarray(im.convert("L")) < 250
        lignes, colonnes = np.nonzero(fond.any(1))[0], np.nonzero(fond.any(0))[0]
        vues.append(im.crop((max(colonnes[0] - 10, 0), max(lignes[0] - 10, 0), colonnes[-1] + 10, lignes[-1] + 10)))
        print(f"  k = {k} : {len(X)} nœuds, {len(conn)} éléments")
    largeur = max(v.width for v in vues)
    image = Image.new("RGB", (largeur, sum(v.height for v in vues) + 40 * (len(vues) - 1)), "white")
    y = 0
    for v in vues:
        image.paste(v, ((largeur - v.width) // 2, y))
        y += v.height + 40
    image.save(ICI.parent / "images" / "figee_maillages.png")
    print("  images/figee_maillages.png")


if __name__ == "__main__":
    main()
    section_o()
    geometrie_figee()

"""
vtk_leger.py — VTK « allégé » : seulement les classes dont le programme se sert.

Pourquoi : `import vtk` charge TOUTE la bibliothèque VTK (rendu, web, entrées-sorties…) : ≈ 2 s à chaque démarrage de
l'application (mesuré : 2,2 s), pour une quinzaine de classes utilisées. Ce module les importe depuis leurs
sous-modules `vtkmodules` (≈ 0,5 s). Usage, sans rien changer au reste du code :

    import vtk_leger as vtk
    fe = vtk.vtkFlyingEdges3D()

Une classe VTK nouvellement utilisée doit être ajoutée ici (sinon : AttributeError explicite au premier essai).
Le rendu 3D (aperçus PNG) passe par pyvista, qui importe lui-même ce dont il a besoin, seulement à ce moment-là.
"""
from vtkmodules.util import numpy_support                                   # noqa: F401
from vtkmodules.vtkCommonCore import vtkIdList, vtkPoints                     # noqa: F401
from vtkmodules.vtkCommonDataModel import (vtkCellArray, vtkImageData, vtkPlane, vtkPolyData,  # noqa: F401
                                           vtkStaticCellLocator)
from vtkmodules.vtkFiltersCore import (vtkCleanPolyData, vtkCutter, vtkFlyingEdges3D,  # noqa: F401
                                       vtkPolyDataConnectivityFilter, vtkQuadricDecimation,
                                       vtkWindowedSincPolyDataFilter)
from vtkmodules.vtkFiltersModeling import vtkSelectEnclosedPoints           # noqa: F401
from vtkmodules.vtkImagingStencil import vtkImageStencilToImage, vtkPolyDataToImageStencil  # noqa: F401

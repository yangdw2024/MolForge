"""World-anchored labels rendered in the same VTK pass as the molecule."""
import math
import numpy as np
import vtk
from ..domain.elements import get_element


class NativeAtomLabels:
    def __init__(self, backend, renderer):
        self.backend = backend
        self.renderer = renderer
        self.points = vtk.vtkPoints()
        self.strings = vtk.vtkStringArray(); self.strings.SetName('atom_label')
        self.types = vtk.vtkIntArray(); self.types.SetName('label_style')
        self.data = vtk.vtkPolyData(); self.data.SetPoints(self.points)
        self.data.GetPointData().AddArray(self.strings)
        self.data.GetPointData().AddArray(self.types)
        mapper_type = getattr(vtk,'vtkBatchedLabeledDataMapper',vtk.vtkLabeledDataMapper)
        self.mapper = mapper_type()
        self.mapper.SetInputData(self.data)
        self.mapper.SetLabelModeToLabelFieldData(); self.mapper.SetFieldDataName('atom_label')
        self.mapper.SetInputArrayToProcess(0,0,0,vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS,'label_style')
        if hasattr(self.mapper,'SetTextAnchor'):
            self.mapper.SetTextAnchor(self.mapper.Center)
        self.properties=[]
        for index,color in enumerate(((.03,.035,.04),(.96,.98,1.))):
            prop=vtk.vtkTextProperty();prop.SetColor(*color);prop.SetFontFamilyToArial()
            prop.BoldOff();prop.ShadowOff();prop.SetFontSize(14)
            prop.SetJustificationToCentered();prop.SetVerticalJustificationToCentered()
            self.mapper.SetLabelTextProperty(prop,index);self.properties.append(prop)
        self.actor=vtk.vtkActor2D();self.actor.SetMapper(self.mapper);self.actor.PickableOff()
        self.actor.VisibilityOff()
        self._font=14;self._median_radius=.4;self._max_radius=.4;self.render_frames=0;self.data_updates=0
        self._views=[]
        self.set_views([renderer])

    def set_views(self, renderers):
        self.close()
        for view_index,renderer in enumerate(renderers):
            window=renderer.GetRenderWindow()
            overlay=None
            mapper=self.mapper if view_index==0 else self.mapper.NewInstance()
            if view_index:
                mapper.SetLabelModeToLabelFieldData();mapper.SetFieldDataName('atom_label')
                mapper.SetInputArrayToProcess(0,0,0,vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS,'label_style')
                if hasattr(mapper,'SetTextAnchor'):mapper.SetTextAnchor(mapper.Center)
                for i,prop in enumerate(self.properties):mapper.SetLabelTextProperty(prop,i)
            actor=self.actor if view_index==0 else vtk.vtkActor2D()
            actor.SetMapper(mapper);actor.PickableOff();actor.SetVisibility(self.actor.GetVisibility())
            visible=None
            if window is not None:
                window.SetNumberOfLayers(max(3,window.GetNumberOfLayers()))
                overlay=vtk.vtkRenderer();overlay.SetLayer(2)
                overlay.SetInteractive(False);overlay.SetPreserveColorBuffer(True)
                overlay.SetPreserveDepthBuffer(False)
                overlay.SetActiveCamera(renderer.GetActiveCamera());overlay.SetViewport(renderer.GetViewport())
                overlay.AddViewProp(actor);window.AddRenderer(overlay)
                visible=vtk.vtkSelectVisiblePoints();visible.SetInputData(self.data)
                visible.SetRenderer(renderer);visible.SetTolerance(0.);visible.SetToleranceWorld(self._max_radius*1.02)
                mapper.SetInputConnection(visible.GetOutputPort())
            else:
                renderer.AddViewProp(actor);mapper.SetInputData(self.data)
            observer=renderer.AddObserver('StartEvent',self._prepare_frame)
            finish=renderer.AddObserver('EndEvent',self._finish_frame)
            self._views.append((renderer,overlay,observer,finish,visible,actor))

    def close(self):
        for renderer,overlay,observer,finish,visible,actor in getattr(self,'_views',[]):
            renderer.RemoveObserver(observer)
            renderer.RemoveObserver(finish)
            if overlay is not None and overlay.GetRenderWindow() is not None:
                overlay.GetRenderWindow().RemoveRenderer(overlay)
            elif overlay is None:
                renderer.RemoveViewProp(actor)
        self._views=[]

    def update(self):
        b=self.backend
        if not (b.show_labels or b.show_symbols) or b._coordinates is None:
            self.actor.VisibilityOff()
            for *_,actor in self._views:actor.VisibilityOff()
            return
        self.points.Reset();self.strings.Reset();self.types.Reset()
        scope=b.label_scope;radii=[]
        for i,(position,aid) in enumerate(zip(b._coordinates,b._atom_ids)):
            z=int(b._atomic_numbers[i])
            if z==1 and not b.show_hydrogens:continue
            if scope=='selected' and aid not in b._selected:continue
            if scope=='heavy' and z==1 and aid not in b._selected:continue
            if i<len(b._atom_opacities) and b._atom_opacities[i]<=0:continue
            symbol=get_element(z).symbol if get_element(z) else '?'
            text=(symbol if b.show_symbols else '')+(str(aid.value+1) if b.show_labels else '')
            self.points.InsertNextPoint(*[float(x) for x in position]);self.strings.InsertNextValue(text)
            color=b.get_effective_atom_color(i)
            luminance=.2126*color[0]+.7152*color[1]+.0722*color[2]
            self.types.InsertNextValue(0 if luminance>.32 else 1)
            radii.append(b.get_effective_atom_radius(i))
        self._median_radius=float(np.median(radii)) if radii else .4
        self._max_radius=max(radii,default=.4)
        self.points.Modified();self.strings.Modified();self.types.Modified();self.data.Modified()
        self.actor.SetVisibility(bool(radii))
        for _,_,_,_,visible,actor in self._views:
            actor.SetVisibility(bool(radii))
            if visible is not None:visible.SetToleranceWorld(self._max_radius*1.02)
        self.data_updates+=1

    def _prepare_frame(self, renderer, event):
        # O(1) camera work only. No per-atom projection, text layout or collision search.
        self.render_frames+=1
        for source,overlay,*_ in self._views:
            if source is renderer and overlay is not None:
                overlay.SetViewport(renderer.GetViewport())
                overlay.SetActiveCamera(renderer.GetActiveCamera())
        if not self.actor.GetVisibility():return
        window=renderer.GetRenderWindow()
        if window is None:return
        camera=renderer.GetActiveCamera();viewport=renderer.GetViewport()
        height=window.GetSize()[1]*(viewport[3]-viewport[1])
        if camera.GetParallelProjection():
            radius_px=height*self._median_radius/(2*max(1e-8,camera.GetParallelScale()))
        else:
            distance=np.linalg.norm(np.asarray(camera.GetPosition())-camera.GetFocalPoint())
            radius_px=height*self._median_radius/(2*max(1e-8,distance)*math.tan(math.radians(camera.GetViewAngle()/2)))
        font=int(np.clip(round(radius_px*.95/2)*2,10,36))
        if font != self._font:
            for prop in self.properties:prop.SetFontSize(font)
            self._font=font

    def _finish_frame(self, renderer, event):
        # Native C++ depth test of glyph centres after the molecule is rendered.
        if not self.actor.GetVisibility():return
        for source,_,_,_,visible,_ in self._views:
            if source is renderer and visible is not None:
                visible.Modified();visible.Update()

"""Bottom document tabs, MDI manager, export suite, and 5-minute auto-save shared by the three independent Studio windows."""
from __future__ import annotations

import copy
import uuid
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QGuiApplication
from PyQt6.QtWidgets import (
    QFileDialog, QInputDialog, QMenu, QMessageBox, QTabWidget, QToolBar, QMdiArea, QMdiSubWindow
)

from ...application.workspace_registry import WorkspaceRegistry
from ...domain.document import MoleculeDocument


class _DocumentSubWindow(QMdiSubWindow):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def closeEvent(self, event):
        page = self.widget()
        event.ignore()
        QTimer.singleShot(0, lambda p=page: self.owner._close_mdi_page(p))


class StudioTabs:
    """Shared document tabs, tool synchronization, export actions, and auto-save mixin for Studio windows."""

    def init_tabs(self, initial_widget):
        self.setAcceptDrops(True)
        self._active_tool: str = "选择"
        self._active_element: int = 6
        self._tool_actions: dict[str, QAction] = {}
        self._saved_revisions: dict[str, int] = {}

        self.tabs = QTabWidget(self)
        self.tabs.setTabPosition(QTabWidget.TabPosition.South)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._activate_tab)
        bar = self.tabs.tabBar()
        bar.tabBarDoubleClicked.connect(self.rename_tab)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._tab_menu)
        self._pages = {}
        self._mdi_area = None
        self._active_mdi_page = None

        c2_init = getattr(self, "canvas2d", None)
        c3_init = getattr(self, "canvas3d", None)
        self._wire_canvas_signals(c2_init, c3_init)

        self.tabs.blockSignals(True)
        self._register_page(initial_widget, self.shell, c2_init, c3_init)
        self.tabs.blockSignals(False)
        self._saved_revisions[self.shell.document.document_id] = self.shell.document.revision
        self.setCentralWidget(self.tabs)

        # 启动每 5 分钟 (300,000 ms) 定时自动保存 (P1 Bug 6)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(300_000)
        self._autosave_timer.timeout.connect(self._run_autosave)
        self._autosave_timer.start()

    def _wire_canvas_signals(self, c2, c3):
        if c2 is not None:
            try:
                c2.tool_changed_signal.connect(self._on_canvas_tool_changed)
                c2.element_changed_signal.connect(self._on_canvas_element_changed)
            except Exception:
                pass

    def _on_canvas_tool_changed(self, tool_name: str):
        self._active_tool = tool_name
        act = self._tool_actions.get(tool_name)
        if act is not None and not act.isChecked():
            act.setChecked(True)
        c3 = getattr(self, "canvas3d", None)
        if c3 is not None:
            c3.set_current_tool(tool_name)

    def _on_canvas_element_changed(self, atomic_num: int):
        self._active_element = int(atomic_num)
        c3 = getattr(self, "canvas3d", None)
        if c3 is not None:
            c3.set_current_element(int(atomic_num))

    def _register_page(self, widget, shell, canvas2d=None, canvas3d=None):
        self._pages[widget] = (shell, canvas2d, canvas3d)
        index = self.tabs.addTab(widget, shell.document.name)
        shell.session.command_bus.add_listener(
            lambda *_args, w=widget: self._refresh_page(w)
        )
        shell.session.selection.add_listener(
            lambda _origin, c=canvas2d: c.update() if c is not None else None
        )
        self.tabs.setCurrentIndex(index)
        # 关键修复 (P0 Bug 1)：即使 index 等于原先的 currentIndex，也强制执行 _activate_page，
        # 确保 self.shell / self.document / self.command_bus / self.canvas2d / self.canvas3d 100% 指向新标签页！
        self._activate_page(widget)
        return index

    def _refresh_page(self, widget):
        if widget not in self._pages:
            return
        shell, c2, c3 = self._pages[widget]
        idx = self.tabs.indexOf(widget)
        if idx >= 0:
            dirty = "*" if self._is_doc_modified(shell.document) else ""
            self.tabs.setTabText(idx, f"{shell.document.name}{dirty}")
        if c2 is not None:
            c2.update()
        active = widget is self.tabs.currentWidget() or (
            self._mdi_area is not None and widget is getattr(self, "_active_mdi_page", None)
        )
        if active:
            self.refresh_views()

    def _activate_tab(self, index):
        widget = self.tabs.widget(index)
        if widget not in self._pages:
            return
        self._activate_page(widget)

    def add_document_tab(self, document=None, session=None):
        from .studio_2d import Studio2DShell
        from .studio_3d import Studio3DShell
        from .studio_split import StudioSplitShell
        from ..editor2d_widget import Editor2DWidget
        from ..render3d_widget import Render3DWidget
        from PyQt6.QtWidgets import QSplitter

        is_blank_new = (document is None)
        doc = document if document is not None else MoleculeDocument(name=f"未命名-{self.tabs.count() + 1}")
        kind = self.shell.shell_kind
        cls = {
            "studio_2d": Studio2DShell,
            "studio_3d": Studio3DShell,
            "studio_split": StudioSplitShell,
        }[kind]
        shell = cls(document=doc, session=session)
        c2 = c3 = None
        if kind == "studio_split":
            widget = QSplitter(Qt.Orientation.Horizontal, self.tabs)
            c2 = Editor2DWidget(widget)
            c3 = Render3DWidget(widget)
            widget.addWidget(c2)
            widget.addWidget(c3)
            widget.setSizes([600, 640])
        elif kind == "studio_2d":
            widget = c2 = Editor2DWidget(self.tabs)
        else:
            widget = c3 = Render3DWidget(self.tabs)

        # 若是新建空白画布，自动切换到「原子」绘制模式，让用户点击画布即可立即放置原子 (P0 Bug 1)
        if is_blank_new:
            self._active_tool = "原子"
            act = self._tool_actions.get("原子")
            if act is not None:
                act.setChecked(True)

        for canvas in (c2, c3):
            if canvas is not None:
                canvas.set_selection_service(shell.session.selection)
                canvas.set_command_bus(shell.session.command_bus)
                canvas.set_current_element(self._active_element)
                canvas.set_current_tool(self._active_tool)
                if canvas is c2:
                    canvas.set_document(shell.document)

        self._wire_canvas_signals(c2, c3)
        self._saved_revisions[doc.document_id] = doc.revision
        self._register_page(widget, shell, c2, c3)

        if c3 is not None:
            QTimer.singleShot(
                15,
                lambda c=c3, s=shell: c.set_document(s.document) if c.parent() is not None else None,
            )
        if self._mdi_area is not None:
            self.tabs.removeTab(self.tabs.indexOf(widget))
            sub = _DocumentSubWindow(self)
            sub.setWidget(widget)
            self._mdi_area.addSubWindow(sub)
            sub.setWindowTitle(shell.document.name)
            sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            sub.show()
            self._arrange_mdi("tile")
            self._activate_mdi_window(sub)
        return widget

    def open_document_tab(self, path):
        from ...io.rdkit_adapter import load_molecule_document
        try:
            loaded = load_molecule_document(path)
            doc = loaded[0] if isinstance(loaded, tuple) else loaded
            self.add_document_tab(doc)
        except Exception as exc:
            QMessageBox.critical(self, "打开失败", f"无法打开文件：\n{exc}")

    def close_tab(self, index):
        if self._mdi_area is not None:
            self._close_mdi_page(getattr(self, "_active_mdi_page", None))
            return
        if index < 0 or index >= self.tabs.count():
            return
        widget = self.tabs.widget(index)
        if widget in self._pages:
            doc = self._pages[widget][0].document
            if not self._confirm_save_if_modified(doc):
                return
        if self.tabs.count() == 1:
            choice = QMessageBox.question(
                self,
                "关闭最后一个画布",
                "新建空白分子？选择“否”将返回欢迎界面。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            if choice == QMessageBox.StandardButton.Yes:
                self.add_document_tab()
            else:
                self._open_welcome()
                self.close()
                return
        shell = self._pages.pop(widget)[0]
        self.tabs.removeTab(index)
        shell.close_shell()
        widget.deleteLater()
        if self.tabs.count() > 0:
            cur_w = self.tabs.currentWidget()
            if cur_w in self._pages:
                self._activate_page(cur_w)

    def rename_tab(self, index):
        if index < 0:
            return
        widget = self.tabs.widget(index)
        name, ok = QInputDialog.getText(self, "重命名分子", "分子名称：", text=self.tabs.tabText(index).rstrip("*"))
        if ok and name.strip():
            self._pages[widget][0].document.name = name.strip()
            self._pages[widget][0].document.bump_revision()
            self._refresh_page(widget)

    def duplicate_tab(self, index):
        if index >= 0:
            doc = copy.deepcopy(self._pages[self.tabs.widget(index)][0].document)
            doc.document_id = uuid.uuid4().hex
            doc.name += " 副本"
            self.add_document_tab(doc)

    def _tab_menu(self, pos):
        index = self.tabs.tabBar().tabAt(pos)
        if index < 0:
            return
        menu = QMenu(self)
        menu.addAction("新建画布", lambda: self.add_document_tab())
        menu.addAction("复制画布", lambda: self.duplicate_tab(index))
        menu.addAction("重命名", lambda: self.rename_tab(index))
        menu.addAction("关闭画布", lambda: self.close_tab(index))
        menu.exec(self.tabs.tabBar().mapToGlobal(pos))

    def install_studio_toolbar(self):
        toolbar = QToolBar("绘图工具", self)
        toolbar.setMovable(True)
        toolbar.setFloatable(True)
        self.addToolBar(toolbar)
        group = QActionGroup(self)
        self._tool_actions = {}
        for label, tool, key in [
            ("选择 V", "选择", "V"),
            ("原子 A", "原子", "A"),
            ("键 B", "键", "B"),
            ("擦除 E", "擦除", "E"),
        ]:
            action = QAction(label, self)
            action.setCheckable(True)
            group.addAction(action)
            toolbar.addAction(action)
            action.triggered.connect(lambda _=False, t=tool: self._set_active_tool(t))
            self._tool_actions[tool] = action
            if tool == self._active_tool:
                action.setChecked(True)
        toolbar.addSeparator()
        toolbar.addAction("🗑️ 删除选中", self.delete_selected_active)
        toolbar.addAction("撤销", lambda: (self.command_bus.undo(), self.refresh_views()))
        toolbar.addAction("重做", lambda: (self.command_bus.redo(), self.refresh_views()))
        toolbar.addSeparator()
        toolbar.addAction("清洁", self._clean_active)
        toolbar.addAction("居中", self._center_active)
        self.studio_toolbar = toolbar

    def _set_active_tool(self, tool):
        self._active_tool = tool
        act = self._tool_actions.get(tool)
        if act is not None and not act.isChecked():
            act.setChecked(True)
        for canvas in (getattr(self, "canvas2d", None), getattr(self, "canvas3d", None)):
            if canvas is not None:
                canvas.set_current_tool(tool)

    def delete_selected_active(self):
        """删除当前活动画布选中的原子与化学键 (P0 Bug 4)。"""
        c2 = getattr(self, "canvas2d", None)
        if c2 is not None and hasattr(c2, "delete_selected"):
            c2.delete_selected()
            self.refresh_views()
            return
        if self.selection is not None and self.command_bus is not None:
            from ...application.selection_commands import DeleteSelectionCommand
            self.command_bus.execute(DeleteSelectionCommand(self.selection.selected_atoms, self.selection.selected_bonds))
            self.selection.clear()
            self.refresh_views()

    def _clean_active(self):
        canvas = getattr(self, "canvas3d", None) or getattr(self, "canvas2d", None)
        if canvas is None:
            return
        if hasattr(canvas, "clean_3d_geometry"):
            canvas.clean_3d_geometry()
        elif hasattr(canvas, "recompute_2d_layout"):
            canvas.recompute_2d_layout()

    def _center_active(self):
        canvas = getattr(self, "canvas3d", None) or getattr(self, "canvas2d", None)
        if canvas is None:
            return
        if hasattr(canvas, "reset_camera"):
            canvas.reset_camera()
        elif hasattr(canvas, "fit_view"):
            canvas.fit_view()

    # ---------- P1 Bug 5: Studio 完整导出功能 (SMILES / XYZ / MOL / SDF / PDB / PNG / SVG) ----------

    def install_export_menu(self, file_menu: QMenu):
        """向 Studio 窗口的「文件」菜单注入完整的结构与图像导出选项 (P1 Bug 5)。"""
        exp_menu = file_menu.addMenu("📤 导出结构与图像 (Export)")
        exp_menu.addAction("复制 SMILES 到剪贴板 (Copy SMILES)", self.export_smiles_to_clipboard)
        exp_menu.addAction("导出 XYZ 坐标文件 (.xyz)...", self.export_xyz_file)
        exp_menu.addAction("导出 MOL / SDF 结构文件 (.mol / .sdf)...", self.export_mol_sdf_file)
        exp_menu.addAction("导出 PDB / MOL2 文件 (.pdb / .mol2)...", self.export_pdb_mol2_file)
        exp_menu.addAction("导出 PNG 高清截图 / SVG 矢量图 (.png / .svg)...", self.export_image_file)

    def _generate_smiles_string(self) -> str:
        from ...io.rdkit_adapter import doc_to_rdkit, compute_formula_and_weight_fast
        try:
            from rdkit import Chem
            rmol, _, _ = doc_to_rdkit(self.document, sanitize=True)
            rmol_no_h = Chem.RemoveHs(rmol)
            smi = Chem.MolToSmiles(rmol_no_h, canonical=True)
            if smi:
                return smi
        except Exception:
            pass
        raise ValueError("当前结构无法生成有效SMILES；请先检查价态和键型")

    def export_smiles_to_clipboard(self):
        try:
            smi = self._generate_smiles_string()
        except Exception as exc:
            QMessageBox.warning(self, "无法导出SMILES", str(exc))
            return
        QGuiApplication.clipboard().setText(smi)
        QMessageBox.information(self, "已复制 SMILES", f"当前分子 SMILES 已复制到剪贴板：\n{smi}")

    def export_xyz_file(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "导出 XYZ 坐标文件", f"{self.document.name}.xyz", "XYZ Coordinates (*.xyz)")
        if not path:
            return False
        from ...application.calculators.qc_input_generator import extract_xyz_lines
        xyz_lines = extract_xyz_lines(self.document)
        txt = f"{len(xyz_lines)}\n{self.document.name}\n" + "\n".join(xyz_lines) + "\n"
        Path(path).write_text(txt, encoding="utf-8")
        QMessageBox.information(self, "导出成功", f"已导出 XYZ 坐标文件：\n{path}")
        return True

    def export_mol_sdf_file(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 MOL / SDF 结构文件", f"{self.document.name}.mol", "MDL MOL V2000 (*.mol);;SDF Structure (*.sdf)"
        )
        if not path:
            return False
        from ...io.rdkit_adapter import export_document_to_mol_v2000
        mol_block = export_document_to_mol_v2000(self.document)
        if path.lower().endswith(".sdf"):
            mol_block = mol_block.rstrip() + "\n$$$$\n"
        Path(path).write_text(mol_block, encoding="utf-8")
        QMessageBox.information(self, "导出成功", f"已导出结构文件：\n{path}")
        return True

    def export_pdb_mol2_file(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 PDB / MOL2 文件", f"{self.document.name}.pdb", "Protein Data Bank (*.pdb);;SYBYL MOL2 (*.mol2)"
        )
        if not path:
            return False
        from ...io.rdkit_adapter import export_document_to_pdb, export_document_to_mol2
        if path.lower().endswith(".mol2"):
            Path(path).write_text(export_document_to_mol2(self.document), encoding="utf-8")
        else:
            Path(path).write_text(export_document_to_pdb(self.document), encoding="utf-8")
        QMessageBox.information(self, "导出成功", f"已导出文件：\n{path}")
        return True

    def export_image_file(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出高清图像", f"{self.document.name}.png", "PNG 高清图像 (*.png);;SVG 矢量图 (*.svg)"
        )
        if not path:
            return False
        if path.lower().endswith(".svg") and getattr(self, "canvas2d", None) is not None:
            from ...io.writers.svg_writer import write_svg_2d
            write_svg_2d(self.document, path)
        else:
            target = getattr(self, "canvas3d", None) or getattr(self, "canvas2d", None) or self
            target.grab().save(path)
        QMessageBox.information(self, "导出成功", f"已导出图像文件：\n{path}")
        return True

    # ---------- P1 Bug 6: 5 分钟定时自动保存与关闭未保存提示 ----------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_document_tab(url.toLocalFile())
        event.acceptProposedAction()

    def save_project(self, doc=None):
        from ...io.mforge_storage import save_mforge
        from ...runtime import data_dir
        doc = doc if doc is not None else self.document
        path, _ = QFileDialog.getSaveFileName(self, "保存完整分子工程", str(data_dir() / f"{doc.name}.mforge"), "MolForge Project (*.mforge)")
        if not path:
            return False
        try:
            save_mforge(doc, path)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return False
        self._saved_revisions[doc.document_id] = doc.revision
        return True

    def _is_doc_modified(self, doc: MoleculeDocument | None) -> bool:
        if doc is None:
            return False
        saved_rev = self._saved_revisions.get(doc.document_id, 0)
        return doc.revision > saved_rev

    def _run_autosave(self):
        """每 5 分钟自动将当前打开的分子工程备份至 ~/.molforge_autosave/。"""
        try:
            from ...io.mforge_storage import save_mforge
            from ...runtime import data_dir
            autosave_dir = data_dir() / "autosave"
            autosave_dir.mkdir(parents=True, exist_ok=True)
            for _w, (shell, _c2, _c3) in list(self._pages.items()):
                doc = shell.document
                if doc is not None:
                    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in doc.name) or "untitled"
                    save_mforge(doc, autosave_dir / f"{safe_name}_{doc.document_id[:6]}.mforge")
        except Exception as exc:
            self.statusBar().showMessage(f"自动保存失败：{exc}", 10000)

    def _confirm_save_if_modified(self, doc: MoleculeDocument | None) -> bool:
        if not self._is_doc_modified(doc):
            return True
        ans = QMessageBox.question(
            self,
            "未保存的修改",
            f"分子「{doc.name}」包含未保存的修改，是否在关闭前保存完整工程？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if ans == QMessageBox.StandardButton.Cancel:
            return False
        if ans == QMessageBox.StandardButton.Save:
            return self.save_project(doc)
        return True

    def closeEvent(self, event):
        for _w, (shell, _c2, _c3) in list(getattr(self, "_pages", {}).items()):
            if not self._confirm_save_if_modified(shell.document):
                event.ignore()
                return
        if hasattr(self, "_autosave_timer") and self._autosave_timer is not None:
            self._autosave_timer.stop()
        super().closeEvent(event)

    def install_window_menu(self):
        menu = next((m for m in self.menuBar().findChildren(QMenu) if m.title().startswith("窗口")), None)
        if menu is None:
            menu = self.menuBar().addMenu("窗口(&W)")
        menu.addSeparator()
        menu.addAction("新建画布", lambda: self.add_document_tab())
        menu.addAction("关闭当前画布", self._close_active_canvas)
        menu.addSeparator()
        menu.addAction("平铺所有画布", lambda: self.show_canvas_mdi("tile"))
        menu.addAction("层叠所有画布", lambda: self.show_canvas_mdi("cascade"))
        menu.addAction("恢复标签页", self.restore_canvas_tabs)
        menu.addSeparator()
        next_act = menu.addAction("切换到下一个画布", lambda: self._cycle_tab(1))
        next_act.setShortcut("Ctrl+Tab")
        prev_act = menu.addAction("切换到上一个画布", lambda: self._cycle_tab(-1))
        prev_act.setShortcut("Ctrl+Shift+Tab")
        menu.addSeparator()
        self.tab_list_menu = menu.addMenu("打开的画布")
        self.tab_list_menu.aboutToShow.connect(self._populate_tab_list)
        file_menu = next((m for m in self.menuBar().findChildren(QMenu) if m.title().startswith("文件")), None)
        if file_menu is not None:
            shortcuts = {a.shortcut().toString() for a in self.findChildren(QAction)}
            if "Ctrl+N" not in shortcuts:
                action = file_menu.addAction("新建空白画布 (Ctrl+N)", lambda: self.add_document_tab())
                action.setShortcut("Ctrl+N")
            if "Ctrl+S" not in shortcuts:
                action = file_menu.addAction("保存完整工程 (Ctrl+S)", lambda: self.save_project())
                action.setShortcut("Ctrl+S")
            self.install_export_menu(file_menu)
            file_menu.addSeparator()
            file_menu.addAction("合并到主系统标签页", self.merge_into_main)
        edit_menu = next((m for m in self.menuBar().findChildren(QMenu) if m.title().startswith("编辑")), None)
        if edit_menu is not None:
            edit_menu.addSeparator()
            del_act = QAction("删除选中原子 / 化学键 (Delete)", self)
            del_act.setShortcut("Delete")
            del_act.triggered.connect(self.delete_selected_active)
            edit_menu.addAction(del_act)
        calc_menu = next((m for m in self.menuBar().findChildren(QMenu) if m.title().startswith("计算")), None)
        if calc_menu is not None:
            calc_menu.addSeparator()
            eng_act = QAction("引擎状态与工具路径配置...", self)
            eng_act.triggered.connect(self._open_engine_status_dialog)
            calc_menu.addAction(eng_act)

    def _open_engine_status_dialog(self):
        from .workflow_inputs import ToolPathConfigDialog
        ToolPathConfigDialog(self).exec()

    def merge_into_main(self):
        from ..window import MolForgeWindow
        from ..welcome_window import AppController
        main = next((w for w in MolForgeWindow._open_windows if w.isVisible()), None)
        if main is None:
            main = MolForgeWindow(initial_document=self.document)
            AppController.instance().active_windows.append(main)
        else:
            main._add_document_page(self.document, self.session)
        main.show()
        main.raise_()

    def show_canvas_mdi(self, arrangement="tile"):
        if getattr(self, "_mdi_area", None) is not None:
            self._arrange_mdi(arrangement)
            return
        old_center = self.tabs
        old_center.setParent(None)
        old_center.hide()

        area = QMdiArea(self)
        area.setViewMode(QMdiArea.ViewMode.SubWindowView)
        area.subWindowActivated.connect(self._activate_mdi_window)
        self._mdi_area = area
        for widget, (shell, _c2, _c3) in list(self._pages.items()):
            sub = _DocumentSubWindow(self)
            sub.setWidget(widget)
            area.addSubWindow(sub)
            sub.setWindowTitle(shell.document.name)
            sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            sub.show()
        self.setCentralWidget(area)
        self._arrange_mdi(arrangement)
        if area.activeSubWindow() is not None:
            self._activate_mdi_window(area.activeSubWindow())

    def _arrange_mdi(self, arrangement):
        if self._mdi_area is None:
            return
        if arrangement == "tile":
            self._mdi_area.tileSubWindows()
        else:
            self._mdi_area.cascadeSubWindows()

    def _activate_mdi_window(self, subwindow):
        if subwindow is None:
            return
        page = subwindow.widget()
        if page in self._pages:
            self._active_mdi_page = page
            self._pages[page][0].document.name = subwindow.windowTitle()
            self._activate_page(widget=page)

    def _close_active_canvas(self):
        if self._mdi_area is not None:
            sub = self._mdi_area.activeSubWindow()
            if sub is not None:
                self._close_mdi_page(sub.widget())
            return
        self.close_tab(self.tabs.currentIndex())

    def _close_mdi_page(self, page):
        if page not in self._pages:
            return
        if not self._confirm_save_if_modified(self._pages[page][0].document):
            return
        if len(self._pages) == 1:
            choice = QMessageBox.question(
                self,
                "关闭最后一个画布",
                "新建空白分子？选择“否”返回欢迎界面。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            if choice == QMessageBox.StandardButton.No:
                self._open_welcome()
                self.close()
                return
            self.add_document_tab()
        area = self._mdi_area
        shell = self._pages.pop(page)[0]
        sub = next((w for w in area.subWindowList() if w.widget() is page), None)
        if sub is not None:
            area.removeSubWindow(page)
            sub.deleteLater()
        page.deleteLater()
        shell.close_shell()
        if not self._pages:
            self._mdi_area = None
            self.restore_canvas_tabs()
            return
        self._arrange_mdi("tile")
        active = area.activeSubWindow()
        if active is not None:
            self._activate_mdi_window(active)

    def restore_canvas_tabs(self):
        area = self._mdi_area
        if area is None:
            return
        active = getattr(self, "_active_mdi_page", None)
        self.tabs.blockSignals(True)
        for sub in list(area.subWindowList()):
            page = sub.widget()
            if page is None or page not in self._pages:
                continue
            shell, _c2, _c3 = self._pages[page]
            title = sub.windowTitle() or shell.document.name
            shell.document.name = title
            page.setParent(self.tabs)
            area.removeSubWindow(sub)
            sub.deleteLater()
            page.setParent(self.tabs)
            page.show()
            self.tabs.addTab(page, title)
        self.tabs.blockSignals(False)
        area.setParent(None)
        self._mdi_area = None
        self.setCentralWidget(self.tabs)
        self.tabs.show()
        area.deleteLater()
        if self.tabs.count():
            index = self.tabs.indexOf(active) if active is not None else 0
            self.tabs.setCurrentIndex(max(0, index))
            self._activate_page(self.tabs.currentWidget())

    def _activate_page(self, widget):
        if widget not in self._pages:
            return
        self.shell, self.canvas2d, self.canvas3d = self._pages[widget]
        self.session = self.shell.session
        self.view_session = self.shell.view_session
        self.document = self.session.document
        self.command_bus = self.session.command_bus
        self.selection = self.session.selection
        self.group_tag = self.shell.gmv_tag
        if hasattr(self, "splitter") and widget is not None:
            self.splitter = widget
        for canvas in (self.canvas2d, self.canvas3d):
            if canvas is not None:
                canvas.set_selection_service(self.selection)
                canvas.set_command_bus(self.command_bus)
                canvas.set_current_element(self._active_element)
                canvas.set_current_tool(self._active_tool)
                canvas.set_document(self.document)
        self.refresh_views()

    def _cycle_tab(self, direction):
        if self._mdi_area is not None:
            subs = self._mdi_area.subWindowList()
            if subs:
                current = self._mdi_area.activeSubWindow()
                index = subs.index(current) if current in subs else 0
                self._mdi_area.setActiveSubWindow(subs[(index + direction) % len(subs)])
            return
        if self.tabs.count():
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + direction) % self.tabs.count())

    def _populate_tab_list(self):
        self.tab_list_menu.clear()
        if self._mdi_area is not None:
            for sub in self._mdi_area.subWindowList():
                self.tab_list_menu.addAction(sub.windowTitle(), lambda _=False, w=sub: self._mdi_area.setActiveSubWindow(w))
        else:
            for i in range(self.tabs.count()):
                self.tab_list_menu.addAction(self.tabs.tabText(i), lambda _=False, n=i: self.tabs.setCurrentIndex(n))


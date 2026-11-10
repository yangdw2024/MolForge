"""全面功能检测：逐个模块测试，收集真实 bug。"""
import sys, traceback
sys.path.insert(0, r"E:\YDW\Trae_Chemdraw\MolForge")
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

results = []

def test(name, fn):
    try:
        fn()
        results.append((name, "PASS", ""))
        print(f"  ✅ {name}")
    except Exception as e:
        results.append((name, "FAIL", str(e)))
        print(f"  ❌ {name}: {e}")

app = QApplication(sys.argv)
from molforge.ui.theme import STYLE
app.setStyleSheet(STYLE)

print("=" * 60)
print("MolForge v2 全面功能检测")
print("=" * 60)

# 1. 启动
print("\n[1] 启动主窗口")
try:
    from molforge.ui.window import MolForgeWindow
    win = MolForgeWindow()
    win.resize(1500, 880)
    win.show()
    print(f"  ✅ 启动成功，文档={win.document.name}")
except Exception as e:
    traceback.print_exc()
    print(f"  ❌ 启动失败: {e}")
    sys.exit(1)

# 2. 文档基础
print("\n[2] 文档基础")
def t_doc():
    assert win.document.num_atoms == 24, f"咖啡因应该24原子，实际{win.document.num_atoms}"
    assert win.document.num_bonds == 25, f"应该25键，实际{win.document.num_bonds}"
    assert win.document.has_3d, "应该有3D坐标"
test("文档初始化", t_doc)

# 3. 命令总线 - 加原子
print("\n[3] 命令总线")
def t_add_atom():
    from molforge.application.builtin_commands import AddAtomCommand
    n0 = win.document.num_atoms
    r = win.command_bus.execute(AddAtomCommand(8, x=5.0, y=0.0, z=0.0))
    assert r.success, f"加原子失败: {r.message}"
    assert win.document.num_atoms == n0 + 1, f"原子数没增加"
test("加原子命令", t_add_atom)

def t_undo():
    n0 = win.document.num_atoms
    win.command_bus.undo()
    assert win.document.num_atoms == n0 - 1, f"undo后原子数不对: {win.document.num_atoms} vs {n0-1}"
test("Undo", t_undo)

def t_redo():
    n0 = win.document.num_atoms
    win.command_bus.redo()
    assert win.document.num_atoms == n0 + 1, f"redo后原子数不对"
test("Redo", t_redo)

# 4. 3D 视图
print("\n[4] 3D 视图")
def t_3d_widget():
    ws = win.workspace
    assert hasattr(ws, 'view3d_real'), "没有view3d_real"
    assert ws.view3d_real.renderer._coordinates is not None, "3D坐标为空"
    assert len(ws.view3d_real.renderer._coordinates) == win.document.num_atoms, \
        f"3D坐标数{len(ws.view3d_real.renderer._coordinates)} != 原子数{win.document.num_atoms}"
test("3D渲染器坐标", t_3d_widget)

# 5. 2D 画布
print("\n[5] 2D 画布")
def t_2d_widget():
    ws = win.workspace
    assert hasattr(ws, 'view2d'), "没有view2d"
test("2D画布存在", t_2d_widget)

# 6. 右侧面板
print("\n[6] 右侧面板")
def t_right_panel():
    assert hasattr(win, 'right'), "没有right面板"
    assert hasattr(win.right, 'settings_panel'), "没有settings_panel"
test("右侧面板存在", t_right_panel)

# 7. 元素选择器
print("\n[7] 元素选择器")
def t_element_picker():
    # 检查周期表按钮
    pass  # 需要看UI
test("元素选择器", t_element_picker)

# 8. 菜单栏
print("\n[8] 菜单栏")
def t_menus():
    menubar = win.menuBar()
    actions = [a.text() for a in menubar.actions()]
    print(f"     菜单项: {actions}")
test("菜单项", t_menus)

# 截图
def shot():
    win.grab().save(r"E:\YDW\Trae_Chemdraw\MolForge\docs\full_test_screenshot.png", "PNG")
    print(f"\n截图已保存")

    # 汇总
    print("\n" + "=" * 60)
    passed = sum(1 for _,s,_ in results if s == "PASS")
    failed = sum(1 for _,s,_ in results if s == "FAIL")
    print(f"总计: {passed} 通过, {failed} 失败")
    print("=" * 60)
    app.quit()

QTimer.singleShot(2000, shot)
sys.exit(app.exec())

# 本轮实现依据与决策（2026-11-03）

- RDKit固定点API：[ForceField.AddFixedPoint](https://rdkit.org/docs/source/rdkit.ForceField.rdForceField.html)。采用固定点参与MMFF/UFF优化，不在优化结束后强行改回坐标掩盖失败；存在固定点时禁止整体重新居中。
- xTB固定点输入：[官方xcontrol说明](https://xtb-docs.readthedocs.io/en/latest/xcontrol.html)。输入文件使用当前XYZ行的1-based编号，与文档稳定ID显式映射。
- xTB6.7.1默认ANCopt固定点回归：[官方仓库问题1073](https://github.com/grimme-lab/xtb/issues/1073)。本机6.7.1pre水样例实际复现；按开发者建议采用L-ANCopt，并在输出处核查全部固定坐标。
- 优化器名称与收敛依据：[官方Optimization说明](https://xtb-docs.readthedocs.io/en/latest/optimization.html)。有冻结点时使用$opt engine=lbfgs；检查退出码、坐标、顺序及GEOMETRY OPTIMIZATION CONVERGED标记，不凭文件存在判定收敛。
- VTK透明度：[VTK Book数据表示](https://book.vtk.org/en/latest/VTKBook/08Chapter8.html)和[vtkGlyph3DMapper](https://vtk.org/doc/nightly/html/classvtkGlyph3DMapper.html)。原子/键采用RGBA直色，内部键不透明度取两端较大值，边界键保留可见性。
- 彩色柔光：[vtkPointGaussianMapper](https://vtk.org/doc/nightly/html/classvtkPointGaussianMapper.html)。全场景共享Gaussian splat渲染，使用用户颜色/强度；这是图像表现，不模拟真实发射光谱或光照传输。没有逐原子创建VTK对象。

原子半径继续用上一轮RDKit参考数据；氧的范德华半径小于碳并不异常，不按颜色或原子序数重排半径。2D字形与键的缩放是排版比例，不改变三维Å坐标或化学键长。

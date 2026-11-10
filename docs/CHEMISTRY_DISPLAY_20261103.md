# 半径、键长与显示尺度调研及实现（2026-11-03）

原子没有唯一的硬球边界。范德华半径适合空间填充，共价半径适合估计成键接触；
同一元素的有效半径与键长还取决于化学环境、键级、电荷和配位状态。
本轮不能将一个常数表等同于完整量子化学理论。

## 一手来源

- RDKit PeriodicTable Python API：
  https://rdkit.org/new_docs/source/rdkit.Chem.PeriodicTable.html
- RDKit C++ reference：
  https://www.rdkit.org/new_docs/cppapi/classRDKit_1_1PeriodicTable.html
- Cordero 等，共价半径研究 Covalent radii revisited，Dalton Trans. 2008，DOI 10.1039/B801115J：
  https://pubs.rsc.org/en/content/articlelanding/2008/dt/b801115j/unauth
- IUPAC 共价键术语： https://goldbook.iupac.org/terms/view/C01384
- IUPAC 教学资料原子大小： https://old.iupac.org/didac/Didac%20Eng/Didac04/Content/CB10.htm

## 实现选择与限制

从本机已安装 RDKit 2026.09.1（文件内保留精确版本字符串）导出118元素参考值，
存为 molforge/domain/element_reference.json，领域层使用标准库读取，不增加运行时导入。
周期表和VTK共用同一来源，取消只有14元素的独立半径表和其他元素统一1.65Å的回退。
参考表含估计或默认值，尤其重元素，不将所有数据宣称为实验实测。原子量同步采用该参考表，
对无稳定同位素元素的数值不能理解为天然标准原子量。其他旧表字段未在本轮全部考据。

CPK/空间填充基础比例由0.90改为1.00；在全局与单原子显示缩放均为1时，球半径就是表中
范德华半径（Å）。球棍保留0.25倍示意球半径，帮助看到键；用户调节显示大小后不再是绝对物理尺度。
键管粗细是视觉参数，不是实际键长或电子密度分布。切换显示模式不改变导入坐标。

新建原子、拖拽生长、缺失坐标补点和弹簧回退使用共价半径和作为单键初值，
双/三键使用0.87/0.78经验收缩、芳香使用0.93。收缩因子是本程序启发式，
不是上列论文给出的普适定律。例如C–F约1.33Å、C–Cl约1.78Å；实际环境需优化验证。
现有环模板仍采用理想多边形模板，不能当作精确异原子环优化构型。
MMFF/UFF或量子优化及可靠输入构型优先；本轮未实现完整价态/配位/轨道理论计算引擎。

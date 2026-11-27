# Engineering Rules — AI 或人工贡献都必须遵守

1. Domain/Application 不得 import GUI/VTK/Mol*/LLM 提供商；基础设施接口放在 application/ports。
2. UI 只发 Commands/Queries，不直接修改 RDKit Mol 或操纵 GPU 数据模型。
3. 一份文档只有一个化学真相源；RDKit、VTK、Mol* 的 ID 映射是明确的适配层。
4. 不得在 GUI 线程做文件解析、轨迹解码、量子化学计算。
5. 不创建逐原子的 Python/VTK 图形对象，不允许逐帧重新建全场景。
6. 不得生成无测试的批量硬编码处理逻辑；功能通过独立 service/adapter 扩展。
7. 未经用户同意，AI 不得修改文件、删除分子、提交昂贵计算或执行 shell。
8. 科学数值、单位、坐标系、化学键型不允许被渲染展示层隐式修改。
9. 每新增依赖先记录许可证、版本、来源、打包影响，再合并代码。
10. 所有公共 API 有类型注解与错误类型；日志有 document_id/job_id/revision。
11. Git PR 需要 ruff、类型检查、pytest、必要的截图回归和性能对照；Windows 打包 smoke test。
12. 非必要不追求文件行数绝对上限，但单文件不能积累多个无关职责；重要决策保存 ADR。

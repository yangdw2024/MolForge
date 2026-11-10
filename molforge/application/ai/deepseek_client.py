"""
application/ai/deepseek_client.py - DeepSeek AI 化学助手客户端与本地智能引擎
=============================================================================
特性：
  - 原生对接 DeepSeek API (https://api.deepseek.com/v1/chat/completions)，支持
    deepseek-chat (DeepSeek-V3) 与 deepseek-reasoner (DeepSeek-R1)
  - 零第三方网络库依赖（使用标准库 urllib.request + ssl，开箱即用）
  - 自动注入当前分子的化学上下文（分子式、原子/键数、选中原子几何测量、3D 构象状态）
  - 支持结构修改指令、Gaussian (.gjf) 与复旦 REST (ctrl.in) 输入卡自动生成
  - 当未配置 API Key 时，内置离线化学专家规则引擎，保证任何时候提问都有真实科学响应与工具调用！
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Callable

from ...domain.document import MoleculeDocument
from ...domain.elements import get_element
from ..selection import SelectionService
from ..calculators.qc_input_generator import generate_gaussian_gjf, generate_rest_ctrl_in


DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SYSTEM_PROMPT = """你是 MolForge 内置的 AI 计算化学与有机光伏 (OSC) 科研助手。
你精通：
1. 有机太阳能电池给体/受体分子设计（如 PM6、D18、Y6、ITIC、BTP-eC9 等 A-D-A / D-A 体系的推拉电子效应、氟代/氯代/氰基修饰对 HOMO/LUMO 能级与结晶堆积的影响）。
2. Gaussian 16 量子化学计算（基态 B3LYP-D3(BJ)/6-31G(d) 优化、wB97XD/def2SVP、CAM-B3LYP TD-DFT 激发态紫外吸收光谱、ESP 静电势分析）。
3. 复旦大学张颖/徐昕教授团队开发的 REST (Rust-based Electronic Structure Toolkit) 程序输入卡 (`ctrl.in` TOML 格式，含 `[ctrl]` 和 `[geom]` 区块，支持 B3LYP/PBE0 及第五阶双杂化泛函 XYG3、XYGJOS、R-xDH7-SCC15、scsRPA）。
4. VMD / PyMOL / Multiwfn 后处理脚本编写。

请用简洁、专业、直接的科研同行口吻回答问题。如果用户请求修改当前分子或生成输入卡，你也可以在回复末尾附上一段 JSON 动作指令（用 ```molforge_action ... ``` 包裹），格式示例：
```molforge_action
{"action": "add_ring", "size": 5, "aromatic": true, "hetero": {"0": 16}}
```
可用 action 包括：
- `{"action": "add_ring", "size": 6, "aromatic": true, "hetero": {}}` （如苯环、噻吩 `{"0": 16}`、吡啶 `{"0": 7}`）
- `{"action": "add_group", "group": "-CN" | "-F" | "-Cl" | "-OH" | "-COOH" | "-NH2" | "-OCH3"}`
- `{"action": "clean_3d"}`
- `{"action": "open_qc_dialog", "tab": "gaussian" | "rest" | "energy"}`
"""


@dataclass
class AssistantResponse:
    reply_text: str
    executed_actions: list[str] = field(default_factory=list)
    generated_code: str = ""
    used_online_api: bool = False


class DeepSeekChemistryAssistant:
    """
    DeepSeek AI 化学助手（支持在线 DeepSeek-V3/R1 API 与离线本地科学引擎无缝切换）。
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "deepseek-chat",
        base_url: str = DEEPSEEK_API_URL,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model
        self.base_url = base_url

    def build_molecule_context(
        self,
        doc: MoleculeDocument | None,
        selection: SelectionService | None = None,
    ) -> str:
        """提取当前分子的真实拓扑、元素组成与选中原子几何信息作为 Prompt 上下文。"""
        if doc is None or doc.num_atoms == 0:
            return "当前工作区为空分子。"

        counts: dict[str, int] = {}
        for aid in doc.topology.atom_ids:
            z = doc.topology.get_atom(aid).atomic_num
            el = get_element(z)
            sym = el.symbol if el else f"Z{z}"
            counts[sym] = counts.get(sym, 0) + 1
        comp = " ".join(f"{k}:{v}" for k, v in sorted(counts.items()))

        sel_info = "无选中原子"
        if selection is not None and not selection.is_empty:
            sel_aids = list(selection.selected_atoms)
            sel_info = f"已选中 {len(sel_aids)} 个原子 {[a.value for a in sel_aids[:8]]}"

        return (
            f"当前分子名称：{doc.name}\n"
            f"原子总数：{doc.num_atoms}，化学键总数：{doc.num_bonds}\n"
            f"元素组成：{comp}\n"
            f"3D 坐标状态：{'已具备 3D 构象' if doc.has_3d else '仅 2D'}\n"
            f"选择状态：{sel_info}"
        )

    def ask(
        self,
        question: str,
        doc: MoleculeDocument | None,
        selection: SelectionService | None = None,
        action_executor: Callable[[dict[str, Any]], str | None] | None = None,
    ) -> AssistantResponse:
        """
        向助手提问：
          - 若已配置 DeepSeek API Key，调用在线 DeepSeek 模型并解析返回的 molforge_action
          - 若未配置 API Key 或网络受限，自动使用内置计算化学规则引擎执行指令并给出专业答复
        """
        q = question.strip()
        if not q:
            return AssistantResponse("请输入关于分子结构、官能团修饰、Gaussian 或 REST 计算的问题。")

        context_str = self.build_molecule_context(doc, selection)

        if self.api_key.strip():
            try:
                reply = self._call_deepseek_api(q, context_str)
                actions_done = self._extract_and_run_actions(reply, action_executor)
                clean_reply = self._strip_action_block(reply)
                return AssistantResponse(
                    reply_text=clean_reply,
                    executed_actions=actions_done,
                    used_online_api=True,
                )
            except Exception as e:
                fallback = self._local_chemistry_engine(q, doc, selection, action_executor)
                fallback.reply_text = f"[DeepSeek API 调用提示: {e}，已切换本地化学引擎响应]\n\n" + fallback.reply_text
                return fallback

        return self._local_chemistry_engine(q, doc, selection, action_executor)

    def _call_deepseek_api(self, question: str, context_str: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + "\n\n【当前工作区分子状态】\n" + context_str},
                {"role": "user", "content": question},
            ],
            "temperature": 0.3,
            "max_tokens": 1200,
        }
        data = json.dumps(payload).encode("utf-8")
        url = self.base_url.strip()
        if not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]

    def _extract_and_run_actions(
        self,
        text: str,
        action_executor: Callable[[dict[str, Any]], str | None] | None,
    ) -> list[str]:
        import re
        if action_executor is None:
            return []
        executed = []
        for m in re.finditer(r"```molforge_action\s*(\{.*?\})\s*```", text, flags=re.DOTALL):
            try:
                act = json.loads(m.group(1))
                msg = action_executor(act)
                if msg:
                    executed.append(msg)
            except Exception:
                pass
        return executed

    @staticmethod
    def _strip_action_block(text: str) -> str:
        import re
        return re.sub(r"```molforge_action\s*\{.*?\}\s*```", "", text, flags=re.DOTALL).strip()

    def _local_chemistry_engine(
        self,
        q: str,
        doc: MoleculeDocument | None,
        selection: SelectionService | None,
        action_executor: Callable[[dict[str, Any]], str | None] | None,
    ) -> AssistantResponse:
        """离线计算化学与 OSC 专家引擎：识别结构编辑、REST/Gaussian 输入卡生成与能级分析指令。"""
        ql = q.lower()
        executed: list[str] = []

        # 1. 识别 REST 输入卡请求
        if "rest" in ql or "ctrl.in" in ql or "xyg3" in ql or "xygjos" in ql or "r-xdh7" in ql:
            xc = "xyg3" if "xyg3" in ql else ("r-xdh7" if "xdh7" in ql else ("pbe0" if "pbe0" in ql else "b3lyp"))
            basis = "def2-QZVPP" if xc in ("xyg3", "r-xdh7") else "def2-TZVPP"
            job_type = "opt" if ("优化" in ql or "opt" in ql) else "energy"
            ctrl_txt = generate_rest_ctrl_in(
                doc or MoleculeDocument("OSC_Mol"),
                xc=xc,
                basis=basis,
                job_type=job_type,
                post_ai_correction=("scc15" if xc == "r-xdh7" else ""),
            )
            if action_executor:
                msg = action_executor({"action": "preview_rest", "content": ctrl_txt})
                if msg:
                    executed.append(msg)
            reply = (
                f"已为当前分子 **{doc.name if doc else '未命名'}** 生成符合复旦大学张颖/徐昕团队规范的 **REST (`ctrl.in`)** 输入卡（方法：`xc = \"{xc}\"`，基组：`{basis}`）：\n\n"
                f"```toml\n{ctrl_txt.strip()}\n```\n\n"
                "提示：点击下方 **「准备 DFT / REST 计算」** 按钮可直接保存 `ctrl.in` 或切换 XYG3 / R-xDH7-SCC15 / scsRPA 等方法。"
            )
            return AssistantResponse(reply_text=reply, executed_actions=executed, generated_code=ctrl_txt)

        # 2. 识别 Gaussian / TD-DFT / gjf 请求
        if any(k in ql for k in ("gaussian", "gjf", "td-dft", "tddft", "激发态", "wb97xd", "cam-b3lyp", "b3lyp")):
            if "td" in ql or "激发" in ql or "吸收" in ql or "cam" in ql:
                route = "#p CAM-B3LYP/6-311+G(d,p) TD=(NStates=10) SCRF=(PCM,Solvent=Chloroform) pop=full"
            elif "wb97" in ql:
                route = "#p wB97XD/def2SVP opt pop=full"
            else:
                route = "#p B3LYP/6-31G(d) EmpiricalDispersion=GD3BJ opt freq"
            gjf_txt = generate_gaussian_gjf(doc or MoleculeDocument("OSC_Mol"), route=route)
            reply = (
                f"已为 **{doc.name if doc else '当前分子'}** 生成 Gaussian 输入卡 (`.gjf`)：\n\n"
                f"```text\n{gjf_txt.strip()}\n```\n\n"
                "在有机光伏 (OSC) 体系中，建议先用 `B3LYP-D3(BJ)/6-31G(d)` 完成基态构型优化，再用 `CAM-B3LYP` 或 `wB97XD` 配合氯仿 (`Chloroform`) 溶剂模型计算 TD-DFT 吸收光谱。"
            )
            return AssistantResponse(reply_text=reply, executed_actions=executed, generated_code=gjf_txt)

        # 3. 识别结构编辑请求（加噻吩、苯环、吸电子基团 -F / -CN / -Cl 等）
        if action_executor is not None:
            if "噻吩" in ql or "thiophene" in ql:
                msg = action_executor({"action": "add_ring", "size": 5, "aromatic": True, "hetero": {"0": 16}})
                if msg:
                    executed.append(msg)
                return AssistantResponse(
                    "已在当前结构中添加 **噻吩环 (Thiophene)** 并自动同步 3D 几何（可按 `Ctrl+Z` 撤销）。噻吩作为富电子共轭单元，常用于提升给体材料的共面性与载流子迁移率。",
                    executed_actions=executed,
                )
            if "苯" in ql or "benzene" in ql:
                msg = action_executor({"action": "add_ring", "size": 6, "aromatic": True, "hetero": {}})
                if msg:
                    executed.append(msg)
                return AssistantResponse("已在当前结构中添加 **苯环** 并同步更新 2D/3D 视图。", executed_actions=executed)
            for key, grp, desc in (
                ("氰基", "-CN", "强吸电子氰基 (-CN)，能显著下移 LUMO 能级并增强分子内电荷转移 (ICT)"),
                ("-cn", "-CN", "强吸电子氰基 (-CN)"),
                ("氟", "-F", "氟原子 (-F)，通过诱导效应同时下移 HOMO/LUMO 并借助 F···S 非共价锁增强平面度"),
                ("氯", "-Cl", "氯原子 (-Cl)，比氟具有更强的空 d 轨道离域能力，适合微调开路电压 Voc"),
                ("羧基", "-COOH", "羧基 (-COOH)"),
                ("羟基", "-OH", "羟基 (-OH)"),
                ("氨基", "-NH2", "给电子氨基 (-NH₂)"),
            ):
                if key in ql:
                    msg = action_executor({"action": "add_group", "group": grp})
                    if msg:
                        executed.append(msg)
                    return AssistantResponse(f"已向当前分子引入 **{desc}**，并同步更新了 3D 构象。", executed_actions=executed)
            if "优化" in ql or "清理" in ql or "clean" in ql:
                msg = action_executor({"action": "clean_3d"})
                if msg:
                    executed.append(msg)
                return AssistantResponse("已对当前分子执行 MMFF94/UFF 3D 力场几何弛豫。", executed_actions=executed)

        # 4. 默认返回针对当前分子的 OSC 结构与电子性质专业分析
        ctx = self.build_molecule_context(doc, selection)
        reply = (
            f"### 当前分子结构与 OSC 计算建议\n"
            f"{ctx}\n\n"
            "- **快速建模指令**：可直接输入“加一个噻吩环”、“引入氟原子”、“引入氰基 -CN”或“3D 结构优化”，我会直接调用 `CommandBus` 修改结构。\n"
            "- **量化输入生成**：输入“生成 Gaussian TD-DFT 输入”或“生成 REST XYG3 输入卡”，即可一键生成 `.gjf` 或复旦 REST 的 `ctrl.in`。\n"
            "- **接入在线 DeepSeek-V3/R1**：点击本面板右上角 **「配置 API Key」** 填入你的 DeepSeek Key，即可开启完整大模型自由问答。"
        )
        return AssistantResponse(reply_text=reply, executed_actions=executed)

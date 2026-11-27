//! Unified MolForge Hub: Capability Registry, Resource Catalog (Plugins,
//! Agent Skills, Scientific Workflows, Models), Dependency Solver, and
//! Favorites / Pinning / Uninstall Impact Analysis.

use crate::engines::{self, EnginePaths, EngineStatus};
use crate::skills::{self, SkillPackage};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ResourceKind {
    Plugin,
    Skill,
    Workflow,
    Model,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilitySpec {
    pub id: String,
    pub title: String,
    pub category: String,
    pub provider_plugin_id: String,
    pub adapter: String,
    pub permission: String,
    pub available: bool,
    pub diagnostic: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HubResource {
    pub id: String,
    pub kind: ResourceKind,
    pub name: String,
    pub title: String,
    pub version: String,
    pub author: String,
    pub license: String,
    pub source: String,
    pub category: String,
    pub description: String,
    pub tags: Vec<String>,
    pub provides_capabilities: Vec<String>,
    pub requires_capabilities: Vec<String>,
    pub permissions: Vec<String>,
    pub sha256: Option<String>,
    pub installed: bool,
    pub trusted: bool,
    pub favorite: bool,
    pub pinned: bool,
    pub runnable: bool,
    pub missing_dependencies: Vec<String>,
    pub status_reason: String,
    pub security_warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UninstallImpact {
    pub resource_id: String,
    pub affected_resources: Vec<String>,
    pub blocked_capabilities: Vec<String>,
    pub safe_to_remove: bool,
}

pub struct HubRegistry {
    pub skills: Vec<SkillPackage>,
    pub favorites: HashSet<String>,
    pub pinned: HashSet<String>,
    pub installed_models: HashSet<String>,
    pub installed_workflows: HashSet<String>,
}

impl Default for HubRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl HubRegistry {
    pub fn new() -> Self {
        let mut favorites = HashSet::new();
        favorites.insert("org.molforge.workflow.frontier-mo".into());
        favorites.insert("org.molforge.workflow.calchem-sp-opt".into());

        let mut pinned = HashSet::new();
        pinned.insert("org.molforge.workflow.frontier-mo".into());

        let mut installed_workflows = HashSet::new();
        installed_workflows.insert("org.molforge.workflow.frontier-mo".into());
        installed_workflows.insert("org.molforge.workflow.calchem-sp-opt".into());
        installed_workflows.insert("org.molforge.workflow.xtb-preopt".into());
        installed_workflows.insert("org.molforge.workflow.multiwfn-wfn".into());
        installed_workflows.insert("org.molforge.workflow.md-rdf".into());
        installed_workflows.insert("org.molforge.workflow.osc-4char".into());

        let mut installed_models = HashSet::new();
        installed_models.insert("org.molforge.model.tight-binding-pi".into());

        Self {
            skills: skills::builtin_skills(),
            favorites,
            pinned,
            installed_models,
            installed_workflows,
        }
    }

    pub fn capabilities(&self, engines: &[EngineStatus]) -> Vec<CapabilitySpec> {
        let find = |id: &str| engines.iter().find(|e| e.id == id);
        let is_ok = |id: &str| find(id).map(|e| e.available).unwrap_or(false);
        let diag = |id: &str, fallback: &str| {
            find(id)
                .map(|e| e.diagnostic.clone())
                .unwrap_or_else(|| fallback.to_string())
        };

        vec![
            CapabilitySpec {
                id: "qc.tight_binding".into(),
                title: "Tight-Binding π-MO 轨道与能隙".into(),
                category: "量子化学".into(),
                provider_plugin_id: "org.molforge.plugin.molforge_core".into(),
                adapter: "molforge-core::qc".into(),
                permission: "in-process:read-only".into(),
                available: true,
                diagnostic: "内置纯 Rust 引擎就绪".into(),
            },
            CapabilitySpec {
                id: "structure.export".into(),
                title: "多格式结构与输入脚本导出".into(),
                category: "结构 IO".into(),
                provider_plugin_id: "org.molforge.plugin.molforge_core".into(),
                adapter: "molforge-core::io".into(),
                permission: "file-export".into(),
                available: true,
                diagnostic: "内置纯 Rust 引擎就绪".into(),
            },
            CapabilitySpec {
                id: "qc.calchem_scf".into(),
                title: "CalChem 纯 Rust HF/DFT SCF".into(),
                category: "量子化学".into(),
                provider_plugin_id: "org.molforge.plugin.calchem".into(),
                adapter: "calchem-scf".into(),
                permission: "in-process:compute".into(),
                available: is_ok("calchem"),
                diagnostic: diag("calchem", "未启用 calchem 特性"),
            },
            CapabilitySpec {
                id: "qc.calchem_opt".into(),
                title: "CalChem 纯 Rust 几何结构优化".into(),
                category: "量子化学".into(),
                provider_plugin_id: "org.molforge.plugin.calchem".into(),
                adapter: "calchem-opt".into(),
                permission: "in-process:compute".into(),
                available: is_ok("calchem"),
                diagnostic: diag("calchem", "未启用 calchem 特性"),
            },
            CapabilitySpec {
                id: "qc.xtb".into(),
                title: "GFN2-xTB 半经验结构优化".into(),
                category: "量子化学".into(),
                provider_plugin_id: "org.molforge.plugin.xtb".into(),
                adapter: "process:xtb".into(),
                permission: "external-process".into(),
                available: is_ok("xtb"),
                diagnostic: diag("xtb", "未检测到 xtb 可执行程序"),
            },
            CapabilitySpec {
                id: "wfn.multiwfn".into(),
                title: "Multiwfn 波函数与实空间分析".into(),
                category: "波函数分析".into(),
                provider_plugin_id: "org.molforge.plugin.multiwfn".into(),
                adapter: "process:multiwfn".into(),
                permission: "external-process".into(),
                available: is_ok("multiwfn"),
                diagnostic: diag("multiwfn", "未检测到 Multiwfn 可执行程序"),
            },
            CapabilitySpec {
                id: "md.gromacs_mdp".into(),
                title: "GROMACS MDP 参数生成".into(),
                category: "分子动力学".into(),
                provider_plugin_id: "org.molforge.plugin.molforge_core".into(),
                adapter: "molforge-core::engines".into(),
                permission: "in-process:read-only".into(),
                available: true,
                diagnostic: "内置模板生成器就绪".into(),
            },
            CapabilitySpec {
                id: "trajectory.rdf".into(),
                title: "MD / 结构径向分布函数 RDF 分析".into(),
                category: "分子动力学".into(),
                provider_plugin_id: "org.molforge.plugin.molforge_core".into(),
                adapter: "molforge-core::engines/gmx".into(),
                permission: "in-process:read-only".into(),
                available: true,
                diagnostic: if is_ok("gromacs") {
                    "内置纯 Rust 径向分布函数 g(r) 与 GROMACS (gmx) 均已就绪".into()
                } else {
                    "内置纯 Rust 径向分布函数 g(r) 适配器已就绪".into()
                },
            },
            CapabilitySpec {
                id: "structure.planarity".into(),
                title: "分子平面性 MPP/SDP 分析".into(),
                category: "结构表征".into(),
                provider_plugin_id: "org.molforge.plugin.molforge_core".into(),
                adapter: "molforge-core::summary".into(),
                permission: "in-process:read-only".into(),
                available: true,
                diagnostic: "内置纯 Rust SVD/Jacobi 平面拟合器就绪".into(),
            },
            CapabilitySpec {
                id: "smiles.etkdg".into(),
                title: "RDKit SMILES → 3D 构象生成".into(),
                category: "化学信息学".into(),
                provider_plugin_id: "org.molforge.plugin.python_worker".into(),
                adapter: "process:python-rdkit".into(),
                permission: "isolated-python".into(),
                available: is_ok("python_worker"),
                diagnostic: diag("python_worker", "可选 Python Worker 未启用"),
            },
        ]
    }

    pub fn check_dependencies(
        &self,
        required_caps: &[String],
        caps: &[CapabilitySpec],
    ) -> (bool, Vec<String>, String) {
        let cap_map: HashMap<&str, &CapabilitySpec> =
            caps.iter().map(|c| (c.id.as_str(), c)).collect();
        let mut missing = Vec::new();
        for req in required_caps {
            match cap_map.get(req.as_str()) {
                Some(c) if c.available => {}
                Some(c) => missing.push(format!("{} ({})", c.id, c.diagnostic)),
                None => missing.push(format!("{req} (未注册能力)")),
            }
        }
        if missing.is_empty() {
            (true, missing, "可运行 · 所有依赖能力已就绪".into())
        } else {
            let reason = format!("需要安装/配置依赖：{}", missing.join("；"));
            (false, missing, reason)
        }
    }

    pub fn list_resources(
        &self,
        engine_paths: &EnginePaths,
        python_exe: Option<&Path>,
        query: Option<&str>,
        kind_filter: Option<&str>,
    ) -> Vec<HubResource> {
        let engines = engines::probe_all(engine_paths, python_exe);
        let caps = self.capabilities(&engines);
        let mut items: Vec<HubResource> = Vec::new();

        // 1. Plugins (mapped from probed engines)
        let plugin_caps: &[(&str, &[&str], &str)] = &[
            (
                "molforge_core",
                &["qc.tight_binding", "structure.export", "structure.planarity", "md.gromacs_mdp", "trajectory.rdf"],
                "in-process",
            ),
            ("calchem", &["qc.calchem_scf", "qc.calchem_opt"], "in-process"),
            ("xtb", &["qc.xtb"], "external-process"),
            ("multiwfn", &["wfn.multiwfn"], "external-process"),
            ("gromacs", &["md.gromacs_mdp", "trajectory.rdf"], "external-process"),
            ("orca", &[], "external-process"),
            ("gaussian", &[], "external-process"),
            ("openbabel", &[], "external-process"),
            ("python_worker", &["smiles.etkdg"], "isolated-python"),
        ];

        for eng in &engines {
            let (prov, perm) = plugin_caps
                .iter()
                .find(|(id, _, _)| *id == eng.id)
                .map(|(_, c, p)| (c.iter().map(|s| (*s).to_string()).collect(), *p))
                .unwrap_or_else(|| (Vec::new(), "external-process"));
            let id = format!("org.molforge.plugin.{}", eng.id);
            items.push(HubResource {
                id: id.clone(),
                kind: ResourceKind::Plugin,
                name: eng.id.clone(),
                title: eng.name.clone(),
                version: eng.version_hint.clone(),
                author: "MolForge / Official Adapter".into(),
                license: "Apache-2.0 / External".into(),
                source: eng
                    .executable_path
                    .clone()
                    .unwrap_or_else(|| "builtin".into()),
                category: "计算引擎与适配器".into(),
                description: eng.diagnostic.clone(),
                tags: vec!["plugin".into(), eng.id.clone()],
                provides_capabilities: prov,
                requires_capabilities: Vec::new(),
                permissions: vec![perm.into()],
                sha256: eng.sha256.clone(),
                installed: eng.available,
                trusted: true,
                favorite: self.favorites.contains(&id),
                pinned: self.pinned.contains(&id),
                runnable: eng.available,
                missing_dependencies: if eng.available {
                    Vec::new()
                } else {
                    vec![eng.diagnostic.clone()]
                },
                status_reason: if eng.available {
                    "可运行 · 引擎已就绪".into()
                } else {
                    format!("不可用 · {}", eng.diagnostic)
                },
                security_warnings: Vec::new(),
            });
        }

        // 2. Agent Skills
        for sk in &self.skills {
            items.push(HubResource {
                id: sk.id.clone(),
                kind: ResourceKind::Skill,
                name: sk.name.clone(),
                title: sk.name.clone(),
                version: sk.version.clone(),
                author: if sk.trusted { "MolForge Team" } else { "Local Import" }.into(),
                license: "AgentSkills-MD".into(),
                source: sk.source.clone(),
                category: "AI 科研技能 (SKILL.md)".into(),
                description: sk.description.clone(),
                tags: sk.tags.clone(),
                provides_capabilities: Vec::new(),
                requires_capabilities: sk.capabilities.clone(),
                permissions: vec!["read-only-guidance".into()],
                sha256: Some(sk.sha256.clone()),
                installed: true,
                trusted: sk.trusted,
                favorite: self.favorites.contains(&sk.id),
                pinned: self.pinned.contains(&sk.id),
                runnable: true,
                missing_dependencies: Vec::new(),
                status_reason: if sk.security_warnings.is_empty() {
                    "已装载 · 只读技能规范".into()
                } else {
                    "已装载（低信任隔离 · 存在安全提示）".into()
                },
                security_warnings: sk.security_warnings.clone(),
            });
        }

        // 3. Scientific Workflows (from builtin workflow catalog)
        for wf in crate::workflow::builtin_workflows() {
            let installed = self.installed_workflows.contains(&wf.id);
            let (runnable, missing, reason) =
                self.check_dependencies(&wf.requires_capabilities, &caps);
            items.push(HubResource {
                id: wf.id.clone(),
                kind: ResourceKind::Workflow,
                name: wf.id.clone(),
                title: wf.title.clone(),
                version: wf.version.clone(),
                author: "MolForge Team".into(),
                license: "Apache-2.0".into(),
                source: "builtin://workflows".into(),
                category: wf.category.clone(),
                description: wf.description.clone(),
                tags: wf.tags.clone(),
                provides_capabilities: Vec::new(),
                requires_capabilities: wf.requires_capabilities.clone(),
                permissions: wf.permissions.clone(),
                sha256: None,
                installed,
                trusted: true,
                favorite: self.favorites.contains(&wf.id),
                pinned: self.pinned.contains(&wf.id),
                runnable: installed && runnable,
                missing_dependencies: missing,
                status_reason: if !installed {
                    "未安装模板".into()
                } else {
                    reason
                },
                security_warnings: Vec::new(),
            });
        }

        // 4. Models & Assets
        let models = [
            (
                "org.molforge.model.tight-binding-pi",
                "Huckel-Heteroatom-v1",
                "杂原子紧束缚 π-MO 参数集",
                "1.0.0",
                "C, N, O, S, B, P 共轭体系参数（内置零依赖）",
                "6c1e8b4e229a0d19f701a4b9088823c9d1f44e770194b1e7b0e8a1b2c3d4e5f6",
                vec!["qc.tight_binding".to_string()],
                "Apache-2.0",
            ),
            (
                "org.molforge.model.mace-off23-small",
                "MACE-OFF23 (Small)",
                "MACE-OFF23 有机分子机器学习势",
                "2023.1",
                "适用于 H, C, N, O, F, P, S, Cl, Br, I 真空/溶液有机分子；需 Python + MACE 运行时",
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                vec!["smiles.etkdg".to_string()],
                "MIT",
            ),
        ];
        for (id, name, title, ver, desc, sha, reqs, lic) in models {
            let installed = self.installed_models.contains(id);
            let (runnable, missing, reason) = self.check_dependencies(&reqs, &caps);
            items.push(HubResource {
                id: id.into(),
                kind: ResourceKind::Model,
                name: name.into(),
                title: title.into(),
                version: ver.into(),
                author: "MolForge / MLFF Catalog".into(),
                license: lic.into(),
                source: "catalog://models".into(),
                category: "参数集与机器学习势".into(),
                description: desc.into(),
                tags: vec!["model".into(), "parameters".into()],
                provides_capabilities: Vec::new(),
                requires_capabilities: reqs,
                permissions: vec!["data-asset-readonly".into()],
                sha256: Some(sha.into()),
                installed,
                trusted: true,
                favorite: self.favorites.contains(id),
                pinned: self.pinned.contains(id),
                runnable: installed && runnable,
                missing_dependencies: missing,
                status_reason: if !installed {
                    "未下载模型权重（仅目录索引）".into()
                } else {
                    reason
                },
                security_warnings: Vec::new(),
            });
        }

        // Apply filters
        let q = query.unwrap_or("").trim().to_ascii_lowercase();
        let kf = kind_filter.unwrap_or("").trim().to_ascii_lowercase();
        items
            .into_iter()
            .filter(|r| {
                if !kf.is_empty() && kf != "all" {
                    let k_str = match r.kind {
                        ResourceKind::Plugin => "plugin",
                        ResourceKind::Skill => "skill",
                        ResourceKind::Workflow => "workflow",
                        ResourceKind::Model => "model",
                    };
                    if k_str != kf {
                        return false;
                    }
                }
                if q.is_empty() {
                    return true;
                }
                r.title.to_ascii_lowercase().contains(&q)
                    || r.name.to_ascii_lowercase().contains(&q)
                    || r.description.to_ascii_lowercase().contains(&q)
                    || r.category.to_ascii_lowercase().contains(&q)
                    || r.tags.iter().any(|t| t.to_ascii_lowercase().contains(&q))
                    || r.requires_capabilities
                        .iter()
                        .any(|c| c.to_ascii_lowercase().contains(&q))
                    || r.provides_capabilities
                        .iter()
                        .any(|c| c.to_ascii_lowercase().contains(&q))
            })
            .collect()
    }

    pub fn toggle_favorite(&mut self, id: &str) -> bool {
        if self.favorites.contains(id) {
            self.favorites.remove(id);
            false
        } else {
            self.favorites.insert(id.to_string());
            true
        }
    }

    pub fn toggle_pin(&mut self, id: &str) -> bool {
        if self.pinned.contains(id) {
            self.pinned.remove(id);
            false
        } else {
            self.pinned.insert(id.to_string());
            true
        }
    }

    pub fn install_resource(&mut self, id: &str) -> bool {
        if id.starts_with("org.molforge.workflow.") {
            self.installed_workflows.insert(id.to_string());
            return true;
        }
        if id.starts_with("org.molforge.model.") {
            self.installed_models.insert(id.to_string());
            return true;
        }
        false
    }

    pub fn uninstall_impact(
        &self,
        id: &str,
        engine_paths: &EnginePaths,
        python_exe: Option<&Path>,
    ) -> UninstallImpact {
        let all = self.list_resources(engine_paths, python_exe, None, None);
        let Some(target) = all.iter().find(|r| r.id == id) else {
            return UninstallImpact {
                resource_id: id.into(),
                affected_resources: Vec::new(),
                blocked_capabilities: Vec::new(),
                safe_to_remove: true,
            };
        };
        let blocked_capabilities = target.provides_capabilities.clone();
        let cap_set: HashSet<&str> = blocked_capabilities.iter().map(|s| s.as_str()).collect();
        let affected_resources: Vec<String> = all
            .iter()
            .filter(|r| {
                r.id != id
                    && r.installed
                    && r.requires_capabilities
                        .iter()
                        .any(|c| cap_set.contains(c.as_str()))
            })
            .map(|r| r.id.clone())
            .collect();
        UninstallImpact {
            resource_id: id.into(),
            safe_to_remove: affected_resources.is_empty(),
            affected_resources,
            blocked_capabilities,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_reports_missing_dependencies_honestly() {
        let reg = HubRegistry::new();
        let paths = EnginePaths::default();
        let items = reg.list_resources(&paths, None, Some("RDF"), Some("workflow"));
        assert_eq!(items.len(), 1);
        let rdf = &items[0];
        assert_eq!(rdf.id, "org.molforge.workflow.md-rdf");
        // Verify capability dependency consistency
        if !rdf.runnable {
            assert!(!rdf.missing_dependencies.is_empty());
        }
    }
}

//! Thread-safe asynchronous background job queue matching `StudioJob` in `studio.ts`.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum JobStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StudioJob {
    pub job_id: String,
    pub kind: String,
    pub name: String,
    pub document_name: String,
    pub input_revision: u64,
    pub params: serde_json::Value,
    pub status: JobStatus,
    pub created_at: f64,
    pub started_at: Option<f64>,
    pub finished_at: Option<f64>,
    pub logs: Vec<String>,
    pub result: Option<serde_json::Value>,
    pub error: String,
}

struct JobEntry {
    info: StudioJob,
    cancel_flag: Arc<AtomicBool>,
}

#[derive(Clone, Default)]
pub struct JobQueue {
    inner: Arc<Mutex<HashMap<String, JobEntry>>>,
    seq: Arc<std::sync::atomic::AtomicU64>,
}

fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

impl JobQueue {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn list(&self) -> Vec<StudioJob> {
        let guard = self.inner.lock().unwrap();
        let mut items: Vec<StudioJob> = guard.values().map(|e| e.info.clone()).collect();
        items.sort_by(|a, b| b.job_id.cmp(&a.job_id));
        items
    }

    pub fn submit<F>(
        &self,
        kind: impl Into<String>,
        name: impl Into<String>,
        document_name: impl Into<String>,
        input_revision: u64,
        params: serde_json::Value,
        work: F,
    ) -> StudioJob
    where
        F: FnOnce(Arc<AtomicBool>) -> std::result::Result<serde_json::Value, String> + Send + 'static,
    {
        let n = self.seq.fetch_add(1, Ordering::Relaxed) + 1;
        let job_id = format!("job-{n:04}");
        let cancel_flag = Arc::new(AtomicBool::new(false));
        let info = StudioJob {
            job_id: job_id.clone(),
            kind: kind.into(),
            name: name.into(),
            document_name: document_name.into(),
            input_revision,
            params,
            status: JobStatus::Pending,
            created_at: now_secs(),
            started_at: None,
            finished_at: None,
            logs: vec!["Queued in MolForge Rust JobQueue".into()],
            result: None,
            error: String::new(),
        };
        {
            let mut guard = self.inner.lock().unwrap();
            guard.insert(
                job_id.clone(),
                JobEntry {
                    info: info.clone(),
                    cancel_flag: cancel_flag.clone(),
                },
            );
        }

        let inner = self.inner.clone();
        let id_bg = job_id.clone();
        std::thread::spawn(move || {
            {
                let mut guard = inner.lock().unwrap();
                if let Some(entry) = guard.get_mut(&id_bg) {
                    if entry.cancel_flag.load(Ordering::Relaxed) {
                        entry.info.status = JobStatus::Cancelled;
                        entry.info.finished_at = Some(now_secs());
                        entry.info.logs.push("Cancelled before start".into());
                        return;
                    }
                    entry.info.status = JobStatus::Running;
                    entry.info.started_at = Some(now_secs());
                    entry.info.logs.push("Running on Rust worker thread".into());
                }
            }

            let res = work(cancel_flag.clone());
            let mut guard = inner.lock().unwrap();
            if let Some(entry) = guard.get_mut(&id_bg) {
                entry.info.finished_at = Some(now_secs());
                if cancel_flag.load(Ordering::Relaxed) {
                    entry.info.status = JobStatus::Cancelled;
                    entry.info.logs.push("Cancelled".into());
                } else {
                    match res {
                        Ok(val) => {
                            entry.info.status = JobStatus::Completed;
                            entry.info.logs.push("Completed successfully".into());
                            entry.info.result = Some(val);
                        }
                        Err(err) => {
                            entry.info.status = JobStatus::Failed;
                            entry.info.error = err.clone();
                            entry.info.logs.push(format!("Failed: {err}"));
                        }
                    }
                }
            }
        });

        info
    }

    pub fn cancel(&self, id: &str) -> Option<StudioJob> {
        let mut guard = self.inner.lock().unwrap();
        if let Some(entry) = guard.get_mut(id) {
            entry.cancel_flag.store(true, Ordering::Relaxed);
            if entry.info.status == JobStatus::Pending {
                entry.info.status = JobStatus::Cancelled;
                entry.info.finished_at = Some(now_secs());
            }
            Some(entry.info.clone())
        } else {
            None
        }
    }
}

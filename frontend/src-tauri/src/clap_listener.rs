//! Clap-to-talk: runs `jarvis listen` as a child process of the desktop app.
//!
//! Running it as a child (instead of a launchd agent) matters on macOS: the
//! microphone permission is attributed to "OpenJarvis" itself rather than to
//! Terminal, and quitting the app stops the listener with it.

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;

use super::{ChildHandle, SharedStatus};

pub type SharedClap = Arc<Mutex<Option<ChildHandle>>>;

/// How long autostart waits for the Python environment to finish syncing.
const AUTOSTART_TIMEOUT: Duration = Duration::from_secs(20 * 60);
const AUTOSTART_POLL: Duration = Duration::from_secs(3);

fn prefs_path() -> std::path::PathBuf {
    std::path::PathBuf::from(super::home_dir())
        .join(".openjarvis")
        .join("desktop-prefs.json")
}

/// Whether the saved preferences ask for the listener to run.
pub(crate) fn parse_clap_pref(text: &str) -> bool {
    serde_json::from_str::<serde_json::Value>(text)
        .ok()
        .and_then(|v| v.get("clap_listener").and_then(|b| b.as_bool()))
        .unwrap_or(false)
}

/// Render the prefs file with `clap_listener` set, keeping any other keys.
pub(crate) fn render_clap_pref(enabled: bool, existing: Option<&str>) -> String {
    let mut value = existing
        .and_then(|text| serde_json::from_str::<serde_json::Value>(text).ok())
        .filter(|v| v.is_object())
        .unwrap_or_else(|| serde_json::json!({}));
    value["clap_listener"] = serde_json::Value::Bool(enabled);
    serde_json::to_string_pretty(&value).unwrap_or_else(|_| "{}".into())
}

pub(crate) fn read_clap_pref() -> bool {
    std::fs::read_to_string(prefs_path())
        .map(|text| parse_clap_pref(&text))
        .unwrap_or(false)
}

fn write_clap_pref(enabled: bool) -> Result<(), String> {
    let path = prefs_path();
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let existing = std::fs::read_to_string(&path).ok();
    std::fs::write(&path, render_clap_pref(enabled, existing.as_deref()))
        .map_err(|err| format!("Could not save desktop preferences: {}", err))
}

/// Build the `uv run jarvis listen` command. The Anthropic key (and any other
/// cloud keys) come from secure storage and are passed through the environment,
/// never written to disk.
pub(crate) fn listen_command(
    uv_bin: &str,
    root: &std::path::Path,
    cloud_keys: &[(String, String)],
) -> tokio::process::Command {
    let mut cmd = tokio::process::Command::new(uv_bin);
    cmd.args(["run", "jarvis", "listen"])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .current_dir(root);
    super::prepare_subprocess_for_appimage(&mut cmd);
    super::add_cargo_bin_to_path(&mut cmd);
    for (key, value) in cloud_keys {
        cmd.env(key, value);
    }
    cmd
}

/// True while the listener process is alive. Clears a handle whose process
/// already exited (for example after a microphone error).
pub(crate) async fn is_running(clap: &SharedClap) -> bool {
    let mut guard = clap.lock().await;
    let alive = match guard.as_mut() {
        Some(handle) => matches!(handle.child.try_wait(), Ok(None)),
        None => return false,
    };
    if !alive {
        *guard = None;
    }
    alive
}

async fn start(clap: &SharedClap) -> Result<(), String> {
    if is_running(clap).await {
        return Ok(());
    }
    let root = super::find_project_root().ok_or_else(|| {
        "OpenJarvis project folder not found. Clone it to ~/OpenJarvis or set OPENJARVIS_ROOT."
            .to_string()
    })?;
    let keys = super::cloud_keys_for_inference(&super::read_inference_config());
    let mut cmd = listen_command(&super::resolve_bin("uv"), &root, &keys);
    let child = super::spawn_owned_child(&mut cmd)
        .map_err(|err| format!("Could not start listener: {}", err))?;
    *clap.lock().await = Some(ChildHandle { child });
    Ok(())
}

pub(crate) async fn stop(clap: &SharedClap) {
    if let Some(mut handle) = clap.lock().await.take() {
        handle.kill().await;
    }
}

/// Start or stop the listener and remember the choice for the next launch.
pub(crate) async fn set_enabled(clap: &SharedClap, enabled: bool) -> Result<(), String> {
    if enabled {
        start(clap).await?;
    } else {
        stop(clap).await;
    }
    write_clap_pref(enabled)
}

/// At app launch, start the listener once the backend finished its first sync
/// (the Python environment must exist before `uv run` can use it).
pub(crate) async fn autostart_when_ready(clap: SharedClap, status: SharedStatus) {
    let deadline = tokio::time::Instant::now() + AUTOSTART_TIMEOUT;
    while tokio::time::Instant::now() < deadline {
        {
            let s = status.lock().await;
            if s.error.is_some() {
                return;
            }
            if s.phase == "ready" {
                break;
            }
        }
        tokio::time::sleep(AUTOSTART_POLL).await;
    }
    if let Err(err) = start(&clap).await {
        eprintln!("Warning: clap listener did not start: {err}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pref_defaults_to_off() {
        assert!(!parse_clap_pref(""));
        assert!(!parse_clap_pref("not json"));
        assert!(!parse_clap_pref("{}"));
        assert!(!parse_clap_pref(r#"{"clap_listener": "yes"}"#));
    }

    #[test]
    fn pref_reads_the_flag() {
        assert!(parse_clap_pref(r#"{"clap_listener": true}"#));
        assert!(!parse_clap_pref(r#"{"clap_listener": false}"#));
    }

    #[test]
    fn render_keeps_other_keys_and_recovers_from_garbage() {
        let kept = render_clap_pref(true, Some(r#"{"theme": "dark"}"#));
        assert!(parse_clap_pref(&kept));
        assert!(kept.contains("\"theme\""));

        // A prefs file that is not a JSON object must not wedge the toggle.
        assert!(parse_clap_pref(&render_clap_pref(true, Some("[1, 2]"))));
        assert!(!parse_clap_pref(&render_clap_pref(false, Some("garbage"))));
    }

    #[test]
    fn listen_command_runs_jarvis_listen_with_keys_in_env() {
        let keys = vec![("ANTHROPIC_API_KEY".to_string(), "sk-test".to_string())];
        let cmd = listen_command("uv", std::path::Path::new("/tmp/proj"), &keys);
        let std_cmd = cmd.as_std();

        let args: Vec<_> = std_cmd
            .get_args()
            .map(|a| a.to_string_lossy().into_owned())
            .collect();
        assert_eq!(args, ["run", "jarvis", "listen"]);
        assert_eq!(
            std_cmd.get_current_dir(),
            Some(std::path::Path::new("/tmp/proj"))
        );
        assert!(std_cmd.get_envs().any(|(k, v)| {
            k == "ANTHROPIC_API_KEY" && v.map(|v| v == "sk-test").unwrap_or(false)
        }));
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn is_running_tracks_the_child_and_stop_kills_it() {
        let clap: SharedClap = Arc::new(Mutex::new(None));
        assert!(!is_running(&clap).await);

        let mut cmd = tokio::process::Command::new("sleep");
        cmd.arg("30");
        let child = super::super::spawn_owned_child(&mut cmd).expect("spawn sleep");
        *clap.lock().await = Some(ChildHandle { child });
        assert!(is_running(&clap).await);

        stop(&clap).await;
        assert!(!is_running(&clap).await);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn is_running_clears_an_exited_child() {
        let clap: SharedClap = Arc::new(Mutex::new(None));
        let mut cmd = tokio::process::Command::new("true");
        let child = super::super::spawn_owned_child(&mut cmd).expect("spawn true");
        *clap.lock().await = Some(ChildHandle { child });

        // Give the short-lived process a moment to exit.
        for _ in 0..50 {
            if !is_running(&clap).await {
                break;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        assert!(!is_running(&clap).await);
        assert!(clap.lock().await.is_none());
    }
}

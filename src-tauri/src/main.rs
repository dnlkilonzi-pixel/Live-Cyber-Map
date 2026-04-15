// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

/// Check if the Ollama service is available at the configured URL.
#[tauri::command]
async fn check_ollama(url: String) -> Result<bool, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| e.to_string())?;

    match client.get(&format!("{}/api/tags", url)).send().await {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

/// Open a URL in the system default browser.
#[tauri::command]
async fn open_external(url: String, app: tauri::AppHandle) -> Result<(), String> {
    tauri::api::shell::open(&app.shell_scope(), url, None)
        .map_err(|e| e.to_string())
}

/// Get application version.
#[tauri::command]
fn get_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // Centre the main window on startup
            if let Some(window) = app.get_window("main") {
                let _ = window.center();
                let _ = window.show();
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            check_ollama,
            open_external,
            get_version,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

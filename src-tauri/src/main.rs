// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

/// Check if the backend API is reachable at the given URL.
#[tauri::command]
async fn health_check(url: String) -> Result<bool, String> {
    let api_url = if url.is_empty() {
        std::env::var("VITE_API_URL")
            .or_else(|_| std::env::var("NEXT_PUBLIC_API_URL"))
            .unwrap_or_else(|_| "http://localhost:8000".to_string())
    } else {
        url
    };

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| e.to_string())?;

    match client.get(&format!("{}/api/health", api_url)).send().await {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

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

            // Non-blocking backend health probe on startup (result ignored – UI
            // shows OFFLINE badge if WebSocket can't connect anyway).
            let app_handle = app.handle();
            tauri::async_runtime::spawn(async move {
                let api_url = std::env::var("VITE_API_URL")
                    .or_else(|_| std::env::var("NEXT_PUBLIC_API_URL"))
                    .unwrap_or_else(|_| "http://localhost:8000".to_string());

                if let Ok(client) = reqwest::Client::builder()
                    .timeout(std::time::Duration::from_secs(5))
                    .build()
                {
                    let ok = client
                        .get(format!("{}/api/health", api_url))
                        .send()
                        .await
                        .map(|r| r.status().is_success())
                        .unwrap_or(false);

                    log::info!("Backend health probe ({}): {}", api_url, if ok { "ok" } else { "unreachable" });

                    // Emit an event the frontend can listen to
                    let _ = app_handle.emit_all(
                        "backend-health",
                        serde_json::json!({ "ok": ok, "url": api_url }),
                    );
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            health_check,
            check_ollama,
            open_external,
            get_version,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/**
 * OllamaSettings – a compact settings drawer for managing the local Ollama model.
 *
 * Features:
 *   - List available models with sizes
 *   - Pull a new model (input box + pull button)
 *   - Switch the active model
 */
import { useCallback, useEffect, useState } from "react";import { motion, AnimatePresence } from "framer-motion";
import { OllamaStatus } from "../types/intelligence";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ModelInfo {
  name: string;
  size: number;
}

interface OllamaSettingsProps {
  onClose: () => void;
  initialStatus: OllamaStatus | null;
}

const POPULAR_MODELS = [
  "llama3.2:3b",
  "llama3.1:8b",
  "mistral:7b",
  "gemma2:2b",
  "phi3:mini",
  "nomic-embed-text",
];

function formatBytes(bytes: number): string {
  if (bytes < 1e6) return `${(bytes / 1e3).toFixed(0)} KB`;
  if (bytes < 1e9) return `${(bytes / 1e6).toFixed(0)} MB`;
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

export default function OllamaSettings({ onClose, initialStatus }: OllamaSettingsProps) {
  const [models, setModels] = useState<ModelInfo[]>(
    (initialStatus?.models as ModelInfo[]) ?? []
  );
  const [available, setAvailable] = useState(initialStatus?.available ?? false);
  const [pullInput, setPullInput] = useState("");
  const [pulling, setPulling] = useState(false);
  const [pullMsg, setPullMsg] = useState<string | null>(null);
  const [selecting, setSelecting] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${API_URL}/api/intelligence/ollama/status`);
      if (resp.ok) {
        const data: OllamaStatus = await resp.json();
        setAvailable(data.available);
        setModels((data.models as ModelInfo[]) ?? []);
      }
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handlePull = async () => {
    if (!pullInput.trim()) return;
    setPulling(true);
    setPullMsg(null);
    try {
      const resp = await fetch(
        `${API_URL}/api/intelligence/ollama/pull?model_name=${encodeURIComponent(pullInput.trim())}`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (data.status === "pull_initiated") {
        setPullMsg(`✓ Pull started for "${pullInput}". This may take several minutes. Check back soon.`);
        setPullInput("");
        setTimeout(refresh, 5000);
      } else {
        setPullMsg(`✗ Pull failed. Is Ollama running at ${API_URL.replace("http://localhost:8000", "localhost:11434")}?`);
      }
    } catch {
      setPullMsg("✗ Could not reach backend.");
    } finally {
      setPulling(false);
    }
  };

  const handleSelect = async (modelName: string) => {
    setSelecting(modelName);
    try {
      const resp = await fetch(
        `${API_URL}/api/intelligence/ollama/select?model_name=${encodeURIComponent(modelName)}`,
        { method: "POST" }
      );
      if (resp.ok) setActiveModel(modelName);
    } catch { /* silent */ } finally {
      setSelecting(null);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-end md:items-center justify-center"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
        <motion.div
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 40, opacity: 0 }}
          className="relative z-10 w-full max-w-md rounded-t-xl md:rounded-xl side-panel border border-white/10 shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold uppercase tracking-widest text-[var(--color-accent)]">
                Ollama Settings
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${available ? "bg-green-900/50 text-green-400" : "bg-gray-800 text-gray-500"}`}>
                {available ? "● Online" : "○ Offline"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={refresh} disabled={loading} className="text-xs text-gray-500 hover:text-white transition-colors disabled:opacity-40">
                {loading ? "⟳" : "↻ Refresh"}
              </button>
              <button onClick={onClose} className="text-gray-400 hover:text-white text-xl px-1">×</button>
            </div>
          </div>

          <div className="p-5 space-y-5 max-h-[70vh] overflow-y-auto scrollbar-thin">
            {/* Available models */}
            <section>
              <h3 className="text-xs uppercase tracking-widest text-gray-500 mb-3">
                Installed Models ({models.length})
              </h3>
              {models.length === 0 ? (
                <p className="text-xs text-gray-600">
                  {available ? "No models installed." : "Ollama is not running. Start it with: ollama serve"}
                </p>
              ) : (
                <div className="space-y-1.5">
                  {models.map((m) => (
                    <div key={m.name} className={`flex items-center justify-between rounded px-3 py-2 ${activeModel === m.name ? "bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/30" : "bg-white/5"}`}>
                      <div>
                        <p className="text-xs font-mono text-gray-200">{m.name}</p>
                        <p className="text-xs text-gray-600">{m.size ? formatBytes(m.size) : ""}</p>
                      </div>
                      <button
                        onClick={() => handleSelect(m.name)}
                        disabled={selecting === m.name}
                        className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                          activeModel === m.name
                            ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                            : "border-white/20 text-gray-400 hover:text-white hover:border-white/40"
                        } disabled:opacity-40`}
                      >
                        {activeModel === m.name ? "Active" : selecting === m.name ? "…" : "Use"}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Pull a model */}
            <section>
              <h3 className="text-xs uppercase tracking-widest text-gray-500 mb-3">Pull a New Model</h3>
              <div className="flex gap-2">
                <input
                  className="flex-1 bg-white/5 border border-white/10 rounded px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[var(--color-accent)]"
                  placeholder="e.g. llama3.2:3b, mistral:7b"
                  value={pullInput}
                  onChange={(e) => setPullInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handlePull()}
                />
                <button
                  onClick={handlePull}
                  disabled={pulling || !pullInput.trim()}
                  className="px-3 py-2 rounded text-xs font-bold bg-[var(--color-accent)] text-black hover:opacity-80 disabled:opacity-50 transition-opacity whitespace-nowrap"
                >
                  {pulling ? "Pulling…" : "↓ Pull"}
                </button>
              </div>
              {pullMsg && (
                <p className={`mt-2 text-xs ${pullMsg.startsWith("✓") ? "text-green-400" : "text-red-400"}`}>
                  {pullMsg}
                </p>
              )}

              {/* Popular models quick-pick */}
              <div className="flex flex-wrap gap-1.5 mt-3">
                {POPULAR_MODELS.filter((m) => !models.find((im) => im.name === m)).map((m) => (
                  <button
                    key={m}
                    onClick={() => setPullInput(m)}
                    className="text-xs px-2 py-0.5 rounded border border-white/10 text-gray-500 hover:text-white hover:border-white/30 transition-colors font-mono"
                  >
                    + {m}
                  </button>
                ))}
              </div>
            </section>

            {/* Help */}
            <section className="text-xs text-gray-600 space-y-1">
              <p>Install Ollama: <span className="text-gray-500">https://ollama.ai</span></p>
              <p>Start server: <span className="font-mono text-gray-500">ollama serve</span></p>
            </section>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

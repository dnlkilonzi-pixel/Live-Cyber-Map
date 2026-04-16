/**
 * AlertRuleManager – modal for creating and managing alert rules.
 *
 * Supports three condition types:
 *   - risk_above   : fire when a country's risk score exceeds a threshold
 *   - attack_type  : fire when a specific attack type is detected
 *   - price_change : fire when an asset price changes by > N%
 */
import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface AlertRule {
  id: number;
  name: string;
  condition: string;
  target: string | null;
  threshold: number | null;
  bbox: string | null;
  enabled: boolean;
  created_at: string;
}

interface AlertRuleManagerProps {
  onClose: () => void;
  onBboxCapture?: (cb: (lat: number, lng: number) => void) => void;
}

const ATTACK_TYPES = ["DDoS", "Malware", "Phishing", "Ransomware", "Intrusion", "BruteForce", "SQLInjection", "XSS", "ZeroDay"];
const RULES_PER_PAGE = 10;

export default function AlertRuleManager({ onClose, onBboxCapture }: AlertRuleManagerProps) {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [rulesPage, setRulesPage] = useState(0);
  const [importError, setImportError] = useState<string | null>(null);

  // Inline-edit state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");

  // Form state
  const [name, setName] = useState("");
  const [condition, setCondition] = useState("risk_above");
  const [target, setTarget] = useState("");
  const [threshold, setThreshold] = useState("");
  // Bbox geofence fields (lat_min, lng_min, lat_max, lng_max)
  const [bboxLatMin, setBboxLatMin] = useState("");
  const [bboxLngMin, setBboxLngMin] = useState("");
  const [bboxLatMax, setBboxLatMax] = useState("");
  const [bboxLngMax, setBboxLngMax] = useState("");
  const [bboxPickingPoint, setBboxPickingPoint] = useState<1 | 2 | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${API_URL}/api/alerts/rules`);
      if (resp.ok) {
        setRules(await resp.json());
        setRulesPage(0);
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const handleCreate = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    if (condition === "bbox") {
      if (!bboxLatMin || !bboxLngMin || !bboxLatMax || !bboxLngMax) {
        setError("All four bounding-box coordinates are required");
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { name: name.trim(), condition, enabled: true };
      if (target.trim()) body.target = target.trim();
      if (threshold.trim()) body.threshold = parseFloat(threshold);
      if (condition === "bbox") {
        body.bbox = `${bboxLatMin},${bboxLngMin},${bboxLatMax},${bboxLngMax}`;
      }

      const resp = await fetch(`${API_URL}/api/alerts/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setShowForm(false);
      setName(""); setCondition("risk_above"); setTarget(""); setThreshold("");
      setBboxLatMin(""); setBboxLngMin(""); setBboxLatMax(""); setBboxLngMax("");
      await fetchRules();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create rule");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    await fetch(`${API_URL}/api/alerts/rules/${id}`, { method: "DELETE" });
    setRules((prev) => prev.filter((r) => r.id !== id));
  };

  const handleToggle = async (id: number) => {
    const resp = await fetch(`${API_URL}/api/alerts/rules/${id}/toggle`, { method: "PATCH" });
    if (resp.ok) {
      const updated: AlertRule = await resp.json();
      setRules((prev) => prev.map((r) => r.id === id ? updated : r));
    }
  };

  const startEdit = (rule: AlertRule) => {
    setEditingId(rule.id);
    setEditingName(rule.name);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingName("");
  };

  const saveEdit = async (id: number) => {
    const trimmed = editingName.trim();
    if (!trimmed) return;
    try {
      const resp = await fetch(`${API_URL}/api/alerts/rules/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (resp.ok) {
        const updated: AlertRule = await resp.json();
        setRules((prev) => prev.map((r) => r.id === id ? updated : r));
      }
    } catch {
      // Silently fail — name will revert on next fetch
    }
    setEditingId(null);
    setEditingName("");
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(rules, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `alert-rules-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (ev) => {
      try {
        const raw = ev.target?.result as string;
        let imported: AlertRule[];
        try {
          imported = JSON.parse(raw);
        } catch {
          setImportError("Invalid JSON — could not parse the selected file.");
          setTimeout(() => setImportError(null), 4000);
          return;
        }
        if (!Array.isArray(imported)) {
          setImportError("Invalid format — expected a JSON array of rules.");
          setTimeout(() => setImportError(null), 4000);
          return;
        }
        for (const rule of imported) {
          await fetch(`${API_URL}/api/alerts/rules`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: rule.name,
              condition: rule.condition,
              target: rule.target ?? undefined,
              threshold: rule.threshold ?? undefined,
              bbox: rule.bbox ?? undefined,
              enabled: rule.enabled,
            }),
          });
        }
        await fetchRules();
      } catch {
        setImportError("Import failed — please try again.");
        setTimeout(() => setImportError(null), 4000);
      }
    };
    reader.readAsText(file);
    // Reset input so the same file can be re-imported
    e.target.value = "";
  };

  const pickBboxPoint = (point: 1 | 2) => {
    if (!onBboxCapture) return;
    setBboxPickingPoint(point);
    onBboxCapture((lat, lng) => {
      const latStr = lat.toFixed(4);
      const lngStr = lng.toFixed(4);
      if (point === 1) {
        setBboxLatMin(latStr);
        setBboxLngMin(lngStr);
      } else {
        setBboxLatMax(latStr);
        setBboxLngMax(lngStr);
      }
      setBboxPickingPoint(null);
    });
  };

  const conditionLabel = (c: string) => {
    if (c === "risk_above") return "Risk > threshold";
    if (c === "attack_type") return "Attack type detected";
    if (c === "price_change") return "Price change > threshold";
    if (c === "bbox") return "Geofence (bounding box)";
    if (c === "anomaly_score") return "Anomaly score > threshold";
    return c;
  };

  const bboxSummary = (rule: AlertRule) => {
    if (rule.condition !== "bbox" || !rule.bbox) return null;
    const parts = rule.bbox.split(",");
    if (parts.length !== 4) return rule.bbox;
    return `Lat ${parts[0]}–${parts[2]}, Lng ${parts[1]}–${parts[3]}`;
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
        <motion.div
          initial={{ scale: 0.92, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.92, opacity: 0 }}
          className="relative z-10 w-full max-w-lg rounded-lg side-panel border border-white/10 shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
            <span className="font-bold text-sm uppercase tracking-widest text-[var(--color-accent)]">Alert Rules</span>
            <div className="flex items-center gap-2">
              {rules.length > 0 && (
                <button
                  onClick={handleExport}
                  className="text-xs text-gray-400 hover:text-white border border-white/10 rounded px-2 py-0.5 transition-colors"
                  title="Export rules as JSON"
                >
                  ↓ Export
                </button>
              )}
              <label className="text-xs text-gray-400 hover:text-white border border-white/10 rounded px-2 py-0.5 transition-colors cursor-pointer" title="Import rules from JSON">
                ↑ Import
                <input type="file" accept=".json,application/json" className="hidden" onChange={handleImport} />
              </label>
              <button onClick={onClose} className="text-gray-400 hover:text-white text-xl px-1">×</button>
            </div>
          </div>

          <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto scrollbar-thin">
            {/* Import error toast */}
            <AnimatePresence>
              {importError && (
                <motion.div
                  key="import-error"
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="flex items-center gap-2 px-3 py-2 rounded border border-red-600/60 bg-red-900/40 text-red-300 text-xs"
                >
                  <span>⚠</span>
                  <span>{importError}</span>
                </motion.div>
              )}
            </AnimatePresence>
            {/* Existing rules */}
            {loading ? (
              <div className="text-xs text-gray-500 text-center py-4">Loading…</div>
            ) : rules.length === 0 ? (
              <div className="flex flex-col items-center gap-2 text-gray-600 py-6">
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <circle cx="20" cy="20" r="18" stroke="#374151" strokeWidth="2" />
                  <path d="M13 20h14M20 13v14" stroke="#4b5563" strokeWidth="2" strokeLinecap="round" />
                </svg>
                <span className="text-xs">No alert rules yet. Create one below.</span>
              </div>
            ) : (() => {
              const totalRulesPages = Math.max(1, Math.ceil(rules.length / RULES_PER_PAGE));
              const safeRulesPage = Math.min(rulesPage, totalRulesPages - 1);
              const pageRules = rules.slice(safeRulesPage * RULES_PER_PAGE, (safeRulesPage + 1) * RULES_PER_PAGE);
              return (
                <div className="space-y-2">
                  {pageRules.map((rule) => (
                  <div key={rule.id} className={`flex items-start justify-between gap-3 px-3 py-2.5 rounded bg-white/5 ${rule.enabled ? "" : "opacity-50"}`}>
                    <div className="min-w-0 flex-1">
                      {editingId === rule.id ? (
                        <div className="flex items-center gap-1">
                          <input
                            className="flex-1 bg-white/10 border border-[var(--color-accent)] rounded px-2 py-0.5 text-xs text-white focus:outline-none"
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") saveEdit(rule.id); if (e.key === "Escape") cancelEdit(); }}
                            autoFocus
                          />
                          <button onClick={() => saveEdit(rule.id)} className="text-xs text-green-400 hover:text-green-300 px-1">✓</button>
                          <button onClick={cancelEdit} className="text-xs text-gray-500 hover:text-white px-1">✕</button>
                        </div>
                      ) : (
                        <p className="text-xs font-semibold text-gray-200">{rule.name}</p>
                      )}
                      <p className="text-xs text-gray-500 mt-0.5">
                          {conditionLabel(rule.condition)}
                          {rule.target ? ` · ${rule.target}` : ""}
                          {rule.threshold != null ? ` > ${rule.threshold}` : ""}
                          {bboxSummary(rule) ? ` · ${bboxSummary(rule)}` : ""}
                        </p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {editingId !== rule.id && (
                        <button
                          onClick={() => startEdit(rule)}
                          className="text-xs text-gray-500 hover:text-white px-1 transition-colors"
                          aria-label="Rename rule"
                          title="Rename"
                        >
                          ✏
                        </button>
                      )}
                      <button
                        onClick={() => handleToggle(rule.id)}
                        className={`text-xs px-2 py-0.5 rounded border transition-colors ${rule.enabled ? "border-green-600 text-green-400 hover:bg-green-900/30" : "border-gray-600 text-gray-500 hover:text-white"}`}
                      >
                        {rule.enabled ? "ON" : "OFF"}
                      </button>
                      <button
                        onClick={() => handleDelete(rule.id)}
                        className="text-xs text-red-500 hover:text-red-300 px-1 transition-colors"
                        aria-label="Delete rule"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
                  {/* Rules pagination */}
                  {totalRulesPages > 1 && (
                    <div className="flex items-center justify-between pt-1">
                      <button
                        onClick={() => setRulesPage((p) => Math.max(0, p - 1))}
                        disabled={safeRulesPage === 0}
                        className="text-[10px] text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed px-2 py-0.5 border border-white/10 rounded transition-colors"
                      >
                        ◀ Prev
                      </button>
                      <span className="text-[10px] text-gray-600 font-mono">
                        {safeRulesPage + 1} / {totalRulesPages}
                      </span>
                      <button
                        onClick={() => setRulesPage((p) => Math.min(totalRulesPages - 1, p + 1))}
                        disabled={safeRulesPage >= totalRulesPages - 1}
                        className="text-[10px] text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed px-2 py-0.5 border border-white/10 rounded transition-colors"
                      >
                        Next ▶
                      </button>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Add rule form */}
            <button
              onClick={() => setShowForm((v) => !v)}
              className="w-full text-xs border border-dashed border-white/20 text-gray-500 hover:text-white hover:border-white/40 rounded py-2 transition-colors"
            >
              {showForm ? "− Cancel" : "+ Add rule"}
            </button>

            <AnimatePresence>
              {showForm && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }} className="overflow-hidden"
                >
                  <div className="space-y-3 pt-1">
                    <input
                      className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[var(--color-accent)]"
                      placeholder="Rule name (e.g. Russia risk spike)"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                    <select
                      className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-[var(--color-accent)]"
                      value={condition}
                      onChange={(e) => setCondition(e.target.value)}
                    >
                      <option value="risk_above">Country risk above threshold</option>
                      <option value="attack_type">Attack type detected</option>
                      <option value="price_change">Asset price change</option>
                      <option value="bbox">Geofence (bounding box)</option>
                      <option value="anomaly_score">Anomaly score above threshold</option>
                    </select>

                    {condition === "attack_type" ? (
                      <select
                        className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-[var(--color-accent)]"
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}
                      >
                        <option value="">Any attack type</option>
                        {ATTACK_TYPES.map((t) => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                      </select>
                    ) : condition === "bbox" ? (
                      <div className="space-y-2">
                        <p className="text-xs text-gray-500">Bounding box coordinates (decimal degrees)</p>
                        {onBboxCapture && (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => pickBboxPoint(1)}
                              className={`flex-1 text-xs py-1 rounded border transition-colors ${bboxPickingPoint === 1 ? "border-[var(--color-accent)] text-[var(--color-accent)] animate-pulse" : "border-white/20 text-gray-500 hover:text-white"}`}
                            >
                              {bboxPickingPoint === 1 ? "Click map for SW…" : "📍 Pick SW corner"}
                            </button>
                            <button
                              type="button"
                              onClick={() => pickBboxPoint(2)}
                              className={`flex-1 text-xs py-1 rounded border transition-colors ${bboxPickingPoint === 2 ? "border-[var(--color-accent)] text-[var(--color-accent)] animate-pulse" : "border-white/20 text-gray-500 hover:text-white"}`}
                            >
                              {bboxPickingPoint === 2 ? "Click map for NE…" : "📍 Pick NE corner"}
                            </button>
                          </div>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                          {[
                            { label: "Lat min (S bound)", val: bboxLatMin, set: setBboxLatMin, placeholder: "e.g. 35.0" },
                            { label: "Lng min (W bound)", val: bboxLngMin, set: setBboxLngMin, placeholder: "e.g. -80.0" },
                            { label: "Lat max (N bound)", val: bboxLatMax, set: setBboxLatMax, placeholder: "e.g. 45.0" },
                            { label: "Lng max (E bound)", val: bboxLngMax, set: setBboxLngMax, placeholder: "e.g. -70.0" },
                          ].map(({ label, val, set, placeholder }) => (
                            <div key={label}>
                              <p className="text-[10px] text-gray-600 mb-0.5">{label}</p>
                              <input
                                type="number"
                                step="any"
                                className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[var(--color-accent)]"
                                placeholder={placeholder}
                                value={val}
                                onChange={(e) => set(e.target.value)}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : condition === "anomaly_score" ? null : (
                      <input
                        className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[var(--color-accent)]"
                        placeholder={condition === "risk_above" ? "Country ISO2 (e.g. RU) – blank = all" : "Asset symbol (e.g. BTC) – blank = all"}
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}
                      />
                    )}

                    {condition !== "attack_type" && condition !== "bbox" && (
                      <input
                        type="number"
                        className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[var(--color-accent)]"
                        placeholder={
                          condition === "risk_above" ? "Threshold (0–100)" :
                          condition === "anomaly_score" ? "Anomaly score threshold (e.g. 1.5)" :
                          "Change % threshold (e.g. 5)"
                        }
                        value={threshold}
                        onChange={(e) => setThreshold(e.target.value)}
                      />
                    )}

                    {error && <p className="text-xs text-red-400">{error}</p>}

                    <button
                      onClick={handleCreate}
                      disabled={saving}
                      className="w-full py-2 rounded text-xs font-bold bg-[var(--color-accent)] text-black hover:opacity-80 disabled:opacity-50 transition-opacity"
                    >
                      {saving ? "Creating…" : "Create Rule"}
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

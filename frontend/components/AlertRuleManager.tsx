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
  enabled: boolean;
  created_at: string;
}

interface AlertRuleManagerProps {
  onClose: () => void;
}

const ATTACK_TYPES = ["DDoS", "Malware", "Phishing", "Ransomware", "Intrusion", "BruteForce", "SQLInjection", "XSS", "ZeroDay"];

export default function AlertRuleManager({ onClose }: AlertRuleManagerProps) {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [name, setName] = useState("");
  const [condition, setCondition] = useState("risk_above");
  const [target, setTarget] = useState("");
  const [threshold, setThreshold] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${API_URL}/api/alerts/rules`);
      if (resp.ok) setRules(await resp.json());
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const handleCreate = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { name: name.trim(), condition, enabled: true };
      if (target.trim()) body.target = target.trim();
      if (threshold.trim()) body.threshold = parseFloat(threshold);

      const resp = await fetch(`${API_URL}/api/alerts/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setShowForm(false);
      setName(""); setCondition("risk_above"); setTarget(""); setThreshold("");
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

  const conditionLabel = (c: string) => {
    if (c === "risk_above") return "Risk > threshold";
    if (c === "attack_type") return "Attack type detected";
    if (c === "price_change") return "Price change > threshold";
    return c;
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
            <button onClick={onClose} className="text-gray-400 hover:text-white text-xl px-1">×</button>
          </div>

          <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto scrollbar-thin">
            {/* Existing rules */}
            {loading ? (
              <div className="text-xs text-gray-500 text-center py-4">Loading…</div>
            ) : rules.length === 0 ? (
              <div className="text-xs text-gray-600 text-center py-4">No alert rules yet. Create one below.</div>
            ) : (
              <div className="space-y-2">
                {rules.map((rule) => (
                  <div key={rule.id} className={`flex items-start justify-between gap-3 px-3 py-2.5 rounded bg-white/5 ${rule.enabled ? "" : "opacity-50"}`}>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-gray-200">{rule.name}</p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {conditionLabel(rule.condition)}
                        {rule.target ? ` · ${rule.target}` : ""}
                        {rule.threshold != null ? ` > ${rule.threshold}` : ""}
                      </p>
                    </div>
                    <div className="flex gap-2 shrink-0">
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
              </div>
            )}

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
                    ) : (
                      <input
                        className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[var(--color-accent)]"
                        placeholder={condition === "risk_above" ? "Country ISO2 (e.g. RU) – blank = all" : "Asset symbol (e.g. BTC) – blank = all"}
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}
                      />
                    )}

                    {condition !== "attack_type" && (
                      <input
                        type="number"
                        className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[var(--color-accent)]"
                        placeholder={condition === "risk_above" ? "Threshold (0–100)" : "Change % threshold (e.g. 5)"}
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

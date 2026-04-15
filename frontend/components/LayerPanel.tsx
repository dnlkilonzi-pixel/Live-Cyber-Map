/**
 * LayerPanel – toggleable panel listing all 40+ data layers.
 * Organised by category with toggle switches.
 */
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { LayerDefinition, LayerState, CATEGORY_META, LayerCategory } from "../types/layers";

interface LayerPanelProps {
  layers: LayerDefinition[];
  enabled: LayerState;
  onToggle: (layerId: string) => void;
  onClose: () => void;
}

export default function LayerPanel({
  layers,
  enabled,
  onToggle,
  onClose,
}: LayerPanelProps) {
  const [expandedCategory, setExpandedCategory] = useState<string | null>("security");
  const [search, setSearch] = useState("");

  const filteredLayers = layers.filter(
    (l) =>
      !search ||
      l.name.toLowerCase().includes(search.toLowerCase()) ||
      l.description.toLowerCase().includes(search.toLowerCase())
  );

  // Group by category
  const grouped = filteredLayers.reduce<Record<string, LayerDefinition[]>>(
    (acc, layer) => {
      (acc[layer.category] ??= []).push(layer);
      return acc;
    },
    {}
  );

  const enabledCount = Object.values(enabled).filter(Boolean).length;

  return (
    <div className="flex flex-col h-full w-72 text-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--color-accent)] font-bold">
            Data Layers
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {enabledCount} of {layers.length} active
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-white text-lg leading-none p-1"
          aria-label="Close layer panel"
        >
          ×
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2 shrink-0">
        <input
          type="text"
          placeholder="Search layers…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-1.5 text-xs text-gray-300 placeholder-gray-600 focus:outline-none focus:border-[var(--color-accent)]"
        />
      </div>

      {/* Category groups */}
      <div className="flex-1 overflow-y-auto">
        {Object.entries(grouped).map(([cat, catLayers]) => {
          const meta = CATEGORY_META[cat as LayerCategory] ?? {
            label: cat,
            icon: "📌",
            color: "#888",
          };
          const isExpanded = expandedCategory === cat || !!search;
          const activeCount = catLayers.filter((l) => enabled[l.id]).length;

          return (
            <div key={cat} className="border-b border-white/5">
              {/* Category header */}
              <button
                className="w-full flex items-center justify-between px-3 py-2 hover:bg-white/5 transition-colors"
                onClick={() =>
                  setExpandedCategory(isExpanded && !search ? null : cat)
                }
              >
                <div className="flex items-center gap-2">
                  <span>{meta.icon}</span>
                  <span className="text-gray-300 font-medium text-xs">
                    {meta.label}
                  </span>
                  {activeCount > 0 && (
                    <span
                      className="text-xs px-1.5 py-0.5 rounded-full font-mono"
                      style={{
                        backgroundColor: meta.color + "33",
                        color: meta.color,
                      }}
                    >
                      {activeCount}
                    </span>
                  )}
                </div>
                <span className="text-gray-600 text-xs">
                  {isExpanded ? "▾" : "▸"}
                </span>
              </button>

              {/* Layer rows */}
              <AnimatePresence initial={false}>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    {catLayers.map((layer) => (
                      <LayerRow
                        key={layer.id}
                        layer={layer}
                        isEnabled={!!enabled[layer.id]}
                        onToggle={() => onToggle(layer.id)}
                      />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}

        {filteredLayers.length === 0 && (
          <div className="px-4 py-6 text-center text-gray-600 text-xs">
            No layers match &ldquo;{search}&rdquo;
          </div>
        )}
      </div>

      {/* Footer actions */}
      <div className="px-3 py-2 border-t border-white/10 shrink-0 flex gap-2">
        <button
          className="flex-1 text-xs text-gray-400 hover:text-white border border-white/10 rounded px-2 py-1 transition-colors"
          onClick={() => {
            layers.forEach((l) => {
              if (!enabled[l.id]) onToggle(l.id);
            });
          }}
        >
          All On
        </button>
        <button
          className="flex-1 text-xs text-gray-400 hover:text-white border border-white/10 rounded px-2 py-1 transition-colors"
          onClick={() => {
            layers.forEach((l) => {
              if (enabled[l.id]) onToggle(l.id);
            });
          }}
        >
          All Off
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Layer row
// ---------------------------------------------------------------------------

function LayerRow({
  layer,
  isEnabled,
  onToggle,
}: {
  layer: LayerDefinition;
  isEnabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={`flex items-center gap-3 px-4 py-2 hover:bg-white/5 cursor-pointer transition-colors group ${
        isEnabled ? "opacity-100" : "opacity-60"
      }`}
      onClick={onToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onToggle()}
    >
      <span className="text-base shrink-0">{layer.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-gray-300 truncate group-hover:text-white transition-colors">
          {layer.name}
        </div>
        {isEnabled && (
          <div className="text-xs text-gray-600 truncate">{layer.description}</div>
        )}
      </div>
      {/* Live badge */}
      {layer.live && (
        <span className="shrink-0 text-xs text-green-400 font-mono">●</span>
      )}
      {/* Toggle */}
      <div
        className={`w-8 h-4 rounded-full shrink-0 relative transition-colors ${
          isEnabled ? "bg-[var(--color-accent)]" : "bg-gray-700"
        }`}
      >
        <div
          className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${
            isEnabled ? "left-4.5 translate-x-0.5" : "left-0.5"
          }`}
          style={{ transform: isEnabled ? "translateX(16px)" : "translateX(0)" }}
        />
      </div>
    </div>
  );
}

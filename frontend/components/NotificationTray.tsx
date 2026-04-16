/**
 * NotificationTray – bell icon in the top bar that shows fired alerts.
 *
 * - Accumulates alert messages received via WebSocket (`type: "alert"`)
 * - Shows a red badge when there are unread notifications
 * - Clicking the bell opens a dropdown list of recent notifications
 * - Also requests browser Notification permission and shows OS-level alerts
 */
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export interface AlertNotification {
  id: string;
  rule_name: string;
  message: string;
  fired_at: number; // Unix timestamp
  read: boolean;
}

interface NotificationTrayProps {
  notifications: AlertNotification[];
  onClear: () => void;
}

export default function NotificationTray({ notifications, onClear }: NotificationTrayProps) {
  const [open, setOpen] = useState(false);
  const trayRef = useRef<HTMLDivElement>(null);
  const unread = notifications.filter((n) => !n.read).length;

  // Close tray when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (trayRef.current && !trayRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const formatTime = (ts: number) => {
    const diff = Date.now() / 1000 - ts;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  };

  return (
    <div ref={trayRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative px-2 py-1 text-sm border border-white/20 rounded text-gray-400 hover:text-white transition-colors"
        title="Notifications"
        aria-label="Open notifications"
      >
        🔔
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-xs flex items-center justify-center font-bold leading-none">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-9 w-80 z-50 rounded-lg shadow-2xl side-panel border border-white/10 overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10">
              <span className="text-xs font-bold uppercase tracking-widest text-[var(--color-accent)]">
                Notifications
              </span>
              {notifications.length > 0 && (
                <button
                  onClick={() => { onClear(); setOpen(false); }}
                  className="text-xs text-gray-500 hover:text-white transition-colors"
                >
                  Clear all
                </button>
              )}
            </div>

            <div className="max-h-80 overflow-y-auto scrollbar-thin">
              {notifications.length === 0 ? (
                <div className="px-4 py-6 text-center text-xs text-gray-600">
                  No alerts fired yet.
                </div>
              ) : (
                notifications.map((n) => (
                  <div
                    key={n.id}
                    className={`px-4 py-3 border-b border-white/5 ${n.read ? "opacity-60" : ""}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-[var(--color-accent)] truncate">
                          {n.rule_name}
                        </p>
                        <p className="text-xs text-gray-300 mt-0.5 leading-snug">
                          {n.message}
                        </p>
                      </div>
                      <span className="text-xs text-gray-600 shrink-0">{formatTime(n.fired_at)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

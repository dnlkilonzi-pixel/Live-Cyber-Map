import { useCallback, useEffect, useRef, useState } from "react";
import { AttackEvent, Stats, WebSocketMessage } from "../types/attack";
import { AlertNotification } from "../components/NotificationTray";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

const MAX_ATTACKS = 500;
const BASE_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;

interface UseWebSocketReturn {
  attacks: AttackEvent[];
  stats: Stats | null;
  isConnected: boolean;
  isAnomaly: boolean;
  anomalyScore: number;
  notifications: AlertNotification[];
  replaySyncPosition: number | null;
  sendMessage: (type: string, data?: unknown) => void;
  clearHistory: () => void;
  clearNotifications: () => void;
  markAllRead: () => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const [attacks, setAttacks] = useState<AttackEvent[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isAnomaly, setIsAnomaly] = useState(false);
  const [anomalyScore, setAnomalyScore] = useState(0);
  const [notifications, setNotifications] = useState<AlertNotification[]>([]);
  const [replaySyncPosition, setReplaySyncPosition] = useState<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const clearHistory = useCallback(() => {
    setAttacks([]);
  }, []);

  const clearNotifications = useCallback(() => {
    setNotifications([]);
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const sendMessage = useCallback((type: string, data: unknown = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, data }));
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        reconnectAttemptRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return;
        try {
          const msg: WebSocketMessage = JSON.parse(event.data as string);

          switch (msg.type) {
            case "attack":
              setAttacks((prev) => {
                const next = [msg.data, ...prev];
                return next.length > MAX_ATTACKS
                  ? next.slice(0, MAX_ATTACKS)
                  : next;
              });
              break;

            case "stats":
              setStats(msg.data);
              if (msg.data.is_anomaly) {
                setIsAnomaly(true);
                setAnomalyScore(msg.data.anomaly_score);
              } else {
                setIsAnomaly(false);
              }
              break;

            case "anomaly":
              setIsAnomaly(true);
              setAnomalyScore(msg.data.score);
              break;

            case "history":
              setAttacks(msg.data.slice(0, MAX_ATTACKS));
              break;

            case "replay_started":
            case "replay_stopped":
              break;

            case "replay_seek":
              setReplaySyncPosition(msg.position);
              break;

            case "alert": {
              const alertData = msg.data;
              const newNotif: AlertNotification = {
                id: `${alertData.rule_id}-${alertData.fired_at}`,
                rule_name: alertData.rule_name,
                message: alertData.message,
                fired_at: alertData.fired_at,
                read: false,
              };
              setNotifications((prev) => [newNotif, ...prev].slice(0, 50));
              // Browser Notification API
              if (typeof Notification !== "undefined" && Notification.permission === "granted") {
                new Notification(`Alert: ${alertData.rule_name}`, {
                  body: alertData.message,
                  icon: "/favicon.ico",
                });
              } else if (typeof Notification !== "undefined" && Notification.permission !== "denied") {
                Notification.requestPermission().then((perm) => {
                  if (perm === "granted") {
                    new Notification(`Alert: ${alertData.rule_name}`, {
                      body: alertData.message,
                      icon: "/favicon.ico",
                    });
                  }
                });
              }
              break;
            }

            default:
              break;
          }
        } catch {
          // Malformed message — ignore silently
        }
      };

      ws.onerror = () => {
        // Errors surface via onclose; nothing extra needed here
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        wsRef.current = null;
        setIsConnected(false);

        const delay = Math.min(
          BASE_RECONNECT_DELAY * 2 ** reconnectAttemptRef.current,
          MAX_RECONNECT_DELAY
        );
        reconnectAttemptRef.current += 1;

        reconnectTimerRef.current = setTimeout(() => {
          if (mountedRef.current) connect();
        }, delay);
      };
    } catch {
      const delay = Math.min(
        BASE_RECONNECT_DELAY * 2 ** reconnectAttemptRef.current,
        MAX_RECONNECT_DELAY
      );
      reconnectAttemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, delay);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    attacks,
    stats,
    isConnected,
    isAnomaly,
    anomalyScore,
    notifications,
    replaySyncPosition,
    sendMessage,
    clearHistory,
    clearNotifications,
    markAllRead,
  };
}

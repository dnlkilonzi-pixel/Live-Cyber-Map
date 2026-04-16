export enum AttackType {
  DDoS = "DDoS",
  Malware = "Malware",
  Phishing = "Phishing",
  Ransomware = "Ransomware",
  Intrusion = "Intrusion",
  BruteForce = "BruteForce",
  SQLInjection = "SQLInjection",
  XSS = "XSS",
  ZeroDay = "ZeroDay",
}

export interface AttackEvent {
  id: string;
  source_ip: string;
  dest_ip: string;
  source_country: string;
  dest_country: string;
  source_lat: number;
  source_lng: number;
  dest_lat: number;
  dest_lng: number;
  attack_type: AttackType;
  severity: number;
  timestamp: string;
  cluster_id?: string;
}

export interface Stats {
  events_per_second: number;
  rolling_avg: number;
  is_anomaly: boolean;
  anomaly_score: number;
  top_attackers: Array<{ ip: string; country: string; count: number }>;
  top_targets: Array<{ country: string; count: number }>;
  attack_type_stats: Record<string, number>;
  total_events: number;
}

export type WebSocketMessage =
  | { type: "attack"; data: AttackEvent }
  | { type: "stats"; data: Stats }
  | { type: "anomaly"; data: { message: string; score: number } }
  | { type: "history"; data: AttackEvent[] }
  | { type: "replay_started"; data: { total: number } }
  | { type: "replay_stopped"; data: Record<string, never> }
  | { type: "replay_seek"; position: number }
  | { type: "alert"; data: { rule_id: number; rule_name: string; message: string; fired_at: number } };

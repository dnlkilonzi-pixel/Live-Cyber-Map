import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { AttackEvent, AttackType } from "../types/attack";

const ATTACK_COLORS: Record<AttackType, string> = {
  [AttackType.DDoS]: "#ff4444",
  [AttackType.Malware]: "#ff8800",
  [AttackType.Phishing]: "#ffff00",
  [AttackType.Ransomware]: "#ff0088",
  [AttackType.Intrusion]: "#00ffff",
  [AttackType.BruteForce]: "#ff00ff",
  [AttackType.SQLInjection]: "#00ff88",
  [AttackType.XSS]: "#8888ff",
  [AttackType.ZeroDay]: "#ffffff",
};

const MAX_ARCS = 200;

// globe.gl is browser-only — must skip SSR
const GlobeGL = dynamic(() => import("globe.gl"), { ssr: false });

interface ArcDatum {
  id: string;
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  color: string;
  stroke: number;
  attackType: AttackType;
}

interface PointDatum {
  id: string;
  lat: number;
  lng: number;
  color: string;
  attackType: AttackType;
}

interface GlobeProps {
  attacks: AttackEvent[];
}

export default function Globe({ attacks }: GlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [arcs, setArcs] = useState<ArcDatum[]>([]);
  const [points, setPoints] = useState<PointDatum[]>([]);

  // Track dimensions for responsive sizing
  useEffect(() => {
    function updateDimensions() {
      setDimensions({
        width: window.innerWidth,
        height: window.innerHeight,
      });
    }
    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  // Convert incoming attacks to arc/point data
  useEffect(() => {
    const recent = attacks.slice(0, MAX_ARCS);

    const newArcs: ArcDatum[] = recent.map((a) => ({
      id: a.id,
      startLat: a.source_lat,
      startLng: a.source_lng,
      endLat: a.dest_lat,
      endLng: a.dest_lng,
      color: ATTACK_COLORS[a.attack_type] ?? "#ffffff",
      stroke: Math.max(0.5, (a.severity / 10) * 2.5),
      attackType: a.attack_type,
    }));

    // Destination glow points (deduplicated by id)
    const pointMap = new Map<string, PointDatum>();
    recent.forEach((a) => {
      const key = `${a.dest_lat.toFixed(2)},${a.dest_lng.toFixed(2)}`;
      if (!pointMap.has(key)) {
        pointMap.set(key, {
          id: a.id,
          lat: a.dest_lat,
          lng: a.dest_lng,
          color: ATTACK_COLORS[a.attack_type] ?? "#ffffff",
          attackType: a.attack_type,
        });
      }
    });

    setArcs(newArcs);
    setPoints(Array.from(pointMap.values()));
  }, [attacks]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100vw", height: "100vh", background: "#000011" }}
    >
      {dimensions.width > 0 && (
        <GlobeGL
          width={dimensions.width}
          height={dimensions.height}
          globeImageUrl="https://unpkg.com/three-globe/example/img/earth-dark.jpg"
          backgroundColor="#000011"
          atmosphereColor="#1a237e"
          atmosphereAltitude={0.25}
          // Arcs
          arcsData={arcs}
          arcStartLat={(d) => (d as ArcDatum).startLat}
          arcStartLng={(d) => (d as ArcDatum).startLng}
          arcEndLat={(d) => (d as ArcDatum).endLat}
          arcEndLng={(d) => (d as ArcDatum).endLng}
          arcColor={(d) => (d as ArcDatum).color}
          arcAltitude={null}
          arcStroke={(d) => (d as ArcDatum).stroke}
          arcDashLength={0.4}
          arcDashGap={0.2}
          arcDashAnimateTime={1500}
          // Destination points
          pointsData={points}
          pointLat={(d) => (d as PointDatum).lat}
          pointLng={(d) => (d as PointDatum).lng}
          pointColor={(d) => (d as PointDatum).color}
          pointAltitude={0.01}
          pointRadius={0.3}
          // Auto-rotate
          animateIn={true}
        />
      )}
    </div>
  );
}

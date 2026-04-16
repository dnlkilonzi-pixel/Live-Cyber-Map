// Type shims for packages without bundled TypeScript declarations.

declare module "globe.gl" {
  import type * as React from "react";

  interface GlobeProps {
    // Geometry
    width?: number;
    height?: number;
    globeImageUrl?: string;
    bumpImageUrl?: string;
    backgroundImageUrl?: string;
    backgroundColor?: string;
    showAtmosphere?: boolean;
    atmosphereColor?: string;
    atmosphereAltitude?: number;
    animateIn?: boolean;

    // Arcs
    arcsData?: object[];
    arcStartLat?: ((d: object) => number) | string;
    arcStartLng?: ((d: object) => number) | string;
    arcEndLat?: ((d: object) => number) | string;
    arcEndLng?: ((d: object) => number) | string;
    arcColor?: ((d: object) => string | string[]) | string;
    arcAltitude?: ((d: object) => number) | number | null;
    arcAltitudeAutoScale?: number;
    arcStroke?: ((d: object) => number) | number | null;
    arcDashLength?: number;
    arcDashGap?: number;
    arcDashAnimateTime?: number;
    onArcClick?: (arc: object) => void;

    // Points
    pointsData?: object[];
    pointLat?: ((d: object) => number) | string;
    pointLng?: ((d: object) => number) | string;
    pointColor?: ((d: object) => string) | string;
    pointAltitude?: ((d: object) => number) | number;
    pointRadius?: ((d: object) => number) | number;
    onPointClick?: (point: object) => void;

    // Labels
    labelsData?: object[];
    labelLat?: ((d: object) => number) | string;
    labelLng?: ((d: object) => number) | string;
    labelText?: ((d: object) => string) | string;
    labelSize?: ((d: object) => number) | number;
    labelColor?: ((d: object) => string) | string;
    labelDotRadius?: ((d: object) => number) | number;
    labelAltitude?: ((d: object) => number) | number;

    // Polygons
    polygonsData?: object[];
    polygonGeoJsonGeometry?: ((d: object) => object) | string;
    polygonCapColor?: ((d: object) => string) | string;
    polygonSideColor?: ((d: object) => string) | string;
    polygonStrokeColor?: ((d: object) => string) | string;
    polygonAltitude?: ((d: object) => number) | number;
    onPolygonClick?: (polygon: object) => void;

    // Hex bins
    hexBinPointsData?: object[];
    hexBinPointLat?: ((d: object) => number) | string;
    hexBinPointLng?: ((d: object) => number) | string;
    hexBinPointWeight?: ((d: object) => number) | string;
    hexBinResolution?: number;
    hexTopColor?: ((d: object) => string) | string;
    hexSideColor?: ((d: object) => string) | string;
    hexAltitude?: ((d: object) => number) | number;

    // Camera / controls
    pointOfView?: { lat: number; lng: number; altitude?: number };

    [key: string]: unknown;
  }

  const Globe: React.ComponentType<GlobeProps>;
  export default Globe;
}

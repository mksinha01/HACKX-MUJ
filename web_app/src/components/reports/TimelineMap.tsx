import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { TimelineBreadcrumb } from '../../types/sighting';
import { APP_CONSTANTS } from '../../config/constants';

interface TimelineMapProps {
  breadcrumbs: TimelineBreadcrumb[];
  height?: string;
}

export const TimelineMap: React.FC<TimelineMapProps> = ({
  breadcrumbs,
  height = '480px',
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    // Filter valid GPS coordinates
    const validPoints = breadcrumbs.filter(
      (b) => b.latitude != null && b.longitude != null && !isNaN(b.latitude) && !isNaN(b.longitude)
    );

    const defaultCenter: [number, number] = validPoints.length > 0
      ? [validPoints[0].latitude!, validPoints[0].longitude!]
      : [28.6139, 77.2090]; // Default New Delhi

    // Initialize Map if not already created
    if (!mapInstanceRef.current) {
      const map = L.map(mapContainerRef.current, {
        center: defaultCenter,
        zoom: 14,
        zoomControl: true,
      });

      L.tileLayer(APP_CONSTANTS.OSM_TILE_URL, {
        attribution: APP_CONSTANTS.OSM_ATTRIBUTION,
        maxZoom: 19,
      }).addTo(map);

      mapInstanceRef.current = map;
    }

    const map = mapInstanceRef.current;

    // Clear existing layers other than tile layer
    map.eachLayer((layer) => {
      if (!(layer instanceof L.TileLayer)) {
        map.removeLayer(layer);
      }
    });

    if (validPoints.length > 0) {
      const latLngs: [number, number][] = validPoints.map((p) => [p.latitude!, p.longitude!]);

      // Draw Polyline path
      const polyline = L.polyline(latLngs, {
        color: '#0e6f8a',
        weight: 3,
        opacity: 0.8,
        dashArray: '8, 8',
      }).addTo(map);

      // Add numbered custom markers
      validPoints.forEach((point, idx) => {
        const isLastSeen = idx === validPoints.length - 1;
        const iconColor = isLastSeen ? '#b34e4e' : '#0e6f8a';

        const customIcon = L.divIcon({
          className: 'custom-map-pin',
          html: `
            <div style="
              width: 32px; height: 32px;
              border-radius: 50%;
              background: ${iconColor};
              border: 3px solid #ffffff;
              box-shadow: 0 0 14px ${iconColor};
              display: flex; align-items: center; justify-content: center;
              color: #ffffff; font-weight: 800; font-size: 13px;
              font-family: sans-serif;
            ">
              ${idx + 1}
            </div>
          `,
          iconSize: [32, 32],
          iconAnchor: [16, 16],
        });

        const marker = L.marker([point.latitude!, point.longitude!], { icon: customIcon }).addTo(map);

        marker.bindPopup(`
          <div style="color: #0f172a; font-family: sans-serif; padding: 4px;">
            <div style="font-weight: 700; font-size: 14px; margin-bottom: 2px;">
              ${isLastSeen ? '🚨 Last Seen Location' : `Stop #${idx + 1}`}
            </div>
            <div style="font-size: 12px; color: #475569;">${point.camera_name}</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 4px;">
              ${new Date(point.detected_at).toLocaleString()}
            </div>
            <div style="font-weight: 700; font-size: 12px; color: #0284c7; margin-top: 4px;">
              Match Confidence: ${Math.round(point.similarity_score * 100)}%
            </div>
          </div>
        `);
      });

      // Fit bounds to polyline
      map.fitBounds(polyline.getBounds(), { padding: [40, 40] });
    }

    // Rule 5: Invalidate size after mount to prevent gray tiles
    const resizeTimer = setTimeout(() => {
      map.invalidateSize();
    }, 150);

    return () => clearTimeout(resizeTimer);
  }, [breadcrumbs]);

  return (
    <div
      ref={mapContainerRef}
      style={{
        width: '100%',
        height,
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-md)',
        zIndex: 1,
      }}
    />
  );
};

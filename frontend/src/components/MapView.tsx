import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { api, dt, ageAr, type AppSettings, type LocationRec } from "../api";

// Historical (consented) locations only. Markers are circles to avoid image assets.
export default function MapView({ locations }: { locations: LocationRec[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [cfg, setCfg] = useState<AppSettings["map"] | null>(null);

  useEffect(() => {
    api<AppSettings>("/api/settings").then((s) => setCfg(s.map)).catch(() => setCfg(null));
  }, []);

  useEffect(() => {
    if (!ref.current || !cfg || !cfg.enabled || locations.length === 0) return;
    const map = L.map(ref.current, { attributionControl: true });
    L.tileLayer(cfg.tile_url, { maxZoom: cfg.max_zoom, attribution: cfg.attribution }).addTo(map);
    const pts: L.LatLngExpression[] = [];
    locations.forEach((l, idx) => {
      const ll: L.LatLngExpression = [l.latitude, l.longitude];
      pts.push(ll);
      const color = idx === 0 ? "#0f5e8c" : "#64748b";
      if (l.accuracy_m) L.circle(ll, { radius: l.accuracy_m, color, weight: 1, fillOpacity: 0.08 }).addTo(map);
      const popup = document.createElement("div");
      popup.dir = "rtl";
      popup.textContent = `موقع تاريخي – تم الجمع ${dt(l.collected_at)} (${ageAr(l.collected_at)})`;
      L.circleMarker(ll, { radius: 7, color, fillColor: color, fillOpacity: 0.9 }).bindPopup(popup).addTo(map);
    });
    if (pts.length === 1) map.setView(pts[0], 16);
    else map.fitBounds(L.latLngBounds(pts), { padding: [30, 30] });
    return () => {
      map.remove();
    };
  }, [cfg, locations]);

  if (locations.length === 0) return null;
  if (cfg && !cfg.enabled)
    return <div className="text-sm text-slate-500">الخريطة معطّلة من الإعدادات – الإحداثيات معروضة في الجدول.</div>;
  return (
    <div>
      <div ref={ref} className="h-80 w-full overflow-hidden rounded-lg ring-1 ring-slate-200" />
      <p className="mt-1 text-xs text-slate-500">
        النقاط تاريخية فقط (الأحدث باللون الأزرق). في حال عدم توفر الإنترنت لن تظهر الخلفية، والإحداثيات تبقى صحيحة في الجدول.
      </p>
    </div>
  );
}

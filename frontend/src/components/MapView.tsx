import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export default function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = mapContainer.current;

    if (!container) return;

    const map = new maplibregl.Map({
      container,

      style: {
        version: 8,

        sources: {
          osm: {
            type: "raster",
            tiles: [
              "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            ],
            tileSize: 256,
            maxzoom: 19,
            attribution: "© OpenStreetMap contributors",
          },
        },

        layers: [
          {
            id: "osm-basemap",
            type: "raster",
            source: "osm",
          },
        ],
      },

      center: [26.1025, 44.4268],
      zoom: 11,
      maxZoom: 19,
    });

    map.addControl(
      new maplibregl.NavigationControl(),
      "top-right"
    );

    const resizeObserver = new ResizeObserver(() => {
      map.resize();
    });

    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      map.remove();
    };
  }, []);

  return (
  <div
    ref={mapContainer}
    className="map-container"
    aria-label="Interactive map of Bucharest"
  />
  );
}
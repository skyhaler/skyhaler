import MapView from "./components/MapView";
import LayerSwitcher from "./components/LayerSwitcher";
import { API_BASE_URL } from "./config/api";
import "./App.css";

function App() {
  return (
    <div className="app" data-api-base-url={API_BASE_URL}>
      <header className="app-header">
        <h1>Skyhaler</h1>
        <p>Pollen and Air Quality Monitoring</p>
      </header>

      <main className="app-content">
        <aside className="sidebar">
          <LayerSwitcher />
        </aside>

        <div className="map-wrapper">
          <MapView />

          <div className="map-credit">
            Data © AIM Space, provided for educational use
            in the ROSPIN Satellite Data Processing
            Masterclass 2026
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
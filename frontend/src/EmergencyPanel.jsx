import React, { useState, useEffect } from "react";
import {
  Phone,
  MapPin,
  Navigation,
  Info,
  AlertOctagon,
  Loader2,
} from "lucide-react";

export default function EmergencyPanel({
  token,
  apiBase,
  context,
  onGoToChat,
}) {
  const [loading, setLoading] = useState(false);
  const [geoStatus, setGeoStatus] = useState("idle"); // 'idle', 'locating', 'success', 'denied', 'error'
  const [location, setLocation] = useState(null); // { lat, lng }
  const [address, setAddress] = useState("");
  const [hospitals, setHospitals] = useState([]);
  const [errorMsg, setErrorMsg] = useState("");

  // 1. Geolocation lookup trigger
  const triggerGeolocation = () => {
    if (!navigator.geolocation) {
      setGeoStatus("error");
      setErrorMsg("Geolocation is not supported by your browser.");
      return;
    }

    setGeoStatus("locating");
    setErrorMsg("");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coords = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        };
        setLocation(coords);
        setGeoStatus("success");
        fetchNearbyHospitals(coords.lat, coords.lng);
      },
      (error) => {
        console.warn("Geolocation permission denied or error:", error);
        setGeoStatus("denied");
        setErrorMsg(
          "Geolocation permission denied or unavailable. Please enter location manually.",
        );
      },
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 },
    );
  };

  // 2. Trigger geolocation automatically if context exists on mount
  useEffect(() => {
    if (context) {
      triggerGeolocation();
    } else {
      setGeoStatus("idle");
      setLocation(null);
      setHospitals([]);
      setErrorMsg("");
    }
  }, [context]);

  // 3. Fetch nearby hospitals from backend API
  const fetchNearbyHospitals = async (lat, lng) => {
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await fetch(
        `${apiBase}/nearby-hospitals?lat=${lat}&lng=${lng}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );
      const data = await res.json();
      if (res.ok && data.results) {
        setHospitals(data.results);
        if (data.results.length === 0) {
          setErrorMsg("No nearby hospitals found within a 10km radius.");
        }
      } else {
        setErrorMsg(data.error || "Failed to retrieve nearby hospitals.");
      }
    } catch (err) {
      console.error("Error fetching hospitals:", err);
      setErrorMsg("Network error while looking up nearby hospitals.");
    } finally {
      setLoading(false);
    }
  };

  // 4. Geocode town name fallback
  const handleGeocode = async (e) => {
    e.preventDefault();
    if (!address.trim()) return;

    setLoading(true);
    setErrorMsg("");
    try {
      const res = await fetch(
        `${apiBase}/geocode?address=${encodeURIComponent(address.trim())}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );
      const data = await res.json();
      if (res.ok && data.lat && data.lng) {
        const coords = { lat: data.lat, lng: data.lng };
        setLocation(coords);
        setGeoStatus("success");
        fetchNearbyHospitals(coords.lat, coords.lng);
      } else {
        setErrorMsg(
          data.error ||
            "Could not find that location. Please check the spelling.",
        );
      }
    } catch (err) {
      console.error("Geocoding error:", err);
      setErrorMsg("Network error while geocoding your town/village name.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="emergency-panel">
      {/* Referral context card if triggered via chat banner */}
      {context && (
        <div className="emergency-context-banner">
          <div>
            <strong>Triggered by query:</strong> "
            {context.queryText.substring(0, 60)}
            {context.queryText.length > 60 ? "..." : ""}"
          </div>
          <button
            type="button"
            className="context-link-btn"
            onClick={() => onGoToChat(context.chatId)}
          >
            Go to Chat →
          </button>
        </div>
      )}

      {/* Header Alert Header */}
      <div className="emergency-header">
        <AlertOctagon size={28} className="emergency-icon animate-pulse" />
        <div>
          <h4 className="emergency-title">
            🚨 EMERGENCY REFERRAL ACTION PANEL
          </h4>
          <p className="emergency-subtitle">
            Find nearby hospitals and emergency contacts
          </p>
        </div>
      </div>

      {/* Ambulance & Helpline Hotlines */}
      <div className="emergency-hotlines">
        <a href="tel:108" className="hotline-btn ambulance">
          <Phone size={20} />
          <div className="text-left">
            <span className="hotline-label">CALL AMBULANCE</span>
            <span className="hotline-number">108</span>
          </div>
        </a>
        <a href="tel:104" className="hotline-btn helpline">
          <Phone size={20} />
          <div className="text-left">
            <span className="hotline-label">HEALTH HELPLINE</span>
            <span className="hotline-number">104</span>
          </div>
        </a>
      </div>

      {/* Location lookup section */}
      <div className="emergency-location-prompt">
        <p className="location-prompt-text">📍 Location Lookup:</p>
        <div className="location-action-row">
          <button
            type="button"
            className="location-submit-btn"
            onClick={triggerGeolocation}
            disabled={loading}
            style={{ backgroundColor: "var(--primary)" }}
          >
            Use Current Location
          </button>
          <span className="location-or-divider">or search manually:</span>
        </div>
        <form onSubmit={handleGeocode} className="location-form">
          <input
            type="text"
            placeholder="e.g. Mandya, Karnataka"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className="location-input"
            disabled={loading}
          />
          <button
            type="submit"
            className="location-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              "Search"
            )}
          </button>
        </form>
      </div>

      {/* Hospitals List */}
      <div className="emergency-hospitals-section">
        <h5 className="hospitals-title">Nearest Facilities (within 10 km)</h5>

        {loading && (
          <div className="emergency-status-container">
            <Loader2 size={24} className="animate-spin text-red-600" />
            <span className="status-text">Locating nearest hospitals...</span>
          </div>
        )}

        {!loading && errorMsg && (
          <div className="emergency-error-state">
            <p className="error-text">⚠️ {errorMsg}</p>
            <p className="error-hint">
              Please call 108 for immediate ambulance assistance.
            </p>
          </div>
        )}

        {!loading && hospitals.length > 0 && (
          <div className="hospitals-list">
            {hospitals.map((h, i) => (
              <div key={h.place_id || i} className="hospital-card">
                <div className="hospital-info">
                  <div className="hospital-name-row">
                    <span className="hospital-name">{h.name}</span>
                    <span
                      className={`hospital-badge ${h.hospital_type.toLowerCase()}`}
                    >
                      {h.hospital_type}
                      <span
                        className="tooltip-trigger"
                        title="Classification is estimated based on facility name heuristics and Place Types. Verify locally."
                      >
                        <Info
                          size={12}
                          className="ml-1 inline text-gray-400"
                          style={{ verticalAlign: "middle" }}
                        />
                      </span>
                    </span>
                  </div>
                  <div className="hospital-meta">
                    <span className="hospital-distance">
                      <MapPin size={14} className="mr-1" />
                      {h.distance_km} km
                    </span>
                    {h.phone && (
                      <a
                        href={`tel:${h.phone}`}
                        className="hospital-phone-link"
                      >
                        <Phone size={14} className="mr-1" />
                        {h.phone}
                      </a>
                    )}
                  </div>
                </div>
                <a
                  href={h.maps_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hospital-directions-btn"
                >
                  <Navigation size={16} className="mr-1.5" />
                  Get Directions
                </a>
              </div>
            ))}
          </div>
        )}

        {!loading &&
          hospitals.length === 0 &&
          !errorMsg &&
          geoStatus !== "denied" && (
            <div className="emergency-status-container">
              <p className="status-text text-gray-500">
                Retrieving location info...
              </p>
            </div>
          )}
      </div>
    </div>
  );
}

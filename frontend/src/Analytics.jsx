import React, { useState, useEffect } from "react";
import {
  RefreshCw,
  ArrowLeft,
  ShieldCheck,
  Zap,
  Image as ImageIcon,
  MessageCircle,
} from "lucide-react";

const API_BASE =
  window.location.port === "5173" ? "http://localhost:8000/api" : "/api";

export default function Analytics({ token, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const fetchAnalytics = async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError("");
    try {
      const res = await fetch(`${API_BASE}/analytics/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      if (res.ok) {
        const result = await res.json();
        setData(result.analytics);
      } else {
        const errorData = await res.json();
        setError(errorData.detail || "Failed to load analytics");
      }
    } catch (err) {
      setError("Unable to connect to the server. Please check your network.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, [token]);

  if (loading) {
    return (
      <div className="analytics-loading">
        <div className="analytics-spinner"></div>
        <p>Retrieving your query trends...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analytics-error-container">
        <div className="analytics-error-card">
          <h3>Oops! Something went wrong</h3>
          <p>{error}</p>
          <button
            onClick={() => fetchAnalytics()}
            className="analytics-btn-primary"
          >
            <RefreshCw className="w-4 h-4 mr-2" /> Try Again
          </button>
        </div>
      </div>
    );
  }

  const stats = data || {
    total_queries: 0,
    success_rate: 0,
    avg_response_ms: 0,
    total_image_uploads: 0,
    query_types: [],
    languages: [],
    queries_per_day: [],
  };

  const isEmpty = stats.total_queries === 0;

  // Query types and designated colors matching badge colors in App
  const queryTypeMeta = {
    maternal_health: { label: "Maternal Health", color: "#ec4899" },
    child_health: { label: "Child Health", color: "#0ea5e9" },
    scheme_eligibility: { label: "Govt Schemes", color: "#f59e0b" },
    referral_decision: { label: "Referral Decision", color: "#ef4444" },
    drug_protocol: { label: "Drug Protocol", color: "#8b5cf6" },
    general_health: { label: "General Health", color: "var(--primary)" },
    greeting: { label: "Greetings", color: "var(--text-muted)" },
    medical_document: { label: "Doc Analysis", color: "#10b981" },
  };

  const queryTypesList = [
    "maternal_health",
    "child_health",
    "scheme_eligibility",
    "referral_decision",
    "drug_protocol",
    "general_health",
  ].map((type) => {
    const found = stats.query_types.find((q) => q.query_type === type);
    return {
      type,
      count: found ? found.count : 0,
      label: queryTypeMeta[type].label,
      color: queryTypeMeta[type].color,
    };
  });

  // Check if there are other query types (like greeting, error, medical_document) to show if count > 0
  stats.query_types.forEach((q) => {
    if (
      ![
        "maternal_health",
        "child_health",
        "scheme_eligibility",
        "referral_decision",
        "drug_protocol",
        "general_health",
      ].includes(q.query_type)
    ) {
      const meta = queryTypeMeta[q.query_type] || {
        label: q.query_type,
        color: "var(--text-muted)",
      };
      queryTypesList.push({
        type: q.query_type,
        count: q.count,
        label: meta.label,
        color: meta.color,
      });
    }
  });

  const languageColors = {
    English: "var(--primary)",
    Hindi: "#3b82f6",
    Tamil: "#f59e0b",
    Telugu: "#ec4899",
  };

  const languageList = stats.languages.map((l) => ({
    ...l,
    color: languageColors[l.language] || "var(--text-muted)",
  }));

  const totalLanguagesCount = languageList.reduce(
    (acc, curr) => acc + curr.count,
    0,
  );

  const donutRadius = 50;
  const donutCircumference = 2 * Math.PI * donutRadius;
  let accumulatedPercent = 0;

  const donutSegments = languageList.map((lang) => {
    const percent =
      totalLanguagesCount > 0 ? lang.count / totalLanguagesCount : 0;
    const strokeLength = percent * donutCircumference;
    const strokeOffset =
      donutCircumference - accumulatedPercent * donutCircumference;
    accumulatedPercent += percent;
    return {
      ...lang,
      percent: (percent * 100).toFixed(1),
      strokeLength,
      strokeOffset,
    };
  });

  const lineChartWidth = 500;
  const lineChartHeight = 220;
  const lineChartPadding = { left: 40, right: 20, top: 20, bottom: 40 };

  const plotWidth =
    lineChartWidth - lineChartPadding.left - lineChartPadding.right;
  const plotHeight =
    lineChartHeight - lineChartPadding.top - lineChartPadding.bottom;

  const dailyData = stats.queries_per_day || [];
  const maxDayCount = Math.max(...dailyData.map((d) => d.count), 4); // default grid scale is at least 4 queries

  const linePoints = dailyData.map((d, i) => {
    const x =
      lineChartPadding.left +
      (i / Math.max(dailyData.length - 1, 1)) * plotWidth;
    const y =
      lineChartPadding.top + plotHeight - (d.count / maxDayCount) * plotHeight;
    return { x, y, date: d.date, count: d.count };
  });

  let linePathD = "";
  let areaPathD = "";
  if (linePoints.length > 0) {
    linePathD =
      `M ${linePoints[0].x} ${linePoints[0].y} ` +
      linePoints
        .slice(1)
        .map((p) => `L ${p.x} ${p.y}`)
        .join(" ");
    areaPathD = `${linePathD} L ${linePoints[linePoints.length - 1].x} ${lineChartPadding.top + plotHeight} L ${linePoints[0].x} ${lineChartPadding.top + plotHeight} Z`;
  }

  const gridLines = [];
  const gridDivisions = 4;
  for (let i = 0; i <= gridDivisions; i++) {
    const ratio = i / gridDivisions;
    const y = lineChartPadding.top + ratio * plotHeight;
    const val = Math.round(maxDayCount * (1 - ratio));
    gridLines.push({ y, val });
  }

  return (
    <div className="analytics-container">
      <header className="analytics-header">
        <div className="analytics-header-left">
          <button
            onClick={onClose}
            className="analytics-back-btn"
            title="Back to Chat"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h2>Your Analytics Dashboard</h2>
            <p className="analytics-subtitle">
              Query trends and activity summaries for your account
            </p>
          </div>
        </div>
        <button
          onClick={() => fetchAnalytics(true)}
          className={`analytics-refresh-btn ${refreshing ? "spinning" : ""}`}
          disabled={refreshing}
          title="Refresh statistics"
        >
          <RefreshCw className="w-4 h-4" />
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {isEmpty ? (
        <div className="analytics-empty-state">
          <div className="empty-state-icon">📊</div>
          <h3>No activity recorded yet</h3>
          <p>
            Start chatting with HealthBridge AI or upload medical documents.
            Once you make queries, your diagnostic support trends will appear
            here.
          </p>
          <button onClick={onClose} className="analytics-btn-primary mt-4">
            Start a Conversation
          </button>
        </div>
      ) : (
        <div className="analytics-content">
          <div className="analytics-summary-grid">
            <div className="summary-card">
              <div className="card-icon-wrapper chat-icon">
                <MessageCircle className="w-5 h-5" />
              </div>
              <div className="card-info">
                <span className="card-label">Total Queries</span>
                <span className="card-value">{stats.total_queries}</span>
              </div>
            </div>

            <div className="summary-card">
              <div className="card-icon-wrapper success-icon">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div className="card-info">
                <span className="card-label">Success Rate</span>
                <span className="card-value">{stats.success_rate}%</span>
              </div>
            </div>

            <div className="summary-card">
              <div className="card-icon-wrapper latency-icon">
                <Zap className="w-5 h-5" />
              </div>
              <div className="card-info">
                <span className="card-label">Avg Latency</span>
                <span className="card-value">
                  {stats.avg_response_ms >= 1000
                    ? `${(stats.avg_response_ms / 1000).toFixed(2)}s`
                    : `${Math.round(stats.avg_response_ms)}ms`}
                </span>
              </div>
            </div>

            <div className="summary-card">
              <div className="card-icon-wrapper image-icon">
                <ImageIcon className="w-5 h-5" />
              </div>
              <div className="card-info">
                <span className="card-label">Image Uploads</span>
                <span className="card-value">{stats.total_image_uploads}</span>
              </div>
            </div>
          </div>

          <div className="analytics-charts-grid">
            <div className="chart-card">
              <h3 className="chart-title">Query Types Distribution</h3>
              <div className="bar-chart-container">
                {queryTypesList.map((item) => {
                  const percentage =
                    stats.total_queries > 0
                      ? (item.count / stats.total_queries) * 100
                      : 0;
                  return (
                    <div key={item.type} className="bar-chart-row">
                      <div className="bar-label-group">
                        <span className="bar-label">{item.label}</span>
                        <span className="bar-value">{item.count}</span>
                      </div>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{
                            width: `${percentage}%`,
                            backgroundColor: item.color,
                            boxShadow: `0 2px 4px ${item.color}25`,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="chart-card flex-col-center">
              <h3 className="chart-title align-self-start">
                Language Distribution
              </h3>
              <div className="donut-chart-wrapper">
                <div className="donut-svg-container">
                  <svg width="150" height="150" viewBox="0 0 120 120">
                    <circle
                      cx="60"
                      cy="60"
                      r={donutRadius}
                      fill="transparent"
                      stroke="var(--primary-border)"
                      strokeWidth="12"
                    />
                    {donutSegments.map((seg, idx) => (
                      <circle
                        key={idx}
                        cx="60"
                        cy="60"
                        r={donutRadius}
                        fill="transparent"
                        stroke={seg.color}
                        strokeWidth="12"
                        strokeDasharray={`${seg.strokeLength} ${donutCircumference - seg.strokeLength}`}
                        strokeDashoffset={seg.strokeOffset}
                        transform="rotate(-90 60 60)"
                        style={{
                          transition:
                            "stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
                        }}
                      />
                    ))}
                  </svg>
                  <div className="donut-center-label">
                    <span className="donut-count">{stats.total_queries}</span>
                    <span className="donut-label">Queries</span>
                  </div>
                </div>

                <div className="donut-legend">
                  {donutSegments.map((seg, idx) => (
                    <div key={idx} className="legend-item">
                      <span
                        className="legend-dot"
                        style={{ backgroundColor: seg.color }}
                      ></span>
                      <span className="legend-name">{seg.language}</span>
                      <span className="legend-count">({seg.count})</span>
                      <span className="legend-percent">{seg.percent}%</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="chart-card full-width-chart">
              <h3 className="chart-title">Query Trends (Last 7 Days)</h3>
              <div className="line-chart-container">
                <svg
                  width="100%"
                  height="100%"
                  viewBox={`0 0 ${lineChartWidth} ${lineChartHeight}`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient
                      id="chartGradient"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="0%"
                        stopColor="var(--primary)"
                        stopOpacity="0.25"
                      />
                      <stop
                        offset="100%"
                        stopColor="var(--primary)"
                        stopOpacity="0.0"
                      />
                    </linearGradient>
                  </defs>

                  {gridLines.map((line, i) => (
                    <g key={i}>
                      <line
                        x1={lineChartPadding.left}
                        y1={line.y}
                        x2={lineChartWidth - lineChartPadding.right}
                        y2={line.y}
                        stroke="var(--primary-border)"
                        strokeWidth="1"
                        strokeDasharray="4 4"
                      />
                      <text
                        x={lineChartPadding.left - 8}
                        y={line.y + 4}
                        textAnchor="end"
                        fontSize="10"
                        fill="var(--text-secondary)"
                        className="grid-text"
                      >
                        {line.val}
                      </text>
                    </g>
                  ))}

                  {areaPathD && (
                    <path d={areaPathD} fill="url(#chartGradient)" />
                  )}

                  {linePathD && (
                    <path
                      d={linePathD}
                      fill="none"
                      stroke="var(--primary)"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  )}

                  {linePoints.map((pt, i) => (
                    <g key={i} className="chart-point-group">
                      <circle
                        cx={pt.x}
                        cy={pt.y}
                        r="5"
                        fill="var(--primary)"
                        stroke="var(--bg-card)"
                        strokeWidth="2"
                        className="chart-circle"
                      />
                      {/* Invisible hover helper with larger trigger area */}
                      <circle
                        cx={pt.x}
                        cy={pt.y}
                        r="12"
                        fill="transparent"
                        className="chart-circle-hover-trigger"
                      >
                        <title>{`${pt.date}: ${pt.count} query(s)`}</title>
                      </circle>
                    </g>
                  ))}

                  {linePoints.map((pt, i) => {
                    const dateObj = new Date(pt.date);
                    const labelStr = dateObj.toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "short",
                    });
                    return (
                      <text
                        key={i}
                        x={pt.x}
                        y={lineChartHeight - lineChartPadding.bottom + 18}
                        textAnchor="middle"
                        fontSize="10"
                        fill="var(--text-secondary)"
                        className="axis-text"
                      >
                        {labelStr}
                      </text>
                    );
                  })}
                </svg>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

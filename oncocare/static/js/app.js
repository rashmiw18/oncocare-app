/* ==========================================================================
   OncoCare AI — Dashboard logic
   Handles: vitals form submission, prediction rendering, charts, history,
   quick-fill sample profiles, and summary stats.
   ========================================================================== */

const FEATURES = ["temperature", "heart_rate", "spo2", "sleep_hours", "pain_level", "fatigue_level", "nausea_level", "dizziness"];

const RISK_COLORS = {
  Low: "#8FD19E",
  Medium: "#F4C669",
  High: "#F2836B"
};

let trendChart, radarChart, donutChart;

const PATIENT_ID = document.body.dataset.patientId;
const IS_DOCTOR_VIEW = document.body.dataset.isDoctorView === "true";

function withPatientParam(url) {
  const u = new URL(url, window.location.origin);
  if (PATIENT_ID) u.searchParams.set("patient_id", PATIENT_ID);
  return u.pathname + u.search;
}

function withPatientBody(body) {
  if (PATIENT_ID) return { ...body, patient_id: PATIENT_ID };
  return body;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function $(id) { return document.getElementById(id); }

function readFormVitals() {
  return {
    temperature: parseFloat($("temperature").value),
    heart_rate: parseFloat($("heart_rate").value),
    spo2: parseFloat($("spo2").value),
    sleep_hours: parseFloat($("sleep_hours").value),
    pain_level: parseFloat($("pain_level").value),
    fatigue_level: parseFloat($("fatigue_level").value),
    nausea_level: parseFloat($("nausea_level").value),
    dizziness: $("dizziness").checked ? 1 : 0
  };
}

function fillForm(vitals) {
  $("temperature").value = vitals.temperature;
  $("heart_rate").value = vitals.heart_rate;
  $("spo2").value = vitals.spo2;
  $("sleep_hours").value = vitals.sleep_hours;
  $("pain_level").value = vitals.pain_level;
  $("fatigue_level").value = vitals.fatigue_level;
  $("nausea_level").value = vitals.nausea_level;
  $("dizziness").checked = !!vitals.dizziness;
  syncSliderLabels();
}

function syncSliderLabels() {
  $("painOut").textContent = $("pain_level").value;
  $("fatigueOut").textContent = $("fatigue_level").value;
  $("nauseaOut").textContent = $("nausea_level").value;
}

function formatTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ---------------------------------------------------------------------------
// Result card rendering
// ---------------------------------------------------------------------------

function renderResult(record) {
  // Normalize record so missing properties won't throw in the UI
  const r = normalizeRecord(record);

  $("resultEmpty").classList.add("hidden");
  $("resultFilled").classList.remove("hidden");
  $("resultTimestamp").textContent = r._prediction_error ? `Prediction issue: ${r._prediction_error}` : "Updated " + formatTime(r.timestamp);

  // Gauge: circumference ~267 for the arc path used in the SVG
  const CIRC = 267;
  const pct = Math.max(0, Math.min(1, r.risk_score / 15));
  const offset = CIRC * (1 - pct);
  const fillEl = $("gaugeFill");
  fillEl.style.strokeDashoffset = offset;
  fillEl.style.stroke = RISK_COLORS[r.risk_level] || RISK_COLORS.Medium;

  $("gaugeScore").textContent = isFinite(r.risk_score) ? r.risk_score.toFixed(1) : "—";

  const levelBadge = $("riskLevelBadge");
  levelBadge.textContent = `${r.risk_level} risk`;
  levelBadge.className = `risk-level ${r.risk_level}`;

  const probaRow = $("probaRow");
  // Ensure the three expected keys exist and render safely
  const probs = { Low: 0, Medium: 0, High: 0, ...r.risk_probabilities };
  probaRow.innerHTML = Object.entries(probs)
    .map(([k, v]) => `<span style="color:${RISK_COLORS[k]}">${k} ${Number(v).toFixed(0)}%</span>`)
    .join("");

  const anomalyBanner = $("anomalyBanner");
  anomalyBanner.classList.toggle("hidden", !r.is_anomaly);

  const flagList = $("flagList");
  flagList.innerHTML = (Array.isArray(r.flags) ? r.flags : []).map(f =>
    `<li>${(f.feature || "").replace("_", " ")}: ${f.value ?? "—"} (normal ${f.normal_range ?? "—"})</li>`
  ).join("");
}

// Ensure a record object has the shape the UI expects
function normalizeRecord(record) {
  record = record || {};
  return {
    timestamp: record.timestamp || new Date().toISOString(),
    vitals: record.vitals || readFormVitals(),
    risk_score: typeof record.risk_score === "number" ? record.risk_score : (record.risk_score ? Number(record.risk_score) : 0),
    risk_level: record.risk_level || "Unknown",
    risk_probabilities: record.risk_probabilities || {},
    is_anomaly: !!record.is_anomaly,
    anomaly_score: record.anomaly_score || 0,
    flags: Array.isArray(record.flags) ? record.flags : [],
    feature_importance: record.feature_importance || {},
    _prediction_error: record._prediction_error || null,
    // keep original object accessible if needed
    __raw: record
  };
}

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------

function initCharts() {
  const mutedGrid = "rgba(234,243,240,0.08)";
  const mutedText = "#9AC0B7";

  Chart.defaults.font.family = "Inter, sans-serif";
  Chart.defaults.color = mutedText;

  trendChart = new Chart($("trendChart"), {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "Risk score",
        data: [],
        borderColor: "#6FE0C5",
        backgroundColor: "rgba(111,224,197,0.15)",
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointBackgroundColor: "#6FE0C5"
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 15, grid: { color: mutedGrid }, ticks: { color: mutedText } },
        x: { grid: { display: false }, ticks: { color: mutedText, maxRotation: 0 } }
      }
    }
  });

  radarChart = new Chart($("radarChart"), {
    type: "radar",
    data: {
      labels: ["Temp", "Heart rate", "SpO\u2082", "Sleep", "Pain", "Fatigue", "Nausea", "Dizziness"],
      datasets: [
        {
          label: "Latest reading",
          data: [0, 0, 0, 0, 0, 0, 0, 0],
          borderColor: "#F2836B",
          backgroundColor: "rgba(242,131,107,0.18)",
          pointBackgroundColor: "#F2836B"
        },
        {
          label: "Normal midpoint",
          data: [50, 40, 98, 60, 15, 15, 15, 0],
          borderColor: "#6FE0C5",
          backgroundColor: "rgba(111,224,197,0.08)",
          pointBackgroundColor: "#6FE0C5"
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: mutedText, boxWidth: 12, font: { size: 11 } } } },
      scales: {
        r: {
          angleLines: { color: mutedGrid },
          grid: { color: mutedGrid },
          pointLabels: { color: mutedText, font: { size: 11 } },
          ticks: { display: false }
        }
      }
    }
  });

  donutChart = new Chart($("donutChart"), {
    type: "doughnut",
    data: {
      labels: ["Low", "Medium", "High"],
      datasets: [{
        data: [0, 0, 0],
        backgroundColor: [RISK_COLORS.Low, RISK_COLORS.Medium, RISK_COLORS.High],
        borderColor: "#14322C",
        borderWidth: 3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { color: mutedText, boxWidth: 12 } } },
      cutout: "68%"
    }
  });
}

// Normalize a raw vital reading onto a 0-100-ish scale matching radar's
// "normal midpoint" reference points, purely for visual comparison.
function normalizeForRadar(vitals) {
  return [
    Math.min(100, ((vitals.temperature - 95) / (106 - 95)) * 100),
    Math.min(100, (vitals.heart_rate / 180) * 100),
    vitals.spo2,
    Math.min(100, (vitals.sleep_hours / 10) * 100),
    vitals.pain_level * 10,
    vitals.fatigue_level * 10,
    vitals.nausea_level * 10,
    vitals.dizziness * 100
  ];
}

function updateTrendChart(history) {
  if (!trendChart) return;
  const labels = Array.isArray(history) && history.length ? history.map(r => formatTime(r.timestamp)) : ["No readings yet"];
  const data = Array.isArray(history) && history.length ? history.map(r => Number.isFinite(r.risk_score) ? r.risk_score : 0) : [0];
  trendChart.data.labels = labels;
  trendChart.data.datasets[0].data = data;
  trendChart.update();
}

function updateRadarChart(record) {
  if (!radarChart) return;
  const vitals = record && record.vitals ? record.vitals : {
    temperature: 98.6,
    heart_rate: 75,
    spo2: 97,
    sleep_hours: 7,
    pain_level: 0,
    fatigue_level: 0,
    nausea_level: 0,
    dizziness: 0
  };
  radarChart.data.datasets[0].data = normalizeForRadar(vitals);
  radarChart.update();
}

function updateDonutChart(dist) {
  if (!donutChart) return;
  const safeDist = dist || {};
  const low = Number.isFinite(safeDist.Low) ? safeDist.Low : 0;
  const medium = Number.isFinite(safeDist.Medium) ? safeDist.Medium : 0;
  const high = Number.isFinite(safeDist.High) ? safeDist.High : 0;
  donutChart.data.datasets[0].data = [low, medium, high];
  donutChart.update();
}

// ---------------------------------------------------------------------------
// Feature importance bars
// ---------------------------------------------------------------------------

function renderImportance(importance) {
  const container = $("importanceBars");
  container.innerHTML = "";
  const maxVal = Math.max(...Object.values(importance));
  Object.entries(importance).forEach(([feat, val]) => {
    const pct = (val / maxVal) * 100;
    const row = document.createElement("div");
    row.className = "imp-row";
    row.innerHTML = `
      <span class="imp-label">${feat.replace("_", " ")}</span>
      <span class="imp-track"><span class="imp-fill" style="width:0%"></span></span>
      <span class="imp-val">${(val * 100).toFixed(1)}%</span>
    `;
    container.appendChild(row);
    requestAnimationFrame(() => {
      row.querySelector(".imp-fill").style.width = pct + "%";
    });
  });
}

// ---------------------------------------------------------------------------
// History table
// ---------------------------------------------------------------------------

function renderHistoryTable(history) {
  const tbody = $("historyBody");
  if (!history.length) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="11">No readings yet — log one above to get started.</td></tr>`;
    return;
  }
  tbody.innerHTML = history.slice().reverse().map(r => `
    <tr>
      <td>${formatTime(r.timestamp)}</td>
      <td>${r.vitals.temperature}°F</td>
      <td>${r.vitals.heart_rate}</td>
      <td>${r.vitals.spo2}%</td>
      <td>${r.vitals.sleep_hours}h</td>
      <td>${r.vitals.pain_level}</td>
      <td>${r.vitals.fatigue_level}</td>
      <td>${r.vitals.nausea_level}</td>
      <td><span class="pill ${r.risk_level}">${r.risk_level}</span></td>
      <td>${r.risk_score.toFixed(1)}</td>
      <td>${r.is_anomaly ? '<span class="anomaly-tag" title="Unusual pattern">⚠</span>' : ""}</td>
    </tr>
  `).join("");
}

// ---------------------------------------------------------------------------
// Stats / hero numbers
// ---------------------------------------------------------------------------

async function refreshStats() {
  const res = await fetch(withPatientParam("/api/stats"));
  const stats = await res.json();

  $("statAccuracy").textContent = (stats.model_metrics.classifier_accuracy * 100).toFixed(1) + "%";
  $("statReadings").textContent = stats.total_readings;
  $("statAnomaly").textContent = stats.anomaly_count;

  updateDonutChart(stats.risk_distribution);
  renderImportance(stats.model_metrics.feature_importance);

  if (stats.latest) {
    renderResult(stats.latest);
    updateRadarChart(stats.latest);
  }
  renderForecast(stats.forecast, stats.latest);
}

async function refreshHistory() {
  const res = await fetch(withPatientParam("/api/history?limit=50"));
  const history = await res.json();
  renderHistoryTable(history);
  updateTrendChart(history);
}

async function refreshNotes() {
  const notesList = $("notesList");
  if (!notesList) return;
  const res = await fetch(withPatientParam("/api/notes"));
  if (res.ok) renderNotes(await res.json());
}

function renderNotes(notes) {
  const notesList = $("notesList");
  if (!notesList) return;
  if (!notes.length) {
    notesList.innerHTML = `<li class="empty-note">No notes yet.</li>`;
    return;
  }
  notesList.innerHTML = notes.map(n => `
    <li class="note-item">
      <div class="note-meta">
        <span class="note-doctor">Dr. ${n.doctor_name}</span>
        <span class="note-time">${new Date(n.timestamp).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</span>
      </div>
      <p>${n.note.replace(/</g, "&lt;")}</p>
    </li>
  `).join("");
}

function renderForecast(forecast, latest) {
  const el = $("forecastBanner");
  if (!el) return;
  if (!forecast || !latest) {
    el.classList.add("hidden");
    return;
  }
  const trendLabel = { rising: "trending up \u2191", falling: "trending down \u2193", stable: "holding steady \u2192" }[forecast.trend];
  const trendClass = { rising: "trend-up", falling: "trend-down", stable: "trend-stable" }[forecast.trend];
  el.className = "forecast-banner " + trendClass;
  el.innerHTML = `Trend forecast: risk score is <strong>${trendLabel}</strong> \u2014 next reading projected around <strong>${forecast.forecast_score.toFixed(1)}/15</strong>.`;
}

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------

function wireEvents() {
  ["pain_level", "fatigue_level", "nausea_level"].forEach(id => {
    $(id).addEventListener("input", syncSliderLabels);
  });

  document.querySelectorAll(".chip[data-profile]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const profile = btn.dataset.profile;
      const res = await fetch(`/api/sample?profile=${profile}`);
      const vitals = await res.json();
      fillForm(vitals);
    });
  });

  $("vitalsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("predictBtn");
    btn.disabled = true;
    btn.querySelector("span").textContent = "Analyzing…";

    try {
      const vitals = readFormVitals();
      const res = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(withPatientBody(vitals))
      });

      // Robust JSON parsing: server may return an HTML error page (e.g. login redirect)
      let record;
      if (res.ok) {
        try {
          record = await res.json();
        } catch (e) {
          const txt = await res.text();
          throw new Error("Invalid JSON response from server: " + (txt.length > 200 ? txt.slice(0,200) + '...' : txt));
        }
      } else {
        // Try parse structured error, otherwise fall back to plaintext/HTML
        let errMsg = "Prediction failed";
        try {
          const body = await res.json();
          errMsg = body.error || JSON.stringify(body);
        } catch (e) {
          const txt = await res.text();
          // Strip tags if HTML
          errMsg = txt.replace(/<[^>]+>/g, '').trim();
          if (!errMsg) errMsg = `HTTP ${res.status} ${res.statusText}`;
        }
        throw new Error(errMsg);
      }

      renderResult(record);
      updateRadarChart(record);
      await refreshHistory();
      await refreshStats();
    } catch (err) {
      console.error('Predict error', err);
      // Show a non-blocking inline error in the result header instead of an alert popup
      try {
        $("resultEmpty").classList.add("hidden");
        $("resultFilled").classList.remove("hidden");
        $("gaugeScore").textContent = "—";
        $("riskLevelBadge").textContent = "Error";
        $("resultTimestamp").textContent = "Prediction failed: " + (err.message || String(err));
      } catch (e) {
        // fallback to console only if DOM updates fail
        console.error('Failed to display inline prediction error', e);
      }
    } finally {
      btn.disabled = false;
      btn.querySelector("span").textContent = "Analyze reading";
    }
  });

  $("clearHistoryBtn").addEventListener("click", async () => {
    if (!confirm("Clear all logged readings?")) return;
    await fetch(withPatientParam("/api/history/clear"), { method: "POST" });
    await refreshHistory();
    await refreshStats();
  });

  const noteForm = $("noteForm");
  if (noteForm) {
    noteForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = $("noteInput");
      const text = input.value.trim();
      if (!text) return;
      const res = await fetch(withPatientParam("/api/notes"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(withPatientBody({ note: text }))
      });
      if (res.ok) {
        input.value = "";
        renderNotes(await res.json());
      }
    });
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

function waitForChartJs(callback, attemptsLeft) {
  if (attemptsLeft === undefined) attemptsLeft = 100; // ~10s at 100ms intervals
  if (typeof Chart !== "undefined") {
    callback(true);
    return;
  }
  if (attemptsLeft <= 0) {
    callback(false);
    return;
  }
  setTimeout(() => waitForChartJs(callback, attemptsLeft - 1), 100);
}

function showChartLoadError() {
  ["trendChart", "radarChart", "donutChart"].forEach(id => {
    const canvas = $(id);
    if (!canvas) return;
    const wrap = canvas.closest(".chart-wrap") || canvas.parentElement;
    wrap.innerHTML = '<div class="chart-error">Couldn\'t load the charting library. Check your internet connection or try disabling any ad-blocker/firewall for this site, then refresh.</div>';
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  syncSliderLabels();

  waitForChartJs((loaded) => {
    if (loaded) {
      try {
        initCharts();
      } catch (e) {
        console.error('Failed to initialize charts:', e);
        showChartLoadError();
      }
    } else {
      console.error('Chart.js failed to load from all sources.');
      showChartLoadError();
    }
    // Re-render with whatever stats/history have already loaded, now that
    // charts exist (safe no-op if they don't).
    refreshStats().catch(() => {});
    refreshHistory().catch(() => {});
  });

  // Wire events regardless of charts initialization so the form still works.
  try {
    wireEvents();
  } catch (e) {
    console.error('Failed to wire events:', e);
  }

  try { await refreshStats(); } catch (e) { console.error('refreshStats failed:', e); }
  try { await refreshHistory(); } catch (e) { console.error('refreshHistory failed:', e); }
  try { await refreshNotes(); } catch (e) { console.error('refreshNotes failed:', e); }
});

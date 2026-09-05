# OncoCare AI

An intelligent health-monitoring dashboard for cancer patients, with separate
**doctor** and **patient** logins. It goes beyond storing vitals: it
**predicts risk**, **flags unusual patterns**, **forecasts trend direction**,
and generates **downloadable PDF reports** — plus a Gemini-powered chatbot for
plain-language Q&A.

## What's inside

- **Authentication** — separate patient/doctor sign-up and login, session-based, passwords hashed (`werkzeug.security`). Patients optionally select their doctor at sign-up; doctors only ever see their own assigned patients.
- **Machine learning** (`model/train_model.py`, `ml.py`)
  - `RandomForestClassifier` → risk level (Low / Medium / High) — **99.3% test accuracy**
  - `RandomForestRegressor` → continuous 0–15 risk score — **R² = 0.997**
  - `IsolationForest` → flags statistically unusual readings, even when no single vital is wildly out of range
  - Lightweight linear-trend **forecast** of the next likely risk score (rising / falling / stable), shown on the dashboard
  - Rule-based normal-range checks layered on top, for interpretability
- **SQLite persistence** (`db.py`) — users, readings, and doctor clinical notes now survive server restarts (replaces the earlier in-memory demo store)
- **PDF reports** (`report.py`) — date-range report with risk trend chart, symptom-burden chart, a table of high-risk/anomalous readings, and any doctor notes, built with ReportLab + Matplotlib
- **Flask backend** (`app.py`) — REST API + page routes, all scoped by role (a doctor must explicitly own a patient to see or act on their data)
- **Frontend** (`templates/`, `static/`) — animated dashboard: live vitals form, risk gauge, trend/radar/donut charts (Chart.js), forecast banner, clinical notes, reading history, and a floating OncoBot chat widget
- **Chatbot** — calls the Gemini API (`gemini-2.0-flash`) directly from the Flask backend using an API key pasted into the UI (kept only in the browser's localStorage), grounded in the viewed patient's latest reading

## Setup

```bash
cd oncocare
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The models are already trained and saved under `model/*.pkl`. To retrain
(e.g. with an updated CSV in `data/`):

```bash
python model/train_model.py
```

## Run

```bash
python app.py
```

Open **http://localhost:5000** — you'll land on the login page.

## Getting started

1. **Register a doctor** first (Sign in page → "Create one" → Doctor tab). Doctors can optionally add a specialization.
2. **Register a patient** (Patient tab) and pick the doctor you just created from the dropdown — this links them.
3. Sign in as the **patient** to log vitals, watch the risk gauge/charts update, and chat with OncoBot.
4. Sign in as the **doctor** to see the patient list (with live risk badges), click into a patient to view their full dashboard, add clinical notes, and generate a PDF report.

A patient's dashboard and a doctor's view of that patient are the *same*
template — the doctor version just adds a "viewing as doctor" banner and the
ability to add notes.

## Using the chatbot

1. Click the round chat button (bottom-right) on any dashboard.
2. Click ⚙ and paste your **Gemini API key** ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)).
3. Ask things like *"What does my current risk level mean?"* — answers are grounded in the currently-viewed patient's latest reading.

You can also set `GEMINI_API_KEY` as a server-side environment variable
instead of entering it per-browser.

## Generating a report

Go to **Report** in the nav bar. Pick a date range (or use the quick-range
chips), select a patient if you're a doctor, and click **Download PDF
report**. The PDF includes a risk-trend chart, symptom-burden chart, a table
of notable (high-risk/anomalous) readings, and any clinical notes for that
period.

## Project structure

```
oncocare/
├── app.py                     # Flask routes: auth, dashboard, doctor, report, API, Gemini relay
├── auth.py                    # login_required / role_required decorators
├── db.py                      # SQLite schema + queries (users, readings, notes)
├── ml.py                      # model loading, make_prediction(), forecast_next_score()
├── report.py                  # PDF report builder (ReportLab + Matplotlib)
├── requirements.txt
├── oncocare.db                 # created on first run
├── data/
│   └── synthetic_oncocare_health_dataset.csv
├── model/
│   ├── train_model.py
│   ├── risk_classifier.pkl / risk_regressor.pkl / anomaly_detector.pkl
│   ├── scaler.pkl / label_encoder.pkl / metrics.json
├── templates/
│   ├── login.html / register.html
│   ├── dashboard.html          # shared by patient self-view and doctor patient-view
│   ├── doctor_home.html        # doctor's patient list
│   └── report.html
└── static/
    ├── css/style.css, auth.css
    └── js/app.js, chatbot.js, report.js
```

## API reference

All `/api/*` routes require login. Doctors must pass `patient_id` (query
string or JSON body) identifying one of their own patients; patients are
always scoped to themselves automatically.

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/predict` | Log a vitals reading → risk level/score, anomaly flag, out-of-range flags |
| GET | `/api/history?limit=50` | Recent logged readings |
| POST | `/api/history/clear` | Wipe a patient's reading history |
| GET | `/api/stats` | Summary stats, model metrics, and trend forecast |
| GET | `/api/sample?profile=healthy\|concerning\|random` | Generate a demo vitals reading |
| GET/POST | `/api/notes` | View / add doctor clinical notes for a patient |
| POST | `/api/chat` | Send a chat message + Gemini API key, get OncoBot's reply |
| GET | `/report/download?start=YYYY-MM-DD&end=YYYY-MM-DD[&patient_id=]` | Download the PDF report |

## Notes on real-world deployment

This remains a demo/prototype:
- SQLite is fine for local use but swap for Postgres/MySQL under real load.
- There's no password reset, email verification, or rate limiting on login.
- `SECRET_KEY` defaults to a hardcoded dev value — **set a real one** via the `SECRET_KEY` environment variable before deploying anywhere reachable.
- Any real clinical deployment handling actual patient data (PHI) needs HIPAA-appropriate hosting, encryption at rest, audit logging, and a security review — this project does not provide those on its own.

## Disclaimer

This is a decision-support demo, not a certified medical device. It does not
replace clinical judgement — always route real deterioration concerns to the
patient's oncology care team.

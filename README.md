# ☕ AI-Powered Smart Coffee Estate Management System

A production-grade, full-stack Agricultural ERP and Decision Support Platform tailored for coffee plantations in Chikmagalur, Karnataka and coffee-growing regions across India.

---

## 🌐 Live Website Links (Clickable in VS Code)

> In VS Code, hold **`Ctrl`** and **click** any of the links below to open them in your browser!

- 🏠 **Main Website:** 👉 [http://127.0.0.1:5000](http://127.0.0.1:5000)
- 📊 **Smart Dashboard:** 👉 [http://127.0.0.1:5000/dashboard](http://127.0.0.1:5000/dashboard)
- 🗺️ **Farm Management:** 👉 [http://127.0.0.1:5000/farm](http://127.0.0.1:5000/farm)
- 🌦️ **Weather & Rainfall:** 👉 [http://127.0.0.1:5000/weather](http://127.0.0.1:5000/weather)
- 💧 **Sprinkler & Irrigation:** 👉 [http://127.0.0.1:5000/sprinkler](http://127.0.0.1:5000/sprinkler)
- 📷 **Biometric Face Attendance:** 👉 [http://127.0.0.1:5000/attendance/face-checkin](http://127.0.0.1:5000/attendance/face-checkin)
- 🤖 **AI Estate Chatbot:** 👉 [http://127.0.0.1:5000/ai/chatbot](http://127.0.0.1:5000/ai/chatbot)
- 📋 **Full List of All 20 Page Links:** 👉 [WEBSITE_LINKS.md](file:///c:/Users/Varsha/OneDrive/Desktop/coffee%20estate/WEBSITE_LINKS.md)

---

## 🚀 Quick Start in Visual Studio Code

### 1. Open in VS Code
Open your terminal or command prompt in this directory and run:
```powershell
code .
```
Or open Visual Studio Code, click **File > Open Folder...**, and select this folder:
`c:\Users\Varsha\OneDrive\Desktop\coffee estate`

### 2. Run the Web Server in VS Code
You can run the web server in any of the following ways:
- **Press `F5`** (or click **Run > Start Debugging**) to run with the pre-configured VS Code debug profile: `"Python: Run Coffee Estate Web App"`.
- **Or via Integrated Terminal in VS Code:**
  ```powershell
  .\venv\Scripts\python.exe wsgi.py
  ```
- The application will immediately start on:
  👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🔑 Login Credentials

| Role | Username / Roll No | Password | Capabilities |
| :--- | :--- | :--- | :--- |
| **Estate Manager** *(Recommended)* | `manager` or `MGR001` | `Manager@123` | Full biometric face attendance, employee enrollment by Roll No, sprinkler irrigation runs, block management, and payroll approval |
| **System Administrator** | `admin` or `ADM001` | `Admin@123` | Full system administration, user management, audit logs, and security |
| **Field Worker** | `employee` or `EMP001` | `Worker@123` | Staff self-service portal (attendance administration restricted) |

---

## 📁 Project Architecture & Directory Layout

```
coffee estate/
├── wsgi.py                          # Flask application entry point
├── seed.py                          # Database seeder with sample data
├── pytest.ini                       # Test configuration
├── requirements.txt                 # Python dependencies
├── alembic.ini                      # Database migration settings
├── .vscode/                         # Visual Studio Code configurations
│   ├── launch.json                  # One-click F5 Run & Debug profiles
│   └── settings.json                # Python virtualenv & pytest bindings
├── app/
│   ├── __init__.py                  # Application factory & context processors
│   ├── config.py                    # Environment & database configurations
│   ├── database.py                  # SQLAlchemy database instance
│   ├── models/                      # SQLAlchemy ORM Models
│   │   ├── user.py                  # User authentication & RBAC roles
│   │   ├── employee.py              # Workforce directory & wage tracking
│   │   ├── attendance.py            # DailyAttendance, AttendanceEvent, FaceEnrollment
│   │   ├── farm.py                  # EstateBlock (Arabica, Robusta, Kaveri) & FieldActivity
│   │   ├── weather_sprinkler.py     # SprinklerLog (runtime in mins) & RainfallRecord
│   │   ├── harvest.py               # Harvest batches & yields
│   │   ├── task.py                  # Task dispatch & tracking
│   │   ├── inventory.py             # Stock in/out tracking
│   │   ├── pesticide.py             # Chemical spraying & Pre-Harvest Intervals
│   │   └── audit.py                 # Tamper-evident audit logging
│   ├── routes/                      # Flask Blueprints
│   │   ├── main.py                  # Splash & landing pages
│   │   ├── auth.py                  # Login, Logout, Face-login & User Registration
│   │   ├── dashboard.py             # Smart Dashboard & KPIs
│   │   ├── farm.py                  # Farm blocks, varieties, & interactive estate map
│   │   ├── weather.py               # All-India Weather Intelligence & Sprinkler logs
│   │   ├── harvest.py               # Cherry harvesting records
│   │   ├── employees.py             # Workforce administration
│   │   ├── attendance.py            # Biometric attendance & Roll No enrollment
│   │   ├── payroll.py               # Payroll calculation & printed salary slips
│   │   ├── inventory.py             # Inventory management
│   │   ├── tasks.py                 # Task dispatching
│   │   ├── pesticides.py            # Spray logs & chemical inventory
│   │   ├── reports.py               # Data exports & analytics
│   │   └── ai.py                    # Disease Detection, Ripeness AI, & Yield AI
│   ├── services/                    # Business Logic Layer
│   │   ├── auth_service.py          # RBAC decorators & password hashing
│   │   ├── geo_weather_service.py   # 36 Indian States/UTs, districts & agro-weather models
│   │   ├── attendance_service.py    # Biometric cosine similarity matching
│   │   ├── payroll_service.py       # Wage calculations & deduction rules
│   │   └── audit_service.py         # Security event recording
│   ├── static/                      # Static Assets
│   │   ├── css/theme.css            # Estate Green & Gold UI Theme
│   │   ├── js/attendance-offline.js # Offline-first IndexedDB attendance sync
│   │   └── images/
│   │       ├── coffee-plant-logo.jpg # Official original coffee plant logo emblem
│   │       ├── coffee-estate-bg.jpg  # Estate background banner
│   │       └── face-frame.svg        # Biometric camera guide frame
│   └── templates/                   # Jinja2 HTML Templates
│       ├── base.html                # Sidebar navigation & theme skeleton
│       ├── dashboard.html           # Operations dashboard
│       ├── login.html               # Frosted glassmorphism sign-in portal
│       ├── loading.html             # Splash loader with coffee plant logo
│       ├── farm.html                # Block diagram with Arabica, Robusta & Kaveri
│       ├── weather.html             # State & District selector with weather telemetry
│       ├── sprinkler.html           # Sprinkler irrigation minutes & runtime muster
│       ├── face_attendance.html     # Biometric face scanning & Green Coffee check-in
│       ├── face_register.html       # Worker face enrollment with Roll No
│       ├── attendance_manual.html   # Fallback muster roll
│       ├── salary_slip.html         # Printable worker salary slip
│       └── ...
└── tests/                           # Complete Pytest Regression Test Suite
    ├── conftest.py                  # Test fixtures & test clients
    ├── test_auth.py                 # Authentication & login tests
    ├── test_rbac.py                 # Role-based access control tests
    ├── test_attendance.py           # Biometric attendance & Roll No security
    ├── test_weather_sprinkler.py    # Weather state/district & sprinkler tests
    ├── test_payroll.py              # Wage & salary slip verification
    ├── test_core_records.py         # Farm blocks, harvest & inventory tests
    ├── test_pesticides.py           # Spray tracking & safety intervals
    └── test_reports.py              # Export & analytics tests
```

---

## 🧪 Running the Pytest Suite in VS Code

Run all **63 automated test cases**:
```powershell
.\venv\Scripts\pytest.exe -v
```
Or in VS Code, click the **Testing** beaker icon in the left activity bar to run tests with one click.

---

## 🌟 Highlight Features

1. **Biometric Face Attendance & Roll No:**
   - Restricted to Estate Manager and Admin only.
   - Enrolls worker faces linked to their official **Roll No** (e.g. `EMP001`, `EMP002`).
   - Facial scanning marks workers as **☕ Green Coffee (Present)**.
   - Regular employees receive `403 Forbidden` if attempting to take attendance.

2. **All-India Weather by State & District:**
   - Choose from all **36 Indian States and Union Territories** and their districts.
   - 1-click shortcuts for key coffee belts (*Chikmagalur, Kodagu, Hassan, Wayanad, Idukki, Nilgiris, Araku Valley, Koraput*).
   - Dynamic microclimate calculations (Temp, High/Low, Humidity, Wind, Rain Probability, Barometer, and Coffee Spray Advisories).

3. **Sprinkler Irrigation Runtime Muster:**
   - Dedicated page to track sprinkler operations: **When** (Date), **What Time** (Start & End), and **How Many Minutes** (with 1-click preset buttons for 60m, 180m, 300m, 360m).
   - Fuel consumed (Diesel Liters) and rain equivalent (mm).

4. **Estate Blocks with Coffee Varieties:**
   - Clear block division (Block A, B, C, D) featuring **Arabica**, **Robusta**, and **Kaveri** coffee varieties.
   - Interactive SVG estate map with elevation markers and soil health metrics.

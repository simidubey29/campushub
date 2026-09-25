# CampusHUB — Student Academic Portal

CampusHUB is a full-stack, role-based academic portal for **Students, Faculty and Administrators**.

## Feature set

- **A — Smart Dashboard:** live role-specific KPIs and academic overview.
- **B — Countdown:** live assignment deadline countdowns.
- **C — Late Detection:** server-side submission timestamp is compared with the deadline.
- **D — Notifications:** persistent in-app notifications for assignments, grades and notices.
- **E — Email:** optional SMTP email delivery for assignment and notice alerts.
- **F — Calendar:** assignments, projects and notices in a unified timeline.
- **G — Marks Analytics:** subject and exam-wise percentage analytics.
- **H — Performance Graph:** visual performance bars and progress cards.
- **I — Search & Filter:** assignment and notice search plus assignment status filtering.
- **J — Resubmission:** controlled resubmission attempts with a configurable limit.
- **K — Feedback:** faculty feedback is stored and shown to students.
- **L — Progress:** assignment, grading and attendance progress.
- **M — Notices:** faculty/admin campus announcements.
- **N — Dark Mode:** persistent light/dark interface preference.
- **O — Audit Trail:** admin-only record of important actions.

## Stack

**Frontend:** React + Vite + CSS + Lucide React  
**Backend:** FastAPI + SQLAlchemy + JWT + Passlib/Bcrypt  
**Database:** MySQL + PyMySQL

## Run locally

### Backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `backend/.env` using `.env.example` and add your real MySQL password and a private JWT secret.

```powershell
python run.py
```

Backend: `http://127.0.0.1:8000`  
Swagger: `http://127.0.0.1:8000/docs`

### Frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

## Database

Create the existing `student_academic_portal` MySQL database and its original tables. On startup, CampusHUB automatically creates the new notification/audit tables and adds the resubmission columns required by v2.

## Email

Email is optional. To enable real email delivery, configure the SMTP variables in `backend/.env`. If SMTP is not configured, the application still works normally and stores in-app notifications.

## Security

- Student public registration can only create student accounts.
- Faculty/admin APIs are protected by backend role checks.
- JWT secret is loaded from `.env`.
- MySQL credentials and `.env` are excluded from Git.
- Audit events record important account and academic actions.

## Project structure

```text
CampusHUB/
├── backend/
│   ├── app/
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── .env.example
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── index.html
│   └── package.json
├── .gitignore
└── README.md
```

## Author

Simi Dubey — B.Sc. Data Science

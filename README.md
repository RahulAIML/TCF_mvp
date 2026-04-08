# TCF Canada Preparation Platform

Full-stack platform for TCF Canada preparation. Includes reading, listening, writing, speaking, a passage analyzer, and a performance dashboard. Questions are generated dynamically to match CEFR progression.

## Features

### Reading
- 39 questions, 60-minute timer
- 4 parts with CEFR progression (A1-A2, A2-B1, B1-B2, B2-C2)
- Question navigator and auto-submit

### Listening
- 39 questions, 35-minute timer
- Progressive A1-C2 difficulty
- Audio plays once per question

### Writing
- Task 1: Short message (A1-A2)
- Task 2: Description (A2-B1)
- Task 3: Opinion + justification (B1-C1)
- Practice mode with step feedback and full exam mode

### Speaking
- Task 1: Basic interaction
- Task 2: Role-play
- Task 3: Opinion + argument
- 12-minute timer in exam mode

### Passage Analyzer
- Generate a passage with comprehension questions
- Select text to explain in context

### Dashboard
- Progress overview and recent performance

## Tech Stack

- Frontend: Next.js 14, React, TypeScript, TailwindCSS
- Backend: FastAPI (Python)
- Database: SQLite by default, Postgres supported

## Project Structure

```text
frontend/
  app/
    tcf/
  components/
  services/
  types/

backend/
  main.py
  tcf_ai_service.py
  auth.py
  database.py
  models.py
  schemas.py
  routers/
    auth_routes.py
    passage_routes.py
    performance_routes.py
    learn_routes.py
    dictionary.py
    tcf_exam_routes.py
    tcf_listening_routes.py
    tcf_writing_routes.py
    tcf_speaking_routes.py
```

## Environment Variables

### Backend (`backend/.env`)

```env
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-2.0-flash
FRONTEND_ORIGIN=http://localhost:3000
JWT_SECRET=change_me
DATABASE_URL=postgresql://postgres:password@localhost:5432/tcf
```

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## API Endpoints

### Reading (TCF)
- `POST /tcf/generate-question`
- `POST /tcf/submit-exam`

### Listening (TCF)
- `POST /tcf/generate-listening-question`
- `POST /tcf/generate-listening-audio`
- `POST /tcf/submit-listening-exam`

### Writing (TCF)
- `POST /tcf/generate-writing-tasks`
- `POST /tcf/evaluate-writing`
- `POST /tcf/evaluate-writing-step`
- `POST /tcf/writing/save-progress`
- `POST /tcf/writing/submit`

### Speaking (TCF)
- `POST /tcf/conversation`
- `POST /tcf/evaluate`

### Helpers
- `POST /generate-passage`
- `POST /generate-passage-quiz`
- `POST /explain-text`
- `POST /translate`
- `POST /word-meaning`
- `GET /dashboard/summary`

## Run Locally

### Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:
```
http://localhost:3000
```

## Notes

- Demo mode enabled (no login required).
- SQLite is the default database for quick local testing; Postgres can be enabled via `DATABASE_URL`.

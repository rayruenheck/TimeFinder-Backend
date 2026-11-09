# TimeFinder API

Flask backend for [TimeFinder](https://github.com/rayruenheck/TimeFinder-Frontend), an
app that schedules your to-do list into the open time on your Google Calendar. It
reads the user's calendar, finds free slots, and places tasks by priority, length, and
how much focus each one needs.

## How scheduling works

1. **Find free time.** Pull today's events from the user's primary Google Calendar
   (in their own time zone), take the 8 AM to 8 PM window, and cut out every event.
2. **Split it into slots.** Break the free time into 30-minute slots and mark which
   ones fall inside the user's chosen focus window (their best concentration hours).
3. **Place tasks by priority.** Tasks are sorted high to low priority, then:
   - high-concentration tasks go only into focus-window slots
   - low-concentration tasks go only outside the focus window
   - medium tasks try the focus window first, then anywhere still open
4. **Leave room between tasks.** A task needs enough back-to-back free slots to cover
   its length plus a 10-minute buffer, and placing it blocks those slots for the rest.

The scheduling logic lives in `app/scheduler.py`, separate from the routes, with
MongoDB access behind small repository classes (`app/repositories.py`) and Google
Calendar calls behind a client (`app/calendar_client.py`).

## Endpoints

| Method | Route | What it does |
| --- | --- | --- |
| POST | `/users` | Create or update a user after Google sign-in |
| POST | `/concentration_time` | Save the user's focus window |
| POST | `/tasks` | Save the user's task list |
| POST | `/add-task` | Add one task |
| GET | `/get-tasks?sub=...` | List a user's tasks |
| POST | `/update-completion` | Mark a task done or not done |
| POST | `/schedule_tasks` | Run the scheduler against today's calendar |
| POST | `/user_calendar_events` | Return the user's calendar events |
| POST | `/schedule_notifications` | Add weekday check-in reminders to the user's calendar for the next 30 days |
| GET | `/health` | Health check |

## Stack

Python, Flask, MongoDB (PyMongo), Google Calendar API, pytz, Gunicorn.

## Run locally

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Create a `.env` with:

```
MONGODB_URI=your MongoDB connection string
SECRET_KEY=any random string
FRONTEND_URL=http://localhost:3000
GOOGLE_CALENDAR_API_BASE_URL=https://www.googleapis.com/calendar/v3
```

The frontend handles Google sign-in and sends the user's OAuth access token to
`/users`; the backend stores it and uses it for Calendar calls. `Procfile` runs the app with Gunicorn for deployment.

## Limitations

- Schedules one day at a time (today), within a fixed 8 AM to 8 PM window.
- No automated tests yet. `test_mongo.py` only checks the database connection.

Started as a team project in 2024 and developed further since.

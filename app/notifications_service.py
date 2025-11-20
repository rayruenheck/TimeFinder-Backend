from datetime import datetime, timedelta
import pytz
from .deps import calendar_client  


def schedule_notification_reminders(access_token: str, user_timezone: str):
    
    tz = pytz.timezone(user_timezone)
    calendar_id = "primary"
    responses = []

    start_date = datetime.now(tz)
    end_date = start_date + timedelta(days=30)

    current_date = start_date
    while current_date <= end_date:
       
        if current_date.weekday() < 5:
            times = ["07:45", "20:15"]
            for time_str in times:
                event_time = tz.localize(
                    datetime.combine(
                        current_date.date(),
                        datetime.strptime(time_str, "%H:%M").time(),
                    )
                )
                event_end_time = event_time + timedelta(minutes=15)

                summary = (
                    "Confirm Scheduled Tasks 💙 TimeFinder"
                    if time_str == "07:45"
                    else "Check TimeFinder"
                )
                description_url = "http://localhost:3000/googleconnect"
                description = (
                    f"Click [here]({description_url}) to visit TimeFinder and manage your tasks!"
                )

                event_details = {
                    "summary": summary,
                    "description": description,
                    "start": {"dateTime": event_time.isoformat()},
                    "end": {"dateTime": event_end_time.isoformat()},
                    "reminders": {
                        "useDefault": False,
                        "overrides": [{"method": "popup", "minutes": 15}],
                    },
                }

                if not event_already_scheduled(
                    access_token, calendar_id, event_time, event_end_time
                ):
                    response = calendar_client.create_event(
                        access_token, calendar_id, event_details
                    )
                    responses.append(response)

        current_date += timedelta(days=1)

    return responses


def event_already_scheduled(access_token, calendar_id, start_time, end_time) -> bool:
    time_min = start_time.isoformat()
    time_max = end_time.isoformat()

    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": True,
    }

    try:
        events = calendar_client.list_events(access_token, calendar_id, params)
    except Exception:
        return False

    for event in events:
        if (
            event.get("start", {}).get("dateTime") == time_min
            and event.get("end", {}).get("dateTime") == time_max
        ):
            return True

    return False

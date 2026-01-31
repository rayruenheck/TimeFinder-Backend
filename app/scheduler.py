from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

import pytz

from .calendar_client import GoogleCalendarClient
from .repositories import UserRepository
from .models import Task

class Scheduler:
    def __init__(self, calendar_client: GoogleCalendarClient, user_repo: UserRepository, buffer_minutes: int = 10):
        self.calendar_client = calendar_client
        self.user_repo = user_repo
        self.buffer_minutes = buffer_minutes
    
    def sort_tasks(self, tasks: List[Task]) -> List[Task]:
        
        return sorted(tasks, key=lambda t: t.priority_value, reverse=True)
    
    def find_optimal_slots(self, access_token: str) -> List[Dict[str, Any]]:

        user_timezone = self.calendar_client.get_primary_timezone(access_token)
        local_timezone = pytz.timezone(user_timezone)
        today = datetime.now(tz=local_timezone).strftime("%Y-%m-%d")

        day_start = local_timezone.localize(
            datetime.strptime(f"{today} 08:00", "%Y-%m-%d %H:%M")
        )
        day_end = local_timezone.localize(
            datetime.strptime(f"{today} 20:00", "%Y-%m-%d %H:%M")
        )
        slots: List[Tuple[datetime, datetime]] = [(day_start, day_end)]

       
        params = {
            "timeMin": f"{today}T00:00:00Z",
            "timeMax": f"{today}T23:59:59Z",
            "singleEvents": True,
            "orderBy": "startTime",
        }

        events = self.calendar_client.list_events(access_token, "primary", params)
        buffer_duration = timedelta(minutes=self.buffer_minutes)

        for event in events:
            start_dt_str = event.get("start", {}).get("dateTime")
            end_dt_str = event.get("end", {}).get("dateTime")
           
            if not start_dt_str or not end_dt_str:
                continue

            event_start = datetime.fromisoformat(start_dt_str).astimezone(local_timezone)
            event_end = datetime.fromisoformat(end_dt_str).astimezone(local_timezone) + buffer_duration

            new_slots: List[Tuple[datetime, datetime]] = []
            for slot in slots:
                new_slots.extend(self._adjust_slot_for_event(slot, event_start, event_end))
            slots = new_slots

        return self._calculate_slot_status(slots, access_token, user_timezone)
    
    def schedule_tasks_in_slots(self, sorted_tasks: List[Task], available_slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
      
        scheduled_tasks: List[Dict[str, Any]] = []
        medium_concentration_tasks: List[Task] = []

        for task in sorted_tasks:
            conc = task.concentration
            if conc == "high":
                target_slots = [
                    s for s in available_slots if s["concentration_time"] and s["available"]
                ]
            elif conc == "low":
                target_slots = [
                    s for s in available_slots if not s["concentration_time"] and s["available"]
                ]
            else:
                medium_concentration_tasks.append(task)
                continue

            for slot in target_slots:
                if self._fits_time_slot(task, slot, available_slots):
                    self._schedule_task(task, slot, scheduled_tasks, available_slots)
                    break
        
        for task in medium_concentration_tasks:
            target_slots = [
                s for s in available_slots if s["concentration_time"] and s["available"]
            ]
            scheduled = False
            for slot in target_slots:
                if self._fits_time_slot(task, slot, available_slots):
                    self._schedule_task(task, slot, scheduled_tasks, available_slots)
                    scheduled = True
                    break

            if not scheduled:
                for slot in [s for s in available_slots if s["available"]]:
                    if self._fits_time_slot(task, slot, available_slots):
                        self._schedule_task(task, slot, scheduled_tasks, available_slots)
                        break

        return scheduled_tasks
    
    def _get_concentration_time(self, access_token: str):
        user = self.user_repo.find_by_access_token(access_token)
        if user and "concentration_time" in user:
            times = user["concentration_time"]
            return times.get("start"), times.get("end")
        return None
    
    def _calculate_slot_status(self, slots: List[Tuple[datetime, datetime]], access_token: str, timezone: str) -> List[Dict[str, Any]]:
    
        all_slots: List[Dict[str, Any]] = []
        user_concentration_times = self._get_concentration_time(access_token)
        tz = pytz.timezone(timezone)
        today_date = datetime.now(tz).date()

        for slot_start, slot_end in slots:
            current_time = slot_start
            while current_time < slot_end:
                slot_end_interval = min(current_time + timedelta(minutes=30), slot_end)
                is_concentration_time = False

                if user_concentration_times:
                    user_start_datetime = self._parse_time(user_concentration_times[0], today_date, tz)
                    user_end_datetime = self._parse_time(user_concentration_times[1], today_date, tz)
                    is_concentration_time = (
                        user_start_datetime <= current_time
                        and slot_end_interval <= user_end_datetime
                    )

                all_slots.append(
                    {
                        "start": current_time,
                        "end": slot_end_interval,
                        "available": True,
                        "concentration_time": is_concentration_time,
                    }
                )
                current_time += timedelta(minutes=30)

        return all_slots
    
    def _adjust_slot_for_event(self, slot: Tuple[datetime, datetime], event_start: datetime, event_end: datetime) -> List[Tuple[datetime, datetime]]:
        slot_start, slot_end = slot
        new_slots: List[Tuple[datetime, datetime]] = []

        if slot_start < event_start:
            new_slots.append((slot_start, min(slot_end, event_start)))
        if slot_end > event_end:
            new_slots.append((max(slot_start, event_end), slot_end))

        return new_slots if new_slots else [slot]
    
    def _fits_time_slot(self, task: Task, slot: Dict[str, Any], available_slots: List[Dict[str, Any]]) -> bool:
        buffer_duration = timedelta(minutes=self.buffer_minutes)
        task_duration = timedelta(minutes=task.time_minutes)
        required_duration = task_duration + buffer_duration

        start_index = available_slots.index(slot)
        accumulated_time = timedelta()

        for i in range(start_index, len(available_slots)):
            if not available_slots[i]["available"]:
                break
            current_slot_duration = available_slots[i]["end"] - available_slots[i]["start"]
            accumulated_time += current_slot_duration
            if accumulated_time >= required_duration:
                return True

        return False

    def _mark_slots_as_used(self, start_time: datetime, end_time: datetime, slots: List[Dict[str, Any]]):
        
        buffer_duration = timedelta(minutes=self.buffer_minutes)
        adjusted_start = start_time
        adjusted_end = end_time + buffer_duration

        for slot in slots:
            slot_start = slot["start"]
            slot_end = slot["end"]
            if slot_start < adjusted_end and slot_end > adjusted_start:
                slot["available"] = False

    def _schedule_task(self, task: Task, slot: Dict[str, Any], scheduled_tasks: List[Dict[str, Any]], available_slots: List[Dict[str, Any]]):
        
        start_time = slot["start"]
        end_time = start_time + timedelta(minutes=task.time_minutes)

        scheduled_tasks.append(
            {
                "task": task.name,
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "id": task.id,
                "isCompleted": task.is_completed,
                "isScheduled": task.is_scheduled,
            }
        )

        self._mark_slots_as_used(start_time, end_time, available_slots)

    @staticmethod
    def _parse_time(time_str: str, date, tz):
        
        try:
            t = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            t = datetime.strptime(time_str, "%H:%M:%S").time()
        return tz.localize(datetime.combine(date, t))
    

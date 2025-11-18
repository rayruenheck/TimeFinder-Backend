import requests

class GoogleCalendarClient:

    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def _headers(self, access_token: str) -> dict:
        return {
            "Authorization" : f"Bearer {access_token}",
            "Content-Type" : "application/json"
        }
    
    def get_primary_timezone(self, access_token: str) -> str:
        url = f"{self.base_url}/users/me/calendarList/primary"
        resp = requests.get(url, headers=self._headers(access_token))

        if resp.status_code == 200:
            return resp.json().get("timeZone", "UTC")
        return "UTC"
    
    def create_event(self, access_token: str, calendar_id: str, event_details: dict):
        url = f"{self.base_url}/calendars/{calendar_id}/events"
        resp = requests.post(url, headers=self._headers(access_token), json=event_details)
        resp.raise_for_status()
        return resp.json()

    def list_events(self, access_token: str, calendar_id: str, params: dict):
        url = f"{self.base_url}/calendars/{calendar_id}/events"
        resp = requests.post(url, headers=self._headers(access_token), params=params)
        resp.raise_for_status()
        return resp.json().get("items", [])
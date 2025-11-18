from typing import Optional, List, Any
from pymongo.collection import Collection

class UserRepository:
    
    def __init__(self, collection: Collection):

        self.collection = collection

    def upsert_user(self, user_data: dict):

        email = user_data.get("email")
        if not email:
            raise ValueError("User data must include 'email")
        
        return self.collection.update_one(
            {"email": email},
            {"$set": user_data},
            upsert=True
        )
    
    def find_by_sub(self, sub: str) -> Optional[dict]:
        return self.collection.find_one({"sub": sub})
    
    def find_by_access_token(self, access_token: str) -> Optional[dict]:

        return self.collection.find_one({"accessToken": access_token})
    
    def upsert_concentration_time(self, sub: str, start: str, end: str):
        return self.collection.update_one(
            {"sub": sub},
            {"$set": {"concentration_time": {"start": start, "end": end}}}
        )
    
    class TaskRepository:
        def __init__(self, collection: Collection):
            self.collection = collection
        
        def upsert_task_cluster(self, sub: str, tasks: List):
            return self.collection.update_one(
                {"sub": sub},
                {"$addToSet": {"tasks": {"$each" : tasks}}},
                upsert=True
            )
        
        def add_single_task(self, sub: str, tasks: dict):
            return self.collection.update_one(
                {"sub": sub},
                {"$addToSet": {"tasks": tasks}},
                upsert=True
            )
        
        def find_by_sub(self, sub: str) -> Optional[dict]:
            return self.collection.find_one({"sub": sub})
        
        def update_task_completion(self, task_id: any, is_completed: bool):
            return self.collection.update_one(
                {"tasks.id": task_id},
                {"$set": {"tasks.$.isCompleted": is_completed}}
            )
        
        def mark_task_scheduled(self, sub: str, task_id: Any, start_time, end_time):
            return self.collection.update_one(
            {"sub": sub, "tasks.id": task_id},
            {
                "$set": {
                    "tasks.$.isScheduled": True,
                    "tasks.$.start_time": start_time,
                    "tasks.$.end_time": end_time,
                }
            }
        )
import os
import motor.motor_asyncio
from bson import ObjectId
from datetime import datetime
from typing import List, Tuple, Dict, Optional, Union, Any

# --- Secure MongoDB URI ---
MONGODB_URL = os.environ.get(
    "MONGODB_URI",
    "mongodb+srv://guardian:guardian@cluster0.thn0z3g.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
db = client["guardianxbot"]

# --- Collections ---
users_col = db["users"]
approved_col = db["approved_users"]
violations_col = db["user_violations"]
groups_col = db["groups"]
alerts_col = db["alerts"]
memberships_col = db["group_memberships"]
start_events_col = db["bot_start_events"]
broadcasts_col = db["broadcast_messages"]
deliveries_col = db["broadcast_deliveries"]

# --- Broadcast Constants ---
BROADCAST_STATUS_PENDING = "pending"
BROADCAST_STATUS_PROCESSING = "processing"
BROADCAST_STATUS_COMPLETED = "completed"
BROADCAST_STATUS_FAILED = "failed"
BROADCAST_TARGET_ALL = "all"
BROADCAST_TARGET_APPROVED = "approved"
BROADCAST_TARGET_GROUP = "group"

# --- Index Creation ---
async def ensure_indexes():
    """Create indexes for collections (call once at startup)."""
    await users_col.create_index("user_id", unique=True)
    await approved_col.create_index("user_id", unique=True)
    await violations_col.create_index([("user_id", 1), ("category", 1)], unique=True)
    await groups_col.create_index("group_id", unique=True)
    await memberships_col.create_index([("user_id", 1), ("group_id", 1)], unique=True)
    await broadcasts_col.create_index("status")
    await alerts_col.create_index("timestamp")

# --- Client Closing (Call on shutdown) ---
def close_client():
    client.close()

# --- USER EXISTENCE/INSERTION HELPERS ---

async def user_exists(user_id: int) -> bool:
    """Return True if user exists in users_col, False otherwise."""
    return await users_col.find_one({"user_id": user_id}) is not None

async def add_user_if_new(user_id: int) -> None:
    """
    Ensure user exists in the users collection.
    No-op if already present.
    """
    await users_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id}},
        upsert=True
    )

# --- USERS ---

async def upsert_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
) -> None:
    """Insert or update user info."""
    doc = {
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "last_active": datetime.utcnow(),
    }
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": doc, "$setOnInsert": {"started_bot": False, "start_date": None, "violation_count": 0}},
        upsert=True
    )

async def get_user_info(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user info as dict, or None if user not found."""
    doc = await users_col.find_one({"user_id": user_id})
    if doc:
        return {
            "user_id": doc.get("user_id"),
            "username": doc.get("username"),
            "first_name": doc.get("first_name"),
            "last_name": doc.get("last_name"),
            "started_bot": doc.get("started_bot", False),
            "start_date": doc.get("start_date"),
            "last_active": doc.get("last_active"),
            "violation_count": doc.get("violation_count", 0),
        }
    return None

# --- APPROVED USERS ---

async def is_approved(user_id: int) -> bool:
    """Return True if user is approved."""
    return await approved_col.find_one({"user_id": user_id}) is not None

async def add_approved_user(user_id: int, added_by: Optional[int] = None) -> None:
    """Add a user to approved list."""
    await approved_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "added_by": added_by,
            "date_added": datetime.utcnow(),
        }},
        upsert=True
    )

async def remove_approved_user(user_id: int) -> None:
    """Remove a user from approved list."""
    await approved_col.delete_one({"user_id": user_id})

async def get_all_approved_users() -> List[Dict[str, Any]]:
    """List all approved users, newest first."""
    users = []
    async for doc in approved_col.find({}).sort("date_added", -1):
        users.append({
            "user_id": doc.get("user_id"),
            "date_added": doc.get("date_added"),
            "added_by": doc.get("added_by"),
        })
    return users

# --- Alias for compatibility (if handlers use get_all_users) ---
get_all_users = get_all_approved_users

# --- VIOLATIONS ---

async def update_violations(user_id: int, category: str) -> None:
    """Increment violation counters for a user and category."""
    now = datetime.utcnow()
    await users_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "violation_count": 0}},
        upsert=True
    )
    await violations_col.update_one(
        {"user_id": user_id, "category": category},
        {"$inc": {"count": 1}, "$set": {"last_updated": now}},
        upsert=True
    )
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"violation_count": 1}}
    )

async def get_user_violations(user_id: int) -> List[Dict[str, Any]]:
    """Return list of dicts for each violation category."""
    result = []
    async for doc in violations_col.find({"user_id": user_id}):
        result.append({
            "category": doc["category"],
            "count": doc["count"],
            "last_updated": doc.get("last_updated")
        })
    return result

# --- ALERTS ---

async def log_alert(user_id: int, category: str, message: str) -> None:
    """Log a user alert."""
    await alerts_col.insert_one({
        "user_id": user_id,
        "category": category,
        "message": message,
        "timestamp": datetime.utcnow()
    })

async def get_recent_alerts(limit: int = 10) -> List[Dict[str, Any]]:
    """Return recent alerts, joined with username if available."""
    cursor = alerts_col.aggregate([
        {"$sort": {"timestamp": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "user_id",
            "as": "user"
        }},
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}}
    ])
    results = []
    async for doc in cursor:
        results.append({
            "id": str(doc.get("_id")),
            "user_id": doc.get("user_id"),
            "username": doc.get("user", {}).get("username") if doc.get("user") else None,
            "category": doc.get("category"),
            "message": doc.get("message"),
            "timestamp": doc.get("timestamp"),
        })
    return results

# --- BOT START EVENTS ---

async def record_bot_start(user_id: int, referral_source: Optional[str] = None) -> None:
    """Log a user start event and mark user as started."""
    now = datetime.utcnow()
    await start_events_col.insert_one({
        "user_id": user_id,
        "start_date": now,
        "referral_source": referral_source
    })
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"started_bot": True, "start_date": now, "last_active": now}},
        upsert=True
    )

# --- GROUPS ---

async def record_group_join(user_id: int, group_id: int, group_title: str) -> None:
    """Log a user joining a group and update member count."""
    now = datetime.utcnow()
    await groups_col.update_one(
        {"group_id": group_id},
        {"$setOnInsert": {
            "group_id": group_id,
            "title": group_title,
            "created_date": now,
            "is_active": True,
            "member_count": 0
        },
         "$set": {"last_active": now}
        },
        upsert=True
    )
    await memberships_col.update_one(
        {"user_id": user_id, "group_id": group_id},
        {"$set": {"is_active": True, "last_active": now}, "$setOnInsert": {"join_date": now}},
        upsert=True
    )
    count = await memberships_col.count_documents({"group_id": group_id, "is_active": True})
    await groups_col.update_one(
        {"group_id": group_id},
        {"$set": {"member_count": count, "last_active": now}}
    )

async def record_group_leave(user_id: int, group_id: int) -> None:
    """Log a user leaving a group and update member count."""
    now = datetime.utcnow()
    await memberships_col.update_one(
        {"user_id": user_id, "group_id": group_id},
        {"$set": {"is_active": False, "last_active": now}}
    )
    count = await memberships_col.count_documents({"group_id": group_id, "is_active": True})
    await groups_col.update_one(
        {"group_id": group_id},
        {"$set": {"member_count": count}}
    )

async def get_user_groups(user_id: int) -> List[Dict[str, Any]]:
    """List all groups the user is a member of."""
    cursor = memberships_col.aggregate([
        {"$match": {"user_id": user_id, "is_active": True}},
        {"$lookup": {
            "from": "groups",
            "localField": "group_id",
            "foreignField": "group_id",
            "as": "group"
        }},
        {"$unwind": {"path": "$group"}}
    ])
    results = []
    async for doc in cursor:
        results.append({
            "group_id": doc["group_id"],
            "title": doc["group"]["title"],
            "join_date": doc.get("join_date"),
            "last_active": doc.get("last_active")
        })
    return results

async def get_group_members(group_id: int) -> List[Dict[str, Any]]:
    """List all active members of a group."""
    cursor = memberships_col.aggregate([
        {"$match": {"group_id": group_id, "is_active": True}},
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "user_id",
            "as": "user"
        }},
        {"$unwind": {"path": "$user"}}
    ])
    results = []
    async for doc in cursor:
        results.append({
            "user_id": doc["user_id"],
            "username": doc["user"].get("username"),
            "first_name": doc["user"].get("first_name"),
            "last_name": doc["user"].get("last_name"),
            "join_date": doc.get("join_date"),
            "last_active": doc.get("last_active")
        })
    return results

# --- USER ACTIVITY SUMMARY ---

async def get_user_activity(user_id: int) -> Dict[str, Any]:
    """Get full user activity summary."""
    user_info = await get_user_info(user_id)
    if not user_info:
        return {}
    start_events = []
    async for e in start_events_col.find({"user_id": user_id}):
        start_events.append({
            "start_date": e.get("start_date"),
            "referral_source": e.get("referral_source")
        })
    groups = await get_user_groups(user_id)
    violations = await get_user_violations(user_id)
    return {
        "user_info": user_info,
        "start_events": start_events,
        "groups": groups,
        "violations": violations
    }

# --- BROADCAST SYSTEM ---

async def add_broadcast_message(
    message: str,
    creator_id: int,
    target: str = BROADCAST_TARGET_ALL,
    group_id: Optional[int] = None
) -> Optional[str]:
    """Create a new broadcast message and return its ID as string."""
    doc = {
        "message": message,
        "creator_id": creator_id,
        "target": target,
        "group_id": group_id,
        "created_at": datetime.utcnow(),
        "status": BROADCAST_STATUS_PENDING,
        "sent_count": 0,
        "failed_count": 0,
        "completed_at": None
    }
    result = await broadcasts_col.insert_one(doc)
    return str(result.inserted_id)

async def get_pending_broadcasts(limit: int = 10) -> List[Dict[str, Any]]:
    """List pending broadcasts."""
    cursor = broadcasts_col.find({"status": BROADCAST_STATUS_PENDING}).sort("created_at", 1).limit(limit)
    results = []
    async for doc in cursor:
        results.append({
            "id": str(doc["_id"]),
            "message": doc["message"],
            "creator_id": doc["creator_id"],
            "target": doc["target"],
            "group_id": doc.get("group_id"),
            "created_at": doc["created_at"]
        })
    return results

async def update_broadcast_status(
    broadcast_id: Union[str, ObjectId],
    status: str,
    sent_count: int = 0,
    failed_count: int = 0
) -> None:
    """Update status (and optionally stats) for a broadcast."""
    if isinstance(broadcast_id, str):
        broadcast_id = ObjectId(broadcast_id)
    completed_at = datetime.utcnow() if status == BROADCAST_STATUS_COMPLETED else None
    await broadcasts_col.update_one(
        {"_id": broadcast_id},
        {"$set": {
            "status": status,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "completed_at": completed_at
        }}
    )

async def get_recipients_for_broadcast(target: str, group_id: Optional[int] = None) -> List[int]:
    """Get user_ids for a broadcast's target audience."""
    if target == BROADCAST_TARGET_ALL:
        cursor = users_col.find({"started_bot": True}, {"user_id": 1})
    elif target == BROADCAST_TARGET_APPROVED:
        cursor = approved_col.find({}, {"user_id": 1})
    elif target == BROADCAST_TARGET_GROUP and group_id:
        cursor = memberships_col.find({"group_id": group_id, "is_active": True}, {"user_id": 1})
    else:
        return []
    return [doc["user_id"] async for doc in cursor]

async def log_broadcast_delivery(
    broadcast_id: Union[str, ObjectId],
    user_id: int,
    status: str,
    error: Optional[str] = None
) -> None:
    """Log delivery status for a broadcast/user."""
    if isinstance(broadcast_id, str):
        broadcast_id = ObjectId(broadcast_id)
    await deliveries_col.insert_one({
        "broadcast_id": broadcast_id,
        "user_id": user_id,
        "status": status,
        "error": error,
        "delivered_at": datetime.utcnow()
    })

async def get_broadcast_stats(broadcast_id: Union[str, ObjectId]) -> Dict[str, Any]:
    """Get statistics for a broadcast."""
    if isinstance(broadcast_id, str):
        broadcast_id = ObjectId(broadcast_id)
    doc = await broadcasts_col.find_one({"_id": broadcast_id})
    if not doc:
        return {}
    deliveries = {}
    async for d in deliveries_col.aggregate([
        {"$match": {"broadcast_id": broadcast_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]):
        deliveries[d["_id"]] = d["count"]
    return {
        "status": doc.get("status"),
        "sent_count": doc.get("sent_count", 0),
        "failed_count": doc.get("failed_count", 0),
        "created_at": doc.get("created_at"),
        "completed_at": doc.get("completed_at"),
        "deliveries": deliveries
    }

async def get_all_group_ids() -> list[int]:
    cursor = groups_col.find({}, {"group_id": 1})
    return [doc["group_id"] async for doc in cursor]

# --- BACKUP ---
# Use mongodump/mongorestore for MongoDB backups.

__all__ = [
    "user_exists", "add_user_if_new",
    "upsert_user", "get_user_info",
    "is_approved", "add_approved_user", "remove_approved_user", "get_all_approved_users", "get_all_users",
    "update_violations", "get_user_violations",
    "log_alert", "get_recent_alerts",
    "record_bot_start",
    "record_group_join", "record_group_leave", "get_user_groups", "get_group_members",
    "get_user_activity",
    "add_broadcast_message", "get_pending_broadcasts", "update_broadcast_status",
    "get_recipients_for_broadcast", "log_broadcast_delivery", "get_broadcast_stats",
    "ensure_indexes", "close_client"
]

import sqlite3
import aiosqlite
from config import DB_PATH, ALERT_CHANNEL_ID
from typing import List, Tuple, Dict, Optional, Union, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Constants for broadcast statuses and targets
BROADCAST_STATUS_PENDING = "pending"
BROADCAST_STATUS_PROCESSING = "processing"
BROADCAST_STATUS_COMPLETED = "completed"
BROADCAST_STATUS_FAILED = "failed"
BROADCAST_TARGET_ALL = "all"
BROADCAST_TARGET_APPROVED = "approved"
BROADCAST_TARGET_GROUP = "group"

class Database:
    """Enhanced SQLite database handler with async support for NSFW bot"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
        self._init_sync_db()

    def _init_sync_db(self) -> None:
        """Initialize database tables (sync)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    started_bot BOOLEAN DEFAULT 0,
                    start_date TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    violation_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS approved_users (
                    user_id INTEGER PRIMARY KEY,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    added_by INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS user_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    UNIQUE(user_id, category)
                );
                CREATE TABLE IF NOT EXISTS groups (
                    group_id INTEGER PRIMARY KEY,
                    title TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    member_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    category TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS group_memberships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(group_id) REFERENCES groups(group_id) ON DELETE CASCADE,
                    UNIQUE(user_id, group_id)
                );
                CREATE TABLE IF NOT EXISTS bot_start_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    referral_source TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS broadcast_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    creator_id INTEGER NOT NULL,
                    target TEXT NOT NULL CHECK(target IN ('all', 'approved', 'group')),
                    group_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
                    sent_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    FOREIGN KEY(creator_id) REFERENCES users(user_id),
                    FOREIGN KEY(group_id) REFERENCES groups(group_id)
                );
                CREATE TABLE IF NOT EXISTS broadcast_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    broadcast_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('success', 'failed')),
                    error TEXT,
                    delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(broadcast_id) REFERENCES broadcast_messages(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_user_violations_user_id ON user_violations(user_id);
                CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
                CREATE INDEX IF NOT EXISTS idx_group_memberships_user ON group_memberships(user_id);
                CREATE INDEX IF NOT EXISTS idx_group_memberships_group ON group_memberships(group_id);
                CREATE INDEX IF NOT EXISTS idx_bot_start_events_user ON bot_start_events(user_id);
                CREATE INDEX IF NOT EXISTS idx_broadcast_status ON broadcast_messages(status);
                CREATE INDEX IF NOT EXISTS idx_broadcast_deliveries ON broadcast_deliveries(broadcast_id);
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    async def init_db(self) -> None:
        """Async database initialization (wrapper for sync version)"""
        if self.conn is not None:
            await self.conn.close()
        self._init_sync_db()
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.execute("PRAGMA defer_foreign_keys = ON")
        await self.conn.commit()

    async def close(self) -> None:
        """Close the async DB connection."""
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def _execute(self, query: str, params: tuple = (), commit: bool = False) -> Optional[List[Tuple[Any, ...]]]:
        """Generic async execute helper with enhanced foreign key handling."""
        if not self.conn:
            raise RuntimeError("Database not initialized. Call await init_db() first.")
        try:
            cursor = await self.conn.execute(query, params)
            result = await cursor.fetchall()
            if commit:
                await self.conn.commit()
            await cursor.close()
            return result
        except aiosqlite.Error as e:
            logger.error(f"Database error: {e}\nQuery: {query}\nParams: {params}")
            raise

    async def fetchone(self, query: str, params: tuple = ()) -> Optional[Tuple]:
        if not self.conn:
            raise RuntimeError("Database not initialized. Call await init_db() first.")
        async with self.conn.execute(query, params) as cursor:
            return await cursor.fetchone()

    # Core NSFW Functions (unchanged logic, improved error handling and type hints)
    async def is_approved(self, user_id: int) -> bool:
        result = await self._execute(
            "SELECT 1 FROM approved_users WHERE user_id = ? LIMIT 1",
            (user_id,)
        )
        return bool(result)

    async def update_violations(self, user_id: int, category: str) -> None:
        try:
            await self._execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                (user_id,), commit=True
            )
            await self._execute(
                "INSERT INTO user_violations (user_id, category) VALUES (?, ?)"
                " ON CONFLICT(user_id, category) DO UPDATE SET"
                " count = count + 1, last_updated = CURRENT_TIMESTAMP",
                (user_id, category), commit=True
            )
            await self._execute(
                "UPDATE users SET violation_count = violation_count + 1 WHERE user_id = ?",
                (user_id,), commit=True
            )
        except Exception as e:
            logger.error(f"Failed to update violations for user {user_id}: {e}")
            raise

    async def add_approved_user(self, user_id: int, added_by: Optional[int] = None) -> None:
        try:
            await self._execute(
                "INSERT OR IGNORE INTO approved_users (user_id, added_by) VALUES (?, ?)",
                (user_id, added_by), commit=True
            )
        except Exception as e:
            logger.error(f"Failed to add approved user {user_id}: {e}")
            raise

    async def remove_approved_user(self, user_id: int) -> None:
        try:
            await self._execute(
                "DELETE FROM approved_users WHERE user_id = ?",
                (user_id,), commit=True
            )
        except Exception as e:
            logger.error(f"Failed to remove approved user {user_id}: {e}")
            raise

    async def get_user_violations(self, user_id: int) -> List[Tuple[str, int, datetime]]:
        return await self._execute(
            "SELECT category, count, last_updated FROM user_violations WHERE user_id = ?",
            (user_id,)
        ) or []

    async def get_all_approved_users(self) -> List[Dict[str, Union[int, datetime, None]]]:
        results = await self._execute(
            "SELECT user_id, date_added, added_by FROM approved_users ORDER BY date_added DESC"
        ) or []
        return [{'user_id': r[0], 'date_added': r[1], 'added_by': r[2]} for r in results]

    async def upsert_user(
        self, user_id: int, username: Optional[str] = None,
        first_name: Optional[str] = None, last_name: Optional[str] = None
    ) -> None:
        await self._execute(
            "INSERT INTO users (user_id, username, first_name, last_name)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            " username = excluded.username,"
            " first_name = excluded.first_name,"
            " last_name = excluded.last_name,"
            " last_active = CURRENT_TIMESTAMP",
            (user_id, username, first_name, last_name), commit=True
        )

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Union[int, str, bool]]]:
        result = await self._execute(
            "SELECT user_id, username, first_name, last_name, started_bot, start_date, last_active, violation_count"
            " FROM users WHERE user_id = ? LIMIT 1",
            (user_id,)
        )
        if result:
            row = result[0]
            return {
                'user_id': row[0], 'username': row[1], 'first_name': row[2],
                'last_name': row[3], 'started_bot': bool(row[4]),
                'start_date': row[5], 'last_active': row[6], 'violation_count': row[7]
            }
        return None

    async def log_alert(self, user_id: int, category: str, message: str) -> None:
        await self._execute(
            "INSERT INTO alerts (user_id, category, message) VALUES (?, ?, ?)",
            (user_id, category, message), commit=True
        )

    async def get_recent_alerts(self, limit: int = 10) -> List[Dict[str, Union[int, str, datetime]]]:
        results = await self._execute(
            "SELECT a.id, a.user_id, u.username, a.category, a.message, a.timestamp"
            " FROM alerts a LEFT JOIN users u ON a.user_id = u.user_id"
            " ORDER BY a.timestamp DESC LIMIT ?",
            (limit,)
        ) or []
        return [{
            'id': r[0], 'user_id': r[1], 'username': r[2],
            'category': r[3], 'message': r[4], 'timestamp': r[5]
        } for r in results]

    async def record_bot_start(self, user_id: int, referral_source: Optional[str] = None) -> None:
        try:
            await self._execute(
                "INSERT INTO bot_start_events (user_id, referral_source) VALUES (?, ?)",
                (user_id, referral_source), commit=True
            )
            await self._execute(
                "UPDATE users SET started_bot = 1, start_date = CURRENT_TIMESTAMP,"
                " last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,), commit=True
            )
        except Exception as e:
            logger.error(f"Failed to record bot start for user {user_id}: {e}")
            raise

    async def record_group_join(self, user_id: int, group_id: int, group_title: str) -> None:
        try:
            await self._execute(
                "INSERT OR IGNORE INTO groups (group_id, title) VALUES (?, ?)",
                (group_id, group_title), commit=True
            )
            await self._execute(
                "INSERT INTO group_memberships (user_id, group_id) VALUES (?, ?)"
                " ON CONFLICT(user_id, group_id) DO UPDATE SET"
                " is_active = 1, last_active = CURRENT_TIMESTAMP",
                (user_id, group_id), commit=True
            )
            await self._execute(
                "UPDATE groups SET member_count = (SELECT COUNT(*) FROM group_memberships"
                " WHERE group_id = ? AND is_active = 1), last_active = CURRENT_TIMESTAMP"
                " WHERE group_id = ?",
                (group_id, group_id), commit=True
            )
        except Exception as e:
            logger.error(f"Failed to record group join for user {user_id}: {e}")
            raise

    async def record_group_leave(self, user_id: int, group_id: int) -> None:
        try:
            await self._execute(
                "UPDATE group_memberships SET is_active = 0, last_active = CURRENT_TIMESTAMP"
                " WHERE user_id = ? AND group_id = ?",
                (user_id, group_id), commit=True
            )
            await self._execute(
                "UPDATE groups SET member_count = (SELECT COUNT(*) FROM group_memberships"
                " WHERE group_id = ? AND is_active = 1) WHERE group_id = ?",
                (group_id, group_id), commit=True
            )
        except Exception as e:
            logger.error(f"Failed to record group leave for user {user_id}: {e}")
            raise

    async def get_user_groups(self, user_id: int) -> List[Dict[str, Union[int, str, datetime]]]:
        results = await self._execute(
            "SELECT g.group_id, g.title, gm.join_date, gm.last_active"
            " FROM group_memberships gm JOIN groups g ON gm.group_id = g.group_id"
            " WHERE gm.user_id = ? AND gm.is_active = 1 ORDER BY gm.last_active DESC",
            (user_id,)
        ) or []
        return [{
            'group_id': r[0], 'title': r[1], 'join_date': r[2], 'last_active': r[3]
        } for r in results]

    async def get_group_members(self, group_id: int) -> List[Dict[str, Union[int, str, datetime]]]:
        results = await self._execute(
            "SELECT u.user_id, u.username, u.first_name, u.last_name, gm.join_date, gm.last_active"
            " FROM group_memberships gm JOIN users u ON gm.user_id = u.user_id"
            " WHERE gm.group_id = ? AND gm.is_active = 1 ORDER BY gm.last_active DESC",
            (group_id,)
        ) or []
        return [{
            'user_id': r[0], 'username': r[1], 'first_name': r[2], 'last_name': r[3],
            'join_date': r[4], 'last_active': r[5]
        } for r in results]

    async def get_user_activity(self, user_id: int) -> Dict[str, Union[int, List[Dict]]]:
        user_info = await self.get_user_info(user_id)
        if not user_info:
            return {}
        start_events = await self._execute(
            "SELECT start_date, referral_source FROM bot_start_events WHERE user_id = ?",
            (user_id,)
        ) or []
        groups = await self.get_user_groups(user_id)
        violations = await self.get_user_violations(user_id)
        return {
            'user_info': user_info,
            'start_events': [{
                'start_date': e[0], 'referral_source': e[1]
            } for e in start_events],
            'groups': groups,
            'violations': [{
                'category': v[0], 'count': v[1], 'last_updated': v[2]
            } for v in violations]
        }

    async def backup_database(self, backup_path: str) -> bool:
        try:
            if not self.conn:
                raise RuntimeError("Database not initialized. Call await init_db() first.")
            async with aiosqlite.connect(backup_path) as target:
                await self.conn.backup(target)
            return True
        except aiosqlite.Error as e:
            logger.error(f"Backup failed: {e}")
            return False

    # Broadcast System Methods (unchanged logic, improved clarity)
    async def add_broadcast_message(
        self, message: str, creator_id: int,
        target: str = BROADCAST_TARGET_ALL, group_id: Optional[int] = None
    ) -> Optional[int]:
        result = await self._execute(
            "INSERT INTO broadcast_messages (message, creator_id, target, group_id, created_at, status)"
            " VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)"
            " RETURNING id",
            (message, creator_id, target, group_id, BROADCAST_STATUS_PENDING), commit=True
        )
        return result[0][0] if result else None

    async def get_pending_broadcasts(self, limit: int = 10) -> List[Dict]:
        results = await self._execute(
            "SELECT id, message, creator_id, target, group_id, created_at"
            " FROM broadcast_messages WHERE status = ?"
            " ORDER BY created_at ASC LIMIT ?",
            (BROADCAST_STATUS_PENDING, limit)
        ) or []
        return [{
            'id': r[0], 'message': r[1], 'creator_id': r[2],
            'target': r[3], 'group_id': r[4], 'created_at': r[5]
        } for r in results]

    async def update_broadcast_status(
        self, broadcast_id: int, status: str,
        sent_count: int = 0, failed_count: int = 0
    ) -> None:
        await self._execute(
            "UPDATE broadcast_messages SET status = ?, sent_count = ?, failed_count = ?,"
            " completed_at = CASE WHEN ? = ? THEN CURRENT_TIMESTAMP ELSE NULL END"
            " WHERE id = ?",
            (status, sent_count, failed_count, status, BROADCAST_STATUS_COMPLETED, broadcast_id),
            commit=True
        )

    async def get_recipients_for_broadcast(self, target: str, group_id: Optional[int] = None) -> List[int]:
        if target == BROADCAST_TARGET_ALL:
            results = await self._execute(
                "SELECT user_id FROM users WHERE started_bot = 1"
            )
        elif target == BROADCAST_TARGET_APPROVED:
            results = await self._execute(
                "SELECT user_id FROM approved_users"
            )
        elif target == BROADCAST_TARGET_GROUP and group_id:
            results = await self._execute(
                "SELECT user_id FROM group_memberships WHERE group_id = ? AND is_active = 1",
                (group_id,)
            )
        else:
            return []
        return [r[0] for r in results] if results else []

    async def log_broadcast_delivery(
        self, broadcast_id: int, user_id: int,
        status: str, error: Optional[str] = None
    ) -> None:
        await self._execute(
            "INSERT INTO broadcast_deliveries (broadcast_id, user_id, status, error, delivered_at)"
            " VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (broadcast_id, user_id, status, error), commit=True
        )

    async def get_broadcast_stats(self, broadcast_id: int) -> Dict:
        result = await self._execute(
            "SELECT status, sent_count, failed_count, created_at, completed_at"
            " FROM broadcast_messages WHERE id = ?",
            (broadcast_id,)
        )
        if not result:
            return {}
        deliveries = await self._execute(
            "SELECT status, COUNT(*) FROM broadcast_deliveries"
            " WHERE broadcast_id = ? GROUP BY status",
            (broadcast_id,)
        ) or []
        return {
            'status': result[0][0], 'sent_count': result[0][1],
            'failed_count': result[0][2], 'created_at': result[0][3],
            'completed_at': result[0][4],
            'deliveries': {d[0]: d[1] for d in deliveries}
        }

# Initialize database instance
db = Database()

__all__ = ['Database', 'db']

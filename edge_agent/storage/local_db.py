"""SQLite storage for Edge Agent local state, camera mappings, embeddings, and offline sighting queue."""
import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class SQLiteStore:
    """
    Thread-safe SQLite persistent store for Edge Agent.
    Manages synchronization state, camera mappings, cached face embeddings,
    and offline pending sighting queues.
    """

    def __init__(self, db_path: str = "local_data.db"):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True) if os.path.dirname(self.db_path) else None
        self._lock = threading.RLock()
        self._init_db()

    def close(self) -> None:
        """Idempotent store closer (connections are managed per operation via context manager)."""
        pass

    @contextmanager
    def _get_connection(self):
        """Context manager yielding a SQLite connection with WAL mode and row factory."""
        with self._lock:
            conn = sqlite3.connect(
                self.db_path,
                timeout=15.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_db(self) -> None:
        """Create tables and indexes idempotently with WAL mode enabled."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA busy_timeout = 5000;")
            cursor.execute("PRAGMA synchronous = NORMAL;")

            # 1. Sync state key-value table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )

            # 2. Camera mappings table (Local ID -> Backend UUID)
            # Fix #17: Local name to backend UUID mapping
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS camera_mappings (
                    local_camera_id TEXT PRIMARY KEY,
                    backend_uuid TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )

            # 3. Multi-photo cached embeddings table
            # Fix #13: id is PRIMARY KEY (UUID), index on person_id
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cached_embeddings (
                    id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    person_name TEXT,
                    embedding_data BLOB NOT NULL,
                    photo_url TEXT,
                    local_photo_path TEXT,
                    metadata_json TEXT,
                    synced_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cached_person
                ON cached_embeddings(person_id);
                """
            )

            # Ensure new columns exist if table was already created
            cursor.execute("PRAGMA table_info(cached_embeddings)")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            if "local_photo_path" not in existing_cols:
                cursor.execute("ALTER TABLE cached_embeddings ADD COLUMN local_photo_path TEXT;")
            if "metadata_json" not in existing_cols:
                cursor.execute("ALTER TABLE cached_embeddings ADD COLUMN metadata_json TEXT;")

            # 4. Durable offline pending sightings queue
            # Fix #18: Guarantee zero evidence loss during network interruptions
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_sightings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    confidence_level TEXT DEFAULT 'POSSIBLE',
                    num_frames_matched INTEGER DEFAULT 1,
                    camera_location TEXT,
                    latitude REAL,
                    longitude REAL,
                    face_crop_path TEXT NOT NULL,
                    full_frame_path TEXT NOT NULL,
                    video_clip_path TEXT,
                    detected_at TEXT NOT NULL,
                    uploaded INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    last_attempt_at TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pending_uploaded
                ON pending_sightings(uploaded, retry_count);
                """
            )

            # 5. Optional track audit log
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS track_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_id INTEGER NOT NULL,
                    camera_id TEXT NOT NULL,
                    person_id TEXT,
                    similarity_score REAL,
                    frame_number INTEGER,
                    timestamp TEXT DEFAULT (datetime('now'))
                );
                """
            )

    # ═════════════════════════════════════════════════════════════════════════
    # Sync State Operations
    # ═════════════════════════════════════════════════════════════════════════

    def get_sync_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a synchronization state value by key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sync_state WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_sync_state(self, key: str, value: str) -> None:
        """Upsert a synchronization state key-value pair."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sync_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
                """,
                (key, str(value), now_str),
            )

    def get_all_sync_state(self) -> Dict[str, str]:
        """Retrieve all sync state key-value pairs as a dictionary."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM sync_state")
            rows = cursor.fetchall()
            return {row["key"]: row["value"] for row in rows}

    # ═════════════════════════════════════════════════════════════════════════
    # Camera Mapping Operations (Fix #17)
    # ═════════════════════════════════════════════════════════════════════════

    def save_camera_mapping(self, local_camera_id: str, backend_uuid: str) -> None:
        """Save or update a local camera name to backend UUID mapping."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO camera_mappings (local_camera_id, backend_uuid, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(local_camera_id) DO UPDATE SET
                    backend_uuid = excluded.backend_uuid,
                    updated_at = excluded.updated_at;
                """,
                (local_camera_id, backend_uuid, now_str),
            )

    def save_camera_mappings(self, mappings: Dict[str, str]) -> None:
        """Batch save or update camera mappings."""
        now_str = datetime.now(timezone.utc).isoformat()
        data = [(local_id, uuid, now_str) for local_id, uuid in mappings.items()]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO camera_mappings (local_camera_id, backend_uuid, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(local_camera_id) DO UPDATE SET
                    backend_uuid = excluded.backend_uuid,
                    updated_at = excluded.updated_at;
                """,
                data,
            )

    def get_camera_uuid(self, local_camera_id: str) -> Optional[str]:
        """Get backend UUID for a local camera identifier."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT backend_uuid FROM camera_mappings WHERE local_camera_id = ?",
                (local_camera_id,),
            )
            row = cursor.fetchone()
            return row["backend_uuid"] if row else None

    def get_local_camera_id(self, backend_uuid: str) -> Optional[str]:
        """Get local camera identifier from a backend UUID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT local_camera_id FROM camera_mappings WHERE backend_uuid = ?",
                (backend_uuid,),
            )
            row = cursor.fetchone()
            return row["local_camera_id"] if row else None

    def get_all_camera_mappings(self) -> Dict[str, str]:
        """Get all local camera ID to backend UUID mappings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT local_camera_id, backend_uuid FROM camera_mappings")
            rows = cursor.fetchall()
            return {row["local_camera_id"]: row["backend_uuid"] for row in rows}

    def delete_camera_mapping(self, local_camera_id: str) -> bool:
        """Delete camera mapping for a local camera."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM camera_mappings WHERE local_camera_id = ?",
                (local_camera_id,),
            )
            return cursor.rowcount > 0

    # ═════════════════════════════════════════════════════════════════════════
    # Cached Embeddings Operations (Fix #13 & Fix #15)
    # ═════════════════════════════════════════════════════════════════════════

    def save_embedding(
        self,
        id: str,
        person_id: str,
        person_name: Optional[str],
        embedding_data: bytes,
        photo_url: Optional[str] = None,
        local_photo_path: Optional[str] = None,
        metadata_json: Optional[str] = None,
    ) -> None:
        """
        Store a face embedding. Multi-photo support: PRIMARY KEY is id (embedding UUID).
        """
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO cached_embeddings (id, person_id, person_name, embedding_data, photo_url, local_photo_path, metadata_json, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    person_id = excluded.person_id,
                    person_name = excluded.person_name,
                    embedding_data = excluded.embedding_data,
                    photo_url = excluded.photo_url,
                    local_photo_path = COALESCE(excluded.local_photo_path, cached_embeddings.local_photo_path),
                    metadata_json = COALESCE(excluded.metadata_json, cached_embeddings.metadata_json),
                    synced_at = excluded.synced_at;
                """,
                (id, person_id, person_name, sqlite3.Binary(embedding_data), photo_url, local_photo_path, metadata_json, now_str),
            )

    def save_embeddings_batch(self, items: List[Dict[str, Any]]) -> int:
        """Batch upsert embeddings."""
        if not items:
            return 0
        now_str = datetime.now(timezone.utc).isoformat()
        params = []
        for item in items:
            raw_meta = item.get("metadata_json")
            if not raw_meta and item.get("metadata"):
                try:
                    raw_meta = json.dumps(item["metadata"])
                except Exception:
                    raw_meta = None
            params.append(
                (
                    item["id"],
                    item["person_id"],
                    item.get("person_name"),
                    sqlite3.Binary(item["embedding_data"]),
                    item.get("photo_url"),
                    item.get("local_photo_path"),
                    raw_meta,
                    now_str,
                )
            )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO cached_embeddings (id, person_id, person_name, embedding_data, photo_url, local_photo_path, metadata_json, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    person_id = excluded.person_id,
                    person_name = excluded.person_name,
                    embedding_data = excluded.embedding_data,
                    photo_url = excluded.photo_url,
                    local_photo_path = COALESCE(excluded.local_photo_path, cached_embeddings.local_photo_path),
                    metadata_json = COALESCE(excluded.metadata_json, cached_embeddings.metadata_json),
                    synced_at = excluded.synced_at;
                """,
                params,
            )
            return len(params)

    def get_all_embeddings(self) -> List[Dict[str, Any]]:
        """Retrieve all cached embeddings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, person_id, person_name, embedding_data, photo_url, local_photo_path, metadata_json, synced_at FROM cached_embeddings"
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "person_id": row["person_id"],
                    "person_name": row["person_name"],
                    "embedding_data": bytes(row["embedding_data"]),
                    "photo_url": row["photo_url"],
                    "local_photo_path": row["local_photo_path"],
                    "metadata_json": row["metadata_json"],
                    "synced_at": row["synced_at"],
                }
                for row in rows
            ]

    def get_embeddings_for_person(self, person_id: str) -> List[Dict[str, Any]]:
        """Retrieve all cached embeddings for a specific person."""
        clean_id = (person_id or "").strip()
        variations = [clean_id]
        if "-" in clean_id:
            variations.append(clean_id.replace("-", ""))
        elif len(clean_id) == 32:
            variations.append(f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in variations)
            cursor.execute(
                f"SELECT id, person_id, person_name, embedding_data, photo_url, local_photo_path, metadata_json, synced_at FROM cached_embeddings WHERE person_id IN ({placeholders})",
                variations,
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "person_id": row["person_id"],
                    "person_name": row["person_name"],
                    "embedding_data": bytes(row["embedding_data"]),
                    "photo_url": row["photo_url"],
                    "local_photo_path": row["local_photo_path"],
                    "metadata_json": row["metadata_json"],
                    "synced_at": row["synced_at"],
                }
                for row in rows
            ]

    def get_person_details(self, person_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached metadata and reference photo path for a person.
        Supports both hyphenated and non-hyphenated UUID formats.
        """
        if not person_id:
            return None
        clean_id = str(person_id).strip()
        variations = [clean_id]
        if "-" in clean_id:
            variations.append(clean_id.replace("-", ""))
        elif len(clean_id) == 32:
            variations.append(f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in variations)
            cursor.execute(
                f"""
                SELECT id, person_id, person_name, photo_url, local_photo_path, metadata_json, synced_at
                FROM cached_embeddings
                WHERE person_id IN ({placeholders})
                ORDER BY CASE WHEN local_photo_path IS NOT NULL AND local_photo_path != '' THEN 0 ELSE 1 END,
                         synced_at DESC
                LIMIT 1
                """,
                variations,
            )
            row = cursor.fetchone()
            if not row:
                return None

            meta: Dict[str, Any] = {}
            if row["metadata_json"]:
                try:
                    meta = json.loads(row["metadata_json"])
                except Exception:
                    meta = {}

            return {
                "id": row["id"],
                "person_id": row["person_id"],
                "person_name": row["person_name"],
                "photo_url": row["photo_url"],
                "local_photo_path": row["local_photo_path"],
                "metadata": meta,
                "synced_at": row["synced_at"],
            }

    def remove_embeddings_for_persons(self, person_ids: List[str]) -> int:
        """
        Prune embeddings for removed/closed/found missing persons (Fix #15).
        """
        if not person_ids:
            return 0
        placeholders = ",".join("?" for _ in person_ids)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM cached_embeddings WHERE person_id IN ({placeholders})",
                person_ids,
            )
            return cursor.rowcount

    def remove_embedding_by_id(self, embedding_id: str) -> bool:
        """Remove a single embedding by its UUID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM cached_embeddings WHERE id = ?",
                (embedding_id,),
            )
            return cursor.rowcount > 0

    def count_embeddings(self) -> int:
        """Count total cached face embeddings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS cnt FROM cached_embeddings")
            row = cursor.fetchone()
            return row["cnt"] if row else 0

    def count_persons(self) -> int:
        """Count unique persons in cached embeddings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(DISTINCT person_id) AS cnt FROM cached_embeddings")
            row = cursor.fetchone()
            return row["cnt"] if row else 0

    def clear_embeddings(self) -> None:
        """Clear all cached embeddings (e.g. before full sync)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cached_embeddings")

    # ═════════════════════════════════════════════════════════════════════════
    # Pending Sightings Operations (Fix #18 - Durable Offline Queue)
    # ═════════════════════════════════════════════════════════════════════════

    def enqueue_sighting(
        self,
        person_id: str,
        camera_id: str,
        similarity_score: float,
        detected_at: str,
        face_crop_path: str,
        full_frame_path: str,
        video_clip_path: Optional[str] = None,
        confidence_level: str = "POSSIBLE",
        num_frames_matched: Optional[int] = 1,
        camera_location: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> int:
        """
        Durable offline queue enqueue: saves pending sighting to SQLite.
        Returns the inserted sighting ID.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO pending_sightings (
                    person_id, camera_id, similarity_score, confidence_level,
                    num_frames_matched, camera_location, latitude, longitude,
                    face_crop_path, full_frame_path, video_clip_path,
                    detected_at, uploaded, retry_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
                """,
                (
                    person_id,
                    camera_id,
                    float(similarity_score),
                    confidence_level,
                    num_frames_matched or 1,
                    camera_location,
                    latitude,
                    longitude,
                    face_crop_path,
                    full_frame_path,
                    video_clip_path,
                    detected_at,
                    now_str,
                ),
            )
            return cursor.lastrowid

    def get_pending_sightings(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve un-uploaded sightings ordered by creation time."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, person_id, camera_id, similarity_score, confidence_level,
                       num_frames_matched, camera_location, latitude, longitude,
                       face_crop_path, full_frame_path, video_clip_path,
                       detected_at, uploaded, retry_count, last_attempt_at, created_at
                FROM pending_sightings
                WHERE uploaded = 0
                ORDER BY retry_count ASC, id ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def mark_sighting_uploaded(self, sighting_id: int) -> None:
        """Mark a pending sighting as uploaded."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pending_sightings SET uploaded = 1 WHERE id = ?",
                (sighting_id,),
            )

    def delete_pending_sighting(self, sighting_id: int) -> bool:
        """Delete a pending sighting from SQLite queue after successful upload."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pending_sightings WHERE id = ?",
                (sighting_id,),
            )
            return cursor.rowcount > 0

    def increment_retry_count(
        self, sighting_id: int, last_attempt_at: Optional[str] = None
    ) -> int:
        """Increment retry count and record attempt timestamp on upload failure."""
        attempt_str = last_attempt_at or datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE pending_sightings
                SET retry_count = retry_count + 1,
                    last_attempt_at = ?
                WHERE id = ?
                """,
                (attempt_str, sighting_id),
            )
            cursor.execute(
                "SELECT retry_count FROM pending_sightings WHERE id = ?",
                (sighting_id,),
            )
            row = cursor.fetchone()
            return row["retry_count"] if row else 0

    def count_pending_sightings(self) -> int:
        """Count un-uploaded sightings currently queued in SQLite."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM pending_sightings WHERE uploaded = 0"
            )
            row = cursor.fetchone()
            return row["cnt"] if row else 0

    def clear_pending_sightings(self) -> None:
        """Clear all pending sightings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_sightings")

    # ═════════════════════════════════════════════════════════════════════════
    # Track Log Operations
    # ═════════════════════════════════════════════════════════════════════════

    def log_track_event(
        self,
        track_id: int,
        camera_id: str,
        person_id: Optional[str] = None,
        similarity_score: Optional[float] = None,
        frame_number: Optional[int] = None,
    ) -> None:
        """Log a tracked detection event for debug / audit."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO track_log (track_id, camera_id, person_id, similarity_score, frame_number)
                VALUES (?, ?, ?, ?, ?)
                """,
                (track_id, camera_id, person_id, similarity_score, frame_number),
            )

"""Embedding synchronization worker for Edge Agent."""
import base64
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from edge_agent.network.api_client import ApiClient, ApiClientError
from edge_agent.storage.faiss_store import FAISSStore
from edge_agent.storage.local_db import SQLiteStore

logger = logging.getLogger(__name__)


class EmbeddingSyncer:
    """
    Synchronizes missing person face embeddings from backend to Edge Agent.
    Handles incremental sync with tombstone pruning (Fix #15) and
    updates local SQLite cache + FAISS vector search index with double-buffering.
    """

    def __init__(
        self,
        api_client: ApiClient,
        local_db: SQLiteStore,
        faiss_store: Optional[FAISSStore] = None,
        sync_interval_seconds: int = 60,
        on_sync_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.api_client = api_client
        self.local_db = local_db
        self.faiss_store = faiss_store
        self.sync_interval_seconds = sync_interval_seconds
        self.on_sync_complete = on_sync_complete
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def sync_now(self, force_full: bool = False) -> Dict[str, Any]:
        """
        Execute an immediate synchronization cycle.
        Returns a summary of the sync operation.
        """
        last_synced_at = None if force_full else self.local_db.get_sync_state("last_synced_at")
        logger.info(f"Starting embeddings sync (since={last_synced_at})")

        try:
            resp = self.api_client.get_embeddings_sync(since=last_synced_at)
        except ApiClientError as e:
            logger.error(f"Failed to fetch embeddings from backend: {e}")
            raise

        full_sync = resp.get("full_sync", False) or force_full
        persons_data = resp.get("persons", [])
        removed_ids = resp.get("removed_ids", [])
        sync_timestamp = resp.get("sync_timestamp")

        if full_sync:
            logger.info("Full sync flag received — resetting local embedding cache")
            self.local_db.clear_embeddings()

        # 1. Decode and store new/modified embeddings with photos and metadata
        stored_items = []
        for p in persons_data:
            b64_data = p.get("embedding_bytes", "")
            try:
                raw_bytes = base64.b64decode(b64_data)
            except Exception as e:
                logger.warning(f"Failed to decode base64 embedding for item {p.get('embedding_id')}: {e}")
                continue

            person_id = str(p["person_id"])
            photo_url = p.get("photo_url")
            local_photo_path = None

            # Resolve reference photo locally
            if photo_url:
                clean_rel = photo_url.lstrip("/\\")
                candidate_paths = [
                    os.path.abspath(clean_rel),
                    os.path.abspath(os.path.join(os.getcwd(), clean_rel)),
                    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", clean_rel)),
                ]
                for cp in candidate_paths:
                    if os.path.isfile(cp):
                        local_photo_path = cp
                        break

                # Download and cache from backend if not local
                if not local_photo_path:
                    try:
                        ref_dir = os.path.abspath("evidence/reference_photos")
                        os.makedirs(ref_dir, exist_ok=True)
                        ext = os.path.splitext(clean_rel)[1] or ".jpg"
                        target_file = os.path.join(ref_dir, f"{person_id}{ext}")
                        req_path = photo_url if photo_url.startswith("/") else f"/{clean_rel}"
                        resp_img = self.api_client._client.get(req_path)
                        if resp_img.status_code == 200 and resp_img.content:
                            with open(target_file, "wb") as pf:
                                pf.write(resp_img.content)
                            local_photo_path = target_file
                    except Exception as err:
                        logger.debug(f"Could not cache reference photo for {person_id}: {err}")

            meta = {
                "age": p.get("age"),
                "gender": p.get("gender"),
                "height_cm": p.get("height_cm"),
                "description": p.get("description"),
                "last_seen_location": p.get("last_seen_location"),
                "last_seen_time": p.get("last_seen_time"),
                "contact_info": p.get("contact_info"),
                "reporter_name": p.get("reporter_name"),
                "reporter_email": p.get("reporter_email"),
                "reporter_phone": p.get("reporter_phone"),
                "created_at": p.get("created_at"),
            }

            stored_items.append(
                {
                    "id": str(p["embedding_id"]),
                    "person_id": person_id,
                    "person_name": p.get("person_name"),
                    "embedding_data": raw_bytes,
                    "photo_url": photo_url,
                    "local_photo_path": local_photo_path,
                    "metadata": meta,
                }
            )

        if stored_items:
            self.local_db.save_embeddings_batch(stored_items)

        # 2. Fix #15: Prune removed/resolved person IDs from SQLite
        removed_count = 0
        if removed_ids:
            removed_count = self.local_db.remove_embeddings_for_persons(removed_ids)
            logger.info(f"Pruned {removed_count} embeddings for {len(removed_ids)} removed persons")

        # 3. Update last sync timestamp in SQLite
        if sync_timestamp:
            self.local_db.set_sync_state("last_synced_at", sync_timestamp)

        # 4. Rebuild FAISS index from local SQLite store (Double-Buffering Rule 7)
        total_embeddings = 0
        if self.faiss_store is not None:
            all_cached = self.local_db.get_all_embeddings()
            total_embeddings = self.faiss_store.rebuild(all_cached)
        else:
            total_embeddings = self.local_db.count_embeddings()

        summary = {
            "status": "success",
            "full_sync": full_sync,
            "added_count": len(stored_items),
            "removed_count": removed_count,
            "total_cached": total_embeddings,
            "sync_timestamp": sync_timestamp,
        }
        logger.info(f"Embeddings sync completed: {summary}")

        if self.on_sync_complete:
            try:
                self.on_sync_complete(summary)
            except Exception as e:
                logger.warning(f"Error in on_sync_complete callback: {e}")

        return summary

    def _run_worker(self) -> None:
        """Background thread loop performing periodic sync."""
        logger.info("EmbeddingSyncer background thread started")
        while not self._stop_event.is_set():
            try:
                self.sync_now()
            except Exception as e:
                logger.warning(f"Background embedding sync encountered error: {e}")

            # Sleep in small increments for responsive cooperative shutdown
            for _ in range(self.sync_interval_seconds):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

        logger.info("EmbeddingSyncer background thread stopped")

    def start(self) -> None:
        """Start periodic synchronization in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("EmbeddingSyncer worker is already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_worker, daemon=True, name="EmbeddingSyncerThread")
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Cooperative thread shutdown signal."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            self._thread = None

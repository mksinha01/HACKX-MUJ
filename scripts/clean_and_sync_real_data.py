"""Clean fake data and synchronize real user missing person reports and photos."""
import os
import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from edge_agent.config import EdgeSettings
from edge_agent.network.api_client import ApiClient
from edge_agent.network.embedding_syncer import EmbeddingSyncer
from edge_agent.storage.faiss_store import FAISSStore
from edge_agent.storage.local_db import SQLiteStore


def clean_backend_db(backend_db_path: str = "backend_local.db") -> None:
    """Purge fake/test reports and retain real user reports."""
    print(f"[CLEAN] Inspecting and purging fake records in {backend_db_path}...")
    conn = sqlite3.connect(backend_db_path)
    c = conn.cursor()

    # Find real user ID (Mk Sinha)
    c.execute("SELECT id, name, email FROM users WHERE email = 'mksinha77756@gmail.com'")
    real_user = c.fetchone()
    if not real_user:
        print("[WARN] User Mk Sinha (mksinha77756@gmail.com) not found, finding any non-test users...")
        c.execute("SELECT id, name, email FROM users WHERE email NOT LIKE '%test%' AND email NOT LIKE '%mock%'")
        real_user = c.fetchone()

    if real_user:
        real_user_id = real_user[0]
        print(f"[CLEAN] Preserving reports for real user: {real_user[1]} ({real_user[2]}), ID: {real_user_id}")
    else:
        real_user_id = None
        print("[WARN] No real user found; keeping all active non-test subjects.")

    # Identify fake missing persons
    c.execute(
        """
        SELECT id, full_name, user_id FROM missing_persons
        WHERE full_name LIKE '%Test%'
           OR full_name LIKE '%Mock%'
           OR full_name LIKE '%Aarav%'
           OR full_name LIKE '%Priya%'
           OR full_name LIKE '%Rohan%'
           OR full_name = 'Reported Missing Person'
           OR full_name = 'Enrolled Person 1'
        """
    )
    fake_persons = c.fetchall()
    fake_ids = [r[0] for r in fake_persons]
    print(f"[CLEAN] Found {len(fake_ids)} fake/mock missing person records to delete: {[r[1] for r in fake_persons]}")

    if fake_ids:
        placeholders = ",".join("?" for _ in fake_ids)
        # Delete embeddings
        c.execute(f"DELETE FROM face_embeddings WHERE person_id IN ({placeholders})", fake_ids)
        # Delete photos
        c.execute(f"DELETE FROM photos WHERE person_id IN ({placeholders})", fake_ids)
        # Delete sightings
        c.execute(f"DELETE FROM sightings WHERE person_id IN ({placeholders})", fake_ids)
        # Delete missing persons
        c.execute(f"DELETE FROM missing_persons WHERE id IN ({placeholders})", fake_ids)
        print(f"[CLEAN] Purged fake missing persons and associated records.")

    # Remove mock/test users
    c.execute(
        """
        DELETE FROM users
        WHERE email LIKE '%test%'
           OR email LIKE '%mock%'
           OR email LIKE '%@dev.local'
        """
    )
    print(f"[CLEAN] Purged test/mock users. Retained: {c.execute('SELECT email, name FROM users').fetchall()}")

    # Remaining real missing persons
    remaining = c.execute("SELECT id, full_name, age, gender, last_seen_location FROM missing_persons").fetchall()
    print(f"[CLEAN] Remaining real missing persons ({len(remaining)}):")
    for row in remaining:
        print(f"  • {row[1]} (ID: {row[0]}, Age: {row[2]}, Gender: {row[3]}, Location: {row[4]})")

    conn.commit()
    conn.close()


def clean_edge_db(local_db_path: str = "local_data.db") -> None:
    """Purge fake/test records from Edge Agent SQLite database."""
    print(f"\n[CLEAN] Purging fake cached embeddings and pending sightings in {local_db_path}...")
    conn = sqlite3.connect(local_db_path)
    c = conn.cursor()

    # Clear old fake cached embeddings
    c.execute(
        """
        DELETE FROM cached_embeddings
        WHERE person_name LIKE '%Test%'
           OR person_name LIKE '%Aarav%'
           OR person_name LIKE '%Priya%'
           OR person_name LIKE '%Rohan%'
           OR person_name = 'Reported Missing Person'
           OR person_name = 'Enrolled Person 1'
        """
    )
    print(f"[CLEAN] Deleted fake cached embeddings.")

    # Clear pending sightings (all old ones were for fake persons)
    c.execute("DELETE FROM pending_sightings;")
    print(f"[CLEAN] Cleared stale pending sightings queue.")

    # Setup camera mappings: CAM-01 and CAM-02 -> backend UUIDs
    # Retrieve backend UUIDs from backend_local.db if possible
    backend_db = "backend_local.db"
    cam_mappings = {
        "CAM-01": "f6d8aceb-5bfa-4b6e-aeb1-69cf863e9ec1",
        "CAM-02": "0308eb7b-0c3e-46e7-a8b0-340cc881fb37",
    }
    if os.path.isfile(backend_db):
        try:
            bconn = sqlite3.connect(backend_db)
            bc = bconn.cursor()
            for row in bc.execute("SELECT local_camera_id, id FROM cameras").fetchall():
                raw_id = str(row[1])
                # Ensure hyphenated UUID format
                if len(raw_id) == 32 and "-" not in raw_id:
                    uuid_str = f"{raw_id[:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"
                else:
                    uuid_str = raw_id
                cam_mappings[row[0]] = uuid_str
            bconn.close()
        except Exception as e:
            print(f"[WARN] Could not read camera UUIDs from backend: {e}")

    for l_id, b_uuid in cam_mappings.items():
        c.execute(
            """
            INSERT INTO camera_mappings (local_camera_id, backend_uuid, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(local_camera_id) DO UPDATE SET backend_uuid = excluded.backend_uuid;
            """,
            (l_id, b_uuid),
        )
    print(f"[CLEAN] Populated camera mappings: {cam_mappings}")

    conn.commit()
    conn.close()


def sync_real_data_to_edge() -> None:
    """Execute a full sync cycle from backend to edge agent."""
    print("\n[SYNC] Initiating full embedding and photo synchronization with backend...")
    settings = EdgeSettings.load_from_ini()
    local_db = SQLiteStore(db_path=settings.agent.db_path)
    faiss_store = FAISSStore(dim=512)

    try:
        api_client = ApiClient(
            base_url=settings.backend.url,
            api_key=settings.backend.api_key or "fmp_agent_key_dev_seed_998877665544332211",
        )
        syncer = EmbeddingSyncer(
            api_client=api_client,
            local_db=local_db,
            faiss_store=faiss_store,
        )
        summary = syncer.sync_now(force_full=True)
        print(f"[SYNC] HTTP synchronization complete: {summary}")
    except Exception as e:
        print(f"[SYNC] Backend HTTP is offline ({e}); performing direct database sync from backend_local.db...")
        backend_db = "backend_local.db"
        if not os.path.isfile(backend_db):
            print(f"[ERROR] Cannot find {backend_db}")
            return

        bconn = sqlite3.connect(backend_db)
        bconn.row_factory = sqlite3.Row
        bc = bconn.cursor()

        # Clear edge cached embeddings
        local_db.clear_embeddings()

        # Query active embeddings with full metadata and photos
        query = """
            SELECT 
                fe.id AS embedding_id,
                fe.person_id,
                fe.embedding,
                mp.full_name,
                mp.age,
                mp.gender,
                mp.height_cm,
                mp.description,
                mp.last_seen_location,
                mp.last_seen_time,
                mp.contact_info,
                p.face_crop_path,
                p.original_path,
                u.name AS reporter_name,
                u.email AS reporter_email,
                u.phone AS reporter_phone
            FROM face_embeddings fe
            JOIN missing_persons mp ON fe.person_id = mp.id
            LEFT JOIN photos p ON fe.photo_id = p.id
            LEFT JOIN users u ON mp.user_id = u.id
            WHERE mp.status = 'ACTIVE' AND fe.is_active = 1
        """
        rows = bc.execute(query).fetchall()
        stored_items = []
        for r in rows:
            person_id = str(r["person_id"])
            # Format hyphenated UUID
            if len(person_id) == 32 and "-" not in person_id:
                formatted_pid = f"{person_id[:8]}-{person_id[8:12]}-{person_id[12:16]}-{person_id[16:20]}-{person_id[20:]}"
            else:
                formatted_pid = person_id

            photo_url = r["face_crop_path"] or r["original_path"]
            local_photo_path = None
            if photo_url:
                clean_rel = photo_url.lstrip("/\\")
                for base in [os.getcwd(), os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))]:
                    c_path = os.path.abspath(os.path.join(base, clean_rel))
                    if os.path.isfile(c_path):
                        local_photo_path = c_path
                        break

            meta = {
                "age": r["age"],
                "gender": r["gender"],
                "height_cm": r["height_cm"],
                "description": r["description"],
                "last_seen_location": r["last_seen_location"],
                "last_seen_time": r["last_seen_time"],
                "contact_info": r["contact_info"],
                "reporter_name": r["reporter_name"],
                "reporter_email": r["reporter_email"],
                "reporter_phone": r["reporter_phone"],
            }

            stored_items.append({
                "id": str(r["embedding_id"]),
                "person_id": formatted_pid,
                "person_name": r["full_name"],
                "embedding_data": r["embedding"],
                "photo_url": photo_url,
                "local_photo_path": local_photo_path,
                "metadata": meta,
            })

        bconn.close()
        if stored_items:
            local_db.save_embeddings_batch(stored_items)
            print(f"[SYNC] Saved {len(stored_items)} real person embeddings into edge SQLite.")

        # Rebuild FAISS index
        all_cached = local_db.get_all_embeddings()
        faiss_store.rebuild(all_cached)
        print(f"[SYNC] FAISS index rebuilt with {faiss_store.size} vectors.")

    # Verify cached embeddings
    cached = local_db.get_all_embeddings()
    print(f"[SYNC] Currently cached embeddings on edge ({len(cached)}):")
    for item in cached:
        meta = local_db.get_person_details(item["person_id"])
        print(f"  • {item['person_name']} (ID: {item['person_id']})")
        print(f"    Photo URL: {item.get('photo_url')}")
        print(f"    Local Photo Path: {item.get('local_photo_path')}")
        if meta and meta.get("metadata"):
            m = meta["metadata"]
            print(f"    Reported By: {m.get('reporter_name')} ({m.get('reporter_email')})")
            print(f"    Last Seen: {m.get('last_seen_location')}")


if __name__ == "__main__":
    clean_backend_db()
    clean_edge_db()
    sync_real_data_to_edge()
    print("\n[DONE] System is now fully clean and running on REAL user data!")

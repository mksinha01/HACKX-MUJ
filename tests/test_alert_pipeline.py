import asyncio
import hashlib
import io
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.main import app
from app.models.camera import Camera
from app.models.edge_agent import EdgeAgent
from app.models.missing_person import MissingPerson
from app.models.user import User

client = TestClient(app)

API_KEY = "fmp_agent_key_dev_seed_998877665544332211"
HEADERS = {"X-API-Key": API_KEY}
MANOJ_ID = "fd12bd71-9df3-4621-b9c6-8696eea0f282"
CAM_UUID = "f6d8aceb-5bfa-4b6e-aeb1-69cf863e9ec1"


@pytest.fixture(autouse=True)
def seed_pipeline_data():
    """Ensure User, MissingPerson, EdgeAgent, and Camera records exist for tests."""
    db_gen = app.dependency_overrides.get(get_db, get_db)()

    async def _seed():
        session = await anext(db_gen)
        try:
            # 1. User
            user_id = UUID("8e764e84-6209-461d-b3db-0599a26bbb67")
            res = await session.execute(select(User).where(User.id == user_id))
            user = res.scalar_one_or_none()
            if not user:
                user = User(
                    id=user_id,
                    firebase_uid="4MUoYzCt3rctqc1xbfykleG8aUd2",
                    name="Mk Sinha",
                    email="mksinha77756@gmail.com",
                    language="en",
                )
                session.add(user)
                await session.flush()

            # 2. Missing Person
            person_id = UUID(MANOJ_ID)
            res = await session.execute(select(MissingPerson).where(MissingPerson.id == person_id))
            person = res.scalar_one_or_none()
            if not person:
                person = MissingPerson(
                    id=person_id,
                    user_id=user.id,
                    full_name="manoj",
                    age=25,
                    gender="Male",
                    status="ACTIVE",
                )
                session.add(person)
                await session.flush()

            # 3. Edge Agent
            dev_id = "EDGE-CAMPUS-01"
            res = await session.execute(select(EdgeAgent).where(EdgeAgent.device_id == dev_id))
            agent = res.scalar_one_or_none()
            api_key_hash = hashlib.sha256(API_KEY.encode("utf-8")).hexdigest()
            if not agent:
                agent = EdgeAgent(
                    id=UUID("c85b716e-6d91-457e-805e-e178d99f3313"),
                    device_id=dev_id,
                    name="Main Campus Hub",
                    location="Administration Building",
                    api_key_hash=api_key_hash,
                    status="ONLINE",
                    camera_count=2,
                    version="1.0.0",
                    last_heartbeat=datetime.now(timezone.utc),
                )
                session.add(agent)
                await session.flush()

            # 4. Camera
            cam_id = UUID(CAM_UUID)
            res = await session.execute(select(Camera).where(Camera.id == cam_id))
            cam = res.scalar_one_or_none()
            if not cam:
                cam = Camera(
                    id=cam_id,
                    agent_id=agent.id,
                    local_camera_id="CAM-01",
                    name="Main Entrance Gate",
                    encrypted_rtsp_url="local://test-feed",
                    location="Main Entrance Gate",
                    status="ACTIVE",
                )
                session.add(cam)
                await session.flush()

            await session.commit()
        finally:
            await session.close()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_seed())
    yield


def test_events_stream_endpoints_accessible():
    """Verify both /events/stream and /api/events/stream routes exist and enforce auth."""
    # Root alias /events/stream
    res1 = client.get("/events/stream")
    assert res1.status_code == 401, f"Expected 401 without token, got {res1.status_code}"

    # Prefix /api/events/stream
    res2 = client.get("/api/events/stream")
    assert res2.status_code == 401, f"Expected 401 without token, got {res2.status_code}"


def test_sighting_upload_with_uuid_and_local_camera_id():
    """Verify that both UUID and local camera identifiers (e.g. CAM-01) succeed and create notifications."""
    face_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JPEG header bytes
    frame_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 200

    # 1. Upload using local camera name 'CAM-01'
    files_cam01 = {
        "face_crop": ("face_crop.jpg", io.BytesIO(face_bytes), "image/jpeg"),
        "full_frame": ("full_frame.jpg", io.BytesIO(frame_bytes), "image/jpeg"),
    }
    data_cam01 = {
        "person_id": MANOJ_ID,
        "camera_id": "CAM-01",
        "similarity_score": "0.89",
        "detected_at": "2026-09-11T14:30:00Z",
        "confidence_level": "CONFIRMED",
        "camera_location": "Main Entrance Gate",
    }
    res_cam01 = client.post("/api/sightings/", data=data_cam01, files=files_cam01, headers=HEADERS)
    assert res_cam01.status_code == 201, f"CAM-01 upload failed: {res_cam01.text}"
    sighting_json = res_cam01.json()
    assert sighting_json["similarity_score"] == 0.89
    assert sighting_json["camera_id"] == CAM_UUID

    # 2. Upload using camera UUID directly
    files_uuid = {
        "face_crop": ("face_crop.jpg", io.BytesIO(face_bytes), "image/jpeg"),
        "full_frame": ("full_frame.jpg", io.BytesIO(frame_bytes), "image/jpeg"),
    }
    data_uuid = {
        "person_id": MANOJ_ID,
        "camera_id": CAM_UUID,
        "similarity_score": "0.94",
        "detected_at": "2026-09-11T14:35:00Z",
        "confidence_level": "CONFIRMED",
        "camera_location": "Main Entrance Gate",
    }
    res_uuid = client.post("/api/sightings/", data=data_uuid, files=files_uuid, headers=HEADERS)
    assert res_uuid.status_code == 201, f"UUID upload failed: {res_uuid.text}"


    # 3. Verify GET /api/sightings/ returns sightings with resolved person_name
    res_list = client.get("/api/sightings/")
    assert res_list.status_code == 200
    sightings = res_list.json()
    assert len(sightings) >= 2
    for s in sightings:
        if s["person_id"] == MANOJ_ID:
            assert s["person_name"] == "manoj"

    # 4. Verify PUT /api/sightings/{id}/confirm closes active search
    s_id = sighting_json["id"]
    auth_headers = {"Authorization": "Bearer mock-token-admin"}
    res_confirm = client.put(f"/api/sightings/{s_id}/confirm", json={"review_notes": "Operator verified match"}, headers=auth_headers)
    assert res_confirm.status_code == 200, f"Confirm failed: {res_confirm.text}"
    assert res_confirm.json()["status"] == "CONFIRMED"
    assert res_confirm.json()["review_notes"] == "Operator verified match"

    # Verify that the missing person status transitioned from ACTIVE to FOUND
    res_person = client.get(f"/api/reports/{MANOJ_ID}")
    assert res_person.status_code == 200
    assert res_person.json()["status"] == "FOUND", f"Expected person status FOUND, got {res_person.json()['status']}"

    # Verify that edge agent sync returns person_id in removed_ids for vector pruning
    res_sync = client.get("/api/embeddings/sync?since=2026-09-01T00:00:00Z", headers=HEADERS)
    assert res_sync.status_code == 200
    sync_data = res_sync.json()
    assert MANOJ_ID in sync_data["removed_ids"], f"Expected {MANOJ_ID} in removed_ids, got {sync_data['removed_ids']}"

    # 5. Verify PUT /api/sightings/{id}/reject
    # Create a fresh pending sighting to test reject without affecting a resolved case
    data_rej = {
        "person_id": MANOJ_ID,
        "camera_id": CAM_UUID,
        "similarity_score": "0.45",
        "detected_at": "2026-09-11T14:40:00Z",
        "confidence_level": "POSSIBLE",
        "camera_location": "Main Entrance Gate",
    }
    res_sighting2 = client.post("/api/sightings/", data=data_rej, files=files_uuid, headers=HEADERS)
    assert res_sighting2.status_code == 201
    s2_id = res_sighting2.json()["id"]

    res_reject = client.put(f"/api/sightings/{s2_id}/reject", json={"review_notes": "False positive"}, headers=auth_headers)
    assert res_reject.status_code == 200, f"Reject failed: {res_reject.text}"
    assert res_reject.json()["status"] == "REJECTED"


if __name__ == "__main__":
    test_events_stream_endpoints_accessible()
    print("[PASS] test_events_stream_endpoints_accessible")
    test_sighting_upload_with_uuid_and_local_camera_id()
    print("[PASS] test_sighting_upload_with_uuid_and_local_camera_id")
    print("ALL ALERT PIPELINE TESTS PASSED!")

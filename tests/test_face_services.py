"""Comprehensive test suite for Story 3: Face Processing, Crypto, File Storage, Embedding Sync, SSE, and Notifications."""
import asyncio
import io
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding_sync import get_sync_package
from app.services.face_processing import process_person_photo
from app.services.notification_service import dispatch_sighting_alert, send_sighting_notification
from app.services.sse_manager import SSEManager
from app.utils.crypto import AESGCMCrypto, decrypt_rtsp_url, encrypt_rtsp_url
from app.utils.file_storage import (
    delete_file,
    ensure_upload_dirs,
    get_absolute_path,
    save_bytes,
    save_upload_file,
)


# ==========================================
# 1. Cryptography Tests
# ==========================================

def test_crypto_roundtrip():
    """Verify AES-256-GCM encryption/decryption roundtrip."""
    secret = "32bytehexsecretforaesencryption00"
    crypto = AESGCMCrypto(secret_key=secret)

    original = "rtsp://admin:pass123@192.168.1.100:554/stream1"
    encrypted = crypto.encrypt(original)

    assert encrypted != original
    assert len(encrypted) > 0

    decrypted = crypto.decrypt(encrypted)
    assert decrypted == original


def test_crypto_key_padding_and_truncation():
    """Verify key padding for short keys and truncation for long keys."""
    short_crypto = AESGCMCrypto(secret_key="short")
    assert len(short_crypto.key) == 32

    long_key = "a" * 64
    long_crypto = AESGCMCrypto(secret_key=long_key)
    assert len(long_crypto.key) == 32

    msg = "rtsp://camera.local/h264"
    assert short_crypto.decrypt(short_crypto.encrypt(msg)) == msg
    assert long_crypto.decrypt(long_crypto.encrypt(msg)) == msg


def test_crypto_error_handling():
    """Verify error handling on invalid inputs and tampered ciphertexts."""
    crypto = AESGCMCrypto(secret_key="32bytehexsecretforaesencryption00")

    with pytest.raises(ValueError):
        AESGCMCrypto(secret_key="")

    with pytest.raises(ValueError):
        crypto.encrypt(None)

    with pytest.raises(ValueError):
        crypto.decrypt("")

    with pytest.raises(ValueError):
        crypto.decrypt("invalid_base64!@#$")

    with pytest.raises(ValueError):
        # Tampered base64 ciphertext
        crypto.decrypt("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==")


def test_crypto_rtsp_helper_functions():
    """Verify encrypt_rtsp_url and decrypt_rtsp_url helper functions."""
    url = "rtsp://10.0.0.50:8554/live"
    token = encrypt_rtsp_url(url)
    assert token != url
    recovered = decrypt_rtsp_url(token)
    assert recovered == url


# ==========================================
# 2. File Storage Tests
# ==========================================

@pytest.mark.asyncio
async def test_file_storage_operations(tmp_path):
    """Verify file saving, byte saving, path resolution, and deletion."""
    upload_dir = str(tmp_path / "uploads")
    ensure_upload_dirs(upload_dir)

    assert (tmp_path / "uploads" / "photos").exists()
    assert (tmp_path / "uploads" / "faces").exists()
    assert (tmp_path / "uploads" / "evidence").exists()

    # 1. Test save_upload_file
    dummy_file = UploadFile(
        file=io.BytesIO(b"fake image content"),
        filename="test_photo.jpg",
    )
    rel_url = await save_upload_file(dummy_file, subfolder="photos", upload_dir=upload_dir)
    assert rel_url.startswith("/uploads/photos/")
    assert rel_url.endswith(".jpg")

    abs_path = get_absolute_path(rel_url, upload_dir=upload_dir)
    assert abs_path.exists()

    # 2. Test save_bytes
    face_bytes = b"fake cropped face bytes"
    face_url = await save_bytes(face_bytes, subfolder="faces", extension=".jpg", upload_dir=upload_dir)
    assert face_url.startswith("/uploads/faces/")
    assert face_url.endswith(".jpg")

    # 3. Test path traversal protection
    with pytest.raises(ValueError, match="Path traversal detected"):
        get_absolute_path("/uploads/../../etc/passwd", upload_dir=upload_dir)

    # 4. Test delete_file
    deleted = await delete_file(rel_url, upload_dir=upload_dir)
    assert deleted is True
    assert not abs_path.exists()

    # Delete non-existent file returns False
    assert await delete_file("/uploads/photos/non_existent.jpg", upload_dir=upload_dir) is False


# ==========================================
# 3. Face Processing Service Tests
# ==========================================

def test_face_processing_empty_and_corrupt_input():
    """Verify rejection of empty or invalid image bytes."""
    with pytest.raises(ValueError, match="Image bytes cannot be empty"):
        process_person_photo(b"")

    with pytest.raises(ValueError, match="Invalid image format"):
        process_person_photo(b"not a valid jpeg or png")


def test_face_processing_no_face_detected(monkeypatch):
    """Verify ValueError is raised when no faces are detected in the image."""
    import app.services.face_processing as fp_module

    class MockEmptyApp:
        def get(self, img):
            return []

    monkeypatch.setattr(fp_module, "get_face_app", lambda: MockEmptyApp())

    dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", dummy_img)

    with pytest.raises(ValueError, match="No face detected"):
        process_person_photo(encoded.tobytes())


def test_face_processing_low_confidence(monkeypatch):
    """Verify rejection when detection confidence is below 0.60."""
    import app.services.face_processing as fp_module

    class MockLowConfFace:
        bbox = [0, 0, 100, 100]
        det_score = 0.45
        kps = np.zeros((5, 2))
        embedding = np.random.rand(512).astype(np.float32)

    class MockApp:
        def get(self, img):
            return [MockLowConfFace()]

    monkeypatch.setattr(fp_module, "get_face_app", lambda: MockApp())

    dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", dummy_img)

    with pytest.raises(ValueError, match="confidence too low"):
        process_person_photo(encoded.tobytes())


def test_face_processing_small_face(monkeypatch):
    """Verify rejection when face dimensions are below 60x60."""
    import app.services.face_processing as fp_module

    class MockSmallFace:
        bbox = [10, 10, 40, 40]  # 30x30 pixels
        det_score = 0.95
        kps = np.zeros((5, 2))
        embedding = np.random.rand(512).astype(np.float32)

    class MockApp:
        def get(self, img):
            return [MockSmallFace()]

    monkeypatch.setattr(fp_module, "get_face_app", lambda: MockApp())

    dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", dummy_img)

    with pytest.raises(ValueError, match="Face size too small"):
        process_person_photo(encoded.tobytes())


def test_face_processing_success_and_l2_norm(monkeypatch):
    """Verify successful face extraction, alignment to 112x112, and L2 normalization."""
    import app.services.face_processing as fp_module

    raw_embedding = np.random.randn(512).astype(np.float32)

    class MockFace:
        bbox = [20, 20, 140, 140]  # 120x120 pixels
        det_score = 0.92
        kps = np.ones((5, 2)) * 50
        embedding = raw_embedding

    class MockFaceApp:
        def get(self, img):
            return [MockFace()]

    class MockFaceAlign:
        @staticmethod
        def norm_crop(img, landmark, image_size):
            return np.ones((image_size, image_size, 3), dtype=np.uint8) * 128

    monkeypatch.setattr(fp_module, "get_face_app", lambda: MockFaceApp())
    monkeypatch.setattr(fp_module, "face_align", MockFaceAlign())

    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 200
    _, encoded = cv2.imencode(".jpg", dummy_img)

    crop_bytes, normed_emb, score = process_person_photo(encoded.tobytes())

    assert isinstance(crop_bytes, bytes)
    assert len(crop_bytes) > 0

    # Verify 512-D ArcFace embedding properties
    assert normed_emb.shape == (512,)
    assert normed_emb.dtype == np.float32

    # Verify L2 normalization: ||normed_emb|| == 1.0
    l2_norm = float(np.linalg.norm(normed_emb))
    assert np.isclose(l2_norm, 1.0, atol=1e-5)
    assert score == 0.92


# ==========================================
# 4. Embedding Synchronization & Tombstone Tests
# ==========================================

@pytest.mark.asyncio
async def test_full_sync_package():
    """Verify full sync package returns all active embeddings with empty removed_ids."""
    mock_db = AsyncMock(spec=AsyncSession)

    active_records = [
        {
            "embedding_id": str(uuid4()),
            "person_id": str(uuid4()),
            "person_name": "Test Person 1",
            "embedding_bytes": np.random.randn(512).astype(np.float32).tobytes(),
            "quality_score": 0.88,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    with patch("app.services.embedding_sync.get_active_embeddings", new=AsyncMock(return_value=active_records)):
        pkg = await get_sync_package(mock_db, since=None)

        assert pkg["full_sync"] is True
        assert len(pkg["persons"]) == 1
        assert pkg["persons"][0]["person_name"] == "Test Person 1"
        assert pkg["removed_ids"] == []
        assert "sync_timestamp" in pkg


@pytest.mark.asyncio
async def test_incremental_sync_tombstones():
    """Verify incremental sync properly computes tombstones (removed_ids)."""
    mock_db = AsyncMock(spec=AsyncSession)

    p1_active_id = str(uuid4())
    p2_found_id = str(uuid4())
    p3_deactivated_id = str(uuid4())

    active_since = [
        {
            "embedding_id": str(uuid4()),
            "person_id": p1_active_id,
            "person_name": "Active Updated Person",
            "embedding_bytes": np.random.randn(512).astype(np.float32).tobytes(),
            "quality_score": 0.95,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    since_time = datetime.now(timezone.utc) - timedelta(hours=2)

    # Mock candidate deactivated / found IDs
    with patch(
        "app.services.embedding_sync.get_embeddings_since",
        new=AsyncMock(return_value=active_since),
    ), patch(
        "app.services.embedding_sync.get_deactivated_person_ids_since",
        new=AsyncMock(return_value=[p2_found_id, p3_deactivated_id]),
    ):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        pkg = await get_sync_package(mock_db, since=since_time)

        assert pkg["full_sync"] is False
        assert len(pkg["persons"]) == 1
        assert pkg["persons"][0]["person_id"] == p1_active_id
        # removed_ids must contain p2 and p3, and exclude p1
        assert sorted(pkg["removed_ids"]) == sorted([p2_found_id, p3_deactivated_id])


# ==========================================
# 5. SSE Manager Tests
# ==========================================

@pytest.mark.asyncio
async def test_sse_manager_publish():
    """Verify SSEManager publishes JSON messages to Redis."""
    sse = SSEManager(redis_url="redis://localhost:6379/0")
    sse._redis = AsyncMock()

    payload = {"event": "sighting", "sighting_id": str(uuid4()), "score": 0.94}
    await sse.publish("user_123", payload)

    sse._redis.publish.assert_awaited_once()
    call_args = sse._redis.publish.call_args[0]
    assert call_args[0] == "user_123"
    assert '"event": "sighting"' in call_args[1]


@pytest.mark.asyncio
async def test_sse_manager_event_generator():
    """Verify SSE event generator outputs formatted events and terminates cleanly."""
    sse = SSEManager()
    mock_redis = AsyncMock()
    mock_pubsub = AsyncMock()

    # Simulate message then disconnect
    messages = [
        {"type": "message", "data": '{"event": "sighting", "score": 0.92}'},
        None,
    ]

    async def mock_get_message(ignore_subscribe_messages=True, timeout=1.0):
        if messages:
            return messages.pop(0)
        return None

    mock_pubsub.get_message = mock_get_message
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    sse._redis = mock_redis

    mock_request = AsyncMock()
    disconnect_calls = [False, True]

    async def mock_is_disconnected():
        if disconnect_calls:
            return disconnect_calls.pop(0)
        return True

    mock_request.is_disconnected = mock_is_disconnected

    events = []
    async for event in sse.event_generator("channel_test", mock_request):
        events.append(event)

    assert len(events) == 1
    assert "event: sighting\n" in events[0]
    assert '"score": 0.92' in events[0]
    mock_pubsub.unsubscribe.assert_awaited_once_with("channel_test")
    mock_pubsub.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_sse_manager_heartbeat_ping(monkeypatch):
    """Verify SSE event generator emits 30-second :ping heartbeat."""
    sse = SSEManager()
    mock_redis = AsyncMock()
    mock_pubsub = AsyncMock()

    # No message arrives, simulate 30 seconds passing
    async def mock_get_message(ignore_subscribe_messages=True, timeout=1.0):
        return None

    mock_pubsub.get_message = mock_get_message
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    sse._redis = mock_redis

    # Advance time on each monotonic call
    time_values = [0.0, 31.0, 31.0, 31.0]

    def mock_monotonic():
        if time_values:
            return time_values.pop(0)
        return 100.0

    monkeypatch.setattr(time, "monotonic", mock_monotonic)

    mock_request = AsyncMock()
    disconnect_calls = [False, False, True]

    async def mock_is_disconnected():
        if disconnect_calls:
            return disconnect_calls.pop(0)
        return True

    mock_request.is_disconnected = mock_is_disconnected

    events = []
    async for event in sse.event_generator("channel_test", mock_request):
        events.append(event)

    assert len(events) >= 1
    assert ":ping\n\n" in events
    mock_pubsub.unsubscribe.assert_awaited_once_with("channel_test")
    mock_pubsub.close.assert_awaited_once()


# ==========================================
# 6. Notification Service Tests
# ==========================================

@pytest.mark.asyncio
async def test_notification_service_flow():
    """Verify dispatch_sighting_alert and send_sighting_notification flows."""
    mock_db = AsyncMock(spec=AsyncSession)
    user_id = uuid4()
    sighting_id = uuid4()

    mock_notif = MagicMock()
    mock_notif.id = uuid4()

    mock_user = MagicMock()
    mock_user.fcm_token = "mock_fcm_token_12345"

    with patch(
        "app.services.notification_service.create_notification",
        new=AsyncMock(return_value=mock_notif),
    ), patch(
        "app.services.notification_service.get_user_by_id",
        new=AsyncMock(return_value=mock_user),
    ), patch(
        "app.services.sse_manager.sse_manager.publish",
        new=AsyncMock(),
    ) as mock_sse_publish:
        notif = await dispatch_sighting_alert(
            db=mock_db,
            user_id=user_id,
            title="Test Sighting Alert",
            body="Match detected in Sector 4",
            sighting_id=sighting_id,
            data={"score": 0.91},
        )

        assert notif == mock_notif
        assert mock_sse_publish.await_count == 2
        calls = [call[0] for call in mock_sse_publish.call_args_list]
        channels_called = [c[0] for c in calls]
        assert f"user_{user_id}" in channels_called
        assert "dashboard_sightings" in channels_called
        assert calls[0][1]["sighting_id"] == str(sighting_id)
        assert calls[0][1]["title"] == "Test Sighting Alert"


@pytest.mark.asyncio
async def test_sse_manager_multi_channel_in_memory():
    """Verify SSEManager in-memory pubsub delivers messages from multiple subscribed channels."""
    from app.services.sse_manager import SSEManager
    manager = SSEManager()
    channels = ["user_test_123", "dashboard_sightings"]

    # Subscribe queue to both channels
    queue = asyncio.Queue(maxsize=256)
    for ch in channels:
        await manager._fallback.subscribe(ch, queue=queue)

    # Publish message to user channel
    await manager.publish("user_test_123", {"event": "sighting", "msg": "User specific"})
    # Publish message to dashboard channel
    await manager.publish("dashboard_sightings", {"event": "sighting", "msg": "Global alert"})

    # Read messages from the combined queue
    msg1 = await asyncio.wait_for(queue.get(), timeout=1.0)
    msg2 = await asyncio.wait_for(queue.get(), timeout=1.0)

    import json
    data1 = json.loads(msg1)
    data2 = json.loads(msg2)
    messages = [data1.get("msg"), data2.get("msg")]
    assert "User specific" in messages
    assert "Global alert" in messages

    # Clean up unsubscriptions
    for ch in channels:
        await manager._fallback.unsubscribe(ch, queue)


@pytest.mark.asyncio
async def test_send_sighting_notification_helper():
    """Verify send_sighting_notification formats sighting metadata correctly."""
    mock_db = AsyncMock(spec=AsyncSession)
    user_id = uuid4()

    mock_sighting = MagicMock()
    mock_sighting.id = uuid4()
    mock_sighting.similarity_score = 0.895
    mock_sighting.camera_id = uuid4()
    mock_sighting.person_id = uuid4()

    with patch(
        "app.services.notification_service.dispatch_sighting_alert",
        new=AsyncMock(),
    ) as mock_dispatch:
        await send_sighting_notification(
            db=mock_db,
            user_id=user_id,
            sighting=mock_sighting,
        )

        mock_dispatch.assert_awaited_once()
        _, kwargs = mock_dispatch.call_args
        assert kwargs["user_id"] == user_id
        assert kwargs["sighting_id"] == mock_sighting.id
        assert "89.5%" in kwargs["body"]
        assert kwargs["data"]["similarity_score"] == 0.895

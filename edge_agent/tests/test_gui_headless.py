"""Headless verification test suite for Edge Agent PySide6 GUI, widgets, and background workers."""
import json
import os
import sys
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure headless offscreen platform for CI and virtual environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QCloseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from edge_agent.config import EdgeSettings
from edge_agent.ui.alert_widget import AlertWidget
from edge_agent.ui.camera_config_dialog import CameraConfigDialog
from edge_agent.ui.camera_feed_widget import CameraFeedWidget
from edge_agent.ui.login_dialog import LoginDialog
from edge_agent.ui.main_window import MainWindow
from edge_agent.ui.settings_dialog import SettingsDialog
from edge_agent.ui.status_bar_widget import StatusBarWidget
from edge_agent.ui.timeline_widget import TimelineWidget
from edge_agent.ui.workers.stream_worker import StreamWorker
from edge_agent.ui.workers.sync_worker import SyncWorker
from edge_agent.utils.path_resolver import get_resource_path


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single shared QApplication instance across all headless tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ═════════════════════════════════════════════════════════════════════════════
# 1. Resource & Path Resolution Tests (Fix #23)
# ═════════════════════════════════════════════════════════════════════════════

def test_resource_resolution_style_and_i18n():
    """Verify that get_resource_path correctly locates style.qss and i18n files."""
    # Test QSS stylesheet path resolution
    qss_rel = os.path.join("edge_agent", "ui", "resources", "style.qss")
    qss_path = get_resource_path(qss_rel)
    assert os.path.exists(qss_path), f"style.qss not found at {qss_path}"

    with open(qss_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "background-color" in content
    assert "#cameraFeedContainer" in content

    # Test English and Hindi translation dictionaries
    for lang in ["en", "hi"]:
        rel = os.path.join("edge_agent", "ui", "resources", "i18n", f"{lang}.json")
        json_path = get_resource_path(rel)
        assert os.path.exists(json_path), f"{lang}.json not found at {json_path}"

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "app" in data
        assert "alert" in data
        assert "status_bar" in data
        assert "camera_feed" in data


# ═════════════════════════════════════════════════════════════════════════════
# 2. CameraFeedWidget Tests
# ═════════════════════════════════════════════════════════════════════════════

def test_camera_feed_widget_headless(qapp):
    """Test CameraFeedWidget rendering, bounding boxes, and FPS updates."""
    feed = CameraFeedWidget(camera_index=0, camera_id="CAM-01", camera_name="Front Gate")
    feed.resize(640, 480)

    # Initial state
    assert not feed.is_connected
    assert feed.camera_id == "CAM-01"

    # Create synthetic frame (480x640x3 BGR)
    synthetic_frame = np.full((480, 640, 3), 40, dtype=np.uint8)

    # Mock face tracks
    class MockTrack:
        def __init__(self, track_id, bbox, person_id=None, similarity=None):
            self.track_id = track_id
            self.bbox = bbox
            self.person_id = person_id
            self.similarity = similarity

    tracks = [
        MockTrack(track_id=101, bbox=[100, 100, 200, 220]),
        MockTrack(track_id=102, bbox=[300, 120, 420, 250], person_id="MP-99", similarity=0.82),
    ]

    # Slot update
    feed.update_frame(0, synthetic_frame, tracks)
    assert feed.is_connected
    assert feed.current_frame is not None
    assert len(feed.current_tracks) == 2

    # FPS update
    feed.update_fps(0, 14.8)
    assert feed.fps == 14.8

    # Render into offscreen pixmap to ensure QPainter executes cleanly without segfault
    pixmap = QPixmap(640, 480)
    painter = QPainter(pixmap)
    feed.paintEvent(None)
    painter.end()


# ═════════════════════════════════════════════════════════════════════════════
# 3. StatusBarWidget Telemetry Tests
# ═════════════════════════════════════════════════════════════════════════

def test_status_bar_widget_headless(qapp):
    """Verify StatusBarWidget metrics update cleanly."""
    status_bar = StatusBarWidget()

    # Update individual metrics
    status_bar.set_ai_status("● AI Running", "#10b981")
    assert "AI Running" in status_bar.ai_status_label.text()

    status_bar.set_cases_count(42)
    assert "42" in status_bar.cases_label.text()

    status_bar.set_fps(15.2)
    assert "15.2" in status_bar.fps_label.text()

    status_bar.set_faces_count(150)
    assert "150" in status_bar.faces_label.text()

    status_bar.increment_faces(10)
    assert "160" in status_bar.faces_label.text()

    status_bar.set_last_sync("14:30:00")
    assert "14:30:00" in status_bar.sync_label.text()

    status_bar.set_backend_online(True)
    assert "Online" in status_bar.backend_status_label.text()

    status_bar.set_backend_online(False)
    assert "Offline" in status_bar.backend_status_label.text()

    # Batch update via stats dict
    status_bar.update_stats({"cases_count": 88, "last_sync": "15:00:00"})
    assert "88" in status_bar.cases_label.text()
    assert "15:00:00" in status_bar.sync_label.text()


# ═════════════════════════════════════════════════════════════════════════════
# 4. AlertWidget Side-by-Side Comparison & Actions Tests (CRITICAL REQUIREMENT)
# ═════════════════════════════════════════════════════════════════════════

def test_alert_widget_side_by_side_and_confirm_reject(qapp, tmp_path):
    """
    CRITICAL REQUIREMENT:
    In alert_widget.py, display side-by-side comparison of registered photo vs live detected crop
    with Confirm and Reject buttons.
    """
    # Create dummy image crops
    import cv2
    crop_path = str(tmp_path / "crop.jpg")
    photo_path = str(tmp_path / "photo.jpg")

    dummy_img = np.full((112, 112, 3), 128, dtype=np.uint8)
    cv2.imwrite(crop_path, dummy_img)
    cv2.imwrite(photo_path, dummy_img)

    sighting_payload = {
        "person_id": "MP-102",
        "person_name": "Aarav Sharma",
        "similarity": 0.784,
        "camera_id": "CAM-01",
        "timestamp": time.time(),
        "face_crop_path": crop_path,
        "registered_photo_path": photo_path,
    }

    alert = AlertWidget(sighting_data=sighting_payload)

    # 1. Verify side-by-side comparison components exist
    assert hasattr(alert, "registered_photo_label")
    assert hasattr(alert, "live_crop_label")
    assert alert.registered_photo_label is not None
    assert alert.live_crop_label is not None

    # Verify progress bar gauge
    assert alert.sim_progress.value() == 78

    # 2. Test Confirm Action
    confirmed_received = []
    alert.confirmed.connect(lambda data: confirmed_received.append(data))

    alert.notes_input.setText("Attire matches blue shirt")
    alert._on_confirm()

    assert len(confirmed_received) == 1
    assert confirmed_received[0]["status"] == "CONFIRMED"
    assert confirmed_received[0]["review_notes"] == "Attire matches blue shirt"
    assert confirmed_received[0]["person_id"] == "MP-102"

    # 3. Test Reject Action
    rejected_received = []
    alert2 = AlertWidget(sighting_data=sighting_payload)
    alert2.rejected.connect(lambda data: rejected_received.append(data))

    alert2.notes_input.setText("Wrong person, false alarm")
    alert2._on_reject()

    assert len(rejected_received) == 1
    assert rejected_received[0]["status"] == "REJECTED"
    assert rejected_received[0]["review_notes"] == "Wrong person, false alarm"


# ═════════════════════════════════════════════════════════════════════════════
# 5. TimelineWidget Operations Tests
# ═════════════════════════════════════════════════════════════════════════

def test_timeline_widget_operations(qapp):
    """Test chronological timeline addition, formatting, and selection."""
    timeline = TimelineWidget()

    sighting1 = {
        "person_id": "MP-101",
        "person_name": "Rohan",
        "similarity": 0.65,
        "camera_id": "CAM-01",
        "timestamp": time.time(),
        "status": "PENDING",
    }
    sighting2 = {
        "person_id": "MP-102",
        "person_name": "Priya",
        "similarity": 0.88,
        "camera_id": "CAM-02",
        "timestamp": time.time() + 1,
        "status": "CONFIRMED",
    }

    timeline.add_sighting(sighting1)
    assert timeline.table.rowCount() == 1
    assert "MP-101" in timeline.table.item(0, 1).text()

    timeline.add_sighting(sighting2)
    assert timeline.table.rowCount() == 2
    # Sighting2 is newest, inserted at row 0
    assert "MP-102" in timeline.table.item(0, 1).text()

    # Update status test
    timeline.update_sighting_status("MP-101", "CONFIRMED")
    assert timeline.table.item(1, 4).text() == "CONFIRMED"

    # Selection signal test
    selected = []
    timeline.sighting_selected.connect(lambda s: selected.append(s))
    timeline._on_row_double_clicked(0, 0)
    assert len(selected) == 1
    assert selected[0]["person_id"] == "MP-102"


# ═════════════════════════════════════════════════════════════════════════════
# 6. StreamWorker Signals and Cooperative Shutdown Tests
# ═════════════════════════════════════════════════════════════════════════

def test_stream_worker_signals_and_graceful_teardown(qapp):
    """
    CRITICAL REQUIREMENT:
    All image updates between QThread workers and UI widgets MUST use Qt signals.
    Implement graceful shutdown in worker using worker.stop() and worker.wait(3000).
    """
    worker = StreamWorker(camera_index=0, camera_id="CAM-TEST", target_fps=30)

    # Verify signal definitions
    assert hasattr(worker, "frame_processed")
    assert hasattr(worker, "sighting_detected")
    assert hasattr(worker, "fps_updated")
    assert hasattr(worker, "status_changed")

    # Start worker thread
    worker.start()
    assert worker.isRunning()
    assert worker.is_running

    # Test cooperative shutdown (wait up to 3000ms)
    worker.stop()
    worker.wait(3000)
    assert not worker.isRunning()
    assert not worker.is_running


# ═════════════════════════════════════════════════════════════════════════════
# 7. SyncWorker Signals and Cooperative Shutdown Tests
# ═════════════════════════════════════════════════════════════════════════

def test_sync_worker_signals_and_graceful_teardown(qapp):
    """Verify SyncWorker signals, manual trigger, and clean stop."""
    mock_syncer = MagicMock()
    mock_syncer.sync_now.return_value = {"added": 2, "pruned": 1}
    mock_uploader = MagicMock()
    mock_uploader.process_queue_once.return_value = 1
    mock_db = MagicMock()
    mock_db.count_persons.return_value = 5
    mock_db.count_embeddings.return_value = 10
    mock_db.get_pending_sightings.return_value = []
    mock_db.get_sync_state.return_value = "2026-09-06T14:00:00"

    worker = SyncWorker(
        syncer=mock_syncer,
        uploader=mock_uploader,
        local_db=mock_db,
        sync_interval_seconds=60,
    )

    stats_emitted = []
    worker.stats_updated.connect(lambda s: stats_emitted.append(s))

    worker.start()
    assert worker.isRunning()

    # Trigger manual sync
    worker.trigger_sync()
    time.sleep(0.2)

    # Cooperative teardown
    worker.stop()
    worker.wait(3000)
    assert not worker.isRunning()


# ═════════════════════════════════════════════════════════════════════════════
# 8. MainWindow Full Lifecycle, Grid & Graceful closeEvent Tests (CRITICAL)
# ═════════════════════════════════════════════════════════════════════════

def test_main_window_headless_and_graceful_shutdown(qapp, tmp_path):
    """
    CRITICAL REQUIREMENT:
    In main_window.py, implement graceful shutdown in closeEvent using
    worker.stop() and worker.wait(3000). Never forcibly terminate threads.
    """
    db_path = str(tmp_path / "test_gui.db")
    settings = EdgeSettings()
    settings.agent.db_path = db_path

    window = MainWindow(settings=settings)
    window.resize(1024, 680)

    # 1. Verify 2x2 grid has 4 camera feed widgets
    assert len(window.camera_feed_widgets) == 4
    assert len(window.stream_workers) == 4
    assert window.sync_worker is not None

    # 2. Verify i18n dynamic language toggle
    window.set_language("hi")
    assert "एआई सीसीटीवी" in window.windowTitle()
    window.set_language("en")
    assert "AI CCTV" in window.windowTitle()

    # 3. Test Sighting Notification Slot (Direct Auto-Confirmation by Agent)
    sighting = {
        "person_id": "MP-202",
        "person_name": "Kavita",
        "similarity": 0.85,
        "camera_id": "CAM-01",
        "timestamp": time.time(),
        "face_crop_path": str(tmp_path / "crop.jpg"),
        "full_frame_path": str(tmp_path / "frame.jpg"),
    }
    # Create dummy files
    open(sighting["face_crop_path"], "w").write("test")
    open(sighting["full_frame_path"], "w").write("test")

    window._on_sighting_detected(sighting)
    assert window.timeline_widget.table.rowCount() >= 1
    assert window.timeline_widget.table.item(0, 4).text() == "CONFIRMED"

    # Verify auto-enqueued in local SQLite store
    pending = window.local_db.get_pending_sightings()
    assert len(pending) >= 1
    assert pending[0]["person_id"] == "MP-202"
    assert pending[0]["confidence_level"] == "CONFIRMED"

    # 4. CRITICAL REQUIREMENT: Test closeEvent cooperative shutdown
    close_evt = QCloseEvent()
    window.closeEvent(close_evt)
    assert close_evt.isAccepted()

    # Verify all stream workers are stopped and not running
    for worker in window.stream_workers:
        assert not worker.isRunning()

    if window.sync_worker:
        assert not window.sync_worker.isRunning()


# ═════════════════════════════════════════════════════════════════════════════
# 9. Dialogs Headless Instantiation Tests
# ═════════════════════════════════════════════════════════════════════════

def test_settings_and_config_dialogs_headless(qapp):
    """Test SettingsDialog, CameraConfigDialog, and LoginDialog instantiation."""
    settings = EdgeSettings()

    # Settings Dialog
    dlg_settings = SettingsDialog(settings=settings)
    assert dlg_settings.detect_thresh_spin.value() == settings.ai.face_detect_threshold

    # Camera Config Dialog
    existing = [{"local_camera_id": "CAM-01", "name": "Entrance", "rtsp_url": "rtsp://10.0.0.1"}]
    dlg_cam = CameraConfigDialog(existing_cameras=existing)
    assert dlg_cam.table.rowCount() == 1

    # Login Dialog
    dlg_login = LoginDialog(settings=settings)
    assert dlg_login.device_id_input.text() != ""

"""Main application window managing 1–4 camera video grid, telemetry, alerts, and graceful shutdown."""
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from edge_agent.ai.pipeline import EdgeAIPipeline
from edge_agent.ai.vector_search import VectorSearchEngine
from edge_agent.config import EdgeSettings
from edge_agent.network.api_client import ApiClient
from edge_agent.network.embedding_syncer import EmbeddingSyncer
from edge_agent.network.sighting_uploader import SightingUploader
from edge_agent.storage.faiss_store import FAISSStore
from edge_agent.storage.local_db import SQLiteStore
from edge_agent.ui.alert_widget import AlertWidget
from edge_agent.ui.camera_config_dialog import CameraConfigDialog
from edge_agent.ui.camera_feed_widget import CameraFeedWidget
from edge_agent.ui.login_dialog import LoginDialog
from edge_agent.ui.settings_dialog import SettingsDialog
from edge_agent.ui.status_bar_widget import StatusBarWidget
from edge_agent.ui.timeline_widget import TimelineWidget
from edge_agent.ui.workers.stream_worker import StreamWorker
from edge_agent.ui.workers.sync_worker import SyncWorker
from edge_agent.utils.path_resolver import get_resource_path

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Primary Edge Agent monitoring dashboard window.

    Architectural Guarantees:
    1. Dynamic 1–4 camera grid layout automatically adapting to registered feeds.
    2. Decoupled cross-thread image streaming via Qt Signals & Slots.
    3. Cooperative graceful shutdown in closeEvent() via worker.stop() and worker.wait(3000).
    4. Bilingual localization (English / Hindi) resolved via get_resource_path().
    5. Real-time biometric verification alert popup with side-by-side comparison.
    """

    MAX_CAMERAS = 4

    def __init__(
        self,
        settings: Optional[EdgeSettings] = None,
        local_db: Optional[SQLiteStore] = None,
        api_client: Optional[ApiClient] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.settings = settings or EdgeSettings.load_from_ini()
        self.local_db = local_db or SQLiteStore(db_path=self.settings.agent.db_path)
        self.api_client = api_client or ApiClient(
            base_url=self.settings.backend.url,
            api_key=self.settings.backend.api_key,
            enrollment_key=self.settings.backend.enrollment_key,
        )

        self.stream_workers: List[Optional[StreamWorker]] = [None] * self.MAX_CAMERAS
        self.camera_feed_widgets: List[CameraFeedWidget] = []
        self.sync_worker: Optional[SyncWorker] = None
        self.active_alerts: List[AlertWidget] = []
        self.i18n_strings: Dict[str, Any] = {}

        # 0. Initialize Shared Thread-Safe FAISS Vector Search Engine
        self.vector_search = VectorSearchEngine(dimension=512)
        try:
            cached = self.local_db.get_all_embeddings()
            if cached:
                self.vector_search.rebuild_index(cached)
                logger.info(f"Initialized FAISS vector index with {len(cached)} cached embeddings")
        except Exception as ve:
            logger.warning(f"Could not load initial cached embeddings: {ve}")

        # 1. Load Internationalization Resources
        self._load_i18n(self.settings.ui.language)

        # 2. Build UI Hierarchy
        self._init_ui()

        # 3. Initialize Background Workers
        self._init_workers()

        # 4. Apply Default & Persisted Camera Channels
        self._setup_cameras()

    # ═════════════════════════════════════════════════════════════════════════
    # Internationalization & Resource Resolution (Fix #23)
    # ═════════════════════════════════════════════════════════════════════════

    def _load_i18n(self, lang: str = "en") -> None:
        """Load localized translation dictionary using get_resource_path."""
        lang_code = "hi" if lang.lower().startswith("hi") else "en"
        filename = f"{lang_code}.json"
        
        candidate_paths = [
            get_resource_path(os.path.join("ui", "resources", "i18n", filename)),
            get_resource_path(os.path.join("edge_agent", "ui", "resources", "i18n", filename)),
            os.path.join(os.path.dirname(__file__), "resources", "i18n", filename),
        ]

        loaded = False
        for path in candidate_paths:
            if path and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.i18n_strings = json.load(f)
                    loaded = True
                    break
                except Exception as e:
                    logger.warning(f"Failed to read translation bundle from {path}: {e}")

        if not loaded:
            logger.warning(f"Using fallback default strings for language {lang_code}")
            self.i18n_strings = {}

    def tr_text(self, section: str, key: str, default: str = "") -> str:
        """Lookup localized string with fallback."""
        sec = self.i18n_strings.get(section, {})
        return sec.get(key, default or key)

    def set_language(self, lang: str) -> None:
        """Dynamically switch interface language."""
        self.settings.ui.language = lang
        self._load_i18n(lang)
        self.setWindowTitle(self.tr_text("app", "title", "FIND-MISSING-PEP — AI CCTV Edge Agent"))
        self._update_menu_labels()

    # ═════════════════════════════════════════════════════════════════════════
    # UI Layout Construction
    # ═════════════════════════════════════════════════════════════════════════

    def _init_ui(self) -> None:
        self.setWindowTitle(self.tr_text("app", "title", "FIND-MISSING-PEP — AI CCTV Edge Agent"))
        self.setMinimumSize(1024, 680)

        # Central Splitter (Camera Grid Left, Sighting Timeline Right)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # Left Container: Dynamic 2x2 Camera Video Grid
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(6)
        self.splitter.addWidget(self.grid_container)

        # Right Container: Chronological Sighting Feed & Activity Log
        self.timeline_widget = TimelineWidget()
        self.timeline_widget.sighting_selected.connect(self._on_timeline_sighting_selected)
        self.splitter.addWidget(self.timeline_widget)

        # Set Splitter ratio: 75% Video Grid, 25% Sighting Feed
        self.splitter.setSizes([750, 250])

        # Bottom Telemetry Status Bar
        self.status_bar_widget = StatusBarWidget()
        self.setStatusBar(QStatusBar())
        self.statusBar().addWidget(self.status_bar_widget, 1)

        # Build Menu Bar
        self._create_menu_bar()

    def _create_menu_bar(self) -> None:
        """Construct top application menu bar."""
        menubar = self.menuBar()

        # 1. File Menu
        self.file_menu = menubar.addMenu("&File")
        self.action_enroll = QAction("Device Registration...", self)
        self.action_enroll.triggered.connect(self._open_enrollment_dialog)
        self.file_menu.addAction(self.action_enroll)

        self.action_exit = QAction("Exit", self)
        self.action_exit.setShortcut(QKeySequence.Quit)
        self.action_exit.triggered.connect(self.close)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.action_exit)

        # 2. Cameras Menu
        self.cameras_menu = menubar.addMenu("&Cameras")
        self.action_config_cams = QAction("Configure Cameras...", self)
        self.action_config_cams.triggered.connect(self._open_camera_config_dialog)
        self.cameras_menu.addAction(self.action_config_cams)

        # 3. Sync Menu
        self.sync_menu = menubar.addMenu("&Sync")
        self.action_sync_now = QAction("Sync Embeddings Now", self)
        self.action_sync_now.triggered.connect(self._trigger_manual_sync)
        self.sync_menu.addAction(self.action_sync_now)

        # 4. Settings Menu
        self.settings_menu = menubar.addMenu("&Settings")
        self.action_lang_en = QAction("English", self)
        self.action_lang_en.triggered.connect(lambda: self.set_language("en"))
        self.action_lang_hi = QAction("हिन्दी (Hindi)", self)
        self.action_lang_hi.triggered.connect(lambda: self.set_language("hi"))
        
        self.lang_menu = self.settings_menu.addMenu("Language")
        self.lang_menu.addAction(self.action_lang_en)
        self.lang_menu.addAction(self.action_lang_hi)

        self.action_preferences = QAction("Preferences...", self)
        self.action_preferences.triggered.connect(self._open_settings_dialog)
        self.settings_menu.addAction(self.action_preferences)

    def _update_menu_labels(self) -> None:
        """Update top menu titles according to current i18n bundle."""
        self.file_menu.setTitle(self.tr_text("app", "menu_file", "File"))
        self.cameras_menu.setTitle(self.tr_text("app", "menu_cameras", "Cameras"))
        self.sync_menu.setTitle(self.tr_text("app", "menu_sync", "Sync"))
        self.settings_menu.setTitle(self.tr_text("app", "menu_settings", "Settings"))
        self.action_enroll.setText(self.tr_text("app", "register_device", "Device Registration..."))
        self.action_config_cams.setText(self.tr_text("app", "configure_cameras", "Configure Cameras..."))
        self.action_sync_now.setText(self.tr_text("app", "sync_now", "Sync Embeddings Now"))
        self.action_preferences.setText(self.tr_text("app", "preferences", "Preferences..."))
        self.action_exit.setText(self.tr_text("app", "menu_exit", "Exit"))

    # ═════════════════════════════════════════════════════════════════════════
    # Camera Grid Management (1 to 4 Cameras)
    # ═════════════════════════════════════════════════════════════════════════

    def _setup_cameras(self) -> None:
        """Instantiate default 4-channel camera grid, load saved feeds, and launch active workers."""
        for i in range(self.MAX_CAMERAS):
            cid = f"CAM-{i+1:02d}"
            name = f"Camera {i+1}"
            feed_widget = CameraFeedWidget(camera_index=i, camera_id=cid, camera_name=name)
            feed_widget.double_clicked.connect(self._on_camera_double_clicked)
            self.camera_feed_widgets.append(feed_widget)

        self._relayout_camera_grid()

        # Load saved camera definitions or default CAM-01 to test feed
        saved_cams = self._get_saved_camera_configs()
        self._apply_camera_configurations(saved_cams)

    def _get_saved_camera_configs(self) -> List[Dict[str, Any]]:
        """Retrieve persisted camera configs from SQLite or provide defaults."""
        raw_json = self.local_db.get_sync_state("configured_cameras")
        if raw_json:
            try:
                configs = json.loads(raw_json)
                if isinstance(configs, list) and len(configs) > 0:
                    return configs
            except Exception as e:
                logger.warning(f"Failed to parse configured_cameras JSON: {e}")

        # Default fallback: check if test_cctv_feed.mp4 exists in workspace root
        test_video_path = "test_cctv_feed.mp4"
        if os.path.isfile(test_video_path) or os.path.isfile(os.path.abspath(test_video_path)):
            default_url = test_video_path
        else:
            default_url = ""

        default_configs = [
            {
                "local_camera_id": "CAM-01",
                "name": "CCTV Monitor 1",
                "rtsp_url": default_url,
            }
        ]
        return default_configs

    def _apply_camera_configurations(self, cameras: List[Dict[str, Any]]) -> None:
        """
        Safely reconfigures and launches StreamWorkers for active camera definitions.
        Ensures thread-safe cooperative restarts and Qt signal-slot binding.
        """
        for i in range(self.MAX_CAMERAS):
            cam_def = cameras[i] if i < len(cameras) else None
            feed_widget = self.camera_feed_widgets[i]

            # 1. Cooperatively stop existing worker on this slot if running
            existing_worker = self.stream_workers[i]
            if existing_worker is not None:
                try:
                    existing_worker.stop()
                    if existing_worker.isRunning():
                        existing_worker.wait(1500)
                except Exception as e:
                    logger.warning(f"Error stopping worker {i}: {e}")

            cid = cam_def.get("local_camera_id", f"CAM-{i+1:02d}") if cam_def else f"CAM-{i+1:02d}"
            name = cam_def.get("name", f"Camera {i+1}") if cam_def else f"Camera {i+1}"
            url = str(cam_def.get("rtsp_url", "")).strip() if cam_def else ""

            feed_widget.camera_id = cid
            feed_widget.camera_name = name

            # 2. If camera is configured with a valid URL, instantiate and start worker
            if url:
                feed_widget.status_text = "Connecting..."
                feed_widget.update()

                # Build per-camera Edge AI Pipeline backed by shared FAISS vector index
                pipeline = EdgeAIPipeline(
                    camera_id=cid,
                    vector_search=self.vector_search,
                    candidate_cutoff=self.settings.ai.face_similarity_threshold,
                )

                worker = StreamWorker(
                    camera_index=i,
                    camera_id=cid,
                    rtsp_url=url,
                    pipeline=pipeline,
                    target_fps=self.settings.ai.tracking_fps,
                )

                # Connect signals (Rule 8: Cross thread boundaries strictly through Qt signals)
                worker.frame_processed.connect(feed_widget.update_frame)
                worker.fps_updated.connect(feed_widget.update_fps)
                worker.fps_updated.connect(self._on_camera_fps_updated)
                worker.status_changed.connect(feed_widget.update_status)
                worker.sighting_detected.connect(self._on_sighting_detected)

                self.stream_workers[i] = worker
                worker.start()
                logger.info(f"Started camera worker [{cid}] for source: {url}")
            else:
                feed_widget.clear_frame()
                idle_worker = StreamWorker(
                    camera_index=i,
                    camera_id=cid,
                    rtsp_url="",
                    target_fps=self.settings.ai.tracking_fps,
                )
                idle_worker.frame_processed.connect(feed_widget.update_frame)
                idle_worker.fps_updated.connect(feed_widget.update_fps)
                idle_worker.fps_updated.connect(self._on_camera_fps_updated)
                idle_worker.status_changed.connect(feed_widget.update_status)
                idle_worker.sighting_detected.connect(self._on_sighting_detected)
                self.stream_workers[i] = idle_worker

        self._relayout_camera_grid()

    def _relayout_camera_grid(self) -> None:
        """Layout active camera widgets in dynamic 2x2 grid."""
        # Clear existing items from layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        count = len(self.camera_feed_widgets)
        if count == 1:
            self.grid_layout.addWidget(self.camera_feed_widgets[0], 0, 0)
        elif count == 2:
            self.grid_layout.addWidget(self.camera_feed_widgets[0], 0, 0)
            self.grid_layout.addWidget(self.camera_feed_widgets[1], 0, 1)
        else:
            # 3 or 4 cameras: 2x2 layout
            self.grid_layout.addWidget(self.camera_feed_widgets[0], 0, 0)
            self.grid_layout.addWidget(self.camera_feed_widgets[1], 0, 1)
            if count >= 3:
                self.grid_layout.addWidget(self.camera_feed_widgets[2], 1, 0)
            if count >= 4:
                self.grid_layout.addWidget(self.camera_feed_widgets[3], 1, 1)

    def _on_camera_double_clicked(self, camera_index: int) -> None:
        """Handle double click on camera preview to maximize single feed."""
        # Toggle between single maximized feed and 2x2 grid
        is_single = (self.grid_layout.count() == 1 and 
                     self.grid_layout.itemAt(0).widget() == self.camera_feed_widgets[camera_index])
        
        if is_single:
            self._relayout_camera_grid()
        else:
            while self.grid_layout.count():
                item = self.grid_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            self.grid_layout.addWidget(self.camera_feed_widgets[camera_index], 0, 0)

    # ═════════════════════════════════════════════════════════════════════════
    # Background Workers & Sighting Handling
    # ═════════════════════════════════════════════════════════════════════════

    def _init_workers(self) -> None:
        """Initialize background synchronization worker thread."""
        try:
            syncer = EmbeddingSyncer(
                api_client=self.api_client,
                local_db=self.local_db,
                faiss_store=self.vector_search,
                sync_interval_seconds=self.settings.agent.sync_interval_seconds,
            )
            uploader = SightingUploader(
                api_client=self.api_client,
                local_db=self.local_db,
            )
            self.sync_worker = SyncWorker(
                syncer=syncer,
                uploader=uploader,
                local_db=self.local_db,
                sync_interval_seconds=self.settings.agent.sync_interval_seconds,
            )

            # Wire sync worker signals
            self.sync_worker.stats_updated.connect(self.status_bar_widget.update_stats)
            self.sync_worker.sync_started.connect(lambda: self.status_bar_widget.set_last_sync("Syncing..."))
            self.sync_worker.sync_finished.connect(self._on_sync_finished)
            self.sync_worker.sync_failed.connect(self._on_sync_failed)

            # Start background sync worker
            self.sync_worker.start()
        except Exception as e:
            logger.error(f"Failed to initialize background SyncWorker: {e}")

    def _on_sync_finished(self, summary: Dict[str, Any]) -> None:
        """Slot receiving sync completion event."""
        now_str = time.strftime("%H:%M:%S")
        self.status_bar_widget.set_last_sync(now_str)
        self.status_bar_widget.set_backend_online(True)
        logger.info(f"Sync complete: {summary}")

    def _on_sync_failed(self, error_msg: str) -> None:
        """Slot receiving sync failure event."""
        self.status_bar_widget.set_backend_online(False)
        logger.warning(f"Sync failed: {error_msg}")

    def _on_camera_fps_updated(self, camera_index: int, fps: float) -> None:
        """Slot updating aggregate FPS in status bar."""
        # Calculate mean across active feeds
        valid_fps = [w.fps for w in self.camera_feed_widgets if w.is_connected and w.fps > 0]
        mean_fps = (sum(valid_fps) / len(valid_fps)) if valid_fps else fps
        self.status_bar_widget.set_fps(mean_fps)

    @Slot(dict)
    def _on_sighting_detected(self, sighting: Dict[str, Any]) -> None:
        """
        Slot triggered when a confirmed biometric match is verified (Rule 8).
        Directly confirmed by agent: automatically marks CONFIRMED, enqueues to SQLite
        offline queue, logs to timeline, and triggers immediate background upload to central backend.
        """
        person_id = sighting.get("person_id", "UNKNOWN")
        logger.info(f"Biometric match directly confirmed by agent for person: {person_id}")

        # 1. Ensure status is CONFIRMED
        sighting["status"] = "CONFIRMED"

        # 2. Enqueue sighting into local SQLite store for durable offline upload
        if self.local_db is not None:
            try:
                raw_ts = sighting.get("timestamp", time.time())
                detected_at_str = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(raw_ts),
                )
                self.local_db.enqueue_sighting(
                    person_id=str(person_id),
                    camera_id=str(sighting.get("camera_id", "CAM-01")),
                    similarity_score=float(sighting.get("similarity", 0.0)),
                    detected_at=detected_at_str,
                    face_crop_path=str(sighting.get("face_crop_path", "")),
                    full_frame_path=str(sighting.get("full_frame_path", "")),
                    video_clip_path=sighting.get("video_clip_path"),
                    confidence_level=str(sighting.get("confidence_level", "CONFIRMED")),
                    num_frames_matched=int(sighting.get("frames_matched", 3)),
                    camera_location=sighting.get("camera_location"),
                )
            except Exception as e:
                logger.error(f"Failed to enqueue auto-confirmed sighting into local SQLite: {e}")

        # 3. Add to Chronological Timeline Feed (Displays as CONFIRMED)
        self.timeline_widget.add_sighting(sighting)

        # 4. Increment status bar faces counter
        self.status_bar_widget.increment_faces(1)

        # 5. Trigger immediate background flush to central backend
        if self.sync_worker is not None:
            self.sync_worker.trigger_sync()

    def _on_alert_confirmed(self, payload: Dict[str, Any]) -> None:
        """Operator confirmed sighting match (legacy slot maintained for compatibility)."""
        person_id = payload.get("person_id", "")
        self.timeline_widget.update_sighting_status(person_id, "CONFIRMED")
        # Trigger immediate background flush to central backend
        if self.sync_worker is not None:
            self.sync_worker.trigger_sync()

    def _on_alert_rejected(self, payload: Dict[str, Any]) -> None:
        """Operator rejected sighting match (legacy slot maintained for compatibility)."""
        person_id = payload.get("person_id", "")
        self.timeline_widget.update_sighting_status(person_id, "REJECTED")

    def _on_timeline_sighting_selected(self, sighting: Dict[str, Any]) -> None:
        """Open read-only evidence inspector when operator double clicks an entry in timeline."""
        dlg = AlertWidget(sighting_data=sighting, show_actions=False, parent=self)
        dlg.exec()

    # ═════════════════════════════════════════════════════════════════════════
    # Dialog Actions
    # ═════════════════════════════════════════════════════════════════════════

    def _open_enrollment_dialog(self) -> None:
        dlg = LoginDialog(settings=self.settings, api_client=self.api_client, parent=self)
        dlg.exec()

    def _open_camera_config_dialog(self) -> None:
        existing = []
        for i, w in enumerate(self.camera_feed_widgets):
            worker = self.stream_workers[i] if i < len(self.stream_workers) else None
            url = getattr(worker, "rtsp_url", "") if worker else ""
            existing.append({
                "local_camera_id": w.camera_id,
                "name": w.camera_name,
                "rtsp_url": url,
            })

        dlg = CameraConfigDialog(existing_cameras=existing, parent=self)
        dlg.cameras_updated.connect(self._on_cameras_reconfigured)
        dlg.exec()

    def _on_cameras_reconfigured(self, cameras: List[Dict[str, Any]]) -> None:
        """Reconfigure stream workers with updated camera definitions and persist to SQLite."""
        try:
            self.local_db.set_sync_state("configured_cameras", json.dumps(cameras))
        except Exception as e:
            logger.warning(f"Failed to persist camera configs to SQLite: {e}")

        self._apply_camera_configurations(cameras)

    def _open_settings_dialog(self) -> None:
        dlg = SettingsDialog(settings=self.settings, parent=self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self, new_settings: EdgeSettings) -> None:
        self.settings = new_settings
        self.set_language(new_settings.ui.language)

    def _trigger_manual_sync(self) -> None:
        if self.sync_worker is not None:
            self.sync_worker.trigger_sync()

    # ═════════════════════════════════════════════════════════════════════════
    # Graceful Cooperative Shutdown (Fix #18 / Fix #26 — CRITICAL REQUIREMENT)
    # ═════════════════════════════════════════════════════════════════════════

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Graceful application termination:
        Cooperatively stop and wait on all background QThreads without forcible termination.
        Prevents C++ segmentation faults, database locks, and corrupt video files.
        """
        logger.info("[MainWindow] Initiating cooperative application shutdown...")

        # 1. Signal and wait for all camera StreamWorker threads
        for worker in self.stream_workers:
            if worker is not None:
                try:
                    worker.stop()
                    if worker.isRunning():
                        worker.wait(3000)
                except Exception as e:
                    logger.warning(f"Error stopping stream worker: {e}")

        # 2. Signal and wait for background SyncWorker thread
        if self.sync_worker is not None:
            try:
                self.sync_worker.stop()
                if self.sync_worker.isRunning():
                    self.sync_worker.wait(3000)
            except Exception as e:
                logger.warning(f"Error stopping sync worker: {e}")

        # 3. Close open child dialogs
        for alert in self.active_alerts:
            try:
                alert.close()
            except Exception:
                pass

        logger.info("[MainWindow] All worker threads cleanly terminated. Accepting close event.")
        event.accept()

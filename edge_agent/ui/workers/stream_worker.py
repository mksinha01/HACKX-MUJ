"""Camera stream ingestion and Edge AI pipeline execution worker running in a dedicated QThread."""
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import QThread, Signal

from edge_agent.ai.pipeline import EdgeAIPipeline, MatchEvent, Evidence
from edge_agent.camera.rtsp_reader import RTSPReader, StreamStatus

logger = logging.getLogger(__name__)


class StreamWorker(QThread):
    """
    Background QThread executing video decoding and AI pipeline processing for a camera.

    Architectural Concurrency Guarantees:
    1. Cross-Thread Signal Delivery: Never touches UI widgets directly; emits
       `frame_processed = Signal(int, np.ndarray, list)` to update GUI viewports safely.
    2. Cooperative Teardown: Listens to `self._stop_event`. UI `closeEvent` calls `stop()`
       followed by `wait(3000)`. Never forcibly terminates threads.
    3. Biometric Alert Dispatch: Emits `sighting_detected = Signal(dict)` whenever
       temporal verification criteria (N=3, >=0.60 within 5s) are confirmed.
    """

    # Signals strictly crossing thread boundaries (Rule 8)
    frame_processed = Signal(int, np.ndarray, list)  # camera_index, frame, detections/tracks
    sighting_detected = Signal(dict)                 # sighting alert payload
    fps_updated = Signal(int, float)                 # camera_index, fps
    status_changed = Signal(int, str)                # camera_index, status text
    error_occurred = Signal(int, str)                # camera_index, error text

    def __init__(
        self,
        camera_index: int = 0,
        camera_id: str = "CAM-01",
        rtsp_url: Optional[str] = None,
        reader: Optional[RTSPReader] = None,
        pipeline: Optional[EdgeAIPipeline] = None,
        target_fps: int = 15,
        local_db: Optional[Any] = None,
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.camera_index = camera_index
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.reader = reader
        self.pipeline = pipeline
        self.target_fps = target_fps
        self.local_db = local_db

        self._stop_event = threading.Event()
        self._fps_counter = 0
        self._fps_timer = time.time()
        self._current_fps = 0.0

        # Wire pipeline match callback if pipeline exists
        if self.pipeline is not None:
            self.pipeline.on_match_callback = self._on_pipeline_match

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    def stop(self) -> None:
        """Cooperative thread shutdown request (Fix #18 / Fix #26)."""
        logger.info(f"[StreamWorker {self.camera_id}] Stop signal received")
        self._stop_event.set()
        if self.pipeline is not None and hasattr(self.pipeline, "stop"):
            self.pipeline.stop()
        if self.reader is not None and hasattr(self.reader, "stop"):
            self.reader.stop()

    def _on_pipeline_match(self, match_event: MatchEvent, evidence: Evidence) -> None:
        """Callback from EdgeAIPipeline upon match confirmation."""
        person_id = getattr(match_event, "person_id", "UNKNOWN")
        person_name = getattr(evidence, "metadata", {}).get("person_name", person_id)
        photo_url = None
        registered_photo_path = None
        meta = {}

        if self.local_db is not None and person_id != "UNKNOWN":
            try:
                details = self.local_db.get_person_details(str(person_id))
                if details:
                    person_name = details.get("person_name") or person_name
                    photo_url = details.get("photo_url")
                    registered_photo_path = details.get("local_photo_path")
                    meta = details.get("metadata") or {}
            except Exception as e:
                logger.debug(f"Failed to lookup person details for {person_id}: {e}")

        sighting_payload = {
            "camera_index": self.camera_index,
            "camera_id": self.camera_id,
            "person_id": person_id,
            "person_name": person_name,
            "photo_url": photo_url,
            "registered_photo_path": registered_photo_path,
            "similarity": float(getattr(match_event, "score", 0.0)),
            "timestamp": getattr(match_event, "timestamp", time.time()),
            "face_crop_path": getattr(evidence, "crop_path", ""),
            "full_frame_path": getattr(evidence, "frame_path", ""),
            "video_clip_path": getattr(evidence, "clip_path", None),
            "confidence_level": "CONFIRMED" if match_event.score >= 0.60 else "POSSIBLE",
            "status": "CONFIRMED",
            "scores": getattr(match_event, "scores", [match_event.score]),
            "frames_matched": getattr(match_event, "frames", 3),
            "metadata": meta,
            "age": meta.get("age"),
            "gender": meta.get("gender"),
            "description": meta.get("description"),
            "last_seen_location": meta.get("last_seen_location"),
            "last_seen_time": meta.get("last_seen_time"),
            "contact_info": meta.get("contact_info"),
            "reporter_name": meta.get("reporter_name"),
            "reporter_email": meta.get("reporter_email"),
            "reporter_phone": meta.get("reporter_phone"),
        }
        logger.warning(
            f"[StreamWorker {self.camera_id}] SIGHTING CONFIRMED: "
            f"{sighting_payload['person_name']} / {sighting_payload['person_id']} ({sighting_payload['similarity']*100:.1f}%)"
        )
        self.sighting_detected.emit(sighting_payload)

    def run(self) -> None:
        """Main camera decoding and AI processing loop."""
        logger.info(f"[StreamWorker {self.camera_id}] Thread started with source: {self.rtsp_url}")
        self.status_changed.emit(self.camera_index, "Connecting")

        if not self.rtsp_url:
            self.status_changed.emit(self.camera_index, "No Source")
            logger.info(f"[StreamWorker {self.camera_id}] No source URL configured; idling.")
            while not self._stop_event.is_set():
                time.sleep(0.5)
            return

        # Initialize reader if URL provided and no reader injected
        if self.reader is None and self.rtsp_url:
            try:
                self.reader = RTSPReader(
                    camera_id=self.camera_id,
                    rtsp_url=self.rtsp_url,
                    buffer_size=150,
                )
                self.reader.start()
            except Exception as e:
                logger.error(f"[StreamWorker {self.camera_id}] Failed to init RTSPReader: {e}")
                self.error_occurred.emit(self.camera_index, str(e))
                self.status_changed.emit(self.camera_index, "Error")
                return

        frame_interval = 1.0 / max(1, self.target_fps)
        self.status_changed.emit(self.camera_index, "Connected")

        while not self._stop_event.is_set():
            loop_start = time.time()
            frame = None
            timestamp = loop_start

            # 1. Fetch frame from RTSP reader
            if self.reader is not None:
                res = self.reader.get_latest_frame()
                if res is not None:
                    timestamp, frame = res

            # 2. Process frame with AI Pipeline or fallback
            if frame is not None and frame.size > 0:
                tracks_or_detections: List[Any] = []
                if self.pipeline is not None:
                    try:
                        matches = self.pipeline.process_frame(frame, timestamp)
                        if hasattr(self.pipeline, "tracker") and hasattr(self.pipeline.tracker, "tracks"):
                            tracks_or_detections = self.pipeline.tracker.tracks
                    except Exception as pe:
                        logger.error(f"[StreamWorker {self.camera_id}] Pipeline error: {pe}", exc_info=True)

                # Emit processed frame with track overlays to GUI (Signal crosses thread safely)
                self.frame_processed.emit(self.camera_index, frame, tracks_or_detections)

                # Update FPS statistics
                self._fps_counter += 1
                now = time.time()
                elapsed = now - self._fps_timer
                if elapsed >= 1.0:
                    self._current_fps = self._fps_counter / elapsed
                    self.fps_updated.emit(self.camera_index, self._current_fps)
                    self._fps_counter = 0
                    self._fps_timer = now

            # Throttle to target FPS
            elapsed_time = time.time() - loop_start
            sleep_time = frame_interval - elapsed_time
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                time.sleep(0.005)

        logger.info(f"[StreamWorker {self.camera_id}] Thread exiting cleanly")
        if self.reader is not None:
            self.reader.stop()
        self.status_changed.emit(self.camera_index, "Offline")

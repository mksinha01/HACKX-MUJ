"""Biometric sighting alert popup with side-by-side photo comparison and Confirm/Reject operator actions."""
import logging
import os
import time
from typing import Any, Dict, Optional

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class AlertWidget(QDialog):
    """
    Operator alert popup triggered upon confirmed biometric temporal verification:
    1. Side-by-side comparison: Registered Missing Person reference photo vs. Live CCTV face crop.
    2. Telemetry metadata: Person ID/Name, similarity score gauge, camera identifier, and timestamp.
    3. Action buttons: 'Confirm Sighting' (marks confirmed, triggers upload) & 'Reject / Dismiss'.
    """

    confirmed = Signal(dict)  # sighting payload + review notes
    rejected = Signal(dict)   # sighting payload + review notes

    def __init__(
        self,
        sighting_data: Dict[str, Any],
        show_actions: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.sighting_data = sighting_data or {}
        self.show_actions = show_actions
        self.setWindowTitle("🚨 Biometric Alert — Match Verified by Agent")
        self.setMinimumSize(560, 520)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #141417;
                border: 1px solid #3f3f46;
                border-radius: 8px;
            }
        """)

        self._init_ui()
        self._load_photos()

        # Emit audible alert chime
        try:
            QApplication.beep()
        except Exception:
            pass

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # 1. Alert Banner
        if self.show_actions:
            banner_text = "🚨 POSSIBLE MATCH DETECTED — OPERATOR REVIEW REQUIRED"
            banner_bg = "#7f1d1d"
            banner_border = "#ef4444"
        else:
            banner_text = "🚨 SIGHTING CONFIRMED — AUTO-VERIFIED BY EDGE AGENT"
            banner_bg = "#065f46"
            banner_border = "#10b981"

        self.banner = QLabel(banner_text)
        self.banner.setObjectName("alertBanner")
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setStyleSheet(f"""
            background-color: {banner_bg};
            color: #ffffff;
            font-size: 13px;
            font-weight: 700;
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid {banner_border};
            letter-spacing: 0.5px;
        """)
        main_layout.addWidget(self.banner)

        # 2. Side-by-Side Comparison Container (CRITICAL REQUIREMENT)
        comp_group = QGroupBox("Biometric Evidence Comparison")
        comp_group.setStyleSheet("""
            QGroupBox {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                font-weight: 600;
                color: #e4e4e7;
            }
        """)
        comp_layout = QHBoxLayout(comp_group)
        comp_layout.setContentsMargins(12, 12, 12, 12)
        comp_layout.setSpacing(16)

        # Left Column: Registered Reference Photo
        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        left_title = QLabel("Registered Photo")
        left_title.setAlignment(Qt.AlignCenter)
        left_title.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px;")
        left_col.addWidget(left_title)

        self.registered_photo_label = QLabel()
        self.registered_photo_label.setObjectName("photoLabel")
        self.registered_photo_label.setFixedSize(180, 180)
        self.registered_photo_label.setAlignment(Qt.AlignCenter)
        self.registered_photo_label.setStyleSheet("background-color: #09090b; border: 1px solid #3f3f46; border-radius: 6px;")
        left_col.addWidget(self.registered_photo_label)
        comp_layout.addLayout(left_col)

        # Center Divider
        center_div = QLabel("VS")
        center_div.setAlignment(Qt.AlignCenter)
        center_div.setStyleSheet("color: #71717a; font-weight: 800; font-size: 14px;")
        comp_layout.addWidget(center_div)

        # Right Column: Live CCTV Detection Crop
        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        right_title = QLabel("Live CCTV Detection")
        right_title.setAlignment(Qt.AlignCenter)
        right_title.setStyleSheet("color: #f59e0b; font-weight: 600; font-size: 12px;")
        right_col.addWidget(right_title)

        self.live_crop_label = QLabel()
        self.live_crop_label.setObjectName("photoLabel")
        self.live_crop_label.setFixedSize(180, 180)
        self.live_crop_label.setAlignment(Qt.AlignCenter)
        self.live_crop_label.setStyleSheet("background-color: #09090b; border: 1px solid #3f3f46; border-radius: 6px;")
        right_col.addWidget(self.live_crop_label)
        comp_layout.addLayout(right_col)

        main_layout.addWidget(comp_group)

        # 3. Telemetry Metadata Pane
        meta_group = QGroupBox("Match Telemetry")
        meta_group.setStyleSheet("""
            QGroupBox {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding-top: 14px;
                font-weight: 600;
                color: #e4e4e7;
            }
        """)
        meta_layout = QVBoxLayout(meta_group)
        meta_layout.setContentsMargins(12, 10, 12, 10)
        meta_layout.setSpacing(8)

        person_id = self.sighting_data.get("person_id", "Unknown")
        person_name = self.sighting_data.get("person_name", person_id)
        camera_id = self.sighting_data.get("camera_id", "CAM-01")
        timestamp_str = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(self.sighting_data.get("timestamp", time.time())),
        )
        sim_score = float(self.sighting_data.get("similarity", 0.0))
        sim_pct = sim_score * 100

        # Person & Camera details grid
        details_layout = QHBoxLayout()
        details_left = QLabel(f"<b>Person:</b> {person_name} (<code>{person_id}</code>)")
        details_left.setStyleSheet("color: #f4f4f5; font-size: 13px;")
        details_right = QLabel(f"<b>Camera:</b> {camera_id} &nbsp;|&nbsp; <b>Time:</b> {timestamp_str}")
        details_right.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        details_layout.addWidget(details_left)
        details_layout.addStretch()
        details_layout.addWidget(details_right)
        meta_layout.addLayout(details_layout)

        # Similarity Score Progress Bar
        sim_layout = QHBoxLayout()
        sim_text = QLabel(f"<b>Confidence:</b> {sim_pct:.1f}% Match")
        sim_text.setStyleSheet("color: #10b981; font-weight: 700; font-size: 13px;")
        sim_layout.addWidget(sim_text)

        self.sim_progress = QProgressBar()
        self.sim_progress.setRange(0, 100)
        self.sim_progress.setValue(int(min(100, max(0, sim_pct))))
        self.sim_progress.setTextVisible(True)
        self.sim_progress.setFormat(f"{sim_pct:.1f}%")
        self.sim_progress.setFixedHeight(18)
        bar_color = "#10b981" if sim_pct >= 70 else "#f59e0b"
        self.sim_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 5px;
                text-align: center;
                color: #ffffff;
                font-weight: 600;
            }}
            QProgressBar::chunk {{
                background-color: {bar_color};
                border-radius: 4px;
            }}
        """)
        sim_layout.addWidget(self.sim_progress)
        meta_layout.addLayout(sim_layout)

        main_layout.addWidget(meta_group)

        # 4. Operator Review Notes Field (Hidden if show_actions is False)
        self.notes_label = QLabel("Operator Review Notes (Optional):")
        self.notes_label.setStyleSheet("color: #a1a1aa; font-size: 12px; font-weight: 500;")
        main_layout.addWidget(self.notes_label)

        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Enter confirmation details, visible attire, or verification notes...")
        main_layout.addWidget(self.notes_input)

        if not self.show_actions:
            self.notes_label.setVisible(False)
            self.notes_input.setVisible(False)

        # 5. Action Buttons (Confirm & Reject for review mode, Close for inspector mode)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(14)

        self.reject_btn = QPushButton("✕ Reject / Dismiss")
        self.reject_btn.setObjectName("rejectButton")
        self.reject_btn.setProperty("action", "reject")
        self.reject_btn.setMinimumHeight(40)
        self.reject_btn.clicked.connect(self._on_reject)
        btn_layout.addWidget(self.reject_btn)

        self.confirm_btn = QPushButton("✓ Confirm Sighting")
        self.confirm_btn.setObjectName("confirmButton")
        self.confirm_btn.setProperty("action", "confirm")
        self.confirm_btn.setMinimumHeight(40)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self.confirm_btn)

        self.close_btn = QPushButton("Close Evidence Inspector")
        self.close_btn.setObjectName("closeButton")
        self.close_btn.setMinimumHeight(40)
        self.close_btn.setStyleSheet("""
            QPushButton#closeButton {
                background-color: #27272a;
                color: #f4f4f5;
                font-weight: 600;
                font-size: 13px;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 20px;
            }
            QPushButton#closeButton:hover {
                background-color: #3f3f46;
                border-color: #52525b;
            }
        """)
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        if not self.show_actions:
            self.reject_btn.setVisible(False)
            self.confirm_btn.setVisible(False)
            self.close_btn.setVisible(True)
        else:
            self.close_btn.setVisible(False)

        main_layout.addLayout(btn_layout)

    def _load_photos(self) -> None:
        """Load and display registered reference photo and live face crop."""
        # 1. Load Live CCTV Detection Crop
        crop_path = self.sighting_data.get("face_crop_path")
        if crop_path and os.path.isfile(crop_path):
            pixmap = QPixmap(crop_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(176, 176, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.live_crop_label.setPixmap(scaled)
            else:
                self.live_crop_label.setText("Corrupt Crop")
        else:
            self.live_crop_label.setText("Crop Not Found")
            self.live_crop_label.setStyleSheet("color: #71717a; font-size: 11px;")

        # 2. Load Registered Reference Photo
        reg_photo = self.sighting_data.get("registered_photo_path")
        if not reg_photo:
            # Check photo_url or local cached photo
            reg_photo = self.sighting_data.get("photo_url")

        if reg_photo and os.path.isfile(reg_photo):
            pixmap = QPixmap(reg_photo)
            if not pixmap.isNull():
                scaled = pixmap.scaled(176, 176, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.registered_photo_label.setPixmap(scaled)
            else:
                self.registered_photo_label.setText("Corrupt Photo")
        else:
            # Fallback: display placeholder avatar or person ID
            self.registered_photo_label.setText(f"Reference Photo\n({self.sighting_data.get('person_id', '')})")
            self.registered_photo_label.setStyleSheet("color: #71717a; font-size: 11px;")

    def _on_confirm(self) -> None:
        """Handler for 'Confirm Sighting' button."""
        notes = self.notes_input.text().strip()
        payload = dict(self.sighting_data)
        payload["status"] = "CONFIRMED"
        payload["review_notes"] = notes
        payload["reviewed_at"] = time.time()
        logger.info(f"[AlertWidget] Confirmed sighting for {payload.get('person_id')}")
        self.confirmed.emit(payload)
        self.accept()

    def _on_reject(self) -> None:
        """Handler for 'Reject / Dismiss' button."""
        notes = self.notes_input.text().strip()
        payload = dict(self.sighting_data)
        payload["status"] = "REJECTED"
        payload["review_notes"] = notes
        payload["reviewed_at"] = time.time()
        logger.info(f"[AlertWidget] Rejected sighting for {payload.get('person_id')}")
        self.rejected.emit(payload)
        self.reject()

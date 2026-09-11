"""Chronological sighting history timeline and operator audit feed widget."""
import logging
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class TimelineWidget(QWidget):
    """
    Displays recent biometric sighting events in reverse-chronological order:
    - Detection Timestamp
    - Missing Person ID & Name
    - Camera Identifier
    - Cosine Similarity Score (%)
    - Review Status (PENDING, CONFIRMED, REJECTED)
    """

    sighting_selected = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._sightings: List[Dict[str, Any]] = []
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header bar with title and clear button
        header_layout = QHBoxLayout()
        title_label = QLabel("📋 Sighting Alerts & Timeline")
        title_label.setStyleSheet("color: #f4f4f5; font-size: 14px; font-weight: 700;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setFixedHeight(26)
        self.clear_btn.setStyleSheet("font-size: 11px; padding: 2px 10px;")
        self.clear_btn.clicked.connect(self.clear_timeline)
        header_layout.addWidget(self.clear_btn)

        layout.addLayout(header_layout)

        # Table widget for sightings
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Time", "Person", "Camera", "Score", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table)

    def add_sighting(self, sighting: Dict[str, Any]) -> None:
        """Add a new sighting entry at the top of the timeline."""
        self._sightings.insert(0, sighting)
        self.table.insertRow(0)

        timestamp = sighting.get("timestamp", time.time())
        time_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
        person_id = sighting.get("person_id", "Unknown")
        person_name = sighting.get("person_name", person_id)
        camera_id = sighting.get("camera_id", "CAM-01")
        sim = float(sighting.get("similarity", 0.0)) * 100
        status = sighting.get("status", "CONFIRMED").upper()

        # Item 0: Time
        item_time = QTableWidgetItem(time_str)
        item_time.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 0, item_time)

        # Item 1: Person
        person_display = f"{person_name} ({person_id})" if person_name != person_id else person_id
        item_person = QTableWidgetItem(person_display)
        self.table.setItem(0, 1, item_person)

        # Item 2: Camera
        item_cam = QTableWidgetItem(camera_id)
        item_cam.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 2, item_cam)

        # Item 3: Similarity Score
        item_score = QTableWidgetItem(f"{sim:.1f}%")
        item_score.setTextAlignment(Qt.AlignCenter)
        if sim >= 70:
            item_score.setForeground(QColor("#10b981"))
        else:
            item_score.setForeground(QColor("#f59e0b"))
        self.table.setItem(0, 3, item_score)

        # Item 4: Status
        item_status = QTableWidgetItem(status)
        item_status.setTextAlignment(Qt.AlignCenter)
        if status == "CONFIRMED":
            item_status.setForeground(QColor("#10b981"))
        elif status == "REJECTED":
            item_status.setForeground(QColor("#ef4444"))
        else:
            item_status.setForeground(QColor("#f59e0b"))
        self.table.setItem(0, 4, item_status)

        # Limit to 100 rows max
        if self.table.rowCount() > 100:
            self.table.removeRow(100)
            self._sightings.pop()

    def update_sighting_status(self, person_id: str, new_status: str) -> None:
        """Update the status label of existing sighting matching person_id."""
        for row in range(self.table.rowCount()):
            person_item = self.table.item(row, 1)
            if person_item and person_id in person_item.text():
                status_item = self.table.item(row, 4)
                if status_item:
                    status_item.setText(new_status)
                    if new_status == "CONFIRMED":
                        status_item.setForeground(QColor("#10b981"))
                    elif new_status == "REJECTED":
                        status_item.setForeground(QColor("#ef4444"))
                    break

    def clear_timeline(self) -> None:
        """Clear all entries."""
        self._sightings.clear()
        self.table.setRowCount(0)

    def _on_row_double_clicked(self, row: int, column: int) -> None:
        """Emit selected sighting for review on double click."""
        if 0 <= row < len(self._sightings):
            sighting = self._sightings[row]
            self.sighting_selected.emit(sighting)

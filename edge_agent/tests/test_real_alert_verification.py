"""Test real user data enrichment, photo resolution, and AlertWidget rendering."""
import os
import sys
import pytest
from PySide6.QtWidgets import QApplication

from edge_agent.storage.local_db import SQLiteStore
from edge_agent.ui.alert_widget import AlertWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_real_person_details_in_local_db():
    db = SQLiteStore(db_path="local_data.db")
    # Test with hyphenated UUID
    person_id = "fd12bd71-9df3-4621-b9c6-8696eea0f282"
    details = db.get_person_details(person_id)
    assert details is not None, f"Person {person_id} should be cached"
    assert details["person_name"] == "manoj"
    assert details["local_photo_path"] is not None
    assert os.path.isfile(details["local_photo_path"]), f"Photo file should exist on disk: {details['local_photo_path']}"
    
    # Check reporter info
    meta = details.get("metadata", {})
    assert meta.get("reporter_name") == "Mk Sinha"
    assert meta.get("reporter_email") == "mksinha77756@gmail.com"
    assert "bhilai" in meta.get("last_seen_location", "").lower()

    # Test with non-hyphenated UUID
    details_hex = db.get_person_details(person_id.replace("-", ""))
    assert details_hex is not None
    assert details_hex["person_name"] == "manoj"


def test_alert_widget_renders_real_user_evidence(qapp):
    db = SQLiteStore(db_path="local_data.db")
    person_id = "fd12bd71-9df3-4621-b9c6-8696eea0f282"
    details = db.get_person_details(person_id)
    assert details is not None

    meta = details["metadata"]
    sighting = {
        "camera_id": "CAM-02",
        "person_id": person_id,
        "person_name": details["person_name"],
        "photo_url": details["photo_url"],
        "registered_photo_path": details["local_photo_path"],
        "face_crop_path": details["local_photo_path"],  # test image crop
        "similarity": 0.961,
        "status": "CONFIRMED",
        "reporter_name": meta.get("reporter_name"),
        "reporter_email": meta.get("reporter_email"),
        "contact_info": meta.get("contact_info"),
        "last_seen_location": meta.get("last_seen_location"),
        "description": meta.get("description"),
        "age": meta.get("age"),
        "gender": meta.get("gender"),
    }

    dialog = AlertWidget(sighting_data=sighting, show_actions=False)
    
    # Verify registered photo was loaded onto the label (not null pixmap)
    reg_pix = dialog.registered_photo_label.pixmap()
    assert reg_pix is not None and not reg_pix.isNull(), "Registered photo should be loaded and displayed"

    # Verify live crop was loaded
    crop_pix = dialog.live_crop_label.pixmap()
    assert crop_pix is not None and not crop_pix.isNull(), "Live crop photo should be loaded and displayed"

    # Verify text elements inside dialog
    banner_text = dialog.banner.text()
    assert "SIGHTING CONFIRMED" in banner_text

    # Close dialog cleanly
    dialog.close()

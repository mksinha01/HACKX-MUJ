"""Face processing service using InsightFace Buffalo_L model."""
import logging
import threading
from typing import Optional, Tuple
import cv2
import numpy as np

try:
    from insightface.app import FaceAnalysis
    from insightface.utils import face_align
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    FaceAnalysis = None  # type: ignore
    face_align = None  # type: ignore
    INSIGHTFACE_AVAILABLE = False

from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)

# Cached singleton instance and initialization lock
_face_app: Optional[FaceAnalysis] = None
_init_lock = threading.Lock()


def _resolve_insightface_root() -> str:
    """
    Finds the directory containing the 'models/buffalo_l' model directory.
    InsightFace FaceAnalysis looks for: <root>/models/buffalo_l/
    """
    backend_dir = Path(__file__).resolve().parent.parent.parent
    project_root = backend_dir.parent

    candidates = [
        Path(settings.AI_MODEL_DIR),
        project_root / "ai_models",
        project_root / "backend" / "ai_models",
        backend_dir / "ai_models",
        project_root,
        Path.home() / ".insightface",
    ]

    for candidate in candidates:
        if candidate is None:
            continue
        c_path = Path(candidate).resolve()
        # InsightFace expects root such that root/models/buffalo_l exists
        if (c_path / "models" / "buffalo_l").exists() and any((c_path / "models" / "buffalo_l").glob("*.onnx")):
            return str(c_path)
        # If candidate itself is .insightface
        if c_path.name == ".insightface" and (c_path / "models" / "buffalo_l").exists():
            return str(c_path)

    # Fallback to configured settings path
    return str(Path(settings.AI_MODEL_DIR).resolve())


def get_face_app() -> FaceAnalysis:
    """
    Returns the singleton InsightFace FaceAnalysis instance configured with buffalo_l.
    Initializes lazily and thread-safely without triggering redundant remote downloads.
    """
    global _face_app
    if not INSIGHTFACE_AVAILABLE:
        raise RuntimeError("InsightFace is not installed in the current Python environment.")

    if _face_app is None:
        with _init_lock:
            if _face_app is None:
                model_root = _resolve_insightface_root()
                logger.info(f"Initializing InsightFace buffalo_l from root '{model_root}'...")
                app = FaceAnalysis(
                    name="buffalo_l",
                    root=model_root,
                    providers=["CPUExecutionProvider"],
                )
                app.prepare(ctx_id=-1, det_size=(640, 640))
                _face_app = app
                logger.info("InsightFace buffalo_l successfully initialized and ready.")

    return _face_app


def warmup_face_models() -> None:
    """Preloads InsightFace buffalo_l models during server startup."""
    try:
        get_face_app()
    except Exception as e:
        logger.warning(f"Face models warmup skipped or failed: {e}")



def process_person_photo(image_bytes: bytes) -> Tuple[bytes, np.ndarray, float]:
    """
    Processes an uploaded person photo for face enrollment:
    1. Decodes image bytes via OpenCV.
    2. Detects faces via SCRFD (from buffalo_l).
    3. Selects the primary face by maximum bounding box area.
    4. Validates detection quality (det_score >= 0.60, size >= 60x60).
    5. Performs landmark-based affine alignment to standard 112x112 dimensions.
    6. Extracts and L2-normalizes the 512-D ArcFace embedding vector.

    Returns:
        (cropped_face_jpg_bytes, normed_emb, det_score)
    Raises:
        ValueError: If the image cannot be decoded, no face is found, or quality constraints fail.
    """
    if not image_bytes:
        raise ValueError("Image bytes cannot be empty.")

    # 1. Decode image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image format or corrupted image file.")

    # 2. Detect faces
    app = get_face_app()
    faces = app.get(img)

    if not faces:
        raise ValueError("No face detected in the provided image.")

    # 3. Pick largest face by bounding box area (x2 - x1) * (y2 - y1)
    def face_area(face) -> float:
        box = face.bbox
        return float((box[2] - box[0]) * (box[3] - box[1]))

    largest_face = max(faces, key=face_area)

    # 4. Quality validation
    det_score = float(largest_face.det_score)
    if det_score < 0.60:
        raise ValueError(
            f"Face detection confidence too low: {det_score:.2f} (minimum threshold 0.60 required)."
        )

    box = largest_face.bbox
    width = box[2] - box[0]
    height = box[3] - box[1]
    if width < 60 or height < 60:
        raise ValueError(
            f"Face size too small: {int(width)}x{int(height)} pixels (minimum 60x60 required)."
        )

    # 5. Affine alignment to standard 112x112 thumbnail
    if face_align is None:
        raise RuntimeError("InsightFace face_align module is unavailable.")
    cropped_img = face_align.norm_crop(img, landmark=largest_face.kps, image_size=112)

    # Encode cropped face to JPEG
    success, encoded_img = cv2.imencode(".jpg", cropped_img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not success:
        raise ValueError("Failed to encode aligned face crop to JPEG format.")
    cropped_face_bytes = encoded_img.tobytes()

    # 6. Extract 512-D ArcFace embedding and enforce L2 normalization
    raw_emb = np.asarray(largest_face.embedding, dtype=np.float32)
    if raw_emb.shape != (512,):
        raise ValueError(f"Unexpected embedding dimension: {raw_emb.shape}, expected (512,).")

    norm = float(np.linalg.norm(raw_emb))
    if norm > 0:
        normed_emb = (raw_emb / norm).astype(np.float32)
    else:
        normed_emb = raw_emb

    return cropped_face_bytes, normed_emb, det_score

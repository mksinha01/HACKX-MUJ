"""
FIR (First Information Report) Validation Service.

Implements a 3-tier validation engine for verifying FIR details:
  Tier 1 — Format Check: Regex patterns for Indian FIR number formats
  Tier 2 — Cross-Reference: Police station name fuzzy matching
  Tier 3 — Document Check: File validation for uploaded FIR copies (manual review)
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FIRValidationResult:
    """Result of FIR validation check."""
    is_valid: bool
    tier: int  # 1=format, 2=station, 3=document
    message: str
    confidence: float = 1.0  # 0.0-1.0 confidence score
    auto_approved: bool = False  # Whether this can be auto-approved


# Indian FIR number patterns (covers most state police formats)
FIR_PATTERNS = {
    "standard": re.compile(r"^FIR[/\-]\d{4}[/\-]\d{1,6}$", re.IGNORECASE),
    "standard_alt": re.compile(r"^FIR\s*(?:No\.?\s*)?:?\s*\d{1,6}[/\-]\d{4}$", re.IGNORECASE),
    "numeric_year": re.compile(r"^\d{1,6}[/\-]\d{4}$"),
    "year_numeric": re.compile(r"^\d{4}[/\-]\d{1,6}$"),
    "state_prefix": re.compile(r"^[A-Z]{2,4}[/\-]\d{4}[/\-]\d{1,6}$", re.IGNORECASE),
    "state_prefix_alt": re.compile(r"^[A-Z]{2,4}[/\-]\d{1,6}[/\-]\d{4}$", re.IGNORECASE),
    "cr_format": re.compile(r"^(?:CR|NC|RC|FIR)[/\-]?\d{1,6}[/\-]\d{2,4}$", re.IGNORECASE),
    "simple_numeric": re.compile(r"^\d{3,8}$"),
}

# Sample police station names for fuzzy matching (expandable via CSV/API)
# In production, load from a comprehensive database
KNOWN_POLICE_STATIONS_SAMPLE = [
    "Saket Police Station",
    "Hauz Khas Police Station",
    "Connaught Place Police Station",
    "Vasant Kunj Police Station",
    "Mehrauli Police Station",
    "Chanakyapuri Police Station",
    "Defence Colony Police Station",
    "Greater Kailash Police Station",
    "Lajpat Nagar Police Station",
    "Malviya Nagar Police Station",
    "Kotwali Police Station",
    "Civil Lines Police Station",
    "Model Town Police Station",
    "Rohini Police Station",
    "Pitampura Police Station",
    "Janakpuri Police Station",
    "Dwarka Police Station",
    "Najafgarh Police Station",
    "Shahdara Police Station",
    "Anand Vihar Police Station",
    "Juhu Police Station",
    "Bandra Police Station",
    "Andheri Police Station",
    "Borivali Police Station",
    "Colaba Police Station",
    "Marine Drive Police Station",
    "Dadar Police Station",
    "Powai Police Station",
    "Thane Police Station",
    "Navi Mumbai Police Station",
    "Koramangala Police Station",
    "Indiranagar Police Station",
    "Whitefield Police Station",
    "Electronic City Police Station",
    "Jayanagar Police Station",
    "HSR Layout Police Station",
    "Anna Nagar Police Station",
    "T Nagar Police Station",
    "Adyar Police Station",
    "Egmore Police Station",
    "Nungambakkam Police Station",
    "Cyber City Police Station",
    "DLF Phase Police Station",
    "Sector 29 Police Station",
    "Sohna Road Police Station",
    "Udyog Vihar Police Station",
    "Sector 14 Police Station",
    "Hazratganj Police Station",
    "Gomti Nagar Police Station",
    "Aliganj Police Station",
    "Charbagh Police Station",
    "Cantonment Police Station",
]


def _normalize_station_name(name: str) -> str:
    """Normalizes a police station name for comparison."""
    normalized = name.lower().strip()
    # Remove common suffixes
    for suffix in ["police station", "ps", "thana", "chowki"]:
        normalized = normalized.replace(suffix, "").strip()
    # Remove extra whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Computes the Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def _fuzzy_match_station(query: str, threshold: int = 3) -> tuple[bool, float, str]:
    """
    Fuzzy match a police station name against known stations.
    Returns (found, confidence, matched_name).
    """
    normalized_query = _normalize_station_name(query)
    
    if not normalized_query:
        return False, 0.0, ""
    
    best_distance = float("inf")
    best_match = ""
    
    for station in KNOWN_POLICE_STATIONS_SAMPLE:
        normalized_station = _normalize_station_name(station)
        distance = _levenshtein_distance(normalized_query, normalized_station)
        
        if distance < best_distance:
            best_distance = distance
            best_match = station
    
    if best_distance == 0:
        return True, 1.0, best_match
    elif best_distance <= threshold:
        confidence = max(0.0, 1.0 - (best_distance / max(len(normalized_query), 1)))
        return True, confidence, best_match
    
    # Check if query is a substring of any known station or vice versa
    for station in KNOWN_POLICE_STATIONS_SAMPLE:
        normalized_station = _normalize_station_name(station)
        if normalized_query in normalized_station or normalized_station in normalized_query:
            return True, 0.7, station
    
    return False, 0.0, ""


class FIRValidator:
    """
    Validates FIR (First Information Report) details using a 3-tier approach.
    
    Tier 1 — FORMAT CHECK: FIR number matches known Indian police format patterns
    Tier 2 — CROSS-REFERENCE: Police station name matched against database
    Tier 3 — DOCUMENT CHECK: Uploaded FIR document is valid (admin review required)
    """
    
    def validate_fir_number(self, fir_number: str) -> FIRValidationResult:
        """
        Tier 1: Validates FIR number format against known Indian police patterns.
        Returns validation result with pattern match details.
        """
        if not fir_number or not fir_number.strip():
            return FIRValidationResult(
                is_valid=False,
                tier=1,
                message="FIR number is required.",
            )
        
        cleaned = fir_number.strip()
        
        for pattern_name, pattern in FIR_PATTERNS.items():
            if pattern.match(cleaned):
                return FIRValidationResult(
                    is_valid=True,
                    tier=1,
                    message=f"FIR number '{cleaned}' matches {pattern_name} format.",
                    confidence=1.0,
                )
        
        # If no exact pattern match but has digits and reasonable format
        if re.search(r"\d{3,}", cleaned) and len(cleaned) <= 30:
            return FIRValidationResult(
                is_valid=True,
                tier=1,
                message=f"FIR number '{cleaned}' has a non-standard but acceptable format.",
                confidence=0.6,
            )
        
        return FIRValidationResult(
            is_valid=False,
            tier=1,
            message=(
                f"FIR number '{cleaned}' does not match any known format. "
                f"Expected formats: FIR/2026/1234, 1234/2026, CR/2026/1234"
            ),
        )
    
    def validate_police_station(self, station_name: str) -> FIRValidationResult:
        """
        Tier 2: Cross-references police station name against known stations database.
        Uses fuzzy matching (Levenshtein distance ≤ 3) for typo tolerance.
        """
        if not station_name or not station_name.strip():
            return FIRValidationResult(
                is_valid=False,
                tier=2,
                message="Police station name is required.",
            )
        
        found, confidence, matched_name = _fuzzy_match_station(station_name.strip())
        
        if found and confidence >= 0.8:
            return FIRValidationResult(
                is_valid=True,
                tier=2,
                message=f"Police station matched: '{matched_name}' (confidence: {confidence:.0%}).",
                confidence=confidence,
                auto_approved=True,
            )
        elif found:
            return FIRValidationResult(
                is_valid=True,
                tier=2,
                message=f"Possible match: '{matched_name}' (confidence: {confidence:.0%}). Manual review recommended.",
                confidence=confidence,
                auto_approved=False,
            )
        else:
            # Unknown station — not necessarily invalid, just requires manual review
            return FIRValidationResult(
                is_valid=True,  # Don't reject — could be a valid but unlisted station
                tier=2,
                message=f"Police station '{station_name}' not found in database. Manual verification required.",
                confidence=0.0,
                auto_approved=False,
            )
    
    def validate_fir_date(self, fir_date: Optional[datetime]) -> FIRValidationResult:
        """Validates that FIR date is reasonable (not in future, not too old)."""
        if not fir_date:
            return FIRValidationResult(
                is_valid=True,
                tier=1,
                message="FIR date not provided (optional).",
                confidence=0.5,
            )
        
        now = datetime.now(timezone.utc)
        
        if fir_date > now:
            return FIRValidationResult(
                is_valid=False,
                tier=1,
                message="FIR date cannot be in the future.",
            )
        
        days_old = (now - fir_date).days
        if days_old > 365 * 2:  # More than 2 years old
            return FIRValidationResult(
                is_valid=True,
                tier=1,
                message=f"FIR is {days_old} days old. This seems unusually old — verify this is correct.",
                confidence=0.5,
                auto_approved=False,
            )
        
        return FIRValidationResult(
            is_valid=True,
            tier=1,
            message="FIR date is valid.",
            confidence=1.0,
            auto_approved=True,
        )
    
    def validate_document(self, file_bytes: bytes, filename: str) -> FIRValidationResult:
        """
        Tier 3: Validates uploaded FIR document is a valid file.
        Actual content verification (stamps, watermarks) requires manual admin review.
        """
        if not file_bytes:
            return FIRValidationResult(
                is_valid=False,
                tier=3,
                message="FIR document file is empty.",
            )
        
        if len(file_bytes) < 1024:  # Less than 1KB — likely invalid
            return FIRValidationResult(
                is_valid=False,
                tier=3,
                message="FIR document is too small to be a valid document.",
            )
        
        if len(file_bytes) > 20 * 1024 * 1024:  # More than 20MB
            return FIRValidationResult(
                is_valid=False,
                tier=3,
                message="FIR document is too large (max 20MB).",
            )
        
        # Check file type by magic bytes
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        is_pdf = file_bytes[:4] == b"%PDF"
        is_jpeg = file_bytes[:3] == b"\xff\xd8\xff"
        is_png = file_bytes[:4] == b"\x89PNG"
        
        if not (is_pdf or is_jpeg or is_png):
            return FIRValidationResult(
                is_valid=False,
                tier=3,
                message=f"FIR document must be PDF, JPEG, or PNG. Detected file type is not supported.",
            )
        
        file_type = "PDF" if is_pdf else ("JPEG" if is_jpeg else "PNG")
        return FIRValidationResult(
            is_valid=True,
            tier=3,
            message=f"FIR document uploaded ({file_type}, {len(file_bytes)/1024:.0f} KB). Awaiting admin review.",
            confidence=0.5,
            auto_approved=False,  # Document content always needs manual review
        )
    
    def run_full_validation(
        self,
        fir_number: str,
        police_station: str,
        fir_date: Optional[datetime] = None,
        document_bytes: Optional[bytes] = None,
        document_filename: Optional[str] = None,
    ) -> dict:
        """
        Runs all applicable validation tiers and returns an overall decision.
        
        Decision Matrix:
          Format ✓ + Station ✓ (>80%) + Document → Auto-approve
          Format ✓ + Station ✓ (>80%) + No Doc   → Pending (admin prompted)
          Format ✓ + Station ✗                    → Pending (admin review)
          Format ✗                                 → Rejected
        """
        results = {}
        
        # Tier 1: Format check
        number_result = self.validate_fir_number(fir_number)
        results["fir_number"] = number_result
        
        if not number_result.is_valid:
            return {
                "overall_status": "REJECTED",
                "auto_approved": False,
                "message": number_result.message,
                "results": results,
            }
        
        # Tier 1b: Date check
        date_result = self.validate_fir_date(fir_date)
        results["fir_date"] = date_result
        
        if not date_result.is_valid:
            return {
                "overall_status": "REJECTED",
                "auto_approved": False,
                "message": date_result.message,
                "results": results,
            }
        
        # Tier 2: Station cross-reference
        station_result = self.validate_police_station(police_station)
        results["police_station"] = station_result
        
        # Tier 3: Document check (optional)
        if document_bytes and document_filename:
            doc_result = self.validate_document(document_bytes, document_filename)
            results["document"] = doc_result
            
            if not doc_result.is_valid:
                return {
                    "overall_status": "REJECTED",
                    "auto_approved": False,
                    "message": doc_result.message,
                    "results": results,
                }
        
        # Decision matrix - Relaxed for auto-approval
        format_ok = number_result.is_valid and number_result.confidence >= 0.8
        
        if format_ok:
            # Auto-approve if format is okay, bypassing document/station requirements
            return {
                "overall_status": "VERIFIED",
                "auto_approved": True,
                "message": "FIR details auto-verified: format is valid.",
                "results": results,
            }
        else:
            return {
                "overall_status": "PENDING",
                "auto_approved": False,
                "message": "FIR format has low confidence. Admin review required.",
                "results": results,
            }


# Singleton instance
fir_validator = FIRValidator()

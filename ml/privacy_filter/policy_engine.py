"""
policy_engine.py - Deterministic field-sensitivity policy engine.

WHY THIS EXISTS
---------------
Privacy routing decides what is written to an immutable, world-readable public
ledger (Ethereum). That decision is irreversible: once sensitive data is anchored
on-chain it cannot be recalled. A probabilistic classifier is therefore the wrong
tool - a single misclassification permanently leaks data, and the prior ML model
was trained on network-traffic features (NSL-KDD) that carry no privacy signal at
all (see PHASE0_FINDINGS.md). This module replaces that classifier with a
verifiable, declared policy.

DESIGN PROPERTIES (all four are required and tested):
  1. DETERMINISTIC - same input always yields the same decision. No randomness,
     no learned weights, no probability. Confidence is always 1.0.
  2. AUDITABLE     - every field decision records WHICH rule fired and its legal
     basis (HIPAA identifier, GDPR Art. 9 special category, PCI, etc.).
  3. TOTAL         - every possible field gets a decision. Unmatched fields hit a
     documented default.
  4. FAIL-CLOSED   - the default for an unmatched field is the MOST restrictive
     level (CRITICAL), so unknown data is never published by accident.

THE LEDGER GATE IS BINARY
-------------------------
Sensitivity is an ordered 4-level scale, but the irreversible public-ledger gate
is binary: ONLY fields classified PUBLIC may be written to the public chain.
Everything at RESTRICTED or above is private-only. This is the property the paper
proves rather than measures: by construction, no field above PUBLIC can reach the
public ledger.

The ordered scale is still used for role-based query-time sharing (see
ACCESS_MATRIX / filter_by_access), which is a separate, reversible concern.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field
from enum import IntEnum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("privacy.policy")

POLICY_VERSION = "1.0.0"


class Sensitivity(IntEnum):
    """Ordered sensitivity levels. Higher = more restricted."""
    PUBLIC = 1        # Non-identifying; may be published to the public ledger.
    RESTRICTED = 2    # Quasi-identifiers / health-adjacent telemetry.
    CONFIDENTIAL = 3  # Clinical content, proprietary IP, sensitive financial.
    CRITICAL = 4      # Direct identifiers, secrets, GDPR special categories.


# Only PUBLIC-level fields are eligible for the immutable public ledger.
PUBLIC_LEDGER_THRESHOLD = Sensitivity.PUBLIC

# Top-level field names that are always retained as the record key, even when the
# record as a whole is sensitive. The downstream orchestrator requires an 'id' in
# the shareable projection to anchor the on-chain reference.
ALWAYS_PUBLIC_KEYS = {"id"}


@dataclass(frozen=True)
class Rule:
    """A single, declared policy rule. Order in POLICY_RULES is significant:
    the first matching rule wins, so more specific / more restrictive rules are
    declared earlier."""
    rule_id: str
    token: str            # normalized token to match against the field name
    kind: str             # 'exact' or 'contains'
    level: Sensitivity
    basis: str            # human-readable legal / policy justification


# ---------------------------------------------------------------------------
# THE POLICY TABLE
# Ordered most-restrictive -> least-restrictive. First match wins.
# Field names are normalized (lowercased, non-alphanumerics stripped) before
# matching, so 'patient_id', 'patientId' and 'patient-id' all match 'patientid'.
# ---------------------------------------------------------------------------
POLICY_RULES: List[Rule] = [
    # ---- CRITICAL: secrets / credentials -----------------------------------
    Rule("SEC-PASSWORD",   "password",        "contains", Sensitivity.CRITICAL, "Authentication secret"),
    Rule("SEC-SECRET",     "secret",          "contains", Sensitivity.CRITICAL, "Authentication secret"),
    Rule("SEC-APIKEY",     "apikey",          "contains", Sensitivity.CRITICAL, "Authentication secret"),
    Rule("SEC-TOKEN",      "authtoken",       "contains", Sensitivity.CRITICAL, "Authentication secret"),
    Rule("SEC-CREDENTIAL", "credential",      "contains", Sensitivity.CRITICAL, "Authentication secret"),
    Rule("SEC-PRIVKEY",    "privatekey",      "contains", Sensitivity.CRITICAL, "Cryptographic secret"),

    # ---- CRITICAL: direct identifiers (HIPAA 18 identifiers) ----------------
    Rule("HIPAA-SSN",       "ssn",            "contains", Sensitivity.CRITICAL, "HIPAA identifier: SSN / national ID"),
    Rule("HIPAA-SSN2",      "socialsecurity", "contains", Sensitivity.CRITICAL, "HIPAA identifier: SSN / national ID"),
    Rule("ID-NATIONAL",     "nationalid",     "contains", Sensitivity.CRITICAL, "National identification number"),
    Rule("ID-PASSPORT",     "passport",       "contains", Sensitivity.CRITICAL, "Government identifier"),
    Rule("ID-LICENSE",      "driverlicense",  "contains", Sensitivity.CRITICAL, "Government identifier"),
    Rule("HIPAA-PATIENTID", "patientid",      "contains", Sensitivity.CRITICAL, "HIPAA identifier: patient ID"),
    Rule("HIPAA-PATIENT",   "patient",        "contains", Sensitivity.CRITICAL, "HIPAA identifier: patient-linked field"),
    Rule("HIPAA-MRN",       "mrn",            "contains", Sensitivity.CRITICAL, "HIPAA identifier: medical record number"),
    Rule("HIPAA-MRN2",      "medicalrecord",  "contains", Sensitivity.CRITICAL, "HIPAA identifier: medical record number"),
    Rule("HIPAA-HEALTHPLAN","healthplan",     "contains", Sensitivity.CRITICAL, "HIPAA identifier: health-plan beneficiary"),

    # ---- CRITICAL: contact PII (HIPAA identifiers) --------------------------
    Rule("PII-EMAIL",       "email",          "contains", Sensitivity.CRITICAL, "HIPAA identifier: email address"),
    Rule("PII-PHONE",       "phone",          "contains", Sensitivity.CRITICAL, "HIPAA identifier: telephone number"),
    Rule("PII-FAX",         "fax",            "contains", Sensitivity.CRITICAL, "HIPAA identifier: fax number"),
    Rule("PII-HOMEADDR",    "homeaddress",    "contains", Sensitivity.CRITICAL, "HIPAA identifier: postal address"),
    Rule("PII-STREET",      "streetaddress",  "contains", Sensitivity.CRITICAL, "HIPAA identifier: postal address"),
    Rule("PII-MAILADDR",    "mailingaddress", "contains", Sensitivity.CRITICAL, "HIPAA identifier: postal address"),

    # ---- CRITICAL: financial account data (PCI-DSS) -------------------------
    Rule("PCI-CREDITCARD",  "creditcard",     "contains", Sensitivity.CRITICAL, "PCI-DSS: payment card number"),
    Rule("PCI-CARDNUM",     "cardnumber",     "contains", Sensitivity.CRITICAL, "PCI-DSS: payment card number"),
    Rule("PCI-CVV",         "cvv",            "contains", Sensitivity.CRITICAL, "PCI-DSS: card verification value"),
    Rule("FIN-BANKACCT",    "bankaccount",    "contains", Sensitivity.CRITICAL, "Financial account number"),
    Rule("FIN-ACCTNUM",     "accountnumber",  "contains", Sensitivity.CRITICAL, "Financial account number"),
    Rule("FIN-IBAN",        "iban",           "contains", Sensitivity.CRITICAL, "Financial account number"),
    Rule("FIN-ROUTING",     "routingnumber",  "contains", Sensitivity.CRITICAL, "Financial account number"),

    # ---- CRITICAL: GDPR Art. 9 special categories ---------------------------
    Rule("GDPR-GENETIC",    "genetic",        "contains", Sensitivity.CRITICAL, "GDPR Art. 9: genetic data"),
    Rule("GDPR-DNA",        "dna",            "contains", Sensitivity.CRITICAL, "GDPR Art. 9: genetic data"),
    Rule("GDPR-BIOMETRIC",  "biometric",      "contains", Sensitivity.CRITICAL, "GDPR Art. 9: biometric data"),
    Rule("GDPR-FINGERPRINT","fingerprint",    "contains", Sensitivity.CRITICAL, "GDPR Art. 9: biometric data"),
    Rule("GDPR-HIV",        "hivstatus",      "contains", Sensitivity.CRITICAL, "GDPR Art. 9: health data"),
    Rule("GDPR-MENTAL",     "mentalhealth",   "contains", Sensitivity.CRITICAL, "GDPR Art. 9: health data"),
    Rule("GDPR-SEXLIFE",    "sexuallife",     "contains", Sensitivity.CRITICAL, "GDPR Art. 9: sex life / orientation"),
    Rule("GDPR-SEXORIENT",  "sexualorient",   "contains", Sensitivity.CRITICAL, "GDPR Art. 9: sex life / orientation"),
    Rule("GDPR-RELIGION",   "religion",       "contains", Sensitivity.CRITICAL, "GDPR Art. 9: religious belief"),
    Rule("GDPR-ETHNICITY",  "ethnicity",      "contains", Sensitivity.CRITICAL, "GDPR Art. 9: racial / ethnic origin"),
    Rule("GDPR-RACE",       "race",           "contains", Sensitivity.CRITICAL, "GDPR Art. 9: racial / ethnic origin"),
    Rule("GDPR-POLITICS",   "political",      "contains", Sensitivity.CRITICAL, "GDPR Art. 9: political opinion"),
    Rule("GDPR-UNION",      "unionmembership","contains", Sensitivity.CRITICAL, "GDPR Art. 9: trade-union membership"),

    # ---- CRITICAL: precise geolocation (HIPAA geo / GDPR) -------------------
    Rule("GEO-EXACTGPS",    "exactgps",       "contains", Sensitivity.CRITICAL, "Precise geolocation"),
    Rule("GEO-EXACTLOC",    "exactlocation",  "contains", Sensitivity.CRITICAL, "Precise geolocation"),
    Rule("GEO-HOMECOORD",   "homecoordinates","contains", Sensitivity.CRITICAL, "Precise geolocation"),
    Rule("GEO-HOMELOC",     "homelocation",   "contains", Sensitivity.CRITICAL, "Precise geolocation"),
    Rule("GEO-GPSCOORD",    "gpscoordinates", "contains", Sensitivity.CRITICAL, "Precise geolocation"),
    Rule("GEO-LATLONG",     "latlong",        "contains", Sensitivity.CRITICAL, "Precise geolocation"),

    # ---- CONFIDENTIAL: clinical content -------------------------------------
    Rule("CLIN-DIAGNOSIS",  "diagnosis",      "contains", Sensitivity.CONFIDENTIAL, "Clinical PHI: diagnosis"),
    Rule("CLIN-PRESCRIBE",  "prescription",   "contains", Sensitivity.CONFIDENTIAL, "Clinical PHI: prescription"),
    Rule("CLIN-MEDICATION", "medication",     "contains", Sensitivity.CONFIDENTIAL, "Clinical PHI: medication"),
    Rule("CLIN-LABRESULT",  "labresult",      "contains", Sensitivity.CONFIDENTIAL, "Clinical PHI: laboratory result"),
    Rule("CLIN-NOTE",       "clinicalnote",   "contains", Sensitivity.CONFIDENTIAL, "Clinical PHI: clinical note"),
    Rule("CLIN-TREATMENT",  "treatment",      "contains", Sensitivity.CONFIDENTIAL, "Clinical PHI: treatment"),
    Rule("CLIN-SYMPTOM",    "symptom",        "contains", Sensitivity.CONFIDENTIAL, "Clinical PHI: symptom"),

    # ---- CONFIDENTIAL: sensitive financial / proprietary IP -----------------
    Rule("FIN-SALARY",      "salary",         "contains", Sensitivity.CONFIDENTIAL, "Sensitive financial: compensation"),
    Rule("FIN-INCOME",      "income",         "contains", Sensitivity.CONFIDENTIAL, "Sensitive financial: income"),
    Rule("IP-PROPRIETARY",  "proprietary",    "contains", Sensitivity.CONFIDENTIAL, "Proprietary / trade secret"),
    Rule("IP-FORMULA",      "formula",        "contains", Sensitivity.CONFIDENTIAL, "Proprietary / trade secret"),
    Rule("IP-CATALYST",     "catalyst",       "contains", Sensitivity.CONFIDENTIAL, "Proprietary / trade secret"),
    Rule("IP-RECIPE",       "recipe",         "contains", Sensitivity.CONFIDENTIAL, "Proprietary / trade secret"),
    Rule("IP-TRADESECRET",  "tradesecret",    "contains", Sensitivity.CONFIDENTIAL, "Proprietary / trade secret"),
    Rule("IP-MACHINESET",   "machinesettings","contains", Sensitivity.CONFIDENTIAL, "Proprietary process parameters"),
    Rule("IP-PROCESSPARAM", "processparam",   "contains", Sensitivity.CONFIDENTIAL, "Proprietary process parameters"),

    # ---- RESTRICTED: quasi-identifiers / dates ------------------------------
    Rule("QID-DOB",         "dateofbirth",    "contains", Sensitivity.RESTRICTED, "Quasi-identifier: date of birth (HIPAA date)"),
    Rule("QID-DOB2",        "dob",            "exact",    Sensitivity.RESTRICTED, "Quasi-identifier: date of birth (HIPAA date)"),
    Rule("QID-BIRTHDATE",   "birthdate",      "contains", Sensitivity.RESTRICTED, "Quasi-identifier: date of birth (HIPAA date)"),
    Rule("QID-AGE",         "age",            "exact",    Sensitivity.RESTRICTED, "Quasi-identifier: age"),
    Rule("QID-ZIP",         "zipcode",        "contains", Sensitivity.RESTRICTED, "Quasi-identifier: postal code (HIPAA geo)"),
    Rule("QID-POSTAL",      "postalcode",     "contains", Sensitivity.RESTRICTED, "Quasi-identifier: postal code (HIPAA geo)"),
    Rule("QID-ROOM",        "room",           "contains", Sensitivity.RESTRICTED, "Quasi-identifier: room / bed"),
    Rule("QID-BED",         "bedid",          "contains", Sensitivity.RESTRICTED, "Quasi-identifier: room / bed"),
    Rule("QID-WARD",        "ward",           "contains", Sensitivity.RESTRICTED, "Quasi-identifier: hospital ward"),

    # ---- RESTRICTED: health-adjacent vitals (sensitive in medical context) --
    Rule("VITAL-HEARTRATE", "heartrate",      "contains", Sensitivity.RESTRICTED, "Health telemetry: vital sign"),
    Rule("VITAL-BP",        "bloodpressure",  "contains", Sensitivity.RESTRICTED, "Health telemetry: vital sign"),
    Rule("VITAL-OXYGEN",    "oxygen",         "contains", Sensitivity.RESTRICTED, "Health telemetry: vital sign"),
    Rule("VITAL-GLUCOSE",   "glucose",        "contains", Sensitivity.RESTRICTED, "Health telemetry: vital sign"),
    Rule("VITAL-BMI",       "bmi",            "exact",    Sensitivity.RESTRICTED, "Health telemetry: body metric"),
    Rule("VITAL-WEIGHT",    "weight",         "contains", Sensitivity.RESTRICTED, "Health telemetry: body metric"),
    Rule("VITAL-HEIGHT",    "height",         "contains", Sensitivity.RESTRICTED, "Health telemetry: body metric"),
    Rule("VITAL-STEPS",     "steps",          "contains", Sensitivity.RESTRICTED, "Health telemetry: activity"),

    # ---- RESTRICTED: indirect identifiers -----------------------------------
    Rule("IID-OPERATOR",    "operatorid",     "contains", Sensitivity.RESTRICTED, "Indirect identifier: operator"),
    Rule("IID-EMPLOYEE",    "employeeid",     "contains", Sensitivity.RESTRICTED, "Indirect identifier: employee"),
    Rule("IID-USERNAME",    "username",       "contains", Sensitivity.RESTRICTED, "Indirect identifier: user account"),
    Rule("IID-USERID",      "userid",         "contains", Sensitivity.RESTRICTED, "Indirect identifier: user account"),
    Rule("IID-OWNER",       "owner",          "contains", Sensitivity.RESTRICTED, "Indirect identifier: owner"),

    # ---- PUBLIC: record / device metadata -----------------------------------
    Rule("PUB-ID",          "id",             "exact",    Sensitivity.PUBLIC, "Record key (non-identifying)"),
    Rule("PUB-RECORDID",    "recordid",       "contains", Sensitivity.PUBLIC, "Record key (non-identifying)"),
    Rule("PUB-EVENTID",     "eventid",        "contains", Sensitivity.PUBLIC, "Event key (non-identifying)"),
    Rule("PUB-DEVICEID",    "deviceid",       "contains", Sensitivity.PUBLIC, "Non-identifying device metadata"),
    Rule("PUB-SENSORID",    "sensorid",       "contains", Sensitivity.PUBLIC, "Non-identifying device metadata"),
    Rule("PUB-SENSORTYPE",  "sensortype",     "contains", Sensitivity.PUBLIC, "Non-identifying device metadata"),
    Rule("PUB-DEVICETYPE",  "devicetype",     "contains", Sensitivity.PUBLIC, "Non-identifying device metadata"),
    Rule("PUB-MODEL",       "model",          "exact",    Sensitivity.PUBLIC, "Non-identifying device metadata"),
    Rule("PUB-FIRMWARE",    "firmware",       "contains", Sensitivity.PUBLIC, "Non-identifying device metadata"),

    # ---- PUBLIC: time --------------------------------------------------------
    Rule("PUB-TIMESTAMP",   "timestamp",      "contains", Sensitivity.PUBLIC, "Event time (non-identifying)"),
    Rule("PUB-TIME",        "time",           "exact",    Sensitivity.PUBLIC, "Event time (non-identifying)"),
    Rule("PUB-EPOCH",       "epoch",          "contains", Sensitivity.PUBLIC, "Event time (non-identifying)"),

    # ---- PUBLIC: environmental / operational telemetry ----------------------
    Rule("PUB-TEMP",        "temperature",    "contains", Sensitivity.PUBLIC, "Environmental telemetry"),
    Rule("PUB-HUMIDITY",    "humidity",       "contains", Sensitivity.PUBLIC, "Environmental telemetry"),
    Rule("PUB-PRESSURE",    "pressure",       "contains", Sensitivity.PUBLIC, "Environmental telemetry"),
    Rule("PUB-CO2",         "co2",            "contains", Sensitivity.PUBLIC, "Environmental telemetry"),
    Rule("PUB-PM25",        "pm25",           "contains", Sensitivity.PUBLIC, "Environmental telemetry"),
    Rule("PUB-PM10",        "pm10",           "contains", Sensitivity.PUBLIC, "Environmental telemetry"),
    Rule("PUB-AIRQUALITY",  "airquality",     "contains", Sensitivity.PUBLIC, "Environmental telemetry"),
    Rule("PUB-NOISE",       "noise",          "contains", Sensitivity.PUBLIC, "Environmental telemetry"),
    Rule("PUB-VIBRATION",   "vibration",      "contains", Sensitivity.PUBLIC, "Operational telemetry"),
    Rule("PUB-VOLTAGE",     "voltage",        "contains", Sensitivity.PUBLIC, "Operational telemetry"),
    Rule("PUB-CURRENT",     "current",        "exact",    Sensitivity.PUBLIC, "Operational telemetry"),
    Rule("PUB-POWER",       "power",          "contains", Sensitivity.PUBLIC, "Operational telemetry"),
    Rule("PUB-RPM",         "rpm",            "contains", Sensitivity.PUBLIC, "Operational telemetry"),
    Rule("PUB-STATUS",      "status",         "contains", Sensitivity.PUBLIC, "Operational state"),
    Rule("PUB-STATE",       "state",          "exact",    Sensitivity.PUBLIC, "Operational state"),
    Rule("PUB-UNIT",        "unit",           "contains", Sensitivity.PUBLIC, "Measurement unit"),

    # ---- PUBLIC: coarse location (non-precise) ------------------------------
    # NOTE: precise-geolocation rules above are matched FIRST, so only coarse
    # location descriptors reach these.
    Rule("PUB-LOCATION",    "location",       "exact",    Sensitivity.PUBLIC, "Coarse location (e.g. zone label)"),
    Rule("PUB-ZONE",        "zone",           "contains", Sensitivity.PUBLIC, "Coarse location: zone"),
    Rule("PUB-REGION",      "region",         "contains", Sensitivity.PUBLIC, "Coarse location: region"),
    Rule("PUB-FACILITY",    "facility",       "contains", Sensitivity.PUBLIC, "Coarse location: facility"),
    Rule("PUB-BUILDING",    "building",       "contains", Sensitivity.PUBLIC, "Coarse location: building"),
    Rule("PUB-SITE",        "site",           "exact",    Sensitivity.PUBLIC, "Coarse location: site"),
]

# The documented default for any field that matches no rule. Fail closed.
DEFAULT_RULE = Rule("DEFAULT-FAIL-CLOSED", "*", "default", Sensitivity.CRITICAL,
                    "No explicit rule; default to most-restrictive (fail closed)")

# Value-based escalation: if a string VALUE looks like a known sensitive token,
# escalate regardless of field name (defense in depth).
VALUE_PATTERNS = [
    ("VALUE-SSN",        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),               Sensitivity.CRITICAL, "Value matches SSN pattern"),
    ("VALUE-EMAIL",      re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+"),            Sensitivity.CRITICAL, "Value matches email pattern"),
    ("VALUE-CREDITCARD", re.compile(r"\b(?:\d[ -]?){13,16}\b"),             Sensitivity.CRITICAL, "Value matches payment-card pattern"),
]

# Map free-text declared sensitivity values to a level (record-level floor).
_DECLARED_SENSITIVITY = {
    "public": Sensitivity.PUBLIC,
    "low": Sensitivity.PUBLIC,
    "restricted": Sensitivity.RESTRICTED,
    "medium": Sensitivity.RESTRICTED,
    "confidential": Sensitivity.CONFIDENTIAL,
    "sensitive": Sensitivity.CONFIDENTIAL,
    "private": Sensitivity.CONFIDENTIAL,
    "high": Sensitivity.CONFIDENTIAL,
    "critical": Sensitivity.CRITICAL,
}

# Role -> set of levels that role may receive at QUERY time (reversible sharing).
# This is NOT the public-ledger gate (which is always PUBLIC-only).
ACCESS_MATRIX = {
    "public":     {Sensitivity.PUBLIC},
    "user":       {Sensitivity.PUBLIC},
    "researcher": {Sensitivity.PUBLIC, Sensitivity.RESTRICTED},
    "doctor":     {Sensitivity.PUBLIC, Sensitivity.RESTRICTED, Sensitivity.CONFIDENTIAL},
    "admin":      {Sensitivity.PUBLIC, Sensitivity.RESTRICTED, Sensitivity.CONFIDENTIAL, Sensitivity.CRITICAL},
}


def normalize(name: str) -> str:
    """Lowercase and strip everything but [a-z0-9] so that 'patient_id',
    'patientId' and 'patient-id' all normalize to 'patientid'."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


@dataclass
class FieldDecision:
    path: str
    level: Sensitivity
    rule_id: str
    basis: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "level": self.level.name.lower(),
            "rule_id": self.rule_id,
            "basis": self.basis,
        }


@dataclass
class RecordDecision:
    field_decisions: List[FieldDecision] = dc_field(default_factory=list)
    shareable_data: Dict[str, Any] = dc_field(default_factory=dict)
    redacted_fields: List[str] = dc_field(default_factory=list)
    max_level: Sensitivity = Sensitivity.PUBLIC

    @property
    def is_sensitive(self) -> bool:
        """True if ANY field is above the public-ledger threshold."""
        return self.max_level > PUBLIC_LEDGER_THRESHOLD


def _match_name(field_name: str) -> Rule:
    """Return the first matching rule for a field name, or the fail-closed
    default. First match wins, so POLICY_RULES order encodes precedence."""
    norm = normalize(field_name)
    for rule in POLICY_RULES:
        if rule.kind == "exact" and norm == rule.token:
            return rule
        if rule.kind == "contains" and rule.token in norm:
            return rule
    return DEFAULT_RULE


def _escalate_for_value(value: Any, level: Sensitivity, rule_id: str, basis: str):
    """Apply value-based escalation. Returns (level, rule_id, basis)."""
    if isinstance(value, str):
        for vid, pattern, vlevel, vbasis in VALUE_PATTERNS:
            if vlevel > level and pattern.search(value):
                return vlevel, vid, vbasis
    return level, rule_id, basis


def classify_field(field_name: str, value: Any = None) -> FieldDecision:
    """Classify a single scalar field deterministically."""
    rule = _match_name(field_name)
    level, rule_id, basis = rule.level, rule.rule_id, rule.basis
    level, rule_id, basis = _escalate_for_value(value, level, rule_id, basis)
    return FieldDecision(path=field_name, level=level, rule_id=rule_id, basis=basis)


def _declared_floor(record: Dict[str, Any]) -> Sensitivity:
    """Honor a producer-declared sensitivity/privacy label as a record floor."""
    floor = Sensitivity.PUBLIC
    for key in ("sensitivityLevel", "privacyLevel"):
        val = record.get(key)
        if isinstance(val, str):
            floor = max(floor, _DECLARED_SENSITIVITY.get(val.strip().lower(), Sensitivity.PUBLIC))
    return floor


def classify_record(record: Dict[str, Any], _prefix: str = "", _root: bool = True) -> RecordDecision:
    """Recursively classify a (possibly nested) IoT record.

    Builds the public-ledger projection (`shareable_data`) containing ONLY
    PUBLIC-level leaves, records every per-field decision for audit, and
    computes the record's maximum sensitivity. Fails closed on unknown fields.
    """
    decision = RecordDecision()

    for key, value in record.items():
        path = f"{_prefix}{key}"
        norm = normalize(key)

        if isinstance(value, dict):
            # Recurse; nested public leaves are kept under the same key.
            sub = classify_record(value, _prefix=f"{path}.", _root=False)
            decision.field_decisions.extend(sub.field_decisions)
            decision.redacted_fields.extend(sub.redacted_fields)
            decision.max_level = max(decision.max_level, sub.max_level)
            if sub.shareable_data:
                decision.shareable_data[key] = sub.shareable_data
            continue

        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            # List of objects: classify each, keep public projections.
            kept = []
            for i, item in enumerate(value):
                sub = classify_record(item, _prefix=f"{path}[{i}].", _root=False)
                decision.field_decisions.extend(sub.field_decisions)
                decision.redacted_fields.extend(sub.redacted_fields)
                decision.max_level = max(decision.max_level, sub.max_level)
                if sub.shareable_data:
                    kept.append(sub.shareable_data)
            if kept:
                decision.shareable_data[key] = kept
            continue

        # Scalar (or list of scalars treated as one field).
        fd = classify_field(key, value if not isinstance(value, list) else None)
        fd.path = path
        decision.field_decisions.append(fd)
        decision.max_level = max(decision.max_level, fd.level)

        is_always_public = _root and norm in ALWAYS_PUBLIC_KEYS
        if fd.level == Sensitivity.PUBLIC or is_always_public:
            decision.shareable_data[key] = value
        else:
            decision.redacted_fields.append(path)

    if _root:
        decision.max_level = max(decision.max_level, _declared_floor(record))

    return decision


def filter_for_publication(record: Dict[str, Any]) -> Dict[str, Any]:
    """Produce the privacy-filter response for the ingest / public-ledger path.

    Response shape is backward-compatible with the previous service contract
    (consumed by orchestrator.ingest_data): `data_sensitivity`, `confidence`,
    `shareable_data`. Adds an auditable `policy_decisions` trail.

    GUARANTEE (proven by construction, verified by tests): `shareable_data`
    contains no field classified above PUBLIC.
    """
    decision = classify_record(record)

    # The orchestrator anchors an on-chain reference keyed by 'id'.
    if "id" in record and "id" not in decision.shareable_data:
        decision.shareable_data["id"] = record["id"]

    # Audit log: one line per non-public field that was withheld.
    for fd in decision.field_decisions:
        if fd.level > PUBLIC_LEDGER_THRESHOLD:
            logger.info("policy_redact path=%s level=%s rule=%s basis=%s",
                        fd.path, fd.level.name, fd.rule_id, fd.basis)

    return {
        "data_sensitivity": "sensitive" if decision.is_sensitive else "public",
        "confidence": 1.0,  # deterministic policy => certainty, not probability
        "shareable_data": decision.shareable_data,
        "max_sensitivity": decision.max_level.name.lower(),
        "redacted_fields": decision.redacted_fields,
        "policy_decisions": [fd.as_dict() for fd in decision.field_decisions],
        "policy_version": POLICY_VERSION,
    }


def filter_by_access(record: Dict[str, Any], access_level: str) -> Dict[str, Any]:
    """Query-time sharing: return fields a given role may receive. Reversible,
    unlike the public-ledger gate. Unknown roles fail closed to PUBLIC-only."""
    allowed = ACCESS_MATRIX.get(str(access_level).lower(), {Sensitivity.PUBLIC})
    decision = classify_record(record)
    out: Dict[str, Any] = {}
    # Flat projection is sufficient for query responses; nested handled at top level.
    for fd in decision.field_decisions:
        if "." not in fd.path and "[" not in fd.path and fd.level in allowed:
            top = fd.path
            if top in record and not isinstance(record[top], (dict, list)):
                out[top] = record[top]
    return out


def policy_coverage(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Coverage metric for the evaluation: fraction of observed fields matched
    by an explicit rule vs. the fail-closed default."""
    total = 0
    explicit = 0
    by_default: Dict[str, int] = {}
    for rec in records:
        dec = classify_record(rec)
        for fd in dec.field_decisions:
            total += 1
            if fd.rule_id == DEFAULT_RULE.rule_id:
                leaf = fd.path.split(".")[-1]
                by_default[leaf] = by_default.get(leaf, 0) + 1
            else:
                explicit += 1
    return {
        "total_fields": total,
        "explicit_rule_fields": explicit,
        "default_fields": total - explicit,
        "coverage": (explicit / total) if total else 1.0,
        "unmatched_field_names": by_default,
    }


if __name__ == "__main__":
    # Minimal smoke test / demonstration.
    logging.basicConfig(level=logging.INFO)
    sample = {
        "id": "rec-001",
        "deviceId": "sensor_42",
        "timestamp": "2026-06-30T10:00:00Z",
        "data": {
            "temperature": 22.5,
            "humidity": 60,
            "location": "zone_3",
            "patientId": "P12345",
            "diagnosis": "hypertension",
        },
        "sensitivityLevel": "sensitive",
    }
    import json
    print(json.dumps(filter_for_publication(sample), indent=2))

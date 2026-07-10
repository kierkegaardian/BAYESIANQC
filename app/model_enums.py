from enum import Enum


class Role(str, Enum):
    QC_ANALYST = "qc_analyst"
    SUPERVISOR = "supervisor"
    QA_MANAGER = "qa_manager"
    ADMIN = "admin"
    AUDITOR = "auditor"
    DATA_STEWARD = "data_steward"
    STAKEHOLDER = "stakeholder"


class Permission(str, Enum):
    READ = "read"
    INGEST_QC = "ingest_qc"
    EDIT_CONFIG = "edit_config"
    MANAGE_IMPORTS = "manage_imports"
    APPROVE = "approve"
    OVERRIDE = "override"
    COMMENT_QC = "comment_qc"
    RESOLVE_QC = "resolve_qc"
    MANAGE_ALERTS = "manage_alerts"
    MANAGE_INVESTIGATIONS = "manage_investigations"
    MANAGE_CAPAS = "manage_capas"


class EventType(str, Enum):
    CALIBRATION = "calibration"
    MAINTENANCE = "maintenance"
    REAGENT_LOT_CHANGE = "reagent_lot_change"
    CONTROL_MATERIAL_LOT_CHANGE = "control_material_lot_change"
    SOFTWARE_UPDATE = "software_update"
    ENVIRONMENTAL_ALERT = "environmental_alert"


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"


class InvestigationStatus(str, Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    CLOSED = "closed"


class CapaStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    IMPLEMENTING = "implementing"
    EFFECTIVENESS_CHECK = "effectiveness_check"
    CLOSED = "closed"
    REOPENED = "reopened"


class EntrySource(str, Enum):
    AUTOMATED = "automated"
    MANUAL = "manual"


class QuarantineReason(str, Enum):
    OUT_OF_BOUNDS = "out_of_bounds"
    UNIT_MISMATCH = "unit_mismatch"
    SUSPICIOUS_TIMESTAMP = "suspicious_timestamp"
    MAPPING_FAILURE = "mapping_failure"
    MODEL_EVALUATION_FAILURE = "model_evaluation_failure"


class QuarantineStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class QCBacklogSource(str, Enum):
    SCHEDULED = "scheduled"
    REQUESTED = "requested"


class QCBacklogStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELED = "canceled"


class QCBacklogPriority(str, Enum):
    ROUTINE = "routine"
    SOON = "soon"
    URGENT = "urgent"


class QCCommentTargetType(str, Enum):
    QC_RECORD = "qc_record"
    ALERT = "alert"
    QC_RUN = "qc_run"


class DuplicateStatus(str, Enum):
    UNIQUE = "unique"
    DUPLICATE = "duplicate"
    POSSIBLE_DUPLICATE = "possible_duplicate"


class BayesianRiskStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class BayesianRiskUnavailableReason(str, Enum):
    MISSING_EFFECTIVE_PRIOR = "missing_effective_prior"
    MODEL_EVALUATION_FAILURE = "model_evaluation_failure"

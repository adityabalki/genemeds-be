from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class HcpRegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    mobile: str = Field(min_length=10, max_length=20)
    degree: str = Field(min_length=1, max_length=255)
    specialisation: str = Field(min_length=1, max_length=255)
    experience: str = Field(min_length=1, max_length=50)
    hospital: str = Field(min_length=1, max_length=255)
    registration_number: str = Field(min_length=1, max_length=255)
    council: str = Field(min_length=1, max_length=255)
    registration_year: str = Field(min_length=4, max_length=4)
    clinic_code: str | None = Field(default=None, max_length=255)

    @field_validator("clinic_code", mode="before")
    @classmethod
    def normalize_clinic_code(cls, v: object) -> str | None:
        if not v or (isinstance(v, str) and not v.strip()):
            return None
        return v

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 10:
            raise ValueError("Mobile must be exactly 10 digits.")
        return value

    @field_validator("experience")
    @classmethod
    def validate_experience(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Experience must be numeric.")
        return value

    @field_validator("registration_year")
    @classmethod
    def validate_registration_year(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 4:
            raise ValueError("Registration year must be a 4 digit year.")
        return value


class ReceptionistRegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    mobile: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=6, max_length=128)
    clinic: str = Field(min_length=1, max_length=255)
    clinic_code: str = Field(min_length=1, max_length=255)

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 10:
            raise ValueError("Mobile must be exactly 10 digits.")
        return value


class LabRegisterRequest(BaseModel):
    lab_name: str = Field(min_length=1, max_length=255)
    contact_person: str = Field(min_length=1, max_length=255)
    email: EmailStr
    mobile: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=6, max_length=128)
    license_id: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=255)
    state: str = Field(min_length=1, max_length=255)
    pincode: str = Field(min_length=6, max_length=6)

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 10:
            raise ValueError("Mobile must be exactly 10 digits.")
        return value

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 6:
            raise ValueError("Pincode must be exactly 6 digits.")
        return value


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    message: str
    role: str
    redirect_to: str
    user_id: int
    full_name: str | None = None
    lab_name: str | None = None
    clinic_code: str | None = None


class RegistrationResponse(BaseModel):
    message: str
    status: str
    role: str
    redirect_to: str
    user_id: int


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    service: str


# ── Receptionist schemas ──────────────────────────────────────────────────────

from datetime import date as _date  # noqa: E402
from typing import Literal, Optional  # noqa: E402


class VitalsInput(BaseModel):
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    weight_kg: Optional[float] = None
    o2_level: Optional[float] = None
    notes: Optional[str] = None


class AppointmentInput(BaseModel):
    hcp_id: str
    date: _date
    slot: str  # "HH:MM"


class PatientRegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    mobile: str
    email: Optional[str] = None
    dob: Optional[_date] = None
    gender: Optional[Literal["Male", "Female", "Other", "Prefer not to say"]] = None
    city: Optional[str] = None
    visit_type: Optional[str] = "First Visit"
    chief_complaint: str = Field(min_length=1)
    ongoing_treatment: Optional[str] = None
    known_allergies: Optional[str] = None
    past_medical_history: Optional[str] = None
    family_history: Optional[str] = None
    vitals: Optional[VitalsInput] = None
    appointment: Optional[AppointmentInput] = None

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 10:
            raise ValueError("Mobile must be exactly 10 digits.")
        return value


class PatientRegisterResponse(BaseModel):
    patient_id: str
    token_number: str
    appointment_id: Optional[str] = None


class PatientSummary(BaseModel):
    id: str
    patient_id: str  # PAT-XXXXX
    full_name: str
    mobile: str
    last_visit: Optional[str] = None
    gene_test_status: str
    token_number: Optional[str] = None


class AppointmentRequest(BaseModel):
    patient_id: str
    hcp_id: str
    date: _date
    slot: str  # "HH:MM"
    # Optional visit / clinical info
    visit_type: Optional[str] = "Follow Up"
    chief_complaint: Optional[str] = None
    ongoing_treatment: Optional[str] = None
    known_allergies: Optional[str] = None
    past_medical_history: Optional[str] = None
    family_history: Optional[str] = None
    vitals: Optional[VitalsInput] = None


class AppointmentResponse(BaseModel):
    appointment_id: str
    token_number: str
    slot_datetime: str


class AppointmentStatusUpdate(BaseModel):
    status: Literal["Waiting", "In Consultation", "Done", "Cancelled"]


class HcpAvailabilityRequest(BaseModel):
    hcp_id: str
    day: str  # "Monday" … "Sunday"
    enabled: bool
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    slot_duration: int  # minutes


class HcpSummary(BaseModel):
    id: str
    name: str
    specialisation: str


class UploadUrlRequest(BaseModel):
    patient_id: str
    file_type: Literal["gene_test", "lab_report"]
    filename: str
    content_type: str


class UploadUrlResponse(BaseModel):
    presigned_url: str
    s3_key: str
    expires_in: int = 300


class ConfirmUploadRequest(BaseModel):
    patient_id: str
    s3_key: str
    file_type: Literal["gene_test", "lab_report"]
    genetic_consent: bool = False


# ── HCP schemas ───────────────────────────────────────────────────────────────

from typing import Any  # noqa: E402


class HcpProfileResponse(BaseModel):
    id: int
    hcp_id: Optional[str] = None
    full_name: str
    email: str
    mobile: Optional[str] = None
    degree: Optional[str] = None
    specialisation: Optional[str] = None
    experience: Optional[str] = None
    hospital: Optional[str] = None
    clinic_code: Optional[str] = None
    is_verified: bool = False


class DashboardStatsResponse(BaseModel):
    total_patients: int
    appointments_today: int
    pending_gene_reports: int
    unread_alerts: int
    appointments_today_delta: int = 0
    patients_this_week: int = 0


class HcpPatientSummary(BaseModel):
    id: str
    patient_id: str
    full_name: str
    mobile: str
    dob: Optional[str] = None
    gender: Optional[str] = None
    last_visit: Optional[str] = None
    gene_test_status: str
    risk_level: Optional[str] = None
    chief_complaint: Optional[str] = None


class HcpPatientDetail(BaseModel):
    id: str
    patient_id: str
    full_name: str
    mobile: str
    email: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    city: Optional[str] = None
    chief_complaint: Optional[str] = None
    ongoing_treatment: Optional[str] = None
    known_allergies: Optional[str] = None
    past_medical_history: Optional[str] = None
    family_history: Optional[str] = None
    gene_test_status: str
    vitals: Optional[dict[str, Any]] = None
    created_at: str


class DrugItemSchema(BaseModel):
    name: str
    dose: str
    frequency: str
    duration: str
    notes: Optional[str] = None


class CreatePrescriptionRequest(BaseModel):
    patient_id: str
    diagnosis: Optional[str] = None
    drugs: list[DrugItemSchema] = Field(default_factory=list, min_length=1)
    instructions: Optional[str] = None


class PrescriptionResponse(BaseModel):
    id: int
    prescription_ref: str
    patient_id: str
    diagnosis: Optional[str] = None
    drugs: list[dict[str, Any]]
    instructions: Optional[str] = None
    interaction_flags: list[dict[str, Any]] = []
    created_at: str


class GeneReportResponse(BaseModel):
    id: int
    patient_id: str
    patient_name: Optional[str] = None
    report_date: Optional[str] = None
    summary: Optional[str] = None
    risk_level: str
    processed_at: str


class OrderGeneTestRequest(BaseModel):
    notes: Optional[str] = None


class AlertResponse(BaseModel):
    id: int
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    alert_type: str
    severity: str
    message: str
    dismissed: bool
    created_at: str


class HcpTodayAppointment(BaseModel):
    appointment_ref: str
    token_number: Optional[str] = None
    patient_name: str
    patient_id: str
    mobile: str
    appointment_time: str   # HH:MM (IST)
    status: str


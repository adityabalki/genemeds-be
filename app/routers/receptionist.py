from __future__ import annotations

import os
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import boto3
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.db import get_connection
from app.schemas import (
    AppointmentRequest,
    AppointmentResponse,
    AppointmentStatusUpdate,
    ConfirmUploadRequest,
    HcpAvailabilityRequest,
    HcpSummary,
    PatientRegisterRequest,
    PatientRegisterResponse,
    PatientSummary,
    UploadUrlRequest,
    UploadUrlResponse,
)

router = APIRouter(prefix="/receptionist", tags=["receptionist"])
_bearer = HTTPBearer()
_IST = ZoneInfo("Asia/Kolkata")

_DAY_TO_INT: dict[str, int] = {
    name: i for i, name in enumerate(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    )
}
_INT_TO_DAY: dict[int, str] = {v: k for k, v in _DAY_TO_INT.items()}

_GENE_STATUS_DISPLAY = {
    "not_done": "Not Done",
    "uploaded": "Uploaded",
    "processed": "Processed",
}
_APPT_STATUS_DISPLAY = {
    "scheduled": "Waiting",
    "waiting": "Waiting",
    "in_consultation": "In Consultation",
    "done": "Done",
    "cancelled": "Cancelled",
}
_APPT_STATUS_DB = {
    "Waiting": "waiting",
    "In Consultation": "in_consultation",
    "Done": "done",
    "Cancelled": "cancelled",
}


# ── Auth dependency ───────────────────────────────────────────────────────────

def _current_receptionist(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    if payload.get("role") != "Receptionist":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, full_name, clinic_code FROM core.receptionists WHERE id = %(id)s",
                {"id": user_id},
            )
            rec = cur.fetchone()

    if not rec:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Receptionist not found.")

    if not rec["clinic_code"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No clinic assigned to this account.")

    return {
        "user_id": rec["id"],
        "full_name": rec["full_name"],
        "clinic_code": rec["clinic_code"],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_token(clinic_code: str, conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt FROM core.patient_registrations
            WHERE clinic_code = %(clinic_code)s
              AND (created_at AT TIME ZONE 'Asia/Kolkata')::date =
                  (NOW() AT TIME ZONE 'Asia/Kolkata')::date
            """,
            {"clinic_code": clinic_code},
        )
        row = cur.fetchone()
    count = int(row["cnt"]) if row else 0
    return f"T-{(count + 1):03d}"


def _next_appointment_token(clinic_code: str, hcp_pk: int, slot_dt_utc: datetime, conn: Any) -> str:
    """Token/queue number per HCP per day (IST)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt FROM core.appointments
            WHERE clinic_code = %(clinic)s
              AND hcp_id = %(hcp)s
              AND (appointment_datetime AT TIME ZONE 'Asia/Kolkata')::date =
                  (%(dt)s AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date
              AND status != 'cancelled'
            """,
            {"clinic": clinic_code, "hcp": hcp_pk, "dt": slot_dt_utc},
        )
        row = cur.fetchone()
    count = int(row["cnt"]) if row else 0
    return f"T-{(count + 1):03d}"


def _slot_utc_from_ist(d: date, hhmm: str) -> datetime:
    """Interpret the provided date+time as IST and convert to UTC for storage."""
    slot_local = datetime.combine(d, time.fromisoformat(hhmm)).replace(tzinfo=_IST)
    return slot_local.astimezone(timezone.utc)


def _ensure_not_past_ist(slot_dt_utc: datetime) -> None:
    now_ist = datetime.now(tz=_IST)
    slot_ist = slot_dt_utc.astimezone(_IST)
    if slot_ist.date() < now_ist.date():
        raise HTTPException(status_code=400, detail="Appointment date cannot be in the past.")


def _next_patient_id(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT nextval('core.patient_id_seq') AS seq")
        row = cur.fetchone()
    return f"PAT-{int(row['seq']):05d}"


def _resolve_hcp_pk(hcp_ref: str, conn: Any) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM core.hcps WHERE hcp_id = %(ref)s", {"ref": hcp_ref})
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"HCP '{hcp_ref}' not found.")
    return int(row["id"])


def _check_duplicate_appointment(patient_id: int, hcp_pk: int, slot_dt: datetime, conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM core.appointments
            WHERE patient_id = %(pid)s
              AND hcp_id = %(hcp)s
              AND (appointment_datetime AT TIME ZONE 'Asia/Kolkata')::date =
                  (%(dt)s AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date
              AND status != 'cancelled'
            """,
            {"pid": patient_id, "hcp": hcp_pk, "dt": slot_dt},
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=409,
                detail="This patient already has an appointment with the same doctor on this day.",
            )


def _next_appointment_id(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT nextval('core.appointment_id_seq') AS seq")
        row = cur.fetchone()
    return f"APT-{int(row['seq']):05d}"


def _s3_client():
    settings = get_settings()
    return boto3.client("s3", region_name=settings.aws_region)


def _s3_bucket() -> str:
    bucket = os.environ.get("S3_BUCKET_NAME", "").strip()
    if not bucket:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="S3 bucket not configured.")
    return bucket


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/patient/register", response_model=PatientRegisterResponse, status_code=201)
def register_patient(
    body: PatientRegisterRequest,
    ctx: dict = Depends(_current_receptionist),
) -> PatientRegisterResponse:
    clinic_code = ctx["clinic_code"]
    receptionist_id = ctx["user_id"]

    with get_connection() as conn:
        patient_id_str = _next_patient_id(conn)
        registration_token = _next_token(clinic_code, conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.patient_registrations (
                    patient_id, clinic_code, full_name, mobile, email,
                    date_of_birth, gender, city, visit_type,
                    chief_complaint, ongoing_treatment, known_allergies,
                    past_medical_history, family_history, registered_by, token_number
                ) VALUES (
                    %(patient_id)s, %(clinic_code)s, %(full_name)s, %(mobile)s, %(email)s,
                    %(dob)s, %(gender)s, %(city)s, %(visit_type)s,
                    %(chief_complaint)s, %(ongoing_treatment)s, %(known_allergies)s,
                    %(past_medical_history)s, %(family_history)s, %(registered_by)s, %(token_number)s
                ) RETURNING id
                """,
                {
                    "patient_id": patient_id_str,
                    "clinic_code": clinic_code,
                    "full_name": body.full_name,
                    "mobile": body.mobile,
                    "email": body.email,
                    "dob": body.dob,
                    "gender": body.gender,
                    "city": body.city,
                    "visit_type": body.visit_type or "First Visit",
                    "chief_complaint": body.chief_complaint,
                    "ongoing_treatment": body.ongoing_treatment,
                    "known_allergies": body.known_allergies,
                    "past_medical_history": body.past_medical_history,
                    "family_history": body.family_history,
                    "registered_by": receptionist_id,
                    "token_number": registration_token,
                },
            )
            row = cur.fetchone()

        internal_id: int = row["id"]

        if body.vitals and any(v is not None for v in body.vitals.model_dump().values()):
            v = body.vitals
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO core.patient_vitals
                        (patient_id, bp_systolic, bp_diastolic, weight_kg, o2_level, notes, recorded_by)
                    VALUES (%(pid)s, %(bps)s, %(bpd)s, %(wt)s, %(o2)s, %(notes)s, %(by)s)
                    """,
                    {
                        "pid": internal_id,
                        "bps": v.bp_systolic,
                        "bpd": v.bp_diastolic,
                        "wt": v.weight_kg,
                        "o2": v.o2_level,
                        "notes": v.notes,
                        "by": receptionist_id,
                    },
                )

        appointment_id = None
        appointment_token: str | None = None
        if body.appointment and body.appointment.hcp_id and body.appointment.date and body.appointment.slot:
            apt = body.appointment
            hcp_pk = _resolve_hcp_pk(apt.hcp_id, conn)
            slot_dt = _slot_utc_from_ist(apt.date, apt.slot)
            _ensure_not_past_ist(slot_dt)
            _check_duplicate_appointment(internal_id, hcp_pk, slot_dt, conn)
            apt_ref = _next_appointment_id(conn)
            appointment_token = _next_appointment_token(clinic_code, hcp_pk, slot_dt, conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO core.appointments
                        (appointment_ref, patient_id, hcp_id, clinic_code, appointment_datetime, token_number, visit_type, booked_by)
                    VALUES (%(ref)s, %(pid)s, %(hcp)s, %(clinic)s, %(dt)s, %(tok)s, %(vt)s, %(by)s)
                    RETURNING appointment_ref
                    """,
                    {
                        "ref": apt_ref,
                        "pid": internal_id,
                        "hcp": hcp_pk,
                        "clinic": clinic_code,
                        "dt": slot_dt,
                        "tok": appointment_token,
                        "vt": body.visit_type or "First Visit",
                        "by": receptionist_id,
                    },
                )
                apt_row = cur.fetchone()
                appointment_id = apt_row["appointment_ref"] if apt_row else None

        conn.commit()

    return PatientRegisterResponse(
        patient_id=patient_id_str,
        token_number=appointment_token or registration_token,
        appointment_id=appointment_id,
    )


@router.get("/patient/search", response_model=list[PatientSummary])
def search_patient(
    mobile: str | None = Query(default=None),
    name: str | None = Query(default=None),
    ctx: dict = Depends(_current_receptionist),
) -> list[PatientSummary]:
    if not mobile and not name:
        raise HTTPException(status_code=400, detail="Provide mobile or name query param.")

    clinic_code = ctx["clinic_code"]
    params: dict[str, Any] = {"clinic_code": clinic_code}

    if mobile:
        where = "mobile LIKE %(q)s"
        params["q"] = f"%{mobile}%"
    else:
        where = "lower(full_name) LIKE %(q)s"
        params["q"] = f"%{name.lower()}%"  # type: ignore[union-attr]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, patient_id, full_name, mobile, gene_test_status, token_number,
                       created_at::date AS last_visit
                FROM core.patient_registrations
                WHERE clinic_code = %(clinic_code)s AND {where}
                ORDER BY created_at DESC
                LIMIT 50
                """,
                params,
            )
            rows = cur.fetchall()

    return [
        PatientSummary(
            id=str(r["id"]),   # integer PK — stringified for API consistency
            patient_id=r["patient_id"],
            full_name=r["full_name"],
            mobile=r["mobile"],
            last_visit=str(r["last_visit"]) if r["last_visit"] else None,
            gene_test_status=_GENE_STATUS_DISPLAY.get(r["gene_test_status"] or "not_done", "Not Done"),
            token_number=r["token_number"],
        )
        for r in rows
    ]


@router.post("/appointment", response_model=AppointmentResponse, status_code=201)
def book_appointment(
    body: AppointmentRequest,
    ctx: dict = Depends(_current_receptionist),
) -> AppointmentResponse:
    clinic_code = ctx["clinic_code"]
    receptionist_id = ctx["user_id"]
    slot_dt = _slot_utc_from_ist(body.date, body.slot)
    _ensure_not_past_ist(slot_dt)

    with get_connection() as conn:
        hcp_pk = _resolve_hcp_pk(body.hcp_id, conn)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM core.appointments WHERE hcp_id = %(hcp)s AND appointment_datetime = %(dt)s",
                {"hcp": hcp_pk, "dt": slot_dt},
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="This slot is already booked.")

        try:
            patient_pk = int(body.patient_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid patient_id.")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM core.patient_registrations WHERE id = %(pid)s AND clinic_code = %(clinic)s",
                {"pid": patient_pk, "clinic": clinic_code},
            )
            patient_row = cur.fetchone()
        if not patient_row:
            raise HTTPException(status_code=404, detail="Patient not found.")

        _check_duplicate_appointment(patient_pk, hcp_pk, slot_dt, conn)

        token_number = _next_appointment_token(clinic_code, hcp_pk, slot_dt, conn)
        apt_ref = _next_appointment_id(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.appointments
                    (appointment_ref, patient_id, hcp_id, clinic_code, appointment_datetime, token_number, booked_by)
                VALUES (%(ref)s, %(pid)s, %(hcp)s, %(clinic)s, %(dt)s, %(tok)s, %(by)s)
                RETURNING appointment_ref
                """,
                {
                    "ref": apt_ref,
                    "pid": patient_pk,
                    "hcp": hcp_pk,
                    "clinic": clinic_code,
                    "dt": slot_dt,
                    "tok": token_number,
                    "by": receptionist_id,
                },
            )
            row = cur.fetchone()
        conn.commit()

    return AppointmentResponse(
        appointment_id=row["appointment_ref"],
        token_number=token_number,
        slot_datetime=slot_dt.isoformat(),
    )


@router.get("/appointments/today")
def today_appointments(ctx: dict = Depends(_current_receptionist)) -> dict:
    clinic_code = ctx["clinic_code"]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.appointment_ref, a.token_number, a.appointment_datetime, a.status,
                       p.full_name AS patient_name, p.mobile,
                       h.full_name AS hcp_name
                FROM core.appointments a
                JOIN core.patient_registrations p ON p.id = a.patient_id
                JOIN core.hcps h ON h.id = a.hcp_id
                WHERE a.clinic_code = %(clinic)s
                  AND (a.appointment_datetime AT TIME ZONE 'Asia/Kolkata')::date =
                      (NOW() AT TIME ZONE 'Asia/Kolkata')::date
                ORDER BY a.appointment_datetime ASC
                """,
                {"clinic": clinic_code},
            )
            rows = cur.fetchall()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM core.patient_registrations
                WHERE clinic_code = %(clinic_code)s
                  AND (created_at AT TIME ZONE 'Asia/Kolkata')::date =
                      (NOW() AT TIME ZONE 'Asia/Kolkata')::date
                """,
                {"clinic_code": clinic_code},
            )
            reg_row = cur.fetchone()

    registrations = int(reg_row["cnt"]) if reg_row else 0
    waiting = sum(1 for r in rows if r["status"] in ("waiting", "scheduled"))

    return {
        "registrations": registrations,
        "appointment_count": len(rows),
        "waiting": waiting,
        "appointments": [
            {
                "id": r["appointment_ref"] or str(r["id"]),
                "token": r["token_number"],
                "patient_name": r["patient_name"],
                "mobile": r["mobile"],
                "hcp_name": r["hcp_name"],
                "appointment_time": r["appointment_datetime"].astimezone(_IST).strftime("%H:%M") if r["appointment_datetime"] else "",
                "appointment_date": r["appointment_datetime"].astimezone(_IST).strftime("%d %b %Y") if r["appointment_datetime"] else "",
                "status": _APPT_STATUS_DISPLAY.get(r["status"] or "scheduled", "Waiting"),
            }
            for r in rows
        ],
    }


@router.patch("/appointment/{appointment_id}/status", status_code=200)
def update_appointment_status(
    appointment_id: str,
    body: AppointmentStatusUpdate,
    ctx: dict = Depends(_current_receptionist),
) -> dict:
    clinic_code = ctx["clinic_code"]
    db_status = _APPT_STATUS_DB.get(body.status, "waiting")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE core.appointments SET status = %(status)s
                WHERE appointment_ref = %(id)s AND clinic_code = %(clinic)s
                RETURNING appointment_ref
                """,
                {"status": db_status, "id": appointment_id, "clinic": clinic_code},
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    return {"status": "updated"}


@router.get("/hcps", response_model=list[HcpSummary])
def list_hcps(ctx: dict = Depends(_current_receptionist)) -> list[HcpSummary]:
    clinic_code = ctx["clinic_code"]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT hcp_id, full_name, COALESCE(specialisation, '') AS specialisation FROM core.hcps
                WHERE LOWER(TRIM(clinic_code)) = LOWER(TRIM(%(clinic_code)s))
                   OR NULLIF(TRIM(COALESCE(clinic_code, '')), '') IS NULL
                ORDER BY clinic_code NULLS LAST, full_name
                """,
                {"clinic_code": clinic_code},
            )
            rows = cur.fetchall()

    return [
        HcpSummary(id=r["hcp_id"], name=r["full_name"], specialisation=r["specialisation"])
        for r in rows if r["hcp_id"]
    ]


@router.post("/hcp/availability", status_code=200)
def set_hcp_availability(
    body: HcpAvailabilityRequest,
    ctx: dict = Depends(_current_receptionist),
) -> dict:
    clinic_code = ctx["clinic_code"]
    day_int = _DAY_TO_INT.get(body.day)
    if day_int is None:
        raise HTTPException(status_code=400, detail=f"Invalid day: {body.day}")

    with get_connection() as conn:
        hcp_pk = _resolve_hcp_pk(body.hcp_id, conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.hcp_availability
                    (hcp_id, clinic_code, day_of_week, start_time, end_time, slot_duration_minutes, is_active)
                VALUES (%(hcp)s, %(clinic)s, %(day)s, %(start)s, %(end)s, %(dur)s, %(active)s)
                ON CONFLICT (hcp_id, clinic_code, day_of_week) DO UPDATE SET
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time,
                    slot_duration_minutes = EXCLUDED.slot_duration_minutes,
                    is_active = EXCLUDED.is_active
                """,
                {
                    "hcp": hcp_pk,
                    "clinic": clinic_code,
                    "day": day_int,
                    "start": body.start_time,
                    "end": body.end_time,
                    "dur": body.slot_duration,
                    "active": body.enabled,
                },
            )
        conn.commit()

    return {"status": "saved"}


@router.get("/hcp/availability/{hcp_id}")
def get_hcp_availability(
    hcp_id: str,
    ctx: dict = Depends(_current_receptionist),
) -> dict:
    clinic_code = ctx["clinic_code"]

    with get_connection() as conn:
        hcp_pk = _resolve_hcp_pk(hcp_id, conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT day_of_week, start_time, end_time, slot_duration_minutes, is_active
                FROM core.hcp_availability
                WHERE hcp_id = %(hcp)s AND clinic_code = %(clinic)s
                """,
                {"hcp": hcp_pk, "clinic": clinic_code},
            )
            rows = cur.fetchall()

    result: dict[str, Any] = {}
    for r in rows:
        day_name = _INT_TO_DAY.get(r["day_of_week"], str(r["day_of_week"]))
        result[day_name] = {
            "enabled": r["is_active"],
            "start_time": str(r["start_time"])[:5],
            "end_time": str(r["end_time"])[:5],
            "slot_duration": r["slot_duration_minutes"],
        }

    return result


@router.get("/hcp/slots")
def get_hcp_slots(
    hcp_id: str = Query(),
    date: str = Query(),
    ctx: dict = Depends(_current_receptionist),
) -> dict:
    clinic_code = ctx["clinic_code"]

    try:
        req_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD.")

    day_int = req_date.weekday()  # 0=Monday

    with get_connection() as conn:
        hcp_pk = _resolve_hcp_pk(hcp_id, conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT start_time, end_time, slot_duration_minutes
                FROM core.hcp_availability
                WHERE hcp_id = %(hcp)s AND clinic_code = %(clinic)s
                  AND day_of_week = %(day)s AND is_active = TRUE
                """,
                {"hcp": hcp_pk, "clinic": clinic_code, "day": day_int},
            )
            avail = cur.fetchone()

        if not avail:
            return {"slots": []}

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT appointment_datetime FROM core.appointments
                WHERE hcp_id = %(hcp)s AND appointment_datetime::date = %(date)s
                  AND status NOT IN ('cancelled')
                """,
                {"hcp": int(hcp_id), "date": req_date},
            )
            booked_rows = cur.fetchall()

    booked_times = {r["appointment_datetime"].strftime("%H:%M") for r in booked_rows}

    start = datetime.combine(req_date, avail["start_time"])
    end = datetime.combine(req_date, avail["end_time"])
    duration = avail["slot_duration_minutes"]

    slots: list[str] = []
    current = start
    while current < end:
        slot_str = current.strftime("%H:%M")
        if slot_str not in booked_times:
            slots.append(slot_str)
        current += timedelta(minutes=duration)

    return {"slots": slots}


@router.post("/patient/upload-url", response_model=UploadUrlResponse)
def get_upload_url(
    body: UploadUrlRequest,
    ctx: dict = Depends(_current_receptionist),
) -> UploadUrlResponse:
    clinic_code = ctx["clinic_code"]

    try:
        patient_pk = int(body.patient_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid patient_id.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM core.patient_registrations WHERE id = %(pid)s AND clinic_code = %(clinic)s",
                {"pid": patient_pk, "clinic": clinic_code},
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Patient not found.")

    s3_key = f"patients/{patient_pk}/{body.file_type}/{secrets.token_hex(8)}/{body.filename}"
    bucket = _s3_bucket()
    client = _s3_client()

    presigned_url = client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": s3_key, "ContentType": body.content_type},
        ExpiresIn=300,
    )

    return UploadUrlResponse(presigned_url=presigned_url, s3_key=s3_key, expires_in=300)


@router.post("/patient/confirm-upload", status_code=201)
def confirm_upload(
    body: ConfirmUploadRequest,
    ctx: dict = Depends(_current_receptionist),
) -> dict:
    clinic_code = ctx["clinic_code"]
    receptionist_id = ctx["user_id"]

    if body.file_type == "gene_test" and not body.genetic_consent:
        raise HTTPException(
            status_code=400,
            detail="Genetic consent is required for gene test upload under DPDP Act 2023.",
        )

    try:
        patient_pk = int(body.patient_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid patient_id.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM core.patient_registrations WHERE id = %(pid)s AND clinic_code = %(clinic)s",
                {"pid": patient_pk, "clinic": clinic_code},
            )
            patient_row = cur.fetchone()
        if not patient_row:
            raise HTTPException(status_code=404, detail="Patient not found.")

        internal_id = patient_row["id"]

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.patient_documents
                    (patient_id, s3_key, file_type, uploaded_by)
                VALUES (%(pid)s, %(key)s, %(ftype)s, %(by)s)
                """,
                {
                    "pid": internal_id,
                    "key": body.s3_key,
                    "ftype": body.file_type,
                    "by": receptionist_id,
                },
            )

        if body.file_type == "gene_test" and body.genetic_consent:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO core.patient_consents
                        (patient_id, consent_type, consented_by_role, consented_by_user_id, clinic_code)
                    VALUES (%(pid)s, 'genetic_data_processing', 'receptionist', %(by)s, %(clinic)s)
                    """,
                    {"pid": internal_id, "by": receptionist_id, "clinic": clinic_code},
                )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE core.patient_registrations SET gene_test_status = 'uploaded'
                    WHERE id = %(pid)s
                    """,
                    {"pid": internal_id},
                )

        conn.commit()

    return {"status": "confirmed"}

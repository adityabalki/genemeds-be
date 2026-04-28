from __future__ import annotations

import json as _json
from datetime import date
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.db import get_connection
from app.schemas import (
    AlertResponse,
    CreatePrescriptionRequest,
    DashboardStatsResponse,
    GeneReportResponse,
    HcpPatientDetail,
    HcpPatientSummary,
    HcpProfileResponse,
    OrderGeneTestRequest,
    PrescriptionResponse,
)

router = APIRouter(prefix="/hcp", tags=["hcp"])
_bearer = HTTPBearer()


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")


def _current_hcp(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    payload = _decode_token(credentials.credentials)
    if payload.get("role") != "HCP":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="HCP access only.")
    return payload


# ─── Profile ──────────────────────────────────────────────────────────────────

@router.get("/me", response_model=HcpProfileResponse)
def get_me(hcp: dict[str, Any] = Depends(_current_hcp)) -> HcpProfileResponse:
    hcp_id = int(hcp["sub"])
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, hcp_id, full_name, email, mobile, degree,
                       specialisation, experience, hospital, clinic_code, is_verified
                FROM core.hcps WHERE id = %(id)s
                """,
                {"id": hcp_id},
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="HCP not found.")
    return HcpProfileResponse(**row)


# ─── Dashboard stats ──────────────────────────────────────────────────────────

@router.get("/dashboard/stats", response_model=DashboardStatsResponse)
def dashboard_stats(hcp: dict[str, Any] = Depends(_current_hcp)) -> DashboardStatsResponse:
    hcp_id = int(hcp["sub"])
    today = date.today()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT patient_id) FROM core.appointments WHERE hcp_id = %(id)s",
                {"id": hcp_id},
            )
            total_patients = int((cur.fetchone() or {}).get("count", 0) or 0)

            cur.execute(
                """
                SELECT COUNT(*) FROM core.appointments
                WHERE hcp_id = %(id)s
                  AND CAST(appointment_datetime AT TIME ZONE 'Asia/Kolkata' AS date) = %(today)s
                  AND status != 'cancelled'
                """,
                {"id": hcp_id, "today": today},
            )
            appointments_today = int((cur.fetchone() or {}).get("count", 0) or 0)

            cur.execute(
                """
                SELECT COUNT(*)
                FROM core.patient_registrations pr
                JOIN core.appointments a ON a.patient_id = pr.id
                WHERE a.hcp_id = %(id)s AND pr.gene_test_status = 'uploaded'
                """,
                {"id": hcp_id},
            )
            pending_gene_reports = int((cur.fetchone() or {}).get("count", 0) or 0)

            cur.execute(
                "SELECT COUNT(*) FROM core.hcp_alerts WHERE hcp_id = %(id)s AND is_dismissed = FALSE",
                {"id": hcp_id},
            )
            unread_alerts = int((cur.fetchone() or {}).get("count", 0) or 0)

    return DashboardStatsResponse(
        total_patients=total_patients,
        appointments_today=appointments_today,
        pending_gene_reports=pending_gene_reports,
        unread_alerts=unread_alerts,
    )


# ─── Patients ─────────────────────────────────────────────────────────────────

@router.get("/patients", response_model=list[HcpPatientSummary])
def list_patients(
    search: str | None = Query(default=None),
    gene_status: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> list[HcpPatientSummary]:
    hcp_id = int(hcp["sub"])

    where_clauses = ["a.hcp_id = %(hcp_id)s"]
    params: dict[str, Any] = {"hcp_id": hcp_id, "skip": skip, "limit": limit}

    if search:
        where_clauses.append(
            "(pr.full_name ILIKE %(search)s OR pr.mobile ILIKE %(search)s "
            "OR pr.patient_id ILIKE %(search)s)"
        )
        params["search"] = f"%{search}%"

    if gene_status:
        where_clauses.append("pr.gene_test_status = %(gene_status)s")
        params["gene_status"] = gene_status

    if risk_level:
        where_clauses.append("gr.risk_level = %(risk_level)s")
        params["risk_level"] = risk_level

    where_sql = " AND ".join(where_clauses)

    sql = f"""
        WITH latest_appt AS (
            SELECT patient_id,
                   MAX(appointment_datetime) AS last_appt_dt
            FROM core.appointments
            WHERE hcp_id = %(hcp_id)s
            GROUP BY patient_id
        ),
        latest_gene AS (
            SELECT DISTINCT ON (patient_id) patient_id, risk_level
            FROM core.gene_reports
            ORDER BY patient_id, processed_at DESC
        )
        SELECT DISTINCT
            pr.id::text            AS id,
            pr.patient_id,
            pr.full_name,
            pr.mobile,
            pr.date_of_birth::text AS dob,
            pr.gender,
            la.last_appt_dt::text  AS last_visit,
            pr.gene_test_status,
            gr.risk_level,
            pr.chief_complaint
        FROM core.appointments a
        JOIN core.patient_registrations pr ON pr.id = a.patient_id
        LEFT JOIN latest_appt la ON la.patient_id = pr.id
        LEFT JOIN latest_gene  gr ON gr.patient_id = pr.id
        WHERE {where_sql}
        ORDER BY la.last_appt_dt DESC NULLS LAST
        OFFSET %(skip)s LIMIT %(limit)s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [HcpPatientSummary(**r) for r in rows]


@router.get("/patients/{patient_id}", response_model=HcpPatientDetail)
def get_patient(
    patient_id: str,
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> HcpPatientDetail:
    hcp_id = int(hcp["sub"])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pr.id::text, pr.patient_id, pr.full_name, pr.mobile, pr.email,
                       pr.date_of_birth::text AS dob, pr.gender, pr.city,
                       pr.chief_complaint, pr.ongoing_treatment, pr.known_allergies,
                       pr.past_medical_history, pr.family_history,
                       pr.gene_test_status, pr.created_at::text
                FROM core.patient_registrations pr
                JOIN core.appointments a ON a.patient_id = pr.id AND a.hcp_id = %(hcp_id)s
                WHERE pr.patient_id = %(patient_id)s
                LIMIT 1
                """,
                {"hcp_id": hcp_id, "patient_id": patient_id},
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Patient not found.")

            cur.execute(
                """
                SELECT bp_systolic, bp_diastolic, weight_kg::float,
                       o2_level::float, notes
                FROM core.patient_vitals
                WHERE patient_id = %(pid)s
                ORDER BY recorded_at DESC
                LIMIT 1
                """,
                {"pid": int(row["id"])},
            )
            vitals_row = cur.fetchone()

    data = dict(row)
    data["vitals"] = dict(vitals_row) if vitals_row else None
    return HcpPatientDetail(**data)


# ─── Prescriptions ────────────────────────────────────────────────────────────

@router.post("/prescriptions", response_model=PrescriptionResponse, status_code=201)
def create_prescription(
    body: CreatePrescriptionRequest,
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> PrescriptionResponse:
    hcp_id = int(hcp["sub"])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pr.id, pr.patient_id, a.clinic_code
                FROM core.patient_registrations pr
                JOIN core.appointments a ON a.patient_id = pr.id AND a.hcp_id = %(hcp_id)s
                WHERE pr.patient_id = %(patient_id)s
                LIMIT 1
                """,
                {"hcp_id": hcp_id, "patient_id": body.patient_id},
            )
            pat = cur.fetchone()
            if not pat:
                raise HTTPException(status_code=404, detail="Patient not found.")

            drugs_json = _json.dumps([d.model_dump() for d in body.drugs])

            cur.execute(
                """
                INSERT INTO core.prescriptions
                    (prescription_ref, patient_id, hcp_id, clinic_code,
                     diagnosis, drugs, instructions)
                VALUES (
                    'RX-' || LPAD(nextval('core.prescription_id_seq')::text, 5, '0'),
                    %(patient_id)s, %(hcp_id)s, %(clinic_code)s,
                    %(diagnosis)s, %(drugs)s::jsonb, %(instructions)s
                )
                RETURNING id, prescription_ref, patient_id, diagnosis,
                          drugs, instructions, interaction_flags,
                          created_at::text
                """,
                {
                    "patient_id": pat["id"],
                    "hcp_id": hcp_id,
                    "clinic_code": pat["clinic_code"],
                    "diagnosis": body.diagnosis,
                    "drugs": drugs_json,
                    "instructions": body.instructions,
                },
            )
            rx = dict(cur.fetchone())
        conn.commit()

    rx["patient_id"] = body.patient_id
    return PrescriptionResponse(**rx)


@router.get("/patients/{patient_id}/prescriptions", response_model=list[PrescriptionResponse])
def get_prescriptions_for_patient(
    patient_id: str,
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> list[PrescriptionResponse]:
    hcp_id = int(hcp["sub"])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rx.id, rx.prescription_ref, pr.patient_id,
                       rx.diagnosis, rx.drugs, rx.instructions,
                       rx.interaction_flags, rx.created_at::text
                FROM core.prescriptions rx
                JOIN core.patient_registrations pr ON pr.id = rx.patient_id
                WHERE pr.patient_id = %(patient_id)s AND rx.hcp_id = %(hcp_id)s
                ORDER BY rx.created_at DESC
                """,
                {"patient_id": patient_id, "hcp_id": hcp_id},
            )
            rows = cur.fetchall()
    return [PrescriptionResponse(**r) for r in rows]


# ─── Gene reports ─────────────────────────────────────────────────────────────

@router.get("/patients/{patient_id}/gene-report", response_model=GeneReportResponse | None)
def get_gene_report_for_patient(
    patient_id: str,
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> GeneReportResponse | None:
    hcp_id = int(hcp["sub"])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT gr.id, pr.patient_id, pr.full_name AS patient_name,
                       gr.report_date::text, gr.summary, gr.risk_level,
                       gr.processed_at::text
                FROM core.gene_reports gr
                JOIN core.patient_registrations pr ON pr.id = gr.patient_id
                JOIN core.appointments a ON a.patient_id = pr.id AND a.hcp_id = %(hcp_id)s
                WHERE pr.patient_id = %(patient_id)s
                ORDER BY gr.processed_at DESC
                LIMIT 1
                """,
                {"patient_id": patient_id, "hcp_id": hcp_id},
            )
            row = cur.fetchone()
    if not row:
        return None
    return GeneReportResponse(**row)


@router.post("/patients/{patient_id}/gene-test", status_code=200)
def order_gene_test(
    patient_id: str,
    body: OrderGeneTestRequest,
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> dict[str, str]:
    hcp_id = int(hcp["sub"])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE core.patient_registrations
                SET gene_test_status = 'uploaded', updated_at = NOW()
                WHERE patient_id = %(patient_id)s
                  AND EXISTS (
                      SELECT 1 FROM core.appointments a
                      WHERE a.patient_id = core.patient_registrations.id
                        AND a.hcp_id = %(hcp_id)s
                  )
                RETURNING id
                """,
                {"patient_id": patient_id, "hcp_id": hcp_id},
            )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Patient not found.")

            cur.execute(
                """
                INSERT INTO core.gene_reports
                    (patient_id, hcp_id, summary, risk_level, ordered_by)
                VALUES (%(pat_id)s, %(hcp_id)s, %(notes)s, 'unknown', %(hcp_id)s)
                """,
                {
                    "pat_id": updated["id"],
                    "hcp_id": hcp_id,
                    "notes": body.notes or "Gene test ordered",
                },
            )
        conn.commit()

    return {"message": "Gene test ordered successfully."}


@router.get("/gene-reports", response_model=list[GeneReportResponse])
def list_gene_reports(
    risk_level: str | None = Query(default=None),
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> list[GeneReportResponse]:
    hcp_id = int(hcp["sub"])

    params: dict[str, Any] = {"hcp_id": hcp_id}
    extra = ""
    if risk_level:
        extra = "AND gr.risk_level = %(risk_level)s"
        params["risk_level"] = risk_level

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT gr.id, pr.patient_id, pr.full_name AS patient_name,
                       gr.report_date::text, gr.summary, gr.risk_level,
                       gr.processed_at::text
                FROM core.gene_reports gr
                JOIN core.patient_registrations pr ON pr.id = gr.patient_id
                WHERE gr.hcp_id = %(hcp_id)s {extra}
                ORDER BY gr.processed_at DESC
                LIMIT 200
                """,
                params,
            )
            rows = cur.fetchall()
    return [GeneReportResponse(**r) for r in rows]


# ─── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=list[AlertResponse])
def list_alerts(
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> list[AlertResponse]:
    hcp_id = int(hcp["sub"])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT al.id,
                       pr.patient_id,
                       pr.full_name AS patient_name,
                       al.alert_type, al.severity, al.message,
                       al.is_dismissed, al.created_at::text
                FROM core.hcp_alerts al
                LEFT JOIN core.patient_registrations pr ON pr.id = al.patient_id
                WHERE al.hcp_id = %(hcp_id)s AND al.is_dismissed = FALSE
                ORDER BY
                    CASE al.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    al.created_at DESC
                LIMIT 100
                """,
                {"hcp_id": hcp_id},
            )
            rows = cur.fetchall()
    return [AlertResponse(**r) for r in rows]


@router.patch("/alerts/{alert_id}/dismiss", status_code=200)
def dismiss_alert(
    alert_id: int,
    hcp: dict[str, Any] = Depends(_current_hcp),
) -> dict[str, str]:
    hcp_id = int(hcp["sub"])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE core.hcp_alerts
                SET is_dismissed = TRUE
                WHERE id = %(alert_id)s AND hcp_id = %(hcp_id)s
                RETURNING id
                """,
                {"alert_id": alert_id, "hcp_id": hcp_id},
            )
            updated = cur.fetchone()
        conn.commit()

    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return {"message": "Alert dismissed."}

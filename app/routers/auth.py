from __future__ import annotations

from fastapi import APIRouter

from app.schemas import (
    HcpRegisterRequest,
    LabRegisterRequest,
    LoginRequest,
    LoginResponse,
    RegistrationResponse,
    ReceptionistRegisterRequest,
)
from app.service import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/admin/login", response_model=LoginResponse)
def admin_login(payload: LoginRequest) -> LoginResponse:
    return LoginResponse(**authenticate_user("admin", payload.email, payload.password))


@router.post("/hcp/register", response_model=RegistrationResponse, status_code=201)
def hcp_register(payload: HcpRegisterRequest) -> RegistrationResponse:
    return RegistrationResponse(**register_user("hcp", payload.model_dump()))


@router.post("/hcp/login", response_model=LoginResponse)
def hcp_login(payload: LoginRequest) -> LoginResponse:
    return LoginResponse(**authenticate_user("hcp", payload.email, payload.password))


@router.post("/receptionist/register", response_model=RegistrationResponse, status_code=201)
def receptionist_register(payload: ReceptionistRegisterRequest) -> RegistrationResponse:
    return RegistrationResponse(**register_user("receptionist", payload.model_dump()))


@router.post("/receptionist/login", response_model=LoginResponse)
def receptionist_login(payload: LoginRequest) -> LoginResponse:
    return LoginResponse(**authenticate_user("receptionist", payload.email, payload.password))


@router.post("/lab/register", response_model=RegistrationResponse, status_code=201)
def lab_register(payload: LabRegisterRequest) -> RegistrationResponse:
    return RegistrationResponse(**register_user("lab", payload.model_dump()))


@router.post("/lab/login", response_model=LoginResponse)
def lab_login(payload: LoginRequest) -> LoginResponse:
    return LoginResponse(**authenticate_user("lab", payload.email, payload.password))


@router.post("/patient/login", response_model=LoginResponse)
def patient_login(payload: LoginRequest) -> LoginResponse:
    return LoginResponse(**authenticate_user("patient", payload.email, payload.password))


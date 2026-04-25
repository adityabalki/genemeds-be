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

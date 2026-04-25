# Genemeds Backend

FastAPI application packaged for AWS Lambda via Mangum. It supports the existing frontend authentication contract:

- `POST /auth/admin/login`
- `POST /auth/hcp/register`
- `POST /auth/hcp/login`
- `POST /auth/receptionist/register`
- `POST /auth/receptionist/login`
- `POST /auth/lab/register`
- `POST /auth/lab/login`
- `POST /auth/patient/login`

## Local setup

1. Create and activate a Python 3.11 virtual environment.
2. Install dependencies:
   - `pip install -e .[dev]`
3. Copy `.env.example` to `.env` and fill only non-secret values.
4. Export `JWT_SECRET` securely in your shell or Lambda environment.

## Run locally

`uvicorn app.main:app --reload`

## Run tests

`pytest`

## Lambda handler

Use `app.main.handler` as the Lambda entry point.


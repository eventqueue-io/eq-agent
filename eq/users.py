#     Copyright 2023 EventQueue.io
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#

import asyncio
import sqlite3
import stat
import subprocess
from base64 import b64encode
from json import JSONDecodeError
from os import path, chmod, remove
import logging
from typing import Optional, Any
from uuid import UUID

from cryptography.exceptions import UnsupportedAlgorithm
from fastapi import APIRouter, status, HTTPException, Query
from pydantic import BaseModel, EmailStr, field_serializer

from calls import sse_out
from globals import settings, client, get_credentials, get_private_key, raise_for_status

router = APIRouter(prefix="/api/users")
logger = logging.getLogger(__name__)


class NewUserRequest(BaseModel):
    email: EmailStr

    @field_serializer("email")
    def serialize_body(self, email: EmailStr, _info: Any) -> str:
        return str(email)


class PersonalDetails(BaseModel):
    verified: bool


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(request: NewUserRequest) -> None:
    response = client.post(
        f"{settings.central_url}api/users",
        json={"email": request.email},
    )

    if response.status_code == status.HTTP_403_FORBIDDEN:
        body = response.json()
        if "detail" in body and "ref" in body["detail"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "New users are not allowed",
                    "ref": body["detail"]["ref"],
                },
            )

    raise_for_status(response)


@router.get("/me", status_code=status.HTTP_200_OK)
def me() -> PersonalDetails:
    if all(
        [
            path.exists(x)
            for x in (
                f"{settings.config_path}/credentials",
                f"{settings.config_path}/public.pem",
                f"{settings.config_path}/private.pem",
            )
        ]
    ):
        return PersonalDetails(verified=True)
    else:
        return PersonalDetails(verified=False)


def save_credentials(body: dict[str, str]) -> Optional[str]:
    try:
        key = body["api_key"]
        secret = body["api_secret"]
        file_path = f"{settings.config_path}/credentials"
        with open(file_path, "w") as f:
            f.write(f"{key}\n{secret}")
        chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)
        return None
    except (KeyError, OSError, TypeError) as e:
        logger.error(f"Error saving credentials: {e}")
        return str(e)


@router.get("/queue/{queue_ref}", status_code=status.HTTP_200_OK)
def confirm_queue(queue_ref: UUID) -> None:
    response = client.get(f"{settings.central_url}api/users/queue/{queue_ref}")
    raise_for_status(response)


@router.get("/verify/{token}", status_code=status.HTTP_200_OK)
def verify(token: UUID) -> None:
    response = client.get(f"{settings.central_url}api/users/verify/{token}")
    raise_for_status(response)

    try:
        saved = save_credentials(response.json())
        if saved:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=saved
            )
    except JSONDecodeError as e:
        logger.error(f"Error decoding credentials: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


def generate_keys() -> None:
    if path.exists(f"{settings.config_path}/public.pem"):
        remove(f"{settings.config_path}/public.pem")
    if path.exists(f"{settings.config_path}/private.pem"):
        remove(f"{settings.config_path}/private.pem")

    try:
        subprocess.run(
            [
                "/usr/bin/openssl",
                "genrsa",
                "-out",
                f"{settings.config_path}/private.pem",
                "2048",
            ],
            check=True,
        )
        subprocess.run(
            [
                "openssl",
                "rsa",
                "-in",
                f"{settings.config_path}/private.pem",
                "-pubout",
                "-out",
                f"{settings.config_path}/public.pem",
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
    chmod(f"{settings.config_path}/private.pem", stat.S_IRUSR | stat.S_IWUSR)


@router.post("/key", status_code=status.HTTP_200_OK)
async def create_upload_keys(force: bool = Query(False)) -> None:
    if (
        path.exists(f"{settings.config_path}/public.pem")
        or path.exists(f"{settings.config_path}/private.pem")
    ) and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Public and/or private key(s) already exist",
        )

    generate_keys()

    with open(f"{settings.config_path}/public.pem", "rb") as public_key_file:
        content: bytes = public_key_file.read()

    key, secret = get_credentials()

    response = client.post(
        f"{settings.central_url}api/users/key",
        json={"public_key": b64encode(content).decode()},
        headers={"X-Api-Key": key, "X-Api-Secret": secret},
    )

    raise_for_status(response)

    try:
        private_key = get_private_key()
    except (IOError, TypeError, ValueError, UnsupportedAlgorithm) as e:
        raise HTTPException(
            status_code=500, detail=f"Could not read private key file: {e}"
        )

    conn = sqlite3.connect(f"{settings.config_path}/storage.db")
    asyncio.create_task(sse_out(conn, private_key))


@router.delete("", status_code=status.HTTP_200_OK)
def delete_user() -> None:
    key, secret = get_credentials()

    response = client.delete(
        f"{settings.central_url}api/users",
        headers={"X-Api-Key": key, "X-Api-Secret": secret},
    )

    raise_for_status(response)

    try:
        remove(f"{settings.config_path}/credentials")
        remove(f"{settings.config_path}/public.pem")
        remove(f"{settings.config_path}/private.pem")
    except OSError as e:
        logger.error(f"Error deleting credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

import sqlite3
from base64 import b64decode
from os.path import join, dirname
from sqlite3 import Connection
from typing import Tuple, Optional

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from fastapi import HTTPException
from pydantic import AnyHttpUrl, TypeAdapter
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "local"
    config_path: str = join(dirname(__file__), "config")
    central_url: AnyHttpUrl = TypeAdapter(AnyHttpUrl).validate_python(
        "http://localhost:8000"
    )

    model_config = SettingsConfigDict(
        env_file=join(dirname(__file__), "../.env"), env_file_encoding="utf-8"
    )


settings = Settings()
client = httpx.Client(timeout=30)


def setup_db() -> Connection:
    conn = sqlite3.connect(f"{settings.config_path}/storage.db")
    c = conn.cursor()
    c.execute(
        """create table if not exists notifications (id text unique, delivered int not null, error text, created text not null, private_url text not null, method text not null, headers text not null, params text, body blob)"""  # noqa
    )
    c.execute(
        """create table if not exists encrypted (id text unique, private_url text not null, content text not null, aes text not null, iv text not null, tag text not null, created text not null)"""  # noqa
    )
    conn.commit()

    return conn


def get_credentials() -> Tuple[str, str]:
    try:
        with open(f"{settings.config_path}/credentials", "r") as f:
            lines = f.readlines()
            return lines[0].strip(), lines[1].strip()
    except IOError:
        raise HTTPException(status_code=500, detail="Could not read credentials file")


def get_private_key(key_path: Optional[str] = None) -> PrivateKeyTypes:
    config_path = key_path if key_path else f"{settings.config_path}/private.pem"
    with open(config_path, "rb") as f:
        content: bytes = f.read()
        private_key = serialization.load_pem_private_key(
            content, password=None, backend=default_backend()
        )
    return private_key


def decrypt_with_private_key(s: str, key: PrivateKeyTypes) -> bytes:
    return key.decrypt(  # type: ignore
        b64decode(s),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def raise_for_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=response.status_code, detail=str(e))

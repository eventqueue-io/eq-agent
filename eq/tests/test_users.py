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

import hashlib
import os.path
import shutil
import stat
import uuid
from typing import Generator, Tuple

import httpx
import pytest
from fastapi import HTTPException
from pydantic import EmailStr, TypeAdapter
from pytest_mock import MockerFixture
from respx import MockRouter
from starlette.testclient import TestClient

from globals import settings
from users import NewUserRequest, create_user, router, save_credentials, generate_keys


@pytest.fixture(autouse=True)
def config_dir(mocker: MockerFixture) -> Generator[str, None, None]:
    path = "/dev/shm/eq"
    if not os.path.exists(path):
        os.mkdir(path)
    mocker.patch.object(settings, "config_path", path)
    yield path
    shutil.rmtree(path)


@pytest.fixture
def credentials_path(config_dir: str) -> Generator[str, None, None]:
    yield f"{config_dir}/credentials"
    os.remove(f"{config_dir}/credentials")


@pytest.fixture
def credentials(mocker: MockerFixture) -> Generator[None, None, None]:
    result = str(uuid.uuid4()), str(uuid.uuid4())
    mocker.patch("users.get_credentials", return_value=result)
    yield


def test_create_user_server_error(respx_mock: MockRouter) -> None:
    respx_mock.post(f"{settings.central_url}api/users").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(HTTPException):
        request = NewUserRequest(
            email=TypeAdapter(EmailStr).validate_python("someone@example.com")
        )
        create_user(request)
    assert respx_mock.calls.call_count == 1


def test_create_user_success(respx_mock: MockRouter) -> None:
    respx_mock.post(f"{settings.central_url}api/users").mock(
        return_value=httpx.Response(201)
    )
    request = NewUserRequest(
        email=TypeAdapter(EmailStr).validate_python("someone@example.com")
    )
    response = TestClient(router).post("/api/users", json=request.model_dump())
    assert respx_mock.calls.call_count == 1
    assert respx_mock.calls[0].request.url == f"{settings.central_url}api/users"
    assert respx_mock.calls[0].request.method == "POST"
    assert respx_mock.calls[0].request.content == b'{"email": "someone@example.com"}'
    assert response.status_code == 201


def test_me_unverified(mocker: MockerFixture, respx_mock: MockRouter) -> None:
    mocker.patch("os.path.exists", return_value=False)
    response = TestClient(router).get("/api/users/me")
    assert response.status_code == 200
    assert response.json() == {"verified": False}


def test_me_verified(mocker: MockerFixture, respx_mock: MockRouter) -> None:
    mocker.patch("os.path.exists", return_value=True)
    response = TestClient(router).get("/api/users/me")
    assert response.status_code == 200
    assert response.json() == {"verified": True}


def test_save_credentials(credentials_path: str) -> None:
    save_credentials({"api_key": "a", "api_secret": "b"})
    assert os.path.exists(credentials_path) is True
    with open(credentials_path) as f:
        assert f.read() == "a\nb"
    assert stat.S_IMODE(os.stat(credentials_path).st_mode) == 0o600


def test_verify_user_http_error(respx_mock: MockRouter) -> None:
    token = uuid.uuid4()
    respx_mock.get(f"{settings.central_url}api/users/verify/{token}").mock(
        return_value=httpx.Response(status_code=400)
    )
    with pytest.raises(HTTPException):
        TestClient(router).get(f"/api/users/verify/{token}")


def test_verify_user_other_system_error(respx_mock: MockRouter) -> None:
    token = uuid.uuid4()
    respx_mock.get(f"{settings.central_url}api/users/verify/{token}").mock(
        return_value=httpx.Response(
            status_code=200,
            json={"key": str(uuid.uuid4()), "secret": str(uuid.uuid4())},
        )
    )
    with pytest.raises(HTTPException):
        TestClient(router).get(f"/api/users/verify/{token}")


def test_verify_user_json_error(respx_mock: MockRouter) -> None:
    token = uuid.uuid4()
    respx_mock.get(f"{settings.central_url}api/users/verify/{token}").mock(
        return_value=httpx.Response(
            status_code=200,
            json=None,
        )
    )
    with pytest.raises(HTTPException):
        TestClient(router).get(f"/api/users/verify/{token}")


def test_verify_user_success(
    mocker: MockerFixture, respx_mock: MockRouter, credentials_path: str
) -> None:
    token = uuid.uuid4()
    key = str(uuid.uuid4())
    secret = str(uuid.uuid4())

    import users

    spy = mocker.spy(users, "save_credentials")

    respx_mock.get(f"{settings.central_url}api/users/verify/{token}").mock(
        return_value=httpx.Response(
            status_code=200, json={"api_key": key, "api_secret": secret}
        )
    )
    response = TestClient(router).get(f"/api/users/verify/{token}")

    assert respx_mock.calls.call_count == 1
    assert (
        respx_mock.calls[0].request.url
        == f"{settings.central_url}api/users/verify/{token}"
    )
    assert respx_mock.calls[0].request.method == "GET"

    assert response.status_code == 200
    spy.assert_called_once_with({"api_key": key, "api_secret": secret})


def test_generate_keys() -> None:
    generate_keys()
    with open(f"{settings.config_path}/public.pem") as f:
        public_hash_1 = hashlib.sha256(f.read().encode()).hexdigest()
    with open(f"{settings.config_path}/private.pem") as f:
        private_hash_1 = hashlib.sha256(f.read().encode()).hexdigest()

    generate_keys()
    with open(f"{settings.config_path}/public.pem") as f:
        public_hash_2 = hashlib.sha256(f.read().encode()).hexdigest()
    with open(f"{settings.config_path}/private.pem") as f:
        private_hash_2 = hashlib.sha256(f.read().encode()).hexdigest()

    assert public_hash_1 != public_hash_2
    assert private_hash_1 != private_hash_2
    assert stat.S_IMODE(os.stat(f"{settings.config_path}/private.pem").st_mode) == 0o600


def test_set_public_key_exists_no_force() -> None:
    with open(f"{settings.config_path}/public.pem", "w") as f:
        f.write("test")
    with pytest.raises(HTTPException):
        TestClient(router).post("/api/users/key", json={})


def test_set_public_key_exists_force(respx_mock: MockRouter) -> None:
    with open(f"{settings.config_path}/public.pem", "w") as f:
        f.write("test")

    with pytest.raises(HTTPException):  # No credentials in place
        TestClient(router).post("/api/users/key", json={}, params={"force": True})

    with open(f"{settings.config_path}/credentials", "w") as f:
        f.write("{uuid.uuid4()}\n{uuid.uuid4()}")
    respx_mock.post(f"{settings.central_url}api/users/key").mock(
        return_value=httpx.Response(status_code=200)
    )

    response = TestClient(router).post(
        "/api/users/key", json={}, params={"force": True}
    )
    assert response.status_code == 200
    assert respx_mock.calls.call_count == 1
    assert respx_mock.calls[0].request.url == f"{settings.central_url}api/users/key"
    assert respx_mock.calls[0].request.method == "POST"


def test_set_public_key_on_errors(
    mocker: MockerFixture, respx_mock: MockRouter
) -> None:
    with open(f"{settings.config_path}/credentials", "w") as f:
        f.write("{uuid.uuid4()}\n{uuid.uuid4()}")
    respx_mock.post(f"{settings.central_url}api/users/key").mock(
        return_value=httpx.Response(status_code=400)
    )

    with pytest.raises(HTTPException):
        TestClient(router).post("/api/users/key", json={}, params={"force": True})
    assert respx_mock.calls.call_count == 1

    respx_mock.post(f"{settings.central_url}api/users/key").mock(
        return_value=httpx.Response(status_code=200)
    )
    spy = mocker.patch("users.get_private_key", side_effect=ValueError("test"))

    with pytest.raises(HTTPException):
        TestClient(router).post("/api/users/key", json={}, params={"force": True})
    assert respx_mock.calls.call_count == 2
    assert spy.call_count == 1


def test_delete_user(
    mocker: MockerFixture, respx_mock: MockRouter, credentials: Tuple[str, str]
) -> None:
    respx_mock.delete(f"{settings.central_url}api/users").mock(
        return_value=httpx.Response(status_code=200)
    )
    remove_spy = mocker.patch("users.remove")
    response = TestClient(router).delete("/api/users")
    assert response.status_code == 200
    assert respx_mock.calls.call_count == 1
    assert respx_mock.calls[0].request.url == f"{settings.central_url}api/users"
    assert respx_mock.calls[0].request.method == "DELETE"
    assert remove_spy.call_count == 3


def test_delete_user_no_credentials(mocker: MockerFixture) -> None:
    mocker.patch("users.get_credentials", side_effect=HTTPException(500))
    with pytest.raises(HTTPException):
        TestClient(router).delete("/api/users")


def test_delete_user_bad_server_response(
    mocker: MockerFixture, respx_mock: MockRouter, credentials: Tuple[str, str]
) -> None:
    respx_mock.delete(f"{settings.central_url}api/users").mock(
        return_value=httpx.Response(status_code=400)
    )
    remove_spy = mocker.patch("users.remove")
    with pytest.raises(HTTPException):
        TestClient(router).delete("/api/users")
    assert remove_spy.call_count == 0


def test_delete_user_os_error(
    mocker: MockerFixture, respx_mock: MockRouter, credentials: Tuple[str, str]
) -> None:
    respx_mock.delete(f"{settings.central_url}api/users").mock(
        return_value=httpx.Response(status_code=200)
    )
    remove_spy = mocker.patch("users.remove", side_effect=OSError("test"))
    with pytest.raises(HTTPException):
        TestClient(router).delete("/api/users")
    assert remove_spy.call_count == 1

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

import json
import uuid
from datetime import datetime
from typing import Tuple, Generator

import httpx
import pytest
from pydantic import AnyHttpUrl, TypeAdapter
from pytest_mock import MockerFixture
from respx import MockRouter
from starlette.testclient import TestClient

from endpoints import router, Endpoint, EndpointId
from globals import settings


@pytest.fixture
def credentials(mocker: MockerFixture) -> Generator[None, None, None]:
    result = str(uuid.uuid4()), str(uuid.uuid4())
    mocker.patch("endpoints.get_credentials", return_value=result)
    yield


def test_create_endpoint(credentials: Tuple[str, str], respx_mock: MockRouter) -> None:
    respx_mock.post(f"{settings.central_url}api/endpoints").mock(
        return_value=httpx.Response(status_code=201)
    )
    response = TestClient(router).post(
        "api/endpoints",
        json={
            "private_url": "http://local:8000/abcd",
            "description": "",
        },
    )
    assert respx_mock.calls.call_count == 1
    assert respx_mock.calls[0].request.url == f"{settings.central_url}api/endpoints"
    assert respx_mock.calls[0].request.method == "POST"
    assert (
        respx_mock.calls[0].request.content
        == b'{"private_url": "http://local:8000/abcd", "description": ""}'
    )
    assert response.status_code == 201


def test_list_endpoints(credentials: Tuple[str, str], respx_mock: MockRouter) -> None:
    now = datetime.now()
    ep = Endpoint(
        id=EndpointId(uuid.uuid4()),
        private_url=TypeAdapter(AnyHttpUrl).validate_python("http://local:8000/abcd"),
        description="",
        created=now,
        last_used=None,
    )

    respx_mock.get(f"{settings.central_url}api/endpoints").mock(
        return_value=httpx.Response(
            status_code=200, json=[json.loads(ep.model_dump_json())]
        )
    )
    response = TestClient(router).get("/api/endpoints")
    assert respx_mock.calls.call_count == 1
    assert respx_mock.calls[0].request.url == f"{settings.central_url}api/endpoints"
    assert respx_mock.calls[0].request.method == "GET"
    assert response.status_code == 200
    assert response.json() == [json.loads(ep.model_dump_json())]


def test_update_endpoint(credentials: Tuple[str, str], respx_mock: MockRouter) -> None:
    endpoint_id = EndpointId(uuid.uuid4())
    respx_mock.put(f"{settings.central_url}api/endpoints/{endpoint_id}").mock(
        return_value=httpx.Response(status_code=200)
    )
    response = TestClient(router).put(
        f"/api/endpoints/{endpoint_id}",
        json={
            "private_url": "http://local:8000/xyz",
            "description": "",
        },
    )
    assert respx_mock.calls.call_count == 1
    assert (
        respx_mock.calls[0].request.url
        == f"{settings.central_url}api/endpoints/{endpoint_id}"
    )
    assert respx_mock.calls[0].request.method == "PUT"
    assert (
        respx_mock.calls[0].request.content
        == b'{"private_url": "http://local:8000/xyz", "description": ""}'
    )
    assert response.status_code == 200


def test_delete_endpoint(credentials: Tuple[str, str], respx_mock: MockRouter) -> None:
    endpoint_id = EndpointId(uuid.uuid4())
    respx_mock.delete(f"{settings.central_url}api/endpoints/{endpoint_id}").mock(
        return_value=httpx.Response(status_code=200)
    )
    response = TestClient(router).delete(f"/api/endpoints/{endpoint_id}")
    assert respx_mock.calls.call_count == 1
    assert (
        respx_mock.calls[0].request.url
        == f"{settings.central_url}api/endpoints/{endpoint_id}"
    )
    assert respx_mock.calls[0].request.method == "DELETE"
    assert response.status_code == 200

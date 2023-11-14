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

from datetime import datetime
from typing import Annotated, NewType, Optional, Any
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, AnyHttpUrl, Field, field_serializer

from globals import get_credentials, settings, client, raise_for_status

router = APIRouter(prefix="/api/endpoints")

EndpointId = NewType("EndpointId", UUID)
Description = Annotated[str, Field(max_length=1024)]


class Endpoint(BaseModel):
    id: EndpointId
    private_url: AnyHttpUrl
    description: Description
    created: datetime
    last_used: Optional[datetime]

    @field_serializer("private_url")
    def serialize_body(self, private_url: AnyHttpUrl, _info: Any) -> str:
        return str(private_url)


class NewEndpointRequest(BaseModel):
    private_url: AnyHttpUrl
    description: Description

    @field_serializer("private_url")
    def serialize_body(self, private_url: AnyHttpUrl, _info: Any) -> str:
        return str(private_url)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_endpoint(new_endpoint_request: NewEndpointRequest) -> None:
    key, secret = get_credentials()

    response = client.post(
        f"{settings.central_url}api/endpoints",
        json=new_endpoint_request.model_dump(),
        headers={"X-Api-Key": key, "X-Api-Secret": secret},
    )

    raise_for_status(response)


@router.get("", status_code=status.HTTP_200_OK)
def get_all() -> list[Endpoint]:
    key, secret = get_credentials()

    response = client.get(
        f"{settings.central_url}api/endpoints",
        headers={"X-Api-Key": key, "X-Api-Secret": secret},
    )

    raise_for_status(response)

    endpoints = [Endpoint.model_validate(r) for r in response.json()]
    return endpoints


@router.put("/{endpoint_id}", status_code=status.HTTP_200_OK)
def update_endpoint(
    endpoint_id: EndpointId, updated_endpoint_request: NewEndpointRequest
) -> None:
    key, secret = get_credentials()

    response = client.put(
        f"{settings.central_url}api/endpoints/{endpoint_id}",
        json=updated_endpoint_request.model_dump(),
        headers={"X-Api-Key": key, "X-Api-Secret": secret},
    )
    raise_for_status(response)


@router.delete("/{endpoint_id}", status_code=status.HTTP_200_OK)
def delete_endpoint(endpoint_id: EndpointId) -> None:
    key, secret = get_credentials()
    response = client.delete(
        f"{settings.central_url}api/endpoints/{endpoint_id}",
        headers={"X-Api-Key": key, "X-Api-Secret": secret},
    )
    raise_for_status(response)

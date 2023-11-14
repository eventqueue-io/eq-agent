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
import json
import os
import shutil
import uuid
from asyncio import Queue, CancelledError
from dataclasses import dataclass
from datetime import datetime
from sqlite3 import Connection
from typing import Generator, Tuple, AsyncIterator, Any, Optional
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from httpx import ConnectError, HTTPStatusError, RemoteProtocolError, Request, Response
from pydantic import AnyHttpUrl
from pytest_mock import MockerFixture
from respx import MockRouter

import calls
from calls import (
    CallId,
    Notification,
    forward_call,
    delete_from_server,
    CompleteMessage,
    decrypt,
    save_encrypted,
    save_decrypted,
    id_in_storage,
    BrowserMessage,
    notify_browsers,
    on_reprocessed,
    try_persist,
    process_notification,
    sse_out,
    notify,
    Pending,
    retry_call_delivery,
)
from globals import settings, get_private_key, setup_db


@pytest.fixture
def credentials(mocker: MockerFixture) -> Generator[None, None, None]:
    result = str(uuid.uuid4()), str(uuid.uuid4())
    mocker.patch("calls.get_credentials", return_value=result)
    yield


@pytest.fixture(autouse=True)
def config_dir(mocker: MockerFixture) -> Generator[str, None, None]:
    path = "/dev/shm/eq"
    if not os.path.exists(path):
        os.mkdir(path)
    mocker.patch.object(settings, "config_path", path)
    yield path
    shutil.rmtree(path)


@pytest.fixture
def db_connection() -> Generator[Connection, None, None]:
    conn = setup_db()
    yield conn
    conn.close()


@pytest.fixture
def notification() -> Generator[Notification, None, None]:
    base_path = os.path.dirname(__file__)
    with open(f"{base_path}/test_notification.json") as f:
        data = f.read()
    blob = Notification.model_validate_json(data)
    yield blob


@pytest.fixture
def private_key() -> Generator[PrivateKeyTypes, None, None]:
    base_path = os.path.dirname(__file__)
    yield get_private_key(f"{base_path}/test_private.pem")


@pytest.fixture
def message() -> Generator[CompleteMessage, None, None]:
    yield CompleteMessage(
        method="PUT",
        headers={"Content-Type": "application/xml", "Host": "localhost"},
        params=[("a", "b"), ("c", "d")],
        body=b"<xml></xml>",
    )


def test_decrypt(
    notification: Notification, private_key: PrivateKeyTypes, message: CompleteMessage
) -> None:
    result = decrypt(notification, private_key)
    assert result is not None
    assert result.method == message.method
    assert result.headers == message.headers
    assert result.params == message.params
    assert result.body == message.body


def test_save_encrypted(notification: Notification, db_connection: Connection) -> None:
    save_encrypted(notification, db_connection)
    cursor = db_connection.cursor()
    result = cursor.execute("SELECT * FROM encrypted").fetchall()
    assert len(result) == 1
    assert result[0] == (
        str(notification.id),
        str(notification.private_url),
        notification.content,
        notification.aes,
        notification.iv,
        notification.tag,
        notification.created.isoformat(),
    )


def test_save_decrypted(
    notification: Notification, message: CompleteMessage, db_connection: Connection
) -> None:
    save_decrypted(notification, message, db_connection)
    cursor = db_connection.cursor()
    result = cursor.execute("SELECT * FROM notifications").fetchall()
    assert len(result) == 1
    assert result[0] == (
        str(notification.id),
        0,
        None,
        notification.created.isoformat(),
        str(notification.private_url),
        message.method,
        json.dumps(message.headers),
        json.dumps(message.params),
        message.body,
    )


def test_delete_from_server(
    credentials: Tuple[str, str], respx_mock: MockRouter
) -> None:
    call_id = CallId(uuid.uuid4())
    respx_mock.delete(f"{settings.central_url}api/calls/{call_id}").mock(
        return_value=Response(status_code=200)
    )
    result = delete_from_server(call_id)
    assert result is True
    assert respx_mock.calls.call_count == 1
    assert (
        respx_mock.calls[0].request.url == f"{settings.central_url}api/calls/{call_id}"
    )
    assert respx_mock.calls[0].request.method == "DELETE"


def test_id_in_storage_encrypted(
    notification: Notification, db_connection: Connection
) -> None:
    assert id_in_storage(notification.id, db_connection) is False
    save_encrypted(notification, db_connection)
    assert id_in_storage(notification.id, db_connection) is True


def test_id_in_storage_decrypted(
    notification: Notification, message: CompleteMessage, db_connection: Connection
) -> None:
    assert id_in_storage(notification.id, db_connection) is False
    save_decrypted(notification, message, db_connection)
    assert id_in_storage(notification.id, db_connection) is True


def test_id_not_in_storage(
    notification: Notification, message: CompleteMessage, db_connection: Connection
) -> None:
    save_encrypted(notification, db_connection)
    save_decrypted(notification, message, db_connection)
    assert id_in_storage(CallId(uuid.uuid4()), db_connection) is False


def test_forward_call_success(
    respx_mock: MockRouter,
    notification: Notification,
    private_key: PrivateKeyTypes,
    db_connection: Connection,
    message: CompleteMessage,
) -> None:
    respx_mock.put(
        "http://localhost:8000/?a=b&c=d", headers={"Content-Type": "application/xml"}
    ).mock(
        return_value=Response(status_code=200),
    )
    save_decrypted(notification, message, db_connection)
    result = forward_call(notification, message, db_connection)

    assert result is True
    assert respx_mock.calls.call_count == 1
    assert respx_mock.calls[0].request.url == "http://localhost:8000/?a=b&c=d"
    assert respx_mock.calls[0].request.method == "PUT"
    assert respx_mock.calls[0].request.headers["Content-Type"] == "application/xml"
    assert respx_mock.calls[0].request.content == b"<xml></xml>"

    marked_delivered = (
        db_connection.cursor()
        .execute(
            "SELECT delivered FROM notifications where id=(?)", (str(notification.id),)
        )
        .fetchone()
    )
    assert marked_delivered[0] == 1


def test_forward_call_failure(
    respx_mock: MockRouter,
    notification: Notification,
    private_key: PrivateKeyTypes,
    db_connection: Connection,
    message: CompleteMessage,
) -> None:
    respx_mock.put(
        f"{settings.central_url}?a=b&c=d", headers={"Content-Type": "application/xml"}
    ).mock(
        return_value=Response(status_code=500),
    )
    save_decrypted(notification, message, db_connection)
    result = forward_call(notification, message, db_connection)

    assert result is None
    assert respx_mock.calls.call_count == 3
    assert respx_mock.calls[0].request.url == f"{settings.central_url}?a=b&c=d"
    assert respx_mock.calls[0].request.method == "PUT"
    assert respx_mock.calls[0].request.headers["Content-Type"] == "application/xml"
    assert respx_mock.calls[0].request.content == b"<xml></xml>"

    stored = (
        db_connection.cursor()
        .execute(
            "SELECT delivered, error FROM notifications where id=(?)",
            (str(notification.id),),
        )
        .fetchone()
    )
    assert stored[0] == 0
    assert (
        stored[1]
        == f"""Server error '500 Internal Server Error' for url '{settings.central_url}?a=b&c=d'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500"""
    )


def test_notify_browsers(mocker: MockerFixture) -> None:
    queue = MagicMock(Queue[BrowserMessage])
    spy = mocker.patch.object(queue, "put")
    mocker.patch("calls.queues", [queue, queue])
    asyncio.run(notify_browsers("test", False))
    assert spy.call_count == 2
    spy.assert_called_with(BrowserMessage(message="test", reload_calls=False))


def test_on_reprocessed(mocker: MockerFixture, notification: Notification) -> None:
    spy = mocker.patch("calls.delete_from_server")
    asyncio.run(on_reprocessed(notification))
    spy.assert_called_once_with(notification.id)


def test_try_persist_success(
    notification: Notification, private_key: PrivateKeyTypes, db_connection: Connection
) -> None:
    asyncio.run(try_persist(notification, private_key, db_connection))
    result = (
        db_connection.cursor()
        .execute("select * from notifications where id=(?)", (str(notification.id),))
        .fetchone()
    )
    assert result is not None
    result = (
        db_connection.cursor()
        .execute("select * from encrypted where id=(?)", (str(notification.id),))
        .fetchone()
    )
    assert result is None


def test_try_persist_failure(
    mocker: MockerFixture,
    notification: Notification,
    private_key: PrivateKeyTypes,
    db_connection: Connection,
) -> None:
    mocker.patch("calls.decrypt", side_effect=ValueError(""))
    asyncio.run(try_persist(notification, private_key, db_connection))
    result = (
        db_connection.cursor()
        .execute("select * from notifications where id=(?)", (str(notification.id),))
        .fetchone()
    )
    assert result is None
    result = (
        db_connection.cursor()
        .execute("select * from encrypted where id=(?)", (str(notification.id),))
        .fetchone()
    )
    assert result is not None


def test_process_notification_have_reprocessed(
    mocker: MockerFixture,
    notification: Notification,
    private_key: PrivateKeyTypes,
    db_connection: Connection,
) -> None:
    mocker.patch("calls.id_in_storage", return_value=True)
    spy = mocker.patch("calls.on_reprocessed")
    persist_spy = mocker.patch("calls.try_persist")
    asyncio.run(process_notification(notification, private_key, db_connection))
    spy.assert_called_once_with(notification)
    persist_spy.assert_not_called()


def test_process_notification_cannot_persist(
    mocker: MockerFixture,
    notification: Notification,
    private_key: PrivateKeyTypes,
    db_connection: Connection,
) -> None:
    mocker.patch("calls.id_in_storage", return_value=False)
    mocker.patch("calls.try_persist", return_value=None)
    delete_spy = mocker.patch("calls.delete_from_server")
    asyncio.run(process_notification(notification, private_key, db_connection))
    delete_spy.assert_not_called()


def test_process_notification_cannot_delete_from_server(
    mocker: MockerFixture,
    message: CompleteMessage,
    notification: Notification,
    private_key: PrivateKeyTypes,
    db_connection: Connection,
) -> None:
    mocker.patch("calls.id_in_storage", return_value=False)
    mocker.patch("calls.try_persist", return_value=message)
    mocker.patch("calls.delete_from_server", return_value=None)
    forward_spy = mocker.patch("calls.forward_call")
    asyncio.run(process_notification(notification, private_key, db_connection))
    forward_spy.assert_called()


def test_process_notification_success(
    mocker: MockerFixture,
    message: CompleteMessage,
    notification: Notification,
    private_key: PrivateKeyTypes,
    db_connection: Connection,
) -> None:
    mocker.patch("calls.id_in_storage", return_value=False)
    mocker.patch("calls.try_persist", return_value=message)
    mocker.patch("calls.delete_from_server", return_value=True)
    forward_spy = mocker.patch("calls.forward_call")
    asyncio.run(process_notification(notification, private_key, db_connection))
    forward_spy.assert_called_once_with(notification, message, db_connection)


def test_sse_out_success(
    mocker: MockerFixture,
    credentials: None,
    db_connection: Connection,
    private_key: PrivateKeyTypes,
    notification: Notification,
) -> None:
    @dataclass
    class Event:
        id: str = str(uuid.uuid4())
        data: str = notification.model_dump_json()
        retry: Optional[float] = None

    class MockEventSource:
        async def __aenter__(self) -> "MockEventSource":
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

        async def aiter_sse(self) -> AsyncIterator[Event]:
            yield Event()

    kill_spy = mocker.patch.object(os, "kill")
    process_spy = mocker.patch("calls.process_notification")
    mocker.patch("calls.aconnect_sse", return_value=MockEventSource())
    asyncio.run(sse_out(db_connection, private_key))
    process_spy.assert_called_once_with(notification, private_key, db_connection)
    assert kill_spy.call_count == 2


def test_notify_removes_queue(mocker: MockerFixture) -> None:
    queue: Queue[BrowserMessage] = Queue()
    mocker.patch.object(queue, "get", side_effect=CancelledError(""))
    calls.queues = [queue]

    async def f() -> None:
        async for _ in notify(queue):
            pass

    with pytest.raises(CancelledError):
        asyncio.run(f())
    assert len(calls.queues) == 0


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def test_get_pending_on_server(
    respx_mock: MockRouter, credentials: None, notification: Notification
) -> None:
    respx_mock.get(f"{settings.central_url}api/calls").mock(
        return_value=Response(
            status_code=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                [notification.model_dump(), notification.model_dump()], cls=UUIDEncoder
            ),
        )
    )
    assert calls.get_pending_on_server() == [notification, notification]


def test_get_pending_calls(
    mocker: MockerFixture,
    notification: Notification,
    private_key: PrivateKeyTypes,
    db_connection: Connection,
) -> None:
    mocker.patch("calls.get_private_key", return_value=private_key)
    not1 = notification
    new_id = CallId(uuid.uuid4())
    not2 = notification.model_copy(
        update={
            "id": new_id,
            "content": "test2",
            "private_url": "http://localhost:8001",
        }
    )  # will not decrypt
    mocker.patch("calls.get_pending_on_server", return_value=[not1, not2])
    mocker.patch("calls.delete_from_server", return_value=True)
    forward_spy = mocker.patch("calls.forward_call")

    result = asyncio.run(calls.get_pending_calls())
    assert forward_spy.call_count == 1

    assert result == [
        Pending(
            id=notification.id,
            private_url=AnyHttpUrl("http://localhost:8000/"),
            created=datetime(2023, 1, 1, 12, 0),
            encrypted=False,
        ),
        Pending(
            id=new_id,
            private_url=AnyHttpUrl("http://localhost:8001/"),
            created=datetime(2023, 1, 1, 12, 0),
            encrypted=True,
        ),
    ]


def test_delete_call(db_connection: Connection, notification: Notification) -> None:
    save_encrypted(notification, db_connection)
    assert id_in_storage(notification.id, db_connection) is True
    calls.delete_call(notification.id)
    assert id_in_storage(notification.id, db_connection) is False


def test_retry_call_delivery(
    mocker: MockerFixture,
    db_connection: Connection,
    notification: Notification,
    private_key: PrivateKeyTypes,
) -> None:
    message = decrypt(notification, private_key)
    save_decrypted(notification, message, db_connection)
    assert id_in_storage(notification.id, db_connection) is True

    forward_spy = mocker.patch("calls.forward_call")
    notify_spy = mocker.patch("calls.notify_browsers")

    asyncio.run(retry_call_delivery(notification.id))

    forward_spy.assert_called_once()
    notify_spy.assert_called_once()

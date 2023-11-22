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
import logging
import random
import sqlite3
import time
from asyncio import Queue, CancelledError
from base64 import b64decode
from collections import namedtuple
from datetime import datetime
from sqlite3 import Connection
from typing import NewType, List, AsyncGenerator, Optional, Any
from uuid import UUID
import os
import signal

from backoff import on_exception, expo, full_jitter, constant
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from httpx import (
    HTTPStatusError,
    ConnectError,
    RemoteProtocolError,
    AsyncClient,
    ReadError,
    ReadTimeout,
)
from httpx_sse import aconnect_sse, SSEError
from sse_starlette.sse import EventSourceResponse
from fastapi import APIRouter, status
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ValidationError,
    TypeAdapter,
    field_serializer,
)

from globals import (
    settings,
    get_credentials,
    client,
    decrypt_with_private_key,
    raise_for_status,
    get_private_key,
)

RECONNECT_DELAY = 60.0

logging.getLogger("backoff").addHandler(logging.StreamHandler())
logging.getLogger("backoff").setLevel(logging.INFO)

calls_router = APIRouter(prefix="/api/calls")
sse_router = APIRouter(prefix="/api/events")
logger = logging.getLogger(__name__)


class BrowserMessage(BaseModel):
    message: str
    reload_calls: bool


queues: list[Queue[BrowserMessage]] = []

CallId = NewType("CallId", UUID)


class Notification(BaseModel):
    id: CallId
    private_url: AnyHttpUrl
    content: str
    aes: str
    iv: str
    tag: str
    created: datetime

    @field_serializer("private_url")
    def serialize_body(self, private_url: AnyHttpUrl, _info: Any) -> str:
        return str(private_url)


class CompleteMessage(BaseModel):
    method: str
    headers: dict[str, str]
    params: list[tuple[str, str]]
    body: bytes


def decrypt(
    notification: Notification, private_key: PrivateKeyTypes
) -> CompleteMessage:
    aes = decrypt_with_private_key(notification.aes, private_key)
    iv = decrypt_with_private_key(notification.iv, private_key)
    tag = decrypt_with_private_key(notification.tag, private_key)

    cipher = Cipher(algorithms.AES(aes), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_bytes = (
        decryptor.update(b64decode(notification.content)) + decryptor.finalize()
    )
    decrypted_string = decrypted_bytes.decode()
    decrypted = json.loads(decrypted_string)
    decrypted["body"] = b64decode(decrypted["body"])
    decrypted["headers"] = {
        k: v for k, v in decrypted["headers"].items() if k.lower() != "host"
    }
    decrypted["headers"]["Host"] = notification.private_url.host
    return CompleteMessage(**decrypted)


def save_encrypted(notification: Notification, conn: Connection) -> None:
    conn.cursor().execute(
        "INSERT INTO encrypted (id, private_url, content, aes, iv, tag, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(notification.id),
            str(notification.private_url),
            notification.content,
            notification.aes,
            notification.iv,
            notification.tag,
            notification.created.isoformat(),
        ),
    )
    conn.commit()


def save_decrypted(
    notification: Notification, message: CompleteMessage, conn: Connection
) -> None:
    conn.cursor().execute(
        "INSERT INTO notifications (id, delivered, error, created, private_url, method, headers, params, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",  # noqa
        (
            str(notification.id),
            0,
            None,
            notification.created.isoformat(),
            str(notification.private_url),
            message.method,
            json.dumps(message.headers),
            json.dumps(message.params),
            message.body,
        ),
    )
    conn.commit()


@on_exception(
    expo, (ConnectionError, HTTPStatusError), max_tries=3, raise_on_giveup=False
)
def delete_from_server(call_id: CallId) -> Optional[bool]:
    key, secret = get_credentials()

    response = client.delete(
        f"{settings.central_url}api/calls/{call_id}",
        headers={"X-Api-Key": key, "X-Api-Secret": secret},
    )
    response.raise_for_status()
    return True


def id_in_storage(call_id: CallId, conn: Connection) -> bool:
    return (
        conn.cursor()
        .execute("SELECT id FROM notifications WHERE id = (?)", (str(call_id),))
        .fetchone()
        is not None
        or conn.cursor()
        .execute("SELECT id FROM encrypted WHERE id = (?)", (str(call_id),))
        .fetchone()
        is not None
    )


@on_exception(expo, (ConnectError, HTTPStatusError), max_tries=3, raise_on_giveup=False)
def forward_call(
    notification: Notification, message: CompleteMessage, conn: Connection
) -> Optional[bool]:
    logger.info(f"Forwarding call {notification.id} to {notification.private_url}")
    response = client.request(
        method=message.method,
        url=str(notification.private_url),
        headers=message.headers,
        params=dict(message.params),
        content=message.body,
    )

    try:
        response.raise_for_status()
    except (ConnectError, HTTPStatusError) as e:
        logger.error(
            f"Could not forward call {notification.id} to {notification.private_url}: {e}"
        )
        conn.cursor().execute(
            "update notifications set error=(?) where id=(?)",
            (str(e), str(notification.id)),
        )
        conn.commit()
        raise

    logger.info(f"Done forwarding call {notification.id} to {notification.private_url}")

    conn.cursor().execute(
        "update notifications set delivered=(?), error=(?) where id=(?)",
        (1, None, str(notification.id)),
    )
    conn.commit()

    return True


async def notify_browsers(message: str, reload_calls: bool = False) -> None:
    for queue in queues:
        await queue.put(BrowserMessage(message=message, reload_calls=reload_calls))


async def on_reprocessed(notification: Notification) -> None:
    logger.info(f"Received duplicate for {notification.id}, deleting from server")
    await notify_browsers(
        f"Received duplicate for {notification.id}, deleting from server"
    )
    if delete_from_server(notification.id) is None:
        logger.error(f"Could not delete call {notification.id} from server")
        await notify_browsers(
            f"Could not delete {notification.id} from server, will retry when I see this ID again"
        )


async def try_persist(
    notification: Notification, private_key: PrivateKeyTypes, conn: Connection
) -> Optional[CompleteMessage]:
    try:
        message = decrypt(notification, private_key)
    except (ValueError, UnsupportedAlgorithm) as e:
        logger.error(
            f"Could not decrypt message with id {notification.id}, saving it encrypted: {e}"
        )
        await notify_browsers(
            f"Could not decrypt message with id {notification.id}, saving it encrypted: {e}"
        )
        save_encrypted(notification, conn)
        return None
    else:
        save_decrypted(notification, message, conn)
        return message


async def try_forward(
    notification: Notification, message: CompleteMessage, conn: Connection
) -> None:
    result = forward_call(notification, message, conn)
    if not result:
        logger.error(
            f"Could not forward call {notification.id} to {notification.private_url}"
        )
        await notify_browsers(
            f"Could not forward call {notification.id} to {notification.private_url}",
            reload_calls=True,
        )
    else:
        await notify_browsers(
            f"Forwarded {notification.id} to {notification.private_url}"
        )


async def process_notification(
    notification: Notification,
    private_key: PrivateKeyTypes,
    conn: Connection,
) -> None:
    if id_in_storage(notification.id, conn):
        await on_reprocessed(notification)
        return

    message = await try_persist(notification, private_key, conn)
    if message is None:
        return

    if delete_from_server(notification.id) is None:
        logger.error(f"Could not delete call {notification.id} from server")
        await notify_browsers(
            f"Could not delete {notification.id} from server, will retry when I see this ID again"
        )

    await try_forward(notification, message, conn)


async def sse_out(conn: Connection, private_key: PrivateKeyTypes) -> None:
    last_id = None
    reconnect_delay = 0.0

    @on_exception(expo, (ConnectError, HTTPStatusError, RemoteProtocolError, SSEError))
    @on_exception(constant, (ReadTimeout, ReadError), jitter=full_jitter)
    async def _connect() -> None:
        nonlocal last_id, reconnect_delay

        time.sleep(reconnect_delay)

        key, secret = get_credentials()
        headers = {"X-Api-Key": key, "X-Api-Secret": secret}
        if last_id:
            headers["Last-Event-ID"] = last_id

        try:
            aclient = AsyncClient(timeout=30)
            async with aconnect_sse(
                aclient,
                "GET",
                f"{settings.central_url}api/events",
                headers=headers,
            ) as event_source:
                logger.info("Connected to server")
                async for event in event_source.aiter_sse():
                    last_id = event.id
                    reconnect_delay = (
                        float(event.retry) / 1000
                        if event.retry is not None
                        else RECONNECT_DELAY
                    )
                    try:
                        notification = Notification.model_validate_json(event.data)
                    except ValidationError as e:
                        logger.error(
                            f"Received invalid notification: {e}\n{event.data}"
                        )
                        continue
                    await process_notification(notification, private_key, conn)
            parent = os.getppid()
            pid = os.getpid()
            os.kill(parent, signal.SIGTERM)
            os.kill(pid, signal.SIGTERM)
        except CancelledError:
            logger.info("Cancelled, exiting")
            raise
        except SSEError as e:
            logger.error("Could not establish SSE connection: {}", e)
            raise

    await _connect()


async def notify(queue: Queue[BrowserMessage]) -> AsyncGenerator[str, None]:
    try:
        while True:
            message = await queue.get()
            yield message.model_dump_json()
    except CancelledError:
        queues.remove(queue)
        raise


@sse_router.get("")
async def monitor() -> EventSourceResponse:
    queue: Queue[BrowserMessage] = Queue()
    queues.append(queue)
    return EventSourceResponse(notify(queue))


def get_pending_on_server() -> List[Notification]:
    key, secret = get_credentials()

    response = client.get(
        f"{settings.central_url}api/calls",
        headers={"X-Api-Key": key, "X-Api-Secret": secret},
    )

    raise_for_status(response)

    calls = [Notification.model_validate(r) for r in response.json()]
    return calls


DecryptedTuple = namedtuple(
    "DecryptedTuple",
    [
        "id",
        "delivered",
        "error",
        "created",
        "private_url",
        "method",
        "headers",
        "params",
        "body",
    ],
)
EncryptedTuple = namedtuple(
    "EncryptedTuple", ["id", "private_url", "content", "aes", "iv", "tag", "created"]
)


class Pending(BaseModel):
    id: CallId
    private_url: AnyHttpUrl
    created: datetime
    encrypted: bool

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Pending):
            return NotImplemented

        return (self.id, self.private_url, self.created, self.encrypted) == (
            other.id,
            other.private_url,
            other.created,
            other.encrypted,
        )


@calls_router.get("", status_code=status.HTTP_200_OK)
async def get_pending_calls() -> List[Pending]:
    private_key = get_private_key()
    conn = sqlite3.connect(f"{settings.config_path}/storage.db")

    for call in get_pending_on_server():
        await process_notification(call, private_key, conn)

    decrypted: List[DecryptedTuple] = [
        DecryptedTuple(*t)
        for t in conn.cursor()
        .execute("""select * from notifications where delivered = 0""")
        .fetchall()
    ]
    encrypted: List[EncryptedTuple] = [
        EncryptedTuple(*t)
        for t in conn.cursor().execute("""select * from encrypted""").fetchall()
    ]

    conn.close()

    decrypted_pending = [
        Pending(
            id=CallId(UUID(c.id)),
            private_url=TypeAdapter(AnyHttpUrl).validate_python(c.private_url),
            created=datetime.fromisoformat(c.created),
            encrypted=False,
        )
        for c in decrypted
    ]

    encrypted_pending = [
        Pending(
            id=CallId(UUID(c.id)),
            private_url=TypeAdapter(AnyHttpUrl).validate_python(c.private_url),
            created=datetime.fromisoformat(c.created),
            encrypted=True,
        )
        for c in encrypted
    ]

    return decrypted_pending + encrypted_pending


@calls_router.delete("/{call_id}", status_code=status.HTTP_200_OK)
def delete_call(call_id: CallId) -> None:
    conn = sqlite3.connect(f"{settings.config_path}/storage.db")
    conn.cursor().execute("""delete from notifications where id=(?)""", (str(call_id),))
    conn.cursor().execute("""delete from encrypted where id=(?)""", (str(call_id),))
    conn.commit()
    conn.close()


@calls_router.post("/{call_id}/retry", status_code=status.HTTP_200_OK)
async def retry_call_delivery(call_id: CallId) -> None:
    conn = sqlite3.connect(f"{settings.config_path}/storage.db")
    t = (
        conn.cursor()
        .execute("SELECT * FROM notifications WHERE id = (?)", (str(call_id),))
        .fetchone()
    )
    record = DecryptedTuple(*t)

    notification = Notification(
        id=CallId(UUID(record.id)),
        private_url=TypeAdapter(AnyHttpUrl).validate_python(record.private_url),
        content="",
        aes="",
        iv="",
        tag="",
        created=datetime.fromisoformat(record.created),
    )

    message = CompleteMessage(
        method=record.method,
        headers=json.loads(record.headers),
        params=json.loads(record.params),
        body=record.body,
    )

    if forward_call(notification, message, conn) is None:
        logger.error(
            f"Could not forward call {notification.id} to {notification.private_url}"
        )
        await notify_browsers(
            f"Could not forward call {notification.id} to {notification.private_url}",
            reload_calls=True,
        )
    else:
        await notify_browsers(
            f"Forwarded {notification.id} to {notification.private_url}"
        )

    conn.close()

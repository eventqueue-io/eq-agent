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
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import uvicorn
from fastapi import Request, status, FastAPI, Response
from fastapi.encoders import jsonable_encoder
from funcy import silent
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from globals import setup_db, settings, get_private_key
from users import router as users_router
from endpoints import router as endpoints_router
from calls import sse_router, sse_out, calls_router

logging.basicConfig(encoding="utf-8", level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if not os.path.exists(settings.config_path):
        os.mkdir(settings.config_path)
    conn = setup_db()
    if all(
        [
            os.path.exists(x)
            for x in (
                f"{settings.config_path}/credentials",
                f"{settings.config_path}/public.pem",
                f"{settings.config_path}/private.pem",
            )
        ]
    ):
        asyncio.create_task(sse_out(conn, get_private_key()))
    else:
        conn.close()
    yield
    silent(conn.close)()


app = FastAPI(
    lifespan=lifespan,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)
app.include_router(users_router)
app.include_router(endpoints_router)
app.include_router(sse_router)
app.include_router(calls_router)

app.mount("/assets", StaticFiles(directory="web/assets"), name="assets")


@app.get("/", response_class=Response, include_in_schema=False)
@app.get("/verify", response_class=Response, include_in_schema=False)
@app.get("/activity", response_class=Response, include_in_schema=False)
async def root() -> Response:
    with open("web/index.html", "r") as f:
        return Response(content=f.read(), media_type="text/html")


@app.exception_handler(httpx.TransportError)
async def transport_error_handler(
    _: Request, exc: httpx.TransportError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder({"detail": str(exc)}),
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

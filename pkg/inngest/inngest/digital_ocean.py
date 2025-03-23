"""
DigitalOcean integration for Inngest (Revised for proper registration)
"""

from __future__ import annotations

import asyncio
import json
import typing
import urllib.parse

from ._internal import (
    client_lib,
    comm,
    config_lib,
    const,
    errors,
    execution,
    function,
    net,
    transforms,
    types,
)

FRAMEWORK = const.Framework.DIGITAL_OCEAN


def serve(
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    serve_origin: typing.Optional[str] = None,
    serve_path: typing.Optional[str] = None,
) -> typing.Callable[[dict[str, object], _Context], _Response]:
    """
    Serve Inngest functions in a DigitalOcean Function.
    
    This integration now supports the PUT endpoint for registering functions,
    similar to the FastAPI integration.
    
    Args:
        client: Inngest client.
        functions: List of functions to serve.
        serve_origin: Origin to serve the functions from.
        serve_path: The full function path.
    """
    handler = comm.CommHandler(
        api_base_url=client.api_origin,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
    )

    def main(event: dict[str, object], context: _Context) -> _Response:
        server_kind: typing.Optional[const.ServerKind] = None

        try:
            if not (isinstance(event, dict) and "http" in event):
                raise errors.BodyInvalidError('missing "http" key in event')

            http = _EventHTTP.from_raw(event["http"])
            if isinstance(http, Exception):
                raise errors.BodyInvalidError(http)

            if http.headers is None:
                raise errors.BodyInvalidError(
                    'missing "headers" in event.http; have you set "web: raw"?'
                )
            if http.queryString is None:
                raise errors.BodyInvalidError(
                    'missing "queryString" in event.http; have you set "web: raw"?'
                )

            headers = net.normalize_headers(http.headers)
            _server_kind = transforms.get_server_kind(headers)
            if not isinstance(_server_kind, Exception):
                server_kind = _server_kind
            else:
                client.logger.error(_server_kind)
                server_kind = None

            body = _to_body_bytes(http.body)
            query_params = urllib.parse.parse_qs(http.queryString)

            # DigitalOcean does not give the full function path.
            # We build it by hardcoding a prefix and appending the function name.
            path = "/api/v1/web" + context.function_name
            request_url = urllib.parse.urljoin(context.api_host, path)

            comm_request = comm.CommRequest(
                body=body,
                headers=headers,
                query_params={k: v[0] for k, v in query_params.items() if v},
                raw_request=event,
                request_url=request_url,
                serve_origin=serve_origin,
                serve_path=serve_path,
            )

            if http.method == "GET":
                res = handler.inspect(
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                    server_kind=server_kind,
                    req_sig=net.RequestSignature(
                        body=body,
                        headers=headers,
                        mode=client._mode,
                    ),
                )
                return _to_response(client, res, server_kind)

            if http.method == "POST":
                res = handler.post(comm_request)
                return _to_response(client, res, server_kind)

            if http.method == "PUT":
                # Extract sync_id from the query parameters (if provided)
                sync_id = query_params.get(const.QueryParamKey.SYNC_ID.value, [None])[0]

                # Build the application URL using a helper (mirroring FastAPI)
                app_url = net.create_serve_url(
                    request_url=request_url,
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )

                # Run the registration call. FastAPI awaits handler.register,
                # so here we use asyncio.run to block on the async call.
                res = asyncio.run(
                    handler.register(
                        app_url=app_url,
                        server_kind=server_kind,
                        sync_id=sync_id,
                    )
                )
                return _to_response(client, res, server_kind)

            raise Exception(f"unsupported method: {http.method}")

        except Exception as e:
            comm_res = comm.CommResponse.from_error(client.logger, e)
            if isinstance(e, (errors.BodyInvalidError, errors.QueryParamMissingError)):
                comm_res.status_code = 400

            return _to_response(client, comm_res, server_kind)

    return main


def _get_first(
    items: typing.Optional[list[types.T]],
) -> typing.Optional[types.T]:
    if items is None or len(items) == 0:
        return None
    return items[0]


def _to_body_bytes(body: typing.Optional[str]) -> bytes:
    if body is None:
        return b""
    return body.encode("utf-8")


def _to_response(
    client: client_lib.Inngest,
    comm_res: comm.CommResponse,
    server_kind: typing.Union[const.ServerKind, None],
) -> _Response:
    return {
        "body": comm_res.body,  # type: ignore
        "headers": {
            **comm_res.headers,
            **net.create_headers(
                env=client.env,
                framework=FRAMEWORK,
                server_kind=server_kind,
            ),
        },
        "statusCode": comm_res.status_code,
    }


class _EventHTTP(types.BaseModel):
    body: typing.Optional[str] = None
    headers: typing.Optional[dict[str, str]] = None
    method: typing.Optional[str] = None
    path: typing.Optional[str] = None
    queryString: typing.Optional[str] = None  # noqa: N815


class _Context(typing.Protocol):
    # For example: "https://faas-nyc1-2ef2e6cc.doserverless.co"
    api_host: str

    # For example: "/fn-b094417f/sample/hello"
    function_name: str


class _Response(typing.TypedDict):
    body: str
    headers: dict[str, str]
    statusCode: int
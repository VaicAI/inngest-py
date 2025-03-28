import threading
import unittest

import inngest
import inngest.tornado
import tornado.httpclient
import tornado.ioloop
import tornado.log
import tornado.testing
import tornado.web
from inngest._internal import server_lib
from inngest.experimental import dev_server
from test_core import base, net

from . import cases
from .cases.base import Case

_framework = server_lib.Framework.TORNADO
_app_id = f"{_framework.value}-functions"

_client = inngest.Inngest(
    api_base_url=dev_server.server.origin,
    app_id=_app_id,
    event_api_base_url=dev_server.server.origin,
    is_production=False,
)

_cases: list[Case] = []
for case in cases.create_sync_cases(_client, _framework):
    if case.name == "batch_that_needs_api":
        # Skip because the test is flaky for Tornado for some reason
        continue

    _cases.append(case)

_fns: list[inngest.Function] = []
for case in _cases:
    if isinstance(case.fn, list):
        _fns.extend(case.fn)
    else:
        _fns.append(case.fn)


# Not using tornado.testing.AsyncHTTPTestCase because it:
# - Does not accept requests to localhost (only 127.0.0.1). This won't work with
#   the Dev Server since sometimes it converts 127.0.0.1 to localhost.
# - Binds to a different random port for each test, which necessitates
#   registration on each test.
class TestFunctions(unittest.IsolatedAsyncioTestCase):
    client = _client
    tornado_thread: threading.Thread

    @classmethod
    def setUpClass(cls) -> None:
        port = net.get_available_port()

        def start_app() -> None:
            app = tornado.web.Application()
            app.listen(port)
            inngest.tornado.serve(
                app,
                _client,
                _fns,
            )
            tornado.ioloop.IOLoop.current().start()

        cls.tornado_thread = threading.Thread(daemon=True, target=start_app)
        cls.tornado_thread.start()
        base.register(port)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tornado_thread.join(timeout=1)


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFunctions, test_name, case.run_test)


if __name__ == "__main__":
    tornado.testing.main()

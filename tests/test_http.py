from datetime import datetime, timezone
from io import BytesIO
import unittest
from urllib.error import HTTPError

from wild_rift_skin_version.http import fetch_text


class HttpTests(unittest.TestCase):
    def test_rate_limit_retry_after_and_recovery(self):
        responses = [HTTPError("https://example.test/data", 429, "limited", {"Retry-After": "25"}, BytesIO(b"limited")), BytesIO(b"fresh")]
        delays = []

        def opener(*args, **kwargs):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        self.assertEqual(fetch_text("https://example.test/data", opener=opener, wait=delays.append), "fresh")
        self.assertEqual(delays, [25])

    def test_http_date_retry_after_and_permanent_errors(self):
        responses = [HTTPError("https://example.test/data", 503, "busy", {"Retry-After": "Sun, 27 Sep 2026 12:01:00 GMT"}, BytesIO()), BytesIO(b"fresh")]
        delays = []

        def opener(*args, **kwargs):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        fetch_text("https://example.test/data", opener=opener, wait=delays.append,
                   now=lambda: datetime(2026, 9, 27, 12, tzinfo=timezone.utc).timestamp())
        self.assertEqual(delays, [60])
        requests = []

        def missing(*args, **kwargs):
            requests.append(True)
            raise HTTPError("https://example.test/missing", 404, "missing", {}, BytesIO())

        with self.assertRaises(HTTPError):
            fetch_text("https://example.test/missing", opener=missing, wait=lambda _: self.fail("must not retry"))
        self.assertEqual(len(requests), 1)

    def test_long_cooling_off_period_does_not_retry_early(self):
        def opener(*args, **kwargs):
            raise HTTPError("https://example.test/data", 429, "limited", {"Retry-After": "600"}, BytesIO())
        with self.assertRaises(HTTPError):
            fetch_text("https://example.test/data", opener=opener, wait=lambda _: self.fail("must not retry before cooldown"))

"""HTTP text requests with bounded retries and Retry-After support."""
from email.utils import parsedate_to_datetime
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch_text(url, *, opener=urlopen, wait=time.sleep, now=time.time, attempts=5):
    for attempt in range(attempts):
        delay = 2 ** attempt
        try:
            request = Request(url, headers={"User-Agent": "WildRiftSkinVersion/0.1 (non-commercial community archive)"})
            with opener(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except HTTPError as error:
            permanent = error.code != 429 and error.code < 500
            if error.code in (429, 503):
                retry_after = error.headers.get("Retry-After", "")
                try:
                    requested = float(retry_after) if re.fullmatch(r"\d+(?:\.\d+)?", retry_after) else parsedate_to_datetime(retry_after).timestamp() - now()
                except (TypeError, ValueError, OverflowError):
                    requested = 0
                delay = max(15 * 2 ** attempt if error.code == 429 else delay, requested)
                permanent = permanent or delay > 120
            error.close()
            if permanent or attempt == attempts - 1:
                raise
        except (URLError, TimeoutError, OSError):
            if attempt == attempts - 1:
                raise
        wait(delay)

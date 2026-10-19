# Pass to every OpenRouter call as timeout_ms=REQUEST_TIMEOUT_MS, retries=None.
# The SDK's httpx client otherwise times out after 5s and retries timeouts and
# 5XX responses with backoff for up to an hour, so slow models hang the UI.
REQUEST_TIMEOUT_MS = 180_000

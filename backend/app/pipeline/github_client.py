import os
import time
import random
import requests
from typing import Dict, Any, Optional

class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""
    def __init__(self, message: str, status_code: int, response_body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

class GitHubRateLimitError(GitHubAPIError):
    """Raised when GitHub rate limits (primary or secondary) are hit."""
    pass

class GitHubClient:
    def __init__(self, token: Optional[str] = None, supabase_client: Any = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            print("⚠️ WARNING: GITHUB_TOKEN is missing. Requests will be unauthenticated and rate limits will be highly restricted.")
        
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            })
        
        # Supabase client used to persist ETag cache across cron runs
        # Without this, ETags are lost when the GitHub Actions runner shuts down
        self._supabase = supabase_client

        # In-memory ETag cache: Maps URL -> {"etag": str, "data": Any}
        # Pre-populated from DB on startup so yesterday's ETags are available immediately
        self._etag_cache: Dict[str, Dict[str, Any]] = {}
        if self._supabase:
            self._load_etag_cache_from_db()
        
        # Rate limit metrics tracked dynamically
        self.limit: int = 5000 if self.token else 60
        self.remaining: int = self.limit
        self.reset_time: int = 0
        self.request_count: int = 0

    def _load_etag_cache_from_db(self) -> None:
        """
        Loads all stored ETags from the Supabase etag_cache table into memory.

        Why: GitHub Actions runners are ephemeral — each cron run is a fresh process.
        By loading from DB on startup, we get all ETags from yesterday's run so that
        unchanged repos return a 304 (free, fast) instead of a full 200 (costly).
        """
        try:
            resp = self._supabase.table("etag_cache").select("resource_key, etag, response_data").execute()
            for row in (resp.data or []):
                self._etag_cache[row["resource_key"]] = {
                    "etag": row["etag"],
                    "data": row.get("response_data")  # May be None if column was just added
                }
            print(f"💾 ETag cache loaded: {len(self._etag_cache)} entries from DB.")
        except Exception as e:
            print(f"⚠️ Failed to load ETag cache from DB (non-fatal): {e}")

    def _save_etag_to_db(self, url: str, etag: str, data: Any) -> None:
        """
        Persists a new ETag + response data to the Supabase etag_cache table.

        Why: We store the response data alongside the ETag because when GitHub returns a
        304 next time, it sends NO body — we must return the previously cached data.
        Without storing it in DB, the next cron run would have the ETag but nothing to return.
        We only store list responses (issues), not giant tree payloads, to keep the table small.
        """
        try:
            # Only persist list responses (issue lists). Skip large tree/blob payloads.
            storable_data = data if isinstance(data, list) else None
            self._supabase.table("etag_cache").upsert({
                "resource_key": url,
                "etag": etag,
                "response_data": storable_data,
                "updated_at": "now()"
            }).execute()
        except Exception as e:
            # Non-fatal: if DB save fails, the in-memory cache still works for this run
            print(f"⚠️ Failed to save ETag to DB (non-fatal): {e}")

    def _parse_rate_limits(self, headers: Any) -> None:
        """Parses rate limit headers from the response."""
        try:
            if "X-RateLimit-Limit" in headers:
                self.limit = int(headers["X-RateLimit-Limit"])
            if "X-RateLimit-Remaining" in headers:
                self.remaining = int(headers["X-RateLimit-Remaining"])
            if "X-RateLimit-Reset" in headers:
                self.reset_time = int(headers["X-RateLimit-Reset"])
        except (ValueError, TypeError) as e:
            print(f"⚠️ Error parsing rate limit headers: {e}")

    def request(self, method: str, url: str, **kwargs) -> Any:
        """Makes a request with retries, exponential backoff, and rate limit parsing."""
        self.request_count += 1
        
        # Proactive Rate-Limit Check
        if self.remaining <= 10 and time.time() < self.reset_time:
            wait_time = int(self.reset_time - time.time()) + 1
            print(f"🛑 CRITICAL: GitHub API rate limit nearly exhausted ({self.remaining} left). Reset in {wait_time}s.")
            if wait_time < 300: # If reset is in less than 5 mins, sleep
                print(f"💤 Sleeping for {wait_time}s until rate limit resets...")
                time.sleep(wait_time)
            else:
                raise GitHubRateLimitError(
                    "GitHub API rate limit exhausted. Deferring operations to the next run.",
                    status_code=403
                )

        max_attempts = 3
        base_delay = 2.0
        
        for attempt in range(1, max_attempts + 1):
            try:
                # Add ETag header if we have a cached version for GET requests
                is_get = method.upper() == "GET"
                cached_item = self._etag_cache.get(url) if is_get else None
                
                if cached_item and "etag" in cached_item:
                    headers = kwargs.get("headers", {})
                    headers["If-None-Match"] = cached_item["etag"]
                    kwargs["headers"] = headers

                response = self.session.request(method, url, timeout=(10, 30), **kwargs)
                self._parse_rate_limits(response.headers)

                # Handle Conditional request cache hit (304 Not Modified)
                if response.status_code == 304 and cached_item:
                    cached_data = cached_item.get("data")
                    # If we have cached data (from DB), return it.
                    # If data is None (ETag was stored but response_data column was added later),
                    # return an empty list so the pipeline skips this repo gracefully.
                    return cached_data if cached_data is not None else []

                # Handle Success
                if 200 <= response.status_code < 300:
                    data = response.json()
                    
                    # Store ETag in memory AND persist to DB for next cron run
                    if is_get and "ETag" in response.headers:
                        new_etag = response.headers["ETag"]
                        self._etag_cache[url] = {
                            "etag": new_etag,
                            "data": data
                        }
                        # Persist to DB so tomorrow's run can use this ETag (fixes Gap 2)
                        if self._supabase:
                            self._save_etag_to_db(url, new_etag, data)
                    return data

                # Handle Rate Limiting (429 or 403 with Rate Limit headers)
                if response.status_code == 429 or (response.status_code == 403 and "X-RateLimit-Remaining" in response.headers and int(response.headers.get("X-RateLimit-Remaining", 1)) == 0):
                    retry_after = int(response.headers.get("Retry-After", response.headers.get("X-RateLimit-Reset", time.time() + 60) - time.time()))
                    retry_after = max(retry_after, 5) # Minimum 5s sleep
                    print(f"⚠️ Hit GitHub API rate limit. Sleep for {retry_after}s (Attempt {attempt}/{max_attempts})")
                    time.sleep(retry_after)
                    continue

                # Handle Transient Server Errors (5xx)
                if response.status_code >= 500:
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 1.0)
                    print(f"⚠️ GitHub server error ({response.status_code}). Retrying in {delay:.2f}s... (Attempt {attempt}/{max_attempts})")
                    time.sleep(delay)
                    continue

                # Unrecoverable Client Error (4xx)
                raise GitHubAPIError(
                    f"GitHub API returned error status {response.status_code} for {url}",
                    status_code=response.status_code,
                    response_body=response.text
                )

            except requests.exceptions.RequestException as e:
                if attempt == max_attempts:
                    raise GitHubAPIError(f"GitHub API connection failed: {e}", status_code=500)
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 1.0)
                print(f"⚠️ Connection error: {e}. Retrying in {delay:.2f}s...")
                time.sleep(delay)

        raise GitHubAPIError(f"Failed to get successful response from GitHub after {max_attempts} attempts", status_code=500)

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self.request("GET", url, params=params)

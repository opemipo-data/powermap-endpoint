"""Supabase client setup for PowerFeed.

Logic:
1. Read SUPABASE_URL and SUPABASE_KEY from the environment.
2. Build the Supabase client lazily (on first call), not at import time,
   so importing this module never crashes when env vars are absent
   (e.g. during tests).
3. Cache the client so every request in a process reuses one client.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return a cached Supabase client built from environment variables.

    Reads SUPABASE_URL and SUPABASE_KEY. Raises KeyError if either
    variable is unset.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)

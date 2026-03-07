import uuid
import hashlib
import time
from fastapi import Request, HTTPException
from typing import Dict, Any

class AuthService:
    def __init__(self):
        # Local mock storage for Client IDs and rate limiting buckets
        self.ip_to_client_id: Dict[str, str] = {}
        self.rate_limiter: Dict[str, Dict[str, Any]] = {}
        # Simple limit: 5 requests per 60 seconds
        self.limit = 10 
        self.window = 60

    def get_ip(self, request: Request) -> str:
        """Extracts the real client IP, considering proxies."""
        # Check X-Forwarded-For first (common in proxies like Vercel/HF)
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # Usually the first IP in the comma-separated list is the client's
            return xff.split(",")[0].strip()
        
        # Fallback to direct client host
        return request.client.host if request.client else "unknown"

    def get_or_create_client_id(self, ip: str) -> str:
        """Returns the same client_id per IP. Generates a random one if not exists."""
        if ip not in self.ip_to_client_id:
            # Use a random UUID for the client ID instead of hashing IP to avoid conflicts if IP changes
            # BUT we keep the IP map for local rate limiting.
            new_id = f"client_{uuid.uuid4().hex[:12]}"
            self.ip_to_client_id[ip] = new_id
            # Also store it in a reverse map to allow any valid ID from any IP (more lenient for proxies)
            if not hasattr(self, 'valid_client_ids'):
                self.valid_client_ids = set()
            self.valid_client_ids.add(new_id)
        return self.ip_to_client_id[ip]

    def check_rate_limit(self, client_id: str, ip: str):
        """Enforces a rate limit for each client_id + ip hybrid."""
        key = f"{client_id}:{ip}"
        now = time.time()
        
        if key not in self.rate_limiter:
            self.rate_limiter[key] = {"count": 1, "start_time": now}
            return True
            
        bucket = self.rate_limiter[key]
        if now - bucket["start_time"] > self.window:
            # Reset bucket
            self.rate_limiter[key] = {"count": 1, "start_time": now}
            return True
            
        if bucket["count"] >= self.limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a minute.")
            
        bucket["count"] += 1
        return True

    def validate_client(self, client_id: str, ip: str):
        """Check if client_id exists and is valid for this IP."""
        # Leniency: If the ID is known to be valid, allow it even if IP changed (common with Vercel)
        if not hasattr(self, 'valid_client_ids'):
            self.valid_client_ids = set()
            
        is_known = client_id in self.valid_client_ids
        is_direct_match = (ip in self.ip_to_client_id and self.ip_to_client_id[ip] == client_id)
        
        if not (is_known or is_direct_match):
            raise HTTPException(status_code=403, detail="Invalid client_id session.")
            
        self.check_rate_limit(client_id, ip)

auth_service = AuthService()

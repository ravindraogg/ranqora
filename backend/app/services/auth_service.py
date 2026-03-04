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

    def get_or_create_client_id(self, ip: str) -> str:
        """Returns the same client_id per IP. Generates a random one if not exists."""
        if ip not in self.ip_to_client_id:
            # Hash IP with salt to avoid revealing true IP, or just use a random UUID
            random_salt = uuid.uuid4().hex
            self.ip_to_client_id[ip] = f"client_{hashlib.sha256((ip + random_salt).encode()).hexdigest()[:12]}"
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
        if ip not in self.ip_to_client_id or self.ip_to_client_id[ip] != client_id:
            raise HTTPException(status_code=403, detail="Invalid client_id for this IP.")
        self.check_rate_limit(client_id, ip)

auth_service = AuthService()

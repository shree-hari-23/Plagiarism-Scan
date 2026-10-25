"""
Fluxbase Database Client
Sends raw SQL to Fluxbase REST API (POST /api/execute-sql).

Per the Fluxbase Integration Guide v4.0:
  - Endpoint: POST https://fluxbase.vercel.app/api/execute-sql
  - Auth:     Bearer <FLUXBASE_API_KEY>
  - Body:     { "projectId": "...", "query": "<SQL>" }
  - Rows at:  response["result"]["rows"]
"""

import requests
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class FluxbaseClient:
    """
    Thin wrapper around the Fluxbase REST SQL API.
    All queries go through `execute(sql, params)`.
    Parameters are interpolated client-side (safe for backend use).
    """

    def __init__(self):
        self.url = settings.FLUXBASE_URL
        self.api_key = settings.FLUXBASE_API_KEY
        self.project_id = settings.FLUXBASE_PROJECT_ID

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Connection": "close",
        }

    def execute(self, sql: str, silent: bool = False) -> List[Dict[str, Any]]:
        """
        Execute a raw SQL statement and return the rows.
        Returns an empty list for non-SELECT statements.
        Automatically retries on transient network drops or socket resets.
        Raises RuntimeError on persistent Fluxbase errors.
        """
        import time
        payload = {
            "projectId": self.project_id,
            "query": sql,
        }
        max_retries = 2
        data = None

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    self.url,
                    json=payload,
                    headers=self._headers(),
                    timeout=8,
                )
                if resp.status_code != 200 and not silent:
                    print(f"Fluxbase Error HTTP {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.RequestException as e:
                if attempt < max_retries:
                    time.sleep(0.4 * attempt)
                    continue
                if not silent:
                    print(f"Fluxbase network error after {max_retries} attempts: {e}. Switching to local SQLite fallback...")
                settings.disable_fluxbase()
                raise RuntimeError(f"Fluxbase network error: {e}") from e

        if not data.get("success"):
            err = data.get("error", {})
            msg = err.get("message", "Unknown Fluxbase error")
            code = err.get("code", "UNKNOWN")
            print(f"Fluxbase SQL error [{code}]: {msg}")
            raise RuntimeError(f"Fluxbase error [{code}]: {msg}")

        # Rows live at data["result"]["rows"] per the guide
        result = data.get("result") or {}
        return result.get("rows") or []

    def execute_ddl(self, sql: str) -> None:
        """Execute DDL (CREATE TABLE, etc.) — ignores rows."""
        self.execute(sql)

    def health_check(self) -> bool:
        """Returns True if Fluxbase connection is working (fast 3.5s timeout)."""
        try:
            payload = {
                "projectId": self.project_id,
                "query": "SELECT 1 AS ok;",
            }
            resp = requests.post(
                self.url,
                json=payload,
                headers=self._headers(),
                timeout=3.5,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Fluxbase health check failed / timed out: {e}")
            return False

    def ensure_bucket(self, bucket_name: str) -> None:
        """Ensure the target bucket exists in Fluxbase Storage."""
        url = "https://fluxbase.vercel.app/api/storage/buckets"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "projectId": self.project_id,
            "name": bucket_name,
            "isPublic": False
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
        except Exception as e:
            logger.warning(f"Bucket ensure error (could already exist): {e}")

    def upload_file(self, filename: str, file_bytes: bytes, content_type: str) -> str:
        """
        Uploads a file to Fluxbase S3 storage.
        Returns the s3_key of the uploaded file.
        """
        self.ensure_bucket("documents")
        
        url = "https://fluxbase.vercel.app/api/storage/upload"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        files = {
            "file": (filename, file_bytes, content_type)
        }
        data = {
            "bucketId": "documents",
            "projectId": self.project_id
        }
        
        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
            resp.raise_for_status()
            res = resp.json()
            if not res.get("success"):
                raise RuntimeError(res.get("error", {}).get("message", "Upload failed"))
            return res["file"]["s3_key"]
        except Exception as e:
            logger.error(f"Fluxbase upload error: {e}")
            raise RuntimeError(f"Fluxbase upload error: {e}")

    def get_file_url(self, s3_key: str) -> str:
        """Get a 15-minute presigned download URL for a file in Fluxbase S3 Storage."""
        import urllib.parse
        encoded_key = urllib.parse.quote(s3_key)
        url = f"https://fluxbase.vercel.app/api/storage/url?s3Key={encoded_key}&projectId={self.project_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            res = resp.json()
            if not res.get("success"):
                raise RuntimeError(res.get("error", {}).get("message", "Failed to get presigned URL"))
            return res["url"]
        except Exception as e:
            logger.error(f"Fluxbase get URL error: {e}")
            raise RuntimeError(f"Fluxbase get URL error: {e}")

    def delete_file(self, s3_key: str) -> None:
        """Delete a file from Fluxbase S3 Storage."""
        url = "https://fluxbase.vercel.app/api/storage/files"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "s3Key": s3_key,
            "projectId": self.project_id
        }
        try:
            resp = requests.delete(url, headers=headers, json=payload, timeout=10)
            # Do not raise_for_status to prevent blocking document delete on missing files
        except Exception as e:
            logger.warning(f"Fluxbase delete file error: {e}")


# Singleton instance
_client: Optional[FluxbaseClient] = None


def get_fluxbase_client() -> FluxbaseClient:
    global _client
    if _client is None:
        _client = FluxbaseClient()
    return _client


def initialize_fluxbase_tables():
    """
    Create all required tables in Fluxbase if they don't exist.
    Fluxbase uses AWS MySQL — uses MySQL DDL syntax.
    Called at app startup when Fluxbase credentials are configured.
    """
    client = get_fluxbase_client()
    ddl_statements = [
        """CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            role VARCHAR(10) DEFAULT 'user',
            is_superuser BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT NOW(),
            updated_at DATETIME DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            filename VARCHAR(500) NOT NULL,
            file_path VARCHAR(1000) NOT NULL,
            content_type VARCHAR(255),
            status VARCHAR(50) DEFAULT 'pending',
            extracted_text LONGTEXT,
            meta_data JSON,
            created_at DATETIME DEFAULT NOW(),
            updated_at DATETIME DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS scans (
            id INT AUTO_INCREMENT PRIMARY KEY,
            document_id INT,
            initiated_by INT,
            status VARCHAR(50) DEFAULT 'queued',
            scan_mode VARCHAR(50) DEFAULT 'standard',
            overall_score FLOAT,
            report_data JSON,
            agent_trace JSON,
            citations_detected JSON,
            progress INT DEFAULT 0,
            current_step VARCHAR(255),
            created_at DATETIME DEFAULT NOW(),
            completed_at DATETIME,
            updated_at DATETIME DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS scan_matches (
            id INT AUTO_INCREMENT PRIMARY KEY,
            scan_id INT,
            source_document_id INT,
            chunk_text LONGTEXT,
            matched_text LONGTEXT,
            similarity_score FLOAT,
            created_at DATETIME DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS document_chunks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            document_id INT,
            chunk_index INT,
            chunk_text LONGTEXT,
            created_at DATETIME DEFAULT NOW()
        )""",
    ]

    for ddl in ddl_statements:
        table_name = ddl.strip().split()[5]
        try:
            client.execute_ddl(ddl.strip())
            logger.info(f"Table '{table_name}' ready in Fluxbase.")
        except Exception as e:
            logger.warning(f"Table '{table_name}' DDL skipped: {e}")

    # Auto-migrate scans table if columns are missing
    for col_def in [
        ("scan_mode", "ALTER TABLE scans ADD COLUMN scan_mode VARCHAR(50) DEFAULT 'standard';"),
        ("agent_trace", "ALTER TABLE scans ADD COLUMN agent_trace JSON;"),
        ("citations_detected", "ALTER TABLE scans ADD COLUMN citations_detected JSON;")
    ]:
        try:
            client.execute(col_def[1], silent=True)
        except Exception:
            pass # column already exists

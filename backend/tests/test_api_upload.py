from unittest.mock import patch

def test_upload_file(client):
    # Register and Login
    client.post(
        "/api/v1/auth/register",
        params={"email": "uploader@example.com", "password": "password123"}
    )
    login_res = client.post(
        "/api/v1/auth/login",
        data={"username": "uploader@example.com", "password": "password123"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Mock background task to avoid actual execution
    with patch("app.api.v1.endpoints.documents.process_document"):
        file_content = b"This is a test document."
        files = {"file": ("test.txt", file_content, "text/plain")}
        
        response = client.post("/api/v1/documents/", files=files, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "document_id" in data
        assert data["status"] == "pending"

def test_get_document_404(client):
    response = client.get("/api/v1/documents/9999")
    assert response.status_code == 404

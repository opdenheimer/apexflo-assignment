import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_app_initialization():
    """Verify that the FastAPI application initializes cleanly and routes respond."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request health endpoint
        response = await client.get("/health")
        # Even if DB/Redis are not yet connected, the endpoint responds gracefully with degraded/healthy
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "postgres" in data["services"]
        assert "redis" in data["services"]

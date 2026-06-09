from httpx import AsyncClient


async def test_home_redirects_to_jobs(client: AsyncClient):
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/jobs"


async def test_jobs_page_loads(client: AsyncClient):
    response = await client.get("/jobs")
    assert response.status_code == 200


async def test_admin_requires_auth(client: AsyncClient):
    response = await client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert "/auth/login" in response.headers["location"]

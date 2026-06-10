from httpx import AsyncClient


async def test_active_company_profile_loads(client: AsyncClient, company):
    response = await client.get(f"/companies/{company.slug}")
    assert response.status_code == 200


async def test_defunct_company_hidden_from_anon(client: AsyncClient, company):
    """Non-staff users must get a 404 for a defunct company."""
    company.defunct = True
    response = await client.get(f"/companies/{company.slug}")
    assert response.status_code == 404


async def test_defunct_company_visible_to_staff(
    client: AsyncClient, company, staff_user, make_session_cookie
):
    """Staff can still reach a defunct company profile to re-enable it."""
    company.defunct = True
    client.cookies.set("session", make_session_cookie({"user_id": staff_user.id}))
    response = await client.get(f"/companies/{company.slug}")
    assert response.status_code == 200

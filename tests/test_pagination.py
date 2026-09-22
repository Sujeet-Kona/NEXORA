import pytest

from backend.db.models import OrganizationRole, User, UserRole


PASSWORD = "MySecret123!"


def register_user(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201

    return response.json()


def login(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def auth_headers(token):
    return {
        "Authorization": f"Bearer {token}",
    }


def get_user(db, email):
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    assert user is not None

    return user


def promote_to_admin(db, email):
    user = get_user(db, email)

    user.role = UserRole.ADMIN
    db.commit()
    db.refresh(user)

    return user


def create_organization(client, token, name):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
        headers=auth_headers(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def create_document(client, token, organization_id, name):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": name},
        headers=auth_headers(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def add_member(client, owner_token, organization_id, user_id):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": user_id,
            "role": OrganizationRole.MEMBER,
        },
        headers=auth_headers(owner_token),
    )

    assert response.status_code == 201

    return response.json()


def build_owner(client, suffix):
    email = f"pagination-owner-{suffix}@example.com"

    register_user(client, email)

    token = login(client, email)

    organization_id = create_organization(
        client,
        token,
        f"Pagination Company {suffix}",
    )

    return {
        "email": email,
        "token": token,
        "organization_id": organization_id,
    }


def documents_url(organization_id):
    return f"/api/v1/organizations/{organization_id}/documents"


def members_url(organization_id):
    return f"/api/v1/organizations/{organization_id}/members"


def test_list_documents_returns_items_ordered_by_id(client):
    owner = build_owner(client, "documents-order")

    document_ids = [
        create_document(
            client,
            owner["token"],
            owner["organization_id"],
            f"ordered-{index}.pdf",
        )
        for index in range(3)
    ]

    response = client.get(
        documents_url(owner["organization_id"]),
        headers=auth_headers(owner["token"]),
    )

    assert response.status_code == 200

    assert [document["id"] for document in response.json()] == (
        document_ids
    )


def test_list_documents_paginates_with_limit_and_offset(client):
    owner = build_owner(client, "documents-pages")

    document_ids = [
        create_document(
            client,
            owner["token"],
            owner["organization_id"],
            f"paged-{index}.pdf",
        )
        for index in range(5)
    ]

    url = documents_url(owner["organization_id"])
    headers = auth_headers(owner["token"])

    first_page = client.get(
        url,
        params={"limit": 2, "offset": 0},
        headers=headers,
    )

    second_page = client.get(
        url,
        params={"limit": 2, "offset": 2},
        headers=headers,
    )

    final_page = client.get(
        url,
        params={"limit": 2, "offset": 4},
        headers=headers,
    )

    beyond_last_page = client.get(
        url,
        params={"limit": 2, "offset": 6},
        headers=headers,
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert final_page.status_code == 200
    assert beyond_last_page.status_code == 200

    assert [
        document["id"] for document in first_page.json()
    ] == document_ids[0:2]

    assert [
        document["id"] for document in second_page.json()
    ] == document_ids[2:4]

    assert [
        document["id"] for document in final_page.json()
    ] == document_ids[4:5]

    assert beyond_last_page.json() == []


def test_list_documents_pagination_accepts_boundary_limits(client):
    owner = build_owner(client, "documents-bounds")

    create_document(
        client,
        owner["token"],
        owner["organization_id"],
        "bounded.pdf",
    )

    url = documents_url(owner["organization_id"])
    headers = auth_headers(owner["token"])

    smallest_page = client.get(
        url,
        params={"limit": 1, "offset": 0},
        headers=headers,
    )

    largest_page = client.get(
        url,
        params={"limit": 200, "offset": 0},
        headers=headers,
    )

    assert smallest_page.status_code == 200
    assert len(smallest_page.json()) == 1

    assert largest_page.status_code == 200
    assert len(largest_page.json()) == 1


def test_document_pagination_stays_tenant_scoped(client):
    owner_a = build_owner(client, "documents-scope-a")
    owner_b = build_owner(client, "documents-scope-b")

    document_ids_a = [
        create_document(
            client,
            owner_a["token"],
            owner_a["organization_id"],
            f"scope-a-{index}.pdf",
        )
        for index in range(3)
    ]

    document_ids_b = [
        create_document(
            client,
            owner_b["token"],
            owner_b["organization_id"],
            f"scope-b-{index}.pdf",
        )
        for index in range(3)
    ]

    response = client.get(
        documents_url(owner_a["organization_id"]),
        params={"limit": 100, "offset": 0},
        headers=auth_headers(owner_a["token"]),
    )

    assert response.status_code == 200

    returned_ids = [
        document["id"] for document in response.json()
    ]

    assert returned_ids == document_ids_a
    assert set(returned_ids).isdisjoint(document_ids_b)


def test_list_members_paginates_with_limit_and_offset(
    client,
    db,
):
    owner = build_owner(client, "members-pages")

    owner_user = get_user(db, owner["email"])

    added_member_ids = []

    for index in range(2):
        email = f"pagination-member-{index}@example.com"

        register_user(client, email)

        user = get_user(db, email)

        add_member(
            client,
            owner["token"],
            owner["organization_id"],
            user.id,
        )

        added_member_ids.append(user.id)

    expected_user_ids = [
        owner_user.id,
        *added_member_ids,
    ]

    url = members_url(owner["organization_id"])
    headers = auth_headers(owner["token"])

    first_page = client.get(
        url,
        params={"limit": 2, "offset": 0},
        headers=headers,
    )

    second_page = client.get(
        url,
        params={"limit": 2, "offset": 2},
        headers=headers,
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    assert [
        member["user_id"] for member in first_page.json()
    ] == expected_user_ids[0:2]

    assert [
        member["user_id"] for member in second_page.json()
    ] == expected_user_ids[2:3]


def test_list_members_defaults_when_no_params(client, db):
    owner = build_owner(client, "members-defaults")

    owner_user = get_user(db, owner["email"])

    response = client.get(
        members_url(owner["organization_id"]),
        headers=auth_headers(owner["token"]),
    )

    assert response.status_code == 200

    assert [
        member["user_id"] for member in response.json()
    ] == [owner_user.id]


def test_list_users_paginates_with_limit_and_offset(client, db):
    admin_email = "pagination-admin@example.com"

    register_user(client, admin_email)
    promote_to_admin(db, admin_email)

    admin_user = get_user(db, admin_email)

    other_emails = [
        f"pagination-user-{index}@example.com"
        for index in range(3)
    ]

    for email in other_emails:
        register_user(client, email)

    expected_user_ids = [
        admin_user.id,
        *[
            get_user(db, email).id
            for email in other_emails
        ],
    ]

    headers = auth_headers(login(client, admin_email))

    first_page = client.get(
        "/api/v1/users",
        params={"limit": 2, "offset": 0},
        headers=headers,
    )

    second_page = client.get(
        "/api/v1/users",
        params={"limit": 2, "offset": 2},
        headers=headers,
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    assert [
        user["id"] for user in first_page.json()
    ] == expected_user_ids[0:2]

    assert [
        user["id"] for user in second_page.json()
    ] == expected_user_ids[2:4]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
    ],
)
def test_list_endpoints_reject_out_of_range_pagination(
    client,
    db,
    params,
):
    admin_email = "pagination-bounds-admin@example.com"

    register_user(client, admin_email)
    promote_to_admin(db, admin_email)

    owner = build_owner(client, "validation")

    targets = [
        (
            "/api/v1/users",
            login(client, admin_email),
        ),
        (
            members_url(owner["organization_id"]),
            owner["token"],
        ),
        (
            documents_url(owner["organization_id"]),
            owner["token"],
        ),
    ]

    for path, token in targets:
        response = client.get(
            path,
            params=params,
            headers=auth_headers(token),
        )

        assert response.status_code == 422

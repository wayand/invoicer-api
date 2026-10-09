"""
Organization logos: what is uploaded is served back, wherever UPLOAD_FOLDER
points (relative to the working directory, as in production, or absolute),
and the serving route cannot be used to read anything else.
"""

import io

import pytest
from flask_jwt_extended import create_access_token

from app.models.organization import Organization

PNG = b"\x89PNG\r\n\x1a\n" + b"not-a-real-image-but-the-bytes-we-expect-back"


def auth_headers(user) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(identity=user.email)}"
    }


def upload(client, user, organization, name="logo.png", content=PNG):
    return client.post(
        f"/organizations/{organization.id}/upload-logo",
        data={"file": (io.BytesIO(content), name)},
        content_type="multipart/form-data",
        headers=auth_headers(user),
    )


def logo_url(organization, name="logo.png") -> str:
    return f"/organizations/{organization.slug}/logo/{name}"


@pytest.fixture
def upload_folder(app, tmp_path, monkeypatch):
    """An absolute upload folder for the test."""
    folder = tmp_path / "uploads"
    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", str(folder))
    return folder


def test_uploaded_logo_is_served_from_an_absolute_upload_folder(
    client, test_user, organization, upload_folder
):
    assert upload(client, test_user, organization).status_code == 200

    res = client.get(logo_url(organization))

    assert res.status_code == 200
    assert res.mimetype == "image/png"
    assert res.data == PNG


def test_uploaded_logo_is_served_from_a_relative_upload_folder(
    client, app, test_user, organization, tmp_path, monkeypatch
):
    """The production setting is UPLOAD_FOLDER=./uploads, relative to the
    working directory the app runs in."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", "./uploads")

    assert upload(client, test_user, organization).status_code == 200

    stored = tmp_path / "uploads/organizations/demo-aps/logo/logo.png"
    assert stored.read_bytes() == PNG
    res = client.get(logo_url(organization))
    assert res.status_code == 200
    assert res.data == PNG


def test_upload_stores_the_file_name_on_the_organization(
    client, db_session, test_user, organization, upload_folder
):
    upload(client, test_user, organization, name="my logo.png")

    db_session.refresh(organization)
    assert organization.logo == "my_logo.png"


def test_missing_logo_is_a_404_not_a_200(client, organization, upload_folder):
    res = client.get(logo_url(organization, "nothing-here.png"))

    assert res.status_code == 404
    assert "error" in res.get_json()


def test_logo_route_cannot_read_files_outside_the_logo_folder(
    client, organization, upload_folder
):
    upload_folder.mkdir(parents=True)
    (upload_folder / "secret.txt").write_text("top secret")

    res = client.get(logo_url(organization, "..%2F..%2F..%2Fsecret.txt"))

    assert res.status_code == 404
    assert b"top secret" not in res.data


def test_logo_route_rejects_a_slug_made_of_dot_segments(client, upload_folder):
    # reachable as organizations/../logo/x.png only if organizations/ exists
    (upload_folder / "organizations").mkdir(parents=True)
    (upload_folder / "logo").mkdir()
    (upload_folder / "logo" / "x.png").write_bytes(PNG)

    res = client.get("/organizations/%2e%2e/logo/x.png")

    assert res.status_code == 404
    assert PNG not in res.data


def test_upload_to_another_organization_is_not_found(
    client, db_session, test_user, country, upload_folder
):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.commit()

    res = upload(client, test_user, other)

    assert res.status_code == 404
    assert not upload_folder.exists()


def test_upload_requires_authentication(client, organization, upload_folder):
    res = client.post(
        f"/organizations/{organization.id}/upload-logo",
        data={"file": (io.BytesIO(PNG), "logo.png")},
        content_type="multipart/form-data",
    )

    assert res.status_code == 401


ALLOWED_TYPES_MESSAGE = "gif, jpeg, jpg, png"


@pytest.mark.parametrize(
    "name", ["notes.txt", "script.php", "logo.png.exe", "logo", "logo."]
)
def test_upload_of_a_disallowed_file_type_is_rejected(
    client, db_session, test_user, organization, upload_folder, name
):
    res = upload(client, test_user, organization, name=name)

    assert res.status_code == 400
    assert ALLOWED_TYPES_MESSAGE in res.get_json()["error"]
    assert not upload_folder.exists()
    db_session.refresh(organization)
    assert organization.logo == ""


def test_rejected_upload_keeps_the_existing_logo(
    client, db_session, test_user, organization, upload_folder
):
    assert upload(client, test_user, organization).status_code == 200

    res = upload(client, test_user, organization, name="notes.txt")

    assert res.status_code == 400
    db_session.refresh(organization)
    assert organization.logo == "logo.png"
    assert client.get(logo_url(organization)).data == PNG


def test_upload_with_no_file_chosen_is_rejected(
    client, test_user, organization, upload_folder
):
    res = upload(client, test_user, organization, name="")

    assert res.status_code == 400
    assert not upload_folder.exists()


def test_upload_whose_name_loses_its_extension_is_rejected(
    client, db_session, test_user, organization, upload_folder
):
    """secure_filename turns this into "png", a file with no extension."""
    res = upload(client, test_user, organization, name="日本.png")

    assert res.status_code == 400
    assert not upload_folder.exists()
    db_session.refresh(organization)
    assert organization.logo == ""


@pytest.mark.parametrize(
    "name", ["logo.png", "logo.jpg", "logo.jpeg", "logo.gif", "LOGO.PNG"]
)
def test_upload_accepts_every_allowed_type_in_any_case(
    client, db_session, test_user, organization, upload_folder, name
):
    res = upload(client, test_user, organization, name=name)

    assert res.status_code == 200
    db_session.refresh(organization)
    assert organization.logo == name
    assert (upload_folder / "organizations/demo-aps/logo" / name).exists()

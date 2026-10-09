from pathlib import Path

from flask import current_app, request, send_from_directory
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import exc, not_, or_
from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename

from app.models.base import db
from app.models.organization import Organization
from app.models.organization_schema import (
    organization_schema,
    organizations_schema,
)
from app.models.user import User
from app.routes import bp


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]
    )


def _logo_dir(slug):
    """UPLOAD_FOLDER/organizations/<slug>/logo, where logos are stored and
    served from. UPLOAD_FOLDER is relative to the working directory (as in
    production, ./uploads) or absolute."""
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    return upload_folder / "organizations" / slug / "logo"


def url_for_logo(slug, logo):
    if slug in (".", ".."):
        return {"error": "Logo not found"}, 404
    try:
        return send_from_directory(_logo_dir(slug), logo)
    except NotFound:
        return {"error": "Logo not found"}, 404


@bp.post("/organizations/<int:organization_id>/upload-logo")
@jwt_required()
def upload_logo(organization_id):
    organization = (
        Organization.query.filter_by(id=organization_id)
        .join(Organization.users)
        .filter(User.email == current_user.email)
        .first_or_404(
            description=f"Organization with id {organization_id} not found!"
        )
    )
    try:
        if "file" not in request.files:
            return {"error": "no file found !"}, 400

        file = request.files["file"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            logo_dir = _logo_dir(organization.slug)
            logo_dir.mkdir(parents=True, exist_ok=True)
            file.save(logo_dir / filename)

            organization.logo = filename
            organization.update()
        return {"message": "logo uploaded successfully"}, 200
    except Exception as e:
        return {"error": str(e)}, 500


@bp.get("/organizations/<string:slug>/logo/<path:logo>")
def serv_logo(slug, logo):
    return url_for_logo(slug, logo)


@bp.get("/organizations")
@jwt_required()
def get_organizations():
    organizations = (
        Organization.query.join(Organization.users)
        .filter(User.email == current_user.email)
        .all()
    )
    return organizations_schema.jsonify(organizations)


@bp.get("/organizations/<int:organization_id>")
@jwt_required()
def get_organization(organization_id):
    organization = (
        Organization.query.filter_by(id=organization_id)
        .join(Organization.users)
        .filter(User.email == current_user.email)
        .first_or_404(
            description=f"Organization with id {organization_id} not found!"
        )
    )
    return organization_schema.jsonify(organization)


@bp.delete("/organizations/<int:organization_id>")
@jwt_required()
def delete_organization(organization_id):
    organization = (
        Organization.query.filter_by(id=organization_id)
        .join(Organization.users)
        .filter(User.email == current_user.email)
        .first_or_404(
            description=f"Organization with id {organization_id} not found!"
        )
    )
    try:
        organization.delete()
        return {
            "message": f"Organization with id {organization.id} is deleted!!"
        }, 200
    except exc.IntegrityError:
        return {
            "error": "You can't delete this Organization, it is used in invoices, clients etc."
        }, 202
    except Exception as e:
        return {"error": str(e)}, 400


@bp.post("/organizations")
@jwt_required()
def create_organization():
    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = organization_schema.validate(json_data)
    if errors:
        return {"errors": errors}, 422

    try:
        organization_data = organization_schema.load(json_data)
        duplicate_check = Organization.query.filter(
            or_(
                Organization.name == organization_data.get("name"),
                Organization.slug == organization_data.get("slug"),
            )
        ).first()
        if duplicate_check:
            raise Exception(
                f"Organization name ({duplicate_check.name}) and slug ({duplicate_check.slug}) already exists"
            )

        organization = Organization(**organization_data)
        organization.save()

        return organization_schema.jsonify(organization), 201
    except exc.IntegrityError:
        return {
            "error": f"This Email address is already in use ({organization.email})"
        }, 202
    except Exception as e:
        return {"error": str(e)}, 400


@bp.put("/organizations/<int:organization_id>")
@jwt_required()
def update_organization(organization_id):
    organization = Organization.query.filter_by(
        id=organization_id
    ).first_or_404(
        description=f"Organization with id {organization_id} not found!"
    )

    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = organization_schema.validate(json_data)
    if errors:
        return {"errors": errors}, 422

    try:
        organization_data = organization_schema.load(json_data)
        duplicate_check = (
            Organization.query.filter(
                or_(
                    Organization.name == organization_data["name"],
                    Organization.slug == organization_data["slug"],
                    Organization.email == organization_data["email"],
                )
            )
            .filter(not_(Organization.id == organization_id))
            .first()
        )

        if duplicate_check:
            return {
                "error": f"Organization name {organization_data.get('name')} or slug {organization_data.get('slug')} or email {organization_data.get('email')} already exists"
            }, 400

        organization.name = organization_data.get("name", organization.name)
        organization.country_id = organization_data.get(
            "country_id", organization.country_id
        )
        organization.logo = organization_data.get("logo", organization.logo)
        organization.slug = organization_data.get("slug", organization.slug)
        organization.registration_no = organization_data.get(
            "registration_no", organization.registration_no
        )
        organization.phone = organization_data.get("phone", organization.phone)
        organization.street = organization_data.get(
            "street", organization.street
        )
        organization.zipcode = organization_data.get(
            "zipcode", organization.zipcode
        )
        organization.city = organization_data.get("city", organization.city)
        organization.email = organization_data.get("email", organization.email)

        organization.update()
        return organization_schema.dump(organization), 200
    except exc.IntegrityError:
        db.session.rollback()
        return {"error": "Country doesn't exists"}, 202
    except Exception as e:
        return {"error": str(e)}, 400

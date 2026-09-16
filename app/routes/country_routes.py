from flask import request
from flask_jwt_extended import jwt_required
from sqlalchemy import and_, exc, not_

from app.models.country import Country
from app.models.country_schema import countries_schema, country_schema
from app.routes import bp


@bp.get("/countries")
@jwt_required()
def get_countries():
    countries = Country.query.all()
    return countries_schema.jsonify(countries)


@bp.get("/countries/<int:country_id>")
@jwt_required()
def get_country(country_id):
    country = Country.query.filter_by(id=country_id).first_or_404(
        description="Country with id {country_id} not found!"
    )
    return country_schema.jsonify(country)


@bp.post("/countries")
@jwt_required()
def create_country():
    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = country_schema.validate(json_data)
    if errors:
        return {"error": errors}, 422

    try:
        country_data = country_schema.load(json_data)
        duplicate_check = Country.query.filter_by(
            name=country_data.get("name")
        ).first()
        if duplicate_check:
            raise Exception(
                f"Country name ({duplicate_check.name}) already exists!"
            )

        country = Country(**country_data)
        country.save()

        return country_schema.jsonify(country), 201
    except Exception as e:
        return {"error": str(e)}, 400


@bp.put("/countries/<int:country_id>")
@jwt_required()
def update_country(country_id):
    country = Country.query.filter_by(id=country_id).first_or_404(
        description="Country with id {country_id} not found!"
    )

    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = country_schema.validate(json_data)
    if errors:
        return {"errors": errors}, 422

    try:
        country_data = country_schema.load(json_data)
        duplicate_check = (
            Country.query.filter(and_(Country.name == country_data["name"]))
            .filter(not_(Country.id == country_id))
            .first()
        )

        if duplicate_check:
            return {
                "error": f"Country name {country_data.get('name')} already exists"
            }, 400

        country.currency_id = country_data.get(
            "currency_id", country.currency_id
        )
        country.locale_id = country_data.get("locale_id", country.locale_id)
        country.name = country_data.get("name", country.name)
        country.icon = country_data.get("icon", country.icon)

        country.update()

        return country_schema.jsonify(country)
    except Exception as e:
        return {"error": str(e)}, 400


@bp.delete("/countries/<int:country_id>")
@jwt_required()
def delete_country(country_id):
    country = Country.query.filter_by(id=country_id).first_or_404(
        description=f"Country with id {country_id} not found !"
    )
    try:
        country.delete()
        return {"error": f"Country with id {country.id} is deleted !"}
    except exc.IntegrityError:
        return {
            "error": "You can't delete this country, it is used in clients"
        }, 202
    except Exception as e:
        return {"error": str(e)}, 400

from flask import request
from sqlalchemy import exc, and_, not_
from app.routes import bp
from app.models import db, Contact, contacts_schema, contact_schema
from flask_jwt_extended import (
    jwt_required
)

@bp.get("/organizations/<int:organization_id>/contacts")
@jwt_required()
def get_contacts(organization_id):
    contacts = Contact.query.filter_by(organization_id=organization_id)
    return contacts_schema.jsonify(contacts)

@bp.get("/organizations/<int:organization_id>/contacts/<int:contact_id>")
@jwt_required()
def get_contact(organization_id, contact_id):
    contact = Contact.query.filter_by(organization_id=organization_id, id=contact_id).first_or_404(description=f'Contact with id {contact_id} for Organization id {organization_id} not found !')
    return contact_schema.jsonify(contact)

@bp.delete("/organizations/<int:organization_id>/contacts/<int:contact_id>")
@jwt_required()
def delete_contact(organization_id, contact_id):
    contact = Contact.query.filter_by(organization_id=organization_id, id=contact_id).first_or_404(description=f'Contact with id {contact_id} for Organization id {organization_id} not found !')
    try:
        contact.delete()
        return { "message": f"Contact with id {contact.id} is deleted from Organization id {contact.organization_id}!!" }, 200
    except exc.IntegrityError:
        return {'error': 'You can\'t delete this contact, it is used in invoices'}, 202
    except Exception as e:
        return {'error': str(e)}, 400


@bp.post("/organizations/<int:organization_id>/contacts")
@jwt_required()
def create_contact(organization_id):
    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = contact_schema.validate(json_data)
    if errors:
        return {
            "errors": errors
        }, 422

    try:
        contact_data = contact_schema.load(json_data)
        duplicate_check = Contact.query.filter_by(organization_id=organization_id, name=contact_data.get('name')).first()
        if duplicate_check:
            raise Exception(f'Contact name ({duplicate_check.name}) already exists')

        contact = Contact(**contact_data)
        contact.save()

        return contact_schema.jsonify(contact), 201
    except exc.IntegrityError as e:
        return {'error': f'This Email address is already in use ({contact.email})'}, 409
    except Exception as e:
        return {'error': str(e)}, 400

@bp.put("/organizations/<int:organization_id>/contacts/<int:contact_id>")
@jwt_required()
def update_contact(organization_id, contact_id):
    contact = Contact.query.filter_by(organization_id=organization_id, id=contact_id).first_or_404(description=f'Contact with id {contact_id} not found!')

    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = contact_schema.validate(json_data)
    if errors:
        return {
            "errors": errors
        }, 422

    try:
        contact_data = contact_schema.load(json_data)
        duplicate_check = Contact.query.filter(and_(
            Contact.organization_id==organization_id,
            Contact.name==contact_data['name']
        )).filter(not_(
            Contact.id==contact_id
        )).first()

        if duplicate_check:
            return { 'error': f'Contact name {contact_data.get("name")} already exists' }, 400

        contact.name = contact_data.get("name", contact.name)
        contact.country_id = contact_data.get("country_id", contact.country_id)
        contact.logo = contact_data.get("logo", contact.logo)
        contact.registration_no = contact_data.get("registration_no", contact.registration_no)
        contact.type = contact_data.get("type", contact.type)
        contact.phone = contact_data.get("phone", contact.phone)
        contact.street = contact_data.get("street", contact.street)
        contact.zipcode = contact_data.get("zipcode", contact.zipcode)
        contact.city = contact_data.get("city", contact.city)
        contact.email = contact_data.get("email", contact.email)
        contact.contactperson_name = contact_data.get("contactperson_name", contact.contactperson_name)
        contact.contactperson_email = contact_data.get("contactperson_email", contact.contactperson_email)
        contact.archived = contact_data.get("archived", contact.archived)

        contact.update()

        return contact_schema.dump(contact), 200
    except exc.IntegrityError:
        db.session.rollback()
        return {'error': f'This Email address is already in use ({contact.email})'}, 409
    except Exception as e:
        return {'error': str(e)}, 500

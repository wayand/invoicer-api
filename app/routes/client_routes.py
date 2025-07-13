from flask import request, current_app, jsonify, json
from sqlalchemy import exc, and_, not_
from app.routes import bp
from app.models import db, Client, clients_schema, client_schema
from flask_jwt_extended import (
    jwt_required,
    current_user
)

@bp.get("/organizations/<int:organization_id>/clients")
@jwt_required()
def get_clients(organization_id):
    clients = Client.query.filter_by(organization_id=organization_id)
    return clients_schema.jsonify(clients)

@bp.get("/organizations/<int:organization_id>/clients/<int:client_id>")
@jwt_required()
def get_client(organization_id, client_id):
    client = Client.query.filter_by(organization_id=organization_id, id=client_id).first_or_404(description=f'Client with id {client_id} for Organization id {organization_id} not found !')
    return client_schema.jsonify(client)

@bp.delete("/organizations/<int:organization_id>/clients/<int:client_id>")
@jwt_required()
def delete_client(organization_id, client_id):
    client = Client.query.filter_by(organization_id=organization_id, id=client_id).first_or_404(description=f'Client with id {client_id} for Organization id {organization_id} not found !')
    try:
        client.delete()
        return { "message": f"Client with id {client.id} is deleted from Organization id {client.organization_id}!!" }, 200
    except exc.IntegrityError:
        return {'error': 'You can\'t delete this client, it is used in invoices'}, 202
    except Exception as e:
        return {'error': str(e)}, 400


@bp.post("/organizations/<int:organization_id>/clients")
@jwt_required()
def create_client(organization_id):
    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = client_schema.validate(json_data)
    if errors:
        return {
            "errors": errors
        }, 422
    
    try:
        client_data = client_schema.load(json_data)
        duplicate_check = Client.query.filter_by(organization_id=organization_id, name=client_data.get('name')).first()
        if duplicate_check:
            raise Exception(f'Client name ({duplicate_check.name}) already exists')

        client = Client(**client_data)
        client.save()

        return client_schema.jsonify(client), 201
    except exc.IntegrityError as e:
        return {'error': f'This Email address is already in use ({client.email})'}, 409
    except Exception as e:
        return {'error': str(e)}, 400

@bp.put("/organizations/<int:organization_id>/clients/<int:client_id>")
@jwt_required()
def update_client(organization_id, client_id):
    client = Client.query.filter_by(organization_id=organization_id, id=client_id).first_or_404(description=f'Client with id {client_id} not found!')

    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = client_schema.validate(json_data)
    if errors:
        return {
            "errors": errors
        }, 422
    
    try:
        client_data = client_schema.load(json_data)
        duplicate_check = Client.query.filter(and_(
            Client.organization_id==organization_id,
            Client.name==client_data['name']
        )).filter(not_(
            Client.id==client_id
        )).first()
        
        if duplicate_check:
            return { 'error': f'Client name {client_data.get("name")} already exists' }, 400

        client.name = client_data.get("name", client.name)
        client.country_id = client_data.get("country_id", client.country_id)
        client.logo = client_data.get("logo", client.logo)
        client.registration_no = client_data.get("registration_no", client.registration_no)
        client.type = client_data.get("type", client.type)
        client.phone = client_data.get("phone", client.phone)
        client.street = client_data.get("street", client.street)
        client.zipcode = client_data.get("zipcode", client.zipcode)
        client.city = client_data.get("city", client.city)
        client.email = client_data.get("email", client.email)
        client.contactperson_name = client_data.get("contactperson_name", client.contactperson_name)
        client.contactperson_email = client_data.get("contactperson_email", client.contactperson_email)
        client.archived = client_data.get("archived", client.archived)

        client.update()

        return client_schema.dump(client), 200
    except exc.IntegrityError as e:
        db.session.rollback()
        return {'error': f'This Email address is already in use ({client.email})'}, 409
    except Exception as e:
        return {'error': str(e)}, 500
from flask import request, current_app, jsonify, json
from marshmallow.utils import pprint
from sqlalchemy import exc, and_, not_
from app.routes import bp
from app.models import db, Product, product, product_schema, products_schema
from flask_jwt_extended import (
    jwt_required,
    current_user,
    get_jwt_identity
)


@bp.get("/products")
@jwt_required()
def get_products():
    organization_id = current_user.organization_id
    products = Product.query.filter_by(organization_id=organization_id)
    return products_schema.jsonify(products)

@bp.get("/products/<int:product_id>")
@jwt_required()
def get_product(product_id):
    organization_id = current_user.organization_id
    product = Product.query.filter_by(organization_id=organization_id, id=product_id).first_or_404(description=f'Product with id {product_id} for Organization id {organization_id} not found !')
    return product_schema.jsonify(product)

@bp.delete("/products/<int:product_id>")
@jwt_required()
def delete_product(product_id):
    organization_id = current_user.organization_id
    product = Product.query.filter_by(organization_id=organization_id, id=product_id).first_or_404(description=f'Product with id {product_id} for Organization id {organization_id} not found !')
    try:
        product.delete()
        return { "message": f"Product with id {product.id} is deleted from Organization id {product.organization_id}!!" }, 200
    except exc.IntegrityError:
        return {'error': 'You can\'t delete this product, it is used in invoices'}, 202
    except Exception as e:
        return {'error': str(e)}, 400

@bp.post("/products")
@jwt_required()
def create_product():
    organization_id = current_user.organization_id
    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = product_schema.validate(json_data)
    if errors:
        return {
            "errors": errors
        }, 422

    try:
        product_data = product_schema.load(json_data)
        duplicate_check = Product.query.filter_by(organization_id=organization_id, name=product_data.get('name')).first()
        if duplicate_check:
            raise Exception(f'Product name ({duplicate_check.name}) already exists')
        
        product = Product(**product_data)
        product.save()

        return product_schema.jsonify(product), 201
    except Exception as e:
        return {'error': str(e)}, 400

@bp.put("/products/<int:product_id>")
@jwt_required()
def update_product(product_id):
    organization_id = current_user.organization_id
    product = Product.query.filter_by(organization_id=organization_id, id=product_id).first_or_404(description=f'Product with id {product_id} not found!')

    try:
        json_data = request.get_json()
    except Exception as e:
        return {"error": str(e)}, 400

    errors = product_schema.validate(json_data)
    if errors:
        return {
            "errors": errors
        }, 422
    
    try:
        product_data = product_schema.load(json_data)
        duplicate_check = Product.query.filter(and_(
            Product.organization_id==organization_id,
            Product.name==product_data['name']
        )).filter(not_(
            Product.id==product_id
        )).first()
        
        if duplicate_check:
            return { 'error': f'Product name {product_data.get("name")} already exists' }, 400
        
        product.name = product_data.get("name", product.name)
        product.account_id = product_data.get("account_id", product.account_id)
        product.description = product_data.get("description", product.description)
        product.unit_price = product_data.get("unit_price", product.unit_price)
        product.archived = product_data.get("archived", product.archived)

        product.update()

        return product_schema.dump(product), 200
    except Exception as e:
        return {'error': str(e)}, 400

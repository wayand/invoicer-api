from flask.cli import with_appcontext
from app.models import (
    db, User, Country, Organization, Contact, Invoice, Product, InvoiceLine,
    Account, AccountType, AccountGroup, TaxRate)
import click, json
from sqlalchemy import exc
import glob

@click.command()
@with_appcontext
def seed():
    """Seed the user database."""

    #create new category
    default_country = Country.query.filter_by(id=1).first()
    if not default_country:
        new_country = Country(
            currency_id='DKK',
            locale_id='da_DK',
            name='Danmark',
            icon='dk'
        )
        new_country.save()
        click.echo('created country')
    else:
        click.echo(f'country already exists: {default_country.name}')

    #organizations
    organizations = glob.glob('app/seed/orgs/*.json', recursive=False)
    for org_json_path in organizations:

        with open(org_json_path, "r") as f:
            org_data = json.load(f)
            click.echo('\nCreating Organization: ' + org_data.get('name'))

            # extracting users, contacts and products
            org_users = org_data.pop('users')
            org_products = org_data.pop('products')
            org_contacts = org_data.pop('contacts')
            account_types = org_data.pop('account_types')
            tax_rates = org_data.pop('tax_rates')

            organization_obj = Organization.find_by(
                                                    name=org_data.get('name'),
                                                    slug=org_data.get('slug'),
                                                    email=org_data.get('email')
                                                    )

            if not organization_obj:
                organization_obj = Organization(**org_data)
                organization_obj.save()
                click.echo('done: '+ org_data.get('name'))
            else:
                click.echo('already exists Organization: '+ org_data.get("name"))


            ###########################
            # Organization -> users
            click.echo('\n-> creating users for Organization: '+ org_data.get('name'))
            if org_users:
                for user_data in org_users:
                    try:
                        user_data['organization_id'] = organization_obj.id
                        user_data['password_hash'] = User.generate_hash(user_data.get('password_hash'))
                        user_data['otp_secret'] = User.generate_otp_secret()
                        user_obj = User(**user_data)
                        user_obj.save()
                        click.echo('-- created user: '+ user_data.get('name'))
                    except exc.IntegrityError as e:
                        db.session.rollback()
                        click.echo('-- already exists user: '+ user_data.get("name") + str(e.args))
            else:
                click.echo('-- No users found')

            #############################
            # Organization -> Products
            click.echo('\n-> creating products for Organization: '+ org_data.get('name'))
            if org_products:
                for product_data in org_products:
                    product_obj = Product.find_by(
                                    name=product_data.get('name'),
                                    organization_id=organization_obj.id
                                )
                    if not product_obj:
                        product_data['organization_id'] = organization_obj.id
                        product_obj = Product(**product_data)
                        product_obj.save()
                        click.echo('-- created product: '+ product_data.get('name'))
                    else:
                        click.echo('-- already exists: '+ product_data.get("name"))
            else:
                click.echo('-- No products found')

            ############################
            # Organization -> Contacts
            click.echo('\n-> creating contacts for Organization: '+ org_data.get('name'))
            if org_contacts:
                for contact_data in org_contacts:

                    # extract contact invoices
                    contact_invoices = contact_data.pop('invoices')

                    contact_obj = Contact.find_by(
                                    name=contact_data.get('name'),
                                    email=contact_data.get('email'),
                                    organization_id=organization_obj.id
                                )
                    if not contact_obj:
                        contact_data['organization_id'] = organization_obj.id
                        contact_obj = Contact(**contact_data)
                        contact_obj.save()
                        click.echo('-- created contact: '+ contact_data.get('name'))
                    else:
                        click.echo('-- already exists: '+ contact_data.get("name"))

                    #####################
                    # contact invoices
                    click.echo('\n-- -> creating invoices for contact: ' + contact_data.get('name'))

                    if contact_invoices:
                        for invoice_data in contact_invoices:
                            try:
                                invoice_data['organization_id'] = organization_obj.id
                                invoice_data['contact_id'] = contact_obj.id
                                lines = invoice_data.pop('lines')

                                # add product to invoiceLine
                                for line in lines:
                                    line['product_id'] = product_obj.id

                                invoice_obj = Invoice(**invoice_data, lines=[
                                    InvoiceLine(**line) for line in lines
                                ])
                                invoice_obj.save()
                                click.echo('-- -- created invoice number: '+ invoice_data.get('invoice_no'))
                            except exc.IntegrityError as e:
                                db.session.rollback()
                                click.echo('-- -- already exists: '+ invoice_data.get("invoice_no"))
            else:
                click.echo('-- No contacts found')


            ########################
            # Organization built-in tax_rates
            click.echo('\n-> creating Tax-rates for Organization: '+ org_data.get('name'))
            if tax_rates:
                for tax_rate_data in tax_rates:
                    tax_rate_obj = TaxRate.find_by(
                                        name=tax_rate_data.get('name'),
                                        organization_id=organization_obj.id
                                    )
                    if not tax_rate_obj:
                        tax_rate_data['organization_id'] = organization_obj.id
                        tax_rate_obj = TaxRate(**tax_rate_data)
                        tax_rate_obj.save()
                        click.echo('-- created Tax-rate '+ tax_rate_data.get('name'))
                    else:
                        click.echo('-- already exists: '+ tax_rate_data.get("name"))

            #################################
            # Organization built-in accounts
            click.echo('\n-> creating Account types for Organization: '+ org_data.get('name'))
            if account_types:
                for account_type_data in account_types:

                    # extract account_groups
                    account_type_groups = account_type_data.pop('account_groups')

                    account_type_obj = AccountType.find_by(
                                            name=account_type_data.get('name'),
                                            organization_id=organization_obj.id
                                        )

                    if not account_type_obj:
                        account_type_data['organization_id'] = organization_obj.id
                        account_type_obj = AccountType(**account_type_data)
                        account_type_obj.save()
                        click.echo('-- created Account type: '+ account_type_data.get('name'))
                    else:
                        click.echo('-- already exists: '+ account_type_data.get("name"))

                    #####################
                    # account_groups
                    click.echo('\n-- -> creating account groups for account-type: ' + account_type_data.get('name'))

                    if account_type_groups:
                        for account_group_data in account_type_groups:

                            # extract accounts
                            if account_group_data.get('accounts') is not None:
                                accounts = account_group_data.pop('accounts')

                            account_group_obj = AccountGroup.find_by(
                                                    name=account_group_data.get('name'),
                                                    organization_id=organization_obj.id,
                                                    account_type_id=account_type_obj.id
                                                )

                            if not account_group_obj:
                                account_group_data['organization_id'] = organization_obj.id
                                account_group_data['account_type_id'] = account_type_obj.id
                                account_group_obj = AccountGroup(**account_group_data)
                                account_group_obj.save()
                                click.echo('-- -- created Account group: '+ account_group_data.get('name'))
                            else:
                                click.echo('-- -- already exists: '+ account_group_data.get("name"))

                            #####################
                            # accounts
                            click.echo('\n-- -- -> creating accounts for account-group: ' + account_group_data.get('name'))

                            if accounts:
                                for account_data in accounts:

                                    tax_rate_id = None
                                    if account_data.get('tax_rate_id'):

                                        tax_rate_obj = TaxRate.find_by(
                                                            name=account_data.get('tax_rate_id'),
                                                            organization_id=organization_obj.id
                                                        )
                                        tax_rate_id = tax_rate_obj.id
                                    try:
                                        account_data['organization_id'] = organization_obj.id
                                        account_data['account_type_id'] = account_type_obj.id
                                        account_data['account_group_id'] = account_group_obj.id
                                        account_data['tax_rate_id'] = tax_rate_id
                                        account_obj = Account(**account_data)
                                        account_obj.save()
                                        click.echo('-- -- -- created Account: '+ account_data.get('name'))
                                    except exc.IntegrityError as e:
                                        db.session.rollback()
                                        click.echo('-- -- -- already exists: '+ account_data.get("name"))

def register_commands(app):
    """Register CLI commands."""
    app.cli.add_command(seed)

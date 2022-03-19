from app.models.client import Client
from os import name
from flask.cli import with_appcontext
from app.models import (
    User, Country, Organization, Client, Invoice, Product, InvoiceLine, 
    AccountType, AccountGroup, TaxRate)
import click

@click.command()
@with_appcontext
def seed():
    """Seed the user database."""
    msg=[]

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
        msg.append('created country')
    else:
        msg.append(f'country already exists: {default_country.name}')

    #organization
    default_organization= Organization.query.filter_by(id=1).first()
    if not default_organization:
        new_organization = Organization(
            name='Tolk WB',
            slug='tolk-wb',
            logo='logo.jpg',
            email='lawangjan@hotmail.com',
            country_id=1
        )
        new_organization.save()
        msg.append('created organization')
    else:
        msg.append(f'organization already exists: {default_organization.name}')

    # create new user
    lawangjan = User.query.filter_by(email='lawangjan@hotmail.com').first()
    if not lawangjan:
        new_user = User(
            organization_id=1,
            owner=True,
            name='lawang jan',
            email='lawangjan@hotmail.com',
            password_hash=User.generate_hash('dzpwd@!0'),
            is_two_factor_auth=True,
            otp_secret=User.generate_otp_secret(),
            otp_secret_temp=''
        )
        new_user.save()
        msg.append(f'created user: lawangjan@hotmail.com')
    else:
        msg.append(f'user already exists: {lawangjan.email}')

    default_client= Client.query.filter_by(id=1).first()
    if not default_client:
        new_client = Client(
            name='TolkDanmark',
            logo='logo.jpg',
            email='tolkdanmark@hotmail.com',
            organization_id=1,
            country_id=1
        )
        new_client.save()
        msg.append('created client')
    else:
        msg.append(f'client already exists: {default_client.name}')

    default_invoice = Invoice.query.all()
    if not len(default_invoice) > 0:
        new_invoice = Invoice(
            organization_id=1,
            client_id=1,
            invoice_no='1',
            invoice_date='2021-01-10',
            duedate='2021-01-10',
            amount=12.99,
            gross_amount=13.88,
            vat_amount=4.77    
        )
        new_invoice.save()
        msg.append('created invoice')
    else:
        msg.append(f'invoice already exists: length: {len(default_invoice)} -> {default_invoice[0].amount}')

    default_product = Product.query.all()
    if not len(default_product) > 0:
        new_product= Product(
            organization_id=1,
            name='F.tolk',
            description='',
            unit_price=199.50
        )
        new_product.save()
        msg.append('created Product')
    else:
        msg.append(f'Product already exists: length: {len(default_product)} -> {default_product[0].name}')

    default_invoiceline = InvoiceLine.query.all()
    if not len(default_invoiceline) > 0:
        new_invoiceline = InvoiceLine(
            invoice_id=1,
            product_id=1,
            description='24-09-2021 [2332432] f.tolk 08-10:30 (*)',
            quantity=1,
            unit_price=13.88,
            amount=199.50
        )
        new_invoiceline.save()
        msg.append('created invoiceLine')
    else:
        msg.append(f'invoice already exists: {len(default_invoiceline)} -> {default_invoiceline[0].amount}')

    default_account_types = AccountType.query.all()
    if not len(default_account_types) == 5:
        account_type_list = [
            {'name': 'Liability','normal_balance': 'credit','report_type': 'balanceSheet'},#1
            {'name': 'Asset','normal_balance': 'debit', 'report_type': 'balanceSheet'},#2
            {'name': 'Income','normal_balance': 'credit','report_type': 'incomeStatement'},#3
            {'name': 'Expense','normal_balance': 'debit','report_type': 'incomeStatement'},#4
            {'name': 'Equity','normal_balance': 'credit','report_type': 'balanceSheet'}#5
        ]
        msg.append('creating account-type:')

        for acc_type in account_type_list:
            exist = AccountType.find_by(name=acc_type['name']) is not None
            if not exist:
                acc_type_obj = AccountType(**acc_type)
                acc_type_obj.save()
                msg.append('   -> created account-type: '+ acc_type['name'])
            else:
                msg.append('   -> already exists: '+ acc_type['name'])
    else:
        msg.append('Account types already exists: '+ default_account_types[0].name)

    default_account_groups = AccountGroup.query.all()
    if not len(default_account_groups) > 0:
        account_group_list = [
            {'organization_id': 1, 'account_type_id': 3, 'name': 'Indtægter', 'number': 1100, 'interval_start': 1100, 'interval_end': 1199},
            {'organization_id': 1, 'account_type_id': 4, 'name': 'Salgsomkostninger', 'number': 1200, 'interval_start': 1200, 'interval_end': 1299},
            {'organization_id': 1, 'account_type_id': 4, 'name': 'Lønomkostninger', 'number': 1400, 'interval_start': 1400, 'interval_end': 1499},
            {'organization_id': 1, 'account_type_id': 4, 'name': 'Bilomkostninger', 'number': 1700, 'interval_start': 1700, 'interval_end': 1799},
            {'organization_id': 1, 'account_type_id': 4, 'name': 'Administrationsomkostninger', 'number': 1800, 'interval_start': 1800, 'interval_end': 1899},
            {'organization_id': 1, 'account_type_id': 4, 'name': 'Afskrivninger', 'number': 2000, 'interval_start': 2000, 'interval_end': 2099},
            {'organization_id': 1, 'account_type_id': 3, 'name': 'Finansielle indtægter', 'number': 2200, 'interval_start': 2200, 'interval_end': 2299},
            {'organization_id': 1, 'account_type_id': 4, 'name': 'Finansielle udgifter', 'number': 2300, 'interval_start': 2300, 'interval_end': 2399},
            {'organization_id': 1, 'account_type_id': 2, 'name': 'Bank- og kontantbeholdninger', 'number': 5700, 'interval_start': 5700, 'interval_end': 5799},
            {'organization_id': 1, 'account_type_id': 1, 'name': 'Skyldig moms', 'number': 7200, 'interval_start': 7200, 'interval_end': 7299},
        ]
        msg.append('creating account-group:')

        for acc_group in account_group_list:
            exist = AccountGroup.find_by(organization_id=1, name=acc_group['name']) is not None
            if not exist:
                acc_group_obj = AccountGroup(**acc_group)
                acc_group_obj.save()
                msg.append('   -> created account-group: '+ acc_group['name'])
            else:
                msg.append('   -> already exists: '+ acc_group['name'])
    else:
        msg.append('Account group already exists: '+ default_account_groups[0].name)

    default_tax_rates = TaxRate.query.all()
    if not len(default_tax_rates) > 0:
        tax_rate_list = [
            {'organization_id': 1, 'name': 'Salgsmoms','abbreviation': 'S','applies_to_purchases': False, 'applies_to_sales': True, 'description': '25% moms på salg til Danmark samt private EU-kunder.', 'is_active': True, 'is_predefined': True, 'predefined_tag': '2014_sales', 'rate': 0.25},
            {'organization_id': 1, 'name': 'Købsmoms','abbreviation': 'K','applies_to_purchases': True, 'applies_to_sales': False, 'description': '25% moms på normale fradragsberettigede varer/ydelser købt i Danmark.', 'is_active': True, 'is_predefined': True, 'predefined_tag': '2014_purchases', 'rate': 0.25},
        ]
        msg.append('creating Tax rates:')

        for tax_rate in tax_rate_list:
            exist = TaxRate.find_by(organization_id=1, name=tax_rate['name']) is not None
            if not exist:
                taxrate_obj = TaxRate(**tax_rate)
                taxrate_obj.save()
                msg.append('   -> created tax rate: '+ tax_rate['name'])
            else:
                msg.append('   -> already exists: '+ tax_rate['name'])
    else:
        msg.append('Tax Rates already exists: '+ default_tax_rates[0].name)

    print('Seed results:')
    for m in msg:
        print('--', m)


def register_commands(app):
    """Register CLI commands."""
    app.cli.add_command(seed)
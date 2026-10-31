"""VAT codes: the official list, a VAT period on the organization, default code

See docs/vat-design.md.

- new table vat_codes with the 72 official codes (Erhvervsstyrelsen's
  Momskoder-Bruttoliste, valid from 2025-12-01), classified by us
- organizations.vat_period_type: half_year, quarter or month, or null when the
  organization is not VAT-registered
- accounts.default_vat_code_id: the code a new line on the account starts with

Revision ID: a8c3e5d92f17
Revises: f7a2c8d41b63
Create Date: 2026-10-31 12:00:00

"""
from datetime import date
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8c3e5d92f17'
down_revision = 'f7a2c8d41b63'
branch_labels = None
depends_on = None

VALID_FROM = date(2025, 12, 1)

# The same lists as in app/models/vat_code.py. They are repeated here because
# a migration must not change when the application code does.
APPLIES_TO = ('sales', 'purchases')
DIRECTIONS = ('output', 'input', 'acquisition_goods', 'acquisition_services',
              'none')
BASE_BOXES = ('a_goods', 'a_services', 'b_goods', 'b_services', 'c')
DEFERRED_REASONS = (
    'variable_deduction', 'special_scheme', 'oss', 'fixed_share_unconfirmed',
    'domestic_reverse_charge', 'refund_scheme', 'import_vat',
    'triangular_trade',
)
VAT_PERIOD_TYPES = ('half_year', 'quarter', 'month')


def in_list(column, values):
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


# The rows are data and not read from the file in the repository: a migration
# must give the same result for ever. tests/functional/test_vat_codes.py
# compares the table with the official file and with app/vat.py.
# code, legacy code, name, title, applies to, rate, deduction, direction,
# base box, supported, deferred reason
ROWS = [
    ('S01', 'S1', 'S_DK_25', 'Momspligtige salg (DK), 25% moms', 'sales', '0.25', None, 'output', None, True, None),
    ('S02', 'S0', 'S_DK_0', 'Momspligtige salg (DK) 0% moms', 'sales', '0', None, 'none', 'c', True, None),
    ('S81', 'S%', 'S_DK_UdenforMomslov', 'Udenfor momslovens anvendelsområde', 'sales', None, None, 'none', None, True, None),
    ('S82', 'SMF', 'S_DK_Momsfritaget', 'Momsfritaget salg', 'sales', None, None, 'none', None, True, None),
    ('S83', 'Sbrugt', 'S_DK_Brugtmoms', 'Brugtmoms', 'sales', '0.25', None, None, None, False, 'special_scheme'),
    ('S84', 'Smargin', 'S_DK_Marginmoms', 'Marginmoms', 'sales', '0.25', None, None, None, False, 'special_scheme'),
    ('S85', 'Smotor', 'S_DK_brugtbil', 'Brugte personmotorkøretøjer', 'sales', '0.25', None, None, None, False, 'special_scheme'),
    ('S86', 'Sleasing', 'S_DK_leasingbiler_mm', 'Udlejningsvirksomheder, køreskoler og demobiler', 'sales', '0.2', None, None, None, False, 'special_scheme'),
    ('S87', 'Skunstnere', 'S_DK_kunstnere', 'Kunstneres førstegangssalg', 'sales', '0.05', None, None, None, False, 'special_scheme'),
    ('S88', 'Slokal', 'S_LokalMoms', 'Lokal salg andre lande med moms', 'sales', None, None, None, None, False, 'special_scheme'),
    ('S21', 'S2', 'S_EU_Varer_MomsNulPct', 'Varesalg B2B (EU), 0% moms', 'sales', '0', None, 'none', 'b_goods', True, None),
    ('S22', 'S7', 'S_EU_Varer_MomsNulPct_ejEU_salgsangiv', 'Varesalg B2B (EU), 0% moms, ingen EU-salgsangivelse', 'sales', '0', None, 'none', 'b_goods', True, None),
    ('S23', 'S3', 'S_EU_Ydelser_MomsNulPct', 'Ydelsessalg B2B (EU), 0% moms', 'sales', '0', None, 'none', 'b_services', True, None),
    ('S24', 'SMFEU', 'S_EU_Momsfritaget', 'Momsfritaget salg (EU)', 'sales', None, None, 'none', None, True, None),
    ('S25', 'S8', 'S_EU_Varer_Trekantshandel', 'Varesalg B2B (EU). Trekantshandel', 'sales', '0', None, None, None, False, 'triangular_trade'),
    ('S41', 'S4', 'S_ejEU_Varer_MomsNulPct', 'Varesalg B2B (% EU), 0% moms', 'sales', '0', None, 'none', 'c', True, None),
    ('S42', 'S5', 'S_ejEU_Ydelser_MomsNulPct', 'Ydelsessalg B2B (% EU), 0% moms', 'sales', '0', None, 'none', 'c', True, None),
    ('S43', 'S6', 'S_ejEU_Momsfritaget', 'Momsfritaget salg (udenfor EU) § 13', 'sales', None, None, 'none', None, True, None),
    ('S61', 'S-OSS-Y', 'S_OSS_Ydelser', 'B2C Ydelsessalg omfattet af OSS', 'sales', None, None, None, None, False, 'oss'),
    ('S62', 'S-OSS-V-DK-EU', 'S_OSS_Varer_FraDK_TilEU', 'B2C varesalg fra DK til andre EU-lande', 'sales', None, None, None, None, False, 'oss'),
    ('S63', 'S-OSS-V-%DK', 'S_OSS_Varer_IkkeFraDK', 'B2C varesalg fra andre EU-lande eller lande udenfor EU', 'sales', None, None, None, None, False, 'oss'),
    ('S64', 'S-OSS-V-%EU-DK', 'S_OSS_Varer_FraEjEU_TilDK_25pct', 'B2C varesalg fra et land udenfor EU til kunde i DK', 'sales', '0.25', None, None, None, False, 'oss'),
    ('S65', 'S-OSS-V-L', 'S_OSS_Varer_LokaltSalg', 'B2C varesalg (lokalt salg)', 'sales', '0.25', None, None, None, False, 'oss'),
    ('K010', 'K1', 'K_DK_FuldFradrag', 'Indgående moms (DK), fuld fradrag (100%)', 'purchases', '0.25', '1', 'input', None, True, None),
    ('K020', 'K3', 'K_DK_SkoennetFradrag', 'Indgående moms (DK), skønsmæssigt fradrag', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K030', 'K0', 'K_DK_IngenFradrag', 'Momsfritaget køb, Ingen fradrag, ingen moms på køb', 'purchases', None, '0', 'none', None, True, None),
    ('K610', 'K7', 'K_DK_VejFradrag', 'Indgående moms (DK), lovbestemt delvist fradrag (2/3 fradrag)', 'purchases', '0.25', '0.666', None, None, False, 'fixed_share_unconfirmed'),
    ('K040', 'K5A', 'K_DK_FastnettelefonFuld', 'Indgående moms (DK), lovbestemt delvist fradrag (50%)', 'purchases', '0.25', '0.5', 'input', None, True, None),
    ('K050', 'K5B', 'K_DK_FastnettelefonProRata', 'Indgående moms (DK), lovbestemt delvist fradrag (50% x pro rata)', 'purchases', '0.25', '0.5', None, None, False, 'fixed_share_unconfirmed'),
    ('K060', 'KL1', 'K_DK_GulpladebilFradragPrivat', 'Leasing og drift af gulpladebil, (private og blandede formål samt erhverv)', 'purchases', '0.25', '0.333', None, None, False, 'fixed_share_unconfirmed'),
    ('K070', 'K25A', 'K_DK_ReprFradragFuld', 'Repræsentationsmoms, delvist fradragsberettiget (25%)', 'purchases', '0.25', '0.25', 'input', None, True, None),
    ('K080', 'K25B', 'K_DK_ReprFradragProRata', 'Repræsentationsmoms, delvist fradragsberettiget (25% x pro rata)', 'purchases', '0.25', '0.25', None, None, False, 'fixed_share_unconfirmed'),
    ('K090', 'KL2', 'K_DK_LeasinghvidpladebilFradrag', 'Leasing af hvidpladebil i min. 6 mdr.  (faktura)', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K100', 'KL3', 'K_DK_LeasinghvidpladebilFradrag', 'Leasing af hvidpladebil i min. 6 mdr.  (faktura x pro rata)', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K110', 'K2', 'K_DK_DelvisFradrag', 'Indgående moms (DK), Delvis fradrag (pro rata)', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K120', 'K6', 'K_DK_SektorFradrag', 'Indgående moms (DK), sektorbaseret fradragsret', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K130', 'K4', 'K_DK_ArealFradrag', 'Arealbaseret fradragsret fast ejendom', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K620', 'K-brugtmoms', 'K_DK_Brugtmoms', 'Brugtmoms', 'purchases', None, '0', None, None, False, 'special_scheme'),
    ('K630', 'K-marginmoms', 'K_DK_Marginmoms', 'Marginmoms', 'purchases', None, '0', None, None, False, 'special_scheme'),
    ('K640', 'K-brugtbil', 'K_DK_brugtbil', 'Brugte personmotorkøretøjer', 'purchases', None, '0', None, None, False, 'special_scheme'),
    ('K650', 'K-leasingbil', 'K_DK_leasingbiler_mm', 'Udlejningsvirksomheder, køreskoler og demobiler', 'purchases', None, '0', None, None, False, 'special_scheme'),
    ('K660', 'K-DK0-1', 'K_DK_OmvBetPl_FuldFradrag', 'DK omvendt betalingspligt, Indgående moms, fuldt fradragsberettiget (100%)', 'purchases', '0.25', '1', None, None, False, 'domestic_reverse_charge'),
    ('K670', 'K-DKO-2', 'K_DK_OmvBetPl_DelvisFradrag', 'DK omvendt betalingspligt, Indgående moms, Delvis fradrag (pro rata)', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K680', 'K-DKO-3', 'K_DK_OmvBetPl_SkoennetFradrag', 'DK omvendt betalingspligt, Indgående moms, skønsmæssigt fradrag', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K690', 'K-DKO-0', 'K_DK_OmvBetPl_IngenFradrag', 'DK omvendt betalingspligt, Ingen fradrag', 'purchases', '0.25', '0', None, None, False, 'domestic_reverse_charge'),
    ('K700', 'K-DKO-4', 'K_DK_OmvBetPl_ArealFradrag', 'DK omvendt betalingspligt, Arealbaseret fradragsret fast ejendom', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K710', 'K-LokalMoms', 'K_LokalMoms', 'Køb med lokal moms', 'purchases', None, None, None, None, False, 'refund_scheme'),
    ('K720', 'K-DKO-I', 'K_DK_refusion', 'Køb omfattet af det offentliges refusionsordning', 'purchases', '0.25', None, None, None, False, 'refund_scheme'),
    ('K210', 'K-EU-V-1', 'K_EU_Varer_Fradrag', 'Varekøb, erhvervelsesmoms (EU), fuldt fradragsberettiget (100%)', 'purchases', '0.25', '1', 'acquisition_goods', 'a_goods', True, None),
    ('K220', 'K-EU-V-3', 'K_EU_Varer_SkoennetFradrag', 'Varekøb, erhvervelsesmoms (EU), skønsmæssigt fradrag', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K230', 'K-EU-V-0', 'K_EU_Varer_IngenFradrag', 'Varekøb, erhvervelsesmoms (EU), ingen fradrag', 'purchases', '0.25', '0', 'acquisition_goods', 'a_goods', True, None),
    ('K240', 'K-EU-V-2', 'K_EU_Varer_DelvisFradrag', 'Varekøb, erhvervelsesmoms (EU), Delvis fradrag (pro rata)', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K250', 'K-EU-V-4', 'K_EU_Varer_ArealFradrag', 'Varekøb, erhvervelsesmoms (EU), Arealbaseret fradragsret fast ejendom', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K260', 'K-EU-Y-1', 'K_EU_Ydelser_FuldFradrag', 'Ydelseskøb, omvendt betalingspligt (EU), fuldt fradragsberettiget (100%)', 'purchases', '0.25', '1', 'acquisition_services', 'a_services', True, None),
    ('K270', 'K-EU-Y-3', 'K_EU_Ydelser_SkoennetFradrag', 'Ydelseskøb, omvendt betalingspligt (EU), skønsmæssigt fradrag', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K280', 'K-EU-Y-0', 'K_EU_Ydelser_IngenFradrag', 'Ydelseskøb, omvendt betalingspligt (EU), ingen fradrag', 'purchases', '0.25', '0', 'acquisition_services', 'a_services', True, None),
    ('K290', 'K-EU-Y-2', 'K_EU_Ydelser_DelvisFradrag', 'Ydelseskøb, omvendt betalingspligt (EU), Delvis fradrag', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K300', 'K-EU-Y-4', 'K_EU_Ydelser_ArealFradrag', 'Ydelseskøb, omvendt betalingspligt (EU), Arealbaseret fradragsret fast ejendom', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K310', 'KL-EU-2', 'K_EU_Leasinghvidpladebil_Fradrag', 'Leasing af hvidpladebil i min. 6 mdr.  Udlandet (faktura)', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K320', 'KL-EU-3', 'K_EU_Leasinghvidpladebil_DelvisFradrag', 'Leasing af hvidpladebil i min. 6 mdr.  Udlandet (faktura x pro rata)', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K330', 'K-EU-Y-L1', 'K_EU_Gulpladebil_FradragPrivat', 'Leasing af gulpladebil fra udenlandsk leasinggiver, (private og blandede formål samt erhverv)', 'purchases', '0.25', '0.333', None, None, False, 'fixed_share_unconfirmed'),
    ('K340', 'K-EU-MF', 'K_EU_Momsfritaget', 'Momsfritagede køb af varer og ydelser (EU)', 'purchases', '0', '0', 'none', None, True, None),
    ('K410', 'K-%EU-V-1', 'K_ejEU_Varer_FuldFradrag', 'Varekøb, Importmoms (% EU), fuldt fradragsberettiget (100%)', 'purchases', '0.25', '1', None, None, False, 'import_vat'),
    ('K420', 'K-%EU-V-3', 'K_ejEU_Varer_SkoennetFradrag', 'Varekøb, importmoms (% EU), skønsmæssigt fradrag', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K430', 'K-%EU-V-0', 'K_ejEU_Varer_IngenFradrag', 'Varekøb, importmoms (% EU), ingen fradrag', 'purchases', '0.25', '0', None, None, False, 'import_vat'),
    ('K440', 'K-%EU-V-2', 'K_ejEU_Varer_DelvisFradrag', 'Varekøb, importmoms (% EU), Delvis fradrag (pro rata)', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K450', 'K-%EU-V-4', 'K_ejEU_Varer_ArealFradrag', 'Varekøb, importmoms (% EU), Arealbaseret fradragsret fast ejendom', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K460', 'K-%EU-Y-1', 'K_ejEU_Ydelser_FuldFradrag', 'Ydelseskøb, omvendt betalingspligt (% EU), fuldt fradragsberettiget (100%)', 'purchases', '0.25', '1', 'acquisition_services', None, True, None),
    ('K470', 'K-%EU-Y-3', 'K_ejEU_OmvBetPl_Ydelser_SkoennetFradrag', 'Ydelseskøb, omvendt betalingspligt (% EU), skønsmæssigt fradrag', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K480', 'K-%EU-Y-0', 'K_ejEU_OmvBetPl_Ydelser_IngenFradrag', 'Ydelseskøb, omvendt betalingspligt (% EU), ingen fradrag', 'purchases', '0.25', '0', 'acquisition_services', None, True, None),
    ('K490', 'K-%EU-Y-2', 'K_ejEU_OmvBetPl_Ydelser_DelvisFradrag', 'Ydelseskøb, omvendt betalingspligt (% EU), Delvis fradrag', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
    ('K500', 'K-%EU-Y-4', 'K_ejEU_OmvBetPl_Ydelser_ArealFradrag', 'Ydelseskøb, omvendt betalingspligt (% EU), Arealbaseret fradragsret fast ejendom', 'purchases', '0.25', None, None, None, False, 'variable_deduction'),
]


def upgrade():
    vat_codes = op.create_table(
        'vat_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('legacy_code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('applies_to', sa.String(length=10), nullable=False),
        sa.Column('rate', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('deduction', sa.Numeric(precision=6, scale=4),
                  nullable=True),
        sa.Column('direction', sa.String(length=25), nullable=True),
        sa.Column('base_box', sa.String(length=15), nullable=True),
        sa.Column('is_supported', sa.Boolean(), nullable=False),
        sa.Column('deferred_reason', sa.String(length=30), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.UniqueConstraint('legacy_code'),
        sa.CheckConstraint(in_list('applies_to', APPLIES_TO),
                           name='ck_vat_codes_applies_to'),
        sa.CheckConstraint(
            f"direction IS NULL OR {in_list('direction', DIRECTIONS)}",
            name='ck_vat_codes_direction'),
        sa.CheckConstraint(
            f"base_box IS NULL OR {in_list('base_box', BASE_BOXES)}",
            name='ck_vat_codes_base_box'),
        sa.CheckConstraint(
            'deferred_reason IS NULL OR '
            + in_list('deferred_reason', DEFERRED_REASONS),
            name='ck_vat_codes_deferred_reason'),
        sa.CheckConstraint(
            '(is_supported AND direction IS NOT NULL '
            'AND deferred_reason IS NULL) OR '
            '(NOT is_supported AND direction IS NULL AND base_box IS NULL '
            'AND deferred_reason IS NOT NULL)',
            name='ck_vat_codes_supported'),
        sa.CheckConstraint('rate IS NULL OR (rate >= 0 AND rate <= 1)',
                           name='ck_vat_codes_rate'),
        sa.CheckConstraint(
            'deduction IS NULL OR (deduction >= 0 AND deduction <= 1)',
            name='ck_vat_codes_deduction'),
        sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from',
                           name='ck_vat_codes_valid'),
    )
    op.bulk_insert(vat_codes, [
        {
            'code': code, 'legacy_code': legacy_code, 'name': name,
            'title': title, 'applies_to': applies_to,
            'rate': None if rate is None else Decimal(rate),
            'deduction': None if deduction is None else Decimal(deduction),
            'direction': direction, 'base_box': base_box,
            'is_supported': is_supported, 'deferred_reason': deferred_reason,
            'valid_from': VALID_FROM,
        }
        for (code, legacy_code, name, title, applies_to, rate, deduction,
             direction, base_box, is_supported, deferred_reason) in ROWS
    ])

    op.add_column('organizations',
                  sa.Column('vat_period_type', sa.String(length=10),
                            nullable=True))
    op.create_check_constraint(
        'ck_organizations_vat_period_type', 'organizations',
        'vat_period_type IS NULL OR '
        + in_list('vat_period_type', VAT_PERIOD_TYPES))

    op.add_column('accounts',
                  sa.Column('default_vat_code_id', sa.Integer(),
                            nullable=True))
    op.create_foreign_key('fk_accounts_default_vat_code_id', 'accounts',
                          'vat_codes', ['default_vat_code_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_accounts_default_vat_code_id', 'accounts',
                       type_='foreignkey')
    op.drop_column('accounts', 'default_vat_code_id')
    op.drop_constraint('ck_organizations_vat_period_type', 'organizations',
                       type_='check')
    op.drop_column('organizations', 'vat_period_type')
    op.drop_table('vat_codes')

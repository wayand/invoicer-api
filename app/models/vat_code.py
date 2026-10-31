"""The VAT codes (docs/vat-design.md).

One table for every organization: the codes are the official list of
Erhvervsstyrelsen, classified by app/vat.py. A migration fills it. Rows are
never changed or deleted, because posted lines will point at them: a new
official list adds rows and sets valid_to on the ones that are gone.
"""

from .base import db

APPLIES_TO = ("sales", "purchases")
DIRECTIONS = (
    "output",
    "input",
    "acquisition_goods",
    "acquisition_services",
    "none",
)
BASE_BOXES = ("a_goods", "a_services", "b_goods", "b_services", "c")
DEFERRED_REASONS = (
    "variable_deduction",
    "special_scheme",
    "oss",
    "fixed_share_unconfirmed",
    "domestic_reverse_charge",
    "refund_scheme",
    "import_vat",
    "triangular_trade",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class VatCode(db.Model):
    __tablename__ = "vat_codes"
    __table_args__ = (
        db.CheckConstraint(
            _in("applies_to", APPLIES_TO), name="ck_vat_codes_applies_to"
        ),
        db.CheckConstraint(
            f"direction IS NULL OR {_in('direction', DIRECTIONS)}",
            name="ck_vat_codes_direction",
        ),
        db.CheckConstraint(
            f"base_box IS NULL OR {_in('base_box', BASE_BOXES)}",
            name="ck_vat_codes_base_box",
        ),
        db.CheckConstraint(
            "deferred_reason IS NULL OR "
            + _in("deferred_reason", DEFERRED_REASONS),
            name="ck_vat_codes_deferred_reason",
        ),
        # A code is either supported, with its direction, or deferred, with
        # the reason. Never both and never neither.
        db.CheckConstraint(
            "(is_supported AND direction IS NOT NULL "
            "AND deferred_reason IS NULL) OR "
            "(NOT is_supported AND direction IS NULL AND base_box IS NULL "
            "AND deferred_reason IS NOT NULL)",
            name="ck_vat_codes_supported",
        ),
        db.CheckConstraint(
            "rate IS NULL OR (rate >= 0 AND rate <= 1)",
            name="ck_vat_codes_rate",
        ),
        db.CheckConstraint(
            "deduction IS NULL OR (deduction >= 0 AND deduction <= 1)",
            name="ck_vat_codes_deduction",
        ),
        db.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_vat_codes_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # The new name (S01, K210), which the app shows and the API takes
    code = db.Column(db.String(10), unique=True, nullable=False)
    # The old name (S1, K-EU-V-1)
    legacy_code = db.Column(db.String(20), unique=True, nullable=False)
    # The official long name (S_DK_25) and the heading in the list
    name = db.Column(db.String(60), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    applies_to = db.Column(db.String(10), nullable=False)
    # Fractions: 0.25 is 25%. Null when the list gives no number.
    rate = db.Column(db.Numeric(6, 4), nullable=True)
    deduction = db.Column(db.Numeric(6, 4), nullable=True)
    # Where the VAT is posted, and the box of the return that the net amount
    # is reported in. Null for a deferred code, which is not classified.
    direction = db.Column(db.String(25), nullable=True)
    base_box = db.Column(db.String(15), nullable=True)
    is_supported = db.Column(db.Boolean, nullable=False)
    deferred_reason = db.Column(db.String(30), nullable=True)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=True)

    def __repr__(self):
        return f"<VatCode {self.code}>"

from marshmallow import Schema, fields


class AuditLogSchema(Schema):
    id = fields.Integer()
    occurred_at = fields.DateTime()
    user_id = fields.Integer()
    user_name = fields.String(attribute="user.name")
    action = fields.String()
    entity_type = fields.String()
    entity_id = fields.Integer()
    details = fields.Dict()


audit_log_schema = AuditLogSchema(many=True)

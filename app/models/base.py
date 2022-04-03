from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class BaseModel(db.Model):
    __abstract__ = True
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow, nullable=True)

    """
    Find object by fieldname
    fieldname: dict { username: 'wayand' }
    """
    @classmethod
    def find_by(cls, **fieldname):
        return cls.query.filter_by(**fieldname).first()

    def before_save(self, *args, **kwargs):
        print('')

    def after_save(self, *args, **kwargs):
        pass

    def before_update(self, *args, **kwargs):
        pass

    def after_update(self, *args, **kwargs):
        pass

    def save(self, commit=True):
        self.before_save()
        db.session.add(self)
        if commit:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                raise

        self.after_save()

    def update(self, *args, **kwargs):
        self.before_update(*args, **kwargs)
        res = db.session.commit()
        self.after_update(*args, **kwargs)
        return res

    def delete(self, commit=True):
        db.session.delete(self)
        if commit:
            db.session.commit()
    
    def __repr__(self) -> str:
        return f'this is the baseModal class'
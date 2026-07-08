from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Product


class ProductRepository:

    @staticmethod
    def find_all(session: Session) -> list[Product]:
        return session.query(Product).order_by(Product.sap_number).all()

    @staticmethod
    def find_by_sap(session: Session, sap_number: str) -> Product | None:
        return session.query(Product).filter_by(sap_number=sap_number).first()

    @staticmethod
    def find_by_sap_list(session: Session, sap_numbers: list[str]) -> list[Product]:
        if not sap_numbers:
            return []
        return session.query(Product).filter(Product.sap_number.in_(sap_numbers)).all()

    @staticmethod
    def save(session: Session, product: Product) -> Product:
        session.add(product)
        session.flush()
        return product

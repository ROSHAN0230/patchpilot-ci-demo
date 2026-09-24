from typing import List, Optional
from sqlalchemy.orm import Session
from models import Customer


class CustomerRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, customer_id: int) -> Optional[Customer]:
        return self.session.query(Customer).filter(Customer.id == customer_id).first()

    def get_all_active(self) -> List[Customer]:
        return self.session.query(Customer).filter(Customer.is_active == True).all()

    def add_customer(self, name: str, email: str) -> Customer:
        cust = Customer(name=name, email=email, is_active=True)
        self.session.add(cust)
        self.session.commit()
        return cust

    def delete_by_email(self, email: str) -> int:
        count = self.session.query(Customer).filter(Customer.email == email).delete()
        self.session.commit()
        return count

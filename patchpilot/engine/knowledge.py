"""
Framework Migration Knowledge Registry.
Provides modular, ecosystem-specific migration directives decoupled from the core recovery controller.
"""

from typing import Dict, List, Optional
from patchpilot.types import DependencyDelta, UpgradeSpec


class MigrationKnowledgeRegistry:
    """Registry of declarative framework migration knowledge and rules."""

    _FRAMEWORK_DIRECTIVES: Dict[str, Dict[str, List[str]]] = {
        "pydantic": {
            "2": [
                "Replace `class Config:` with `model_config = ConfigDict(...)` and replace `orm_mode = True` with `from_attributes = True`.",
                "Replace `.from_orm(obj)` with `model_validate(obj)`, replace `.dict(...)` with `.model_dump(...)`, and replace `.copy(update=...)` with `.model_copy(update=...)`.",
                "Replace `__root__ = ...` with `RootModel[...]` from `pydantic` and access elements via `.root`.",
                "Replace `Field(..., regex=...)` with `Field(..., pattern=...)`.",
                "Replace `@validator` with `@field_validator` and ALWAYS decorate with `@classmethod`. Note: `@field_validator` does NOT accept `each_item=True`; to validate collection elements, iterate over items in the validator method.",
            ]
        },
        "sqlalchemy": {
            "2": [
                "Declarative Models: Prefer `from sqlalchemy.orm import DeclarativeBase; class Base(DeclarativeBase): pass` (or `Base = declarative_base()`).",
                "Queries: Replace `session.query(Model).filter(cond).all()` with `session.execute(select(Model).where(cond)).scalars().all()`.",
                "Single item lookup: Replace `session.query(Model).filter(cond).first()` with `session.execute(select(Model).where(cond)).scalars().first()` or `session.get(Model, id)`.",
                "Deletion: Replace `session.query(Model).filter(cond).delete()` with `session.execute(delete(Model).where(cond))`.",
                "Raw SQL execution: `engine.execute(...)` is removed in 2.0. Use `with engine.connect() as conn: conn.execute(text(...)); conn.commit()`.",
                "Explicit Transactions: In SQLAlchemy 2.0, explicit `session.commit()` is required for mutations (no 1.x auto-commit).",
                "Imports: Import `select`, `delete`, `text` from `sqlalchemy` and `DeclarativeBase`, `Session` from `sqlalchemy.orm`.",
            ]
        },
    }

    @classmethod
    def get_directives(cls, package_name: str, new_version: str) -> List[str]:
        pkg = package_name.lower()
        major_v = new_version.split(".")[0] if new_version else "2"
        pkg_rules = cls._FRAMEWORK_DIRECTIVES.get(pkg, {})
        return pkg_rules.get(major_v, [
            f"Upgrade {package_name} to {new_version}, preserving all interfaces, signatures, and behavior."
        ])

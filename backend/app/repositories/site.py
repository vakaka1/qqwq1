from __future__ import annotations

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session, joinedload

from app.models.site import Site


class SiteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[Site]:
        stmt = (
            select(Site)
            .options(joinedload(Site.managed_bot))
            .order_by(desc(Site.created_at), asc(Site.name))
        )
        return list(self.db.scalars(stmt).unique())

    def get(self, site_id: str) -> Site | None:
        stmt = select(Site).options(joinedload(Site.managed_bot)).where(Site.id == site_id)
        return self.db.scalar(stmt)

    def get_by_code(self, code: str) -> Site | None:
        stmt = select(Site).options(joinedload(Site.managed_bot)).where(Site.code == code)
        return self.db.scalar(stmt)

    def create(self, site: Site) -> Site:
        self.db.add(site)
        self.db.flush()
        return site

    def delete(self, site: Site) -> None:
        self.db.delete(site)
        self.db.flush()

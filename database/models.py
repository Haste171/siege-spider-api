from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, ARRAY, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class Client(Base):
    __tablename__ = 'client'
    current_version = Column(String, primary_key=True)
    download_url = Column(String)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

# class SiegeUser(Base):
#     __tablename__ = "siege_users"
#
#     id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, index=True)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Match(Base):
    __tablename__ = "matches"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, index=True, nullable=False)
    teams = Column(JSONB, nullable=False)  # Storing as JSON array of dicts
    signature = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_host = Column(String)


class SiegeBan(Base):
    __tablename__ = "siege_bans"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, index=True, nullable=False)

    # These are the usernames at the time of the ban, this can change which is why we have their uuid (profile id) as well.
    profile_id = Column(String, index=True, nullable=False)
    uplay = Column(String, index=True)
    xbl = Column(String, index=True)
    psn = Column(String, index=True)
    ban_reason = Column(Integer, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    ban_metadata = relationship('SiegeBanMetadata', back_populates='siegeban', cascade="all, delete-orphan")

class SiegeBanMetadata(Base):
    __tablename__ = "siege_bans_metadata"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, index=True, nullable=False)
    ban_id = Column(String, ForeignKey('siege_bans.id'), nullable=False)
    notification_type = Column(String, index=True)
    source_application_id = Column(String, index=True)
    date_posted = Column(DateTime(timezone=False), index=True)
    space_id = Column(String, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    siegeban = relationship('SiegeBan', back_populates='ban_metadata')

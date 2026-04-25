from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer, Float, JSON, UniqueConstraint
from sqlalchemy.sql import func
from core.database import Base


class ObjectTypeDefinition(Base):
    __tablename__ = "ontology_object_types"

    api_name = Column(String(100), primary_key=True)
    display_name = Column(String(200), nullable=False)
    plural_name = Column(String(200), nullable=False)
    description = Column(Text)
    primary_key_field = Column(String(100), nullable=False)
    datasource_mapping = Column(JSON, default={})
    properties = Column(JSON, default=[])
    interfaces = Column(JSON, default=[])
    version = Column(String(20), default="1.0.0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)


class PropertyDefinition(Base):
    __tablename__ = "ontology_property_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    object_type = Column(String(100), nullable=False)
    property_name = Column(String(100), nullable=False)
    display_name = Column(String(200))
    data_type = Column(String(50), nullable=False)
    is_required = Column(Boolean, default=False)
    is_immutable = Column(Boolean, default=False)
    is_derived = Column(Boolean, default=False)
    is_user_editable = Column(Boolean, default=True)
    allowed_values = Column(JSON)
    default_value = Column(Text)
    description = Column(Text)
    security_classification = Column(String(50), default="standard")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("object_type", "property_name"),)


class LinkTypeDefinition(Base):
    __tablename__ = "ontology_link_types"

    api_name = Column(String(100), primary_key=True)
    display_name = Column(String(200), nullable=False)
    source_object_type = Column(String(100), nullable=False)
    target_object_type = Column(String(100), nullable=False)
    is_directed = Column(Boolean, default=True)
    is_inferred = Column(Boolean, default=False)
    inference_rule = Column(Text)
    properties = Column(JSON, default=[])
    cardinality = Column(String(20), default="many-to-many")
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InterfaceDefinition(Base):
    __tablename__ = "ontology_interfaces"

    api_name = Column(String(100), primary_key=True)
    display_name = Column(String(200), nullable=False)
    implementing_types = Column(JSON, default=[])
    shared_properties = Column(JSON, default=[])
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SchemaVersion(Base):
    __tablename__ = "ontology_schema_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(20), nullable=False)
    major = Column(Integer, nullable=False)
    minor = Column(Integer, nullable=False)
    patch = Column(Integer, nullable=False)
    changelog = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(100))
    is_current = Column(Boolean, default=True)


class DataSourceMapping(Base):
    __tablename__ = "ontology_datasource_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    object_type = Column(String(100), nullable=False)
    source_id = Column(String(200), nullable=False)
    column_mappings = Column(JSON, nullable=False)
    transform_rules = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("object_type", "source_id"),)

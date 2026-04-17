"""
메타데이터 관리 v2 API
- 문서 유형 정의 (DocumentType)
- 필드 정의 (FieldDefinition)
- AI 모델 설정 (LLM / NER / Regex)
- CRUD + 검색
"""
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Session, relationship

from database import Base, engine, get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# DB 모델
# ============================================================

class DocumentTypeModel(Base):
    """문서 유형 정의"""
    __tablename__ = "document_types_v2"
    __table_args__ = {"extend_existing": True}

    id          = Column(Integer, primary_key=True, autoincrement=True)
    type_id     = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String(36), nullable=False)
    name        = Column(String(100), nullable=False)        # 예: 진단서
    category    = Column(String(50), nullable=True)          # 의료 / 금융 / 공문서 / 기타
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.now)
    updated_at  = Column(DateTime, default=datetime.now)

    fields = relationship(
        "FieldDefinitionModel",
        back_populates="document_type",
        cascade="all, delete-orphan",
        order_by="FieldDefinitionModel.order",
    )


class FieldDefinitionModel(Base):
    """필드 정의"""
    __tablename__ = "field_definitions_v2"
    __table_args__ = {"extend_existing": True}

    id               = Column(Integer, primary_key=True, autoincrement=True)
    field_id         = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    type_id          = Column(String(36), ForeignKey("document_types_v2.type_id", ondelete="CASCADE"), nullable=False)
    name             = Column(String(100), nullable=False)   # 표시 이름 (예: 환자명)
    key              = Column(String(50), nullable=False)    # 내부 키 (예: patient_name)
    field_type       = Column(String(20), default="text")   # text / number / date / phone / rrn / address / email
    is_pii           = Column(Boolean, default=False)        # 개인정보 여부 → 마스킹 대상
    is_required      = Column(Boolean, default=False)
    ai_model         = Column(String(20), default="regex")   # regex / llm / ner
    extraction_hint  = Column(Text, nullable=True)           # LLM 프롬프트 힌트 or NER 레이블
    order            = Column(Integer, default=0)
    created_at       = Column(DateTime, default=datetime.now)

    document_type = relationship("DocumentTypeModel", back_populates="fields")


# 테이블 생성
Base.metadata.create_all(bind=engine)


# ============================================================
# Pydantic 스키마
# ============================================================

class FieldSchema(BaseModel):
    field_id:        Optional[str]  = None
    name:            str
    key:             str
    field_type:      str            = "text"
    is_pii:          bool           = False
    is_required:     bool           = False
    ai_model:        str            = "regex"
    extraction_hint: Optional[str]  = None
    order:           int            = 0

    class Config:
        from_attributes = True


class FieldResponse(FieldSchema):
    field_id:   str
    created_at: str


class DocumentTypeCreate(BaseModel):
    name:        str
    category:    Optional[str] = None
    description: Optional[str] = None


class DocumentTypeUpdate(BaseModel):
    name:        Optional[str] = None
    category:    Optional[str] = None
    description: Optional[str] = None
    is_active:   Optional[bool] = None


class DocumentTypeResponse(BaseModel):
    type_id:     str
    name:        str
    category:    Optional[str]
    description: Optional[str]
    is_active:   bool
    created_at:  str
    updated_at:  str
    field_count: int

    class Config:
        from_attributes = True


class DocumentTypeDetail(DocumentTypeResponse):
    fields: List[FieldResponse]


# ============================================================
# 유틸리티
# ============================================================

def _type_to_response(doc: DocumentTypeModel) -> DocumentTypeResponse:
    return DocumentTypeResponse(
        type_id=doc.type_id,
        name=doc.name,
        category=doc.category,
        description=doc.description,
        is_active=doc.is_active,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat(),
        field_count=len(doc.fields),
    )


def _field_to_response(f: FieldDefinitionModel) -> FieldResponse:
    return FieldResponse(
        field_id=f.field_id,
        name=f.name,
        key=f.key,
        field_type=f.field_type,
        is_pii=f.is_pii,
        is_required=f.is_required,
        ai_model=f.ai_model,
        extraction_hint=f.extraction_hint,
        order=f.order,
        created_at=f.created_at.isoformat(),
    )


# ============================================================
# 문서 유형 API
# ============================================================

@router.get("/metadata-v2/document-types", response_model=List[DocumentTypeResponse])
def list_document_types(
    user_id: str = Query("default"),
    q:       str = Query("", description="이름/카테고리 검색"),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """문서 유형 목록 조회 (검색 포함)"""
    query = db.query(DocumentTypeModel).filter_by(user_id=user_id)
    if q:
        query = query.filter(
            (DocumentTypeModel.name.contains(q)) |
            (DocumentTypeModel.category.contains(q)) |
            (DocumentTypeModel.description.contains(q))
        )
    if category:
        query = query.filter_by(category=category)
    docs = query.order_by(DocumentTypeModel.created_at.desc()).all()
    return [_type_to_response(d) for d in docs]


@router.get("/metadata-v2/document-types/{type_id}", response_model=DocumentTypeDetail)
def get_document_type(type_id: str, db: Session = Depends(get_db)):
    """문서 유형 상세 (필드 포함)"""
    doc = db.query(DocumentTypeModel).filter_by(type_id=type_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="문서 유형을 찾을 수 없습니다")
    return DocumentTypeDetail(
        **_type_to_response(doc).model_dump(),
        fields=[_field_to_response(f) for f in doc.fields],
    )


@router.post("/metadata-v2/document-types", response_model=DocumentTypeResponse, status_code=201)
def create_document_type(
    body:    DocumentTypeCreate,
    user_id: str = Query("default"),
    db:      Session = Depends(get_db),
):
    """문서 유형 생성"""
    doc = DocumentTypeModel(
        type_id=str(uuid.uuid4()),
        user_id=user_id,
        name=body.name,
        category=body.category,
        description=body.description,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info(f"[MetaV2] 문서유형 생성: {doc.name} ({doc.type_id})")
    return _type_to_response(doc)


@router.put("/metadata-v2/document-types/{type_id}", response_model=DocumentTypeResponse)
def update_document_type(
    type_id: str,
    body:    DocumentTypeUpdate,
    db:      Session = Depends(get_db),
):
    """문서 유형 수정"""
    doc = db.query(DocumentTypeModel).filter_by(type_id=type_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="문서 유형을 찾을 수 없습니다")
    if body.name        is not None: doc.name        = body.name
    if body.category    is not None: doc.category    = body.category
    if body.description is not None: doc.description = body.description
    if body.is_active   is not None: doc.is_active   = body.is_active
    doc.updated_at = datetime.now()
    db.commit()
    db.refresh(doc)
    return _type_to_response(doc)


@router.delete("/metadata-v2/document-types/{type_id}", status_code=204)
def delete_document_type(type_id: str, db: Session = Depends(get_db)):
    """문서 유형 삭제 (하위 필드 포함)"""
    doc = db.query(DocumentTypeModel).filter_by(type_id=type_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="문서 유형을 찾을 수 없습니다")
    db.delete(doc)
    db.commit()


# ============================================================
# 필드 정의 API
# ============================================================

@router.get("/metadata-v2/document-types/{type_id}/fields", response_model=List[FieldResponse])
def list_fields(type_id: str, db: Session = Depends(get_db)):
    """특정 문서 유형의 필드 목록"""
    fields = (
        db.query(FieldDefinitionModel)
        .filter_by(type_id=type_id)
        .order_by(FieldDefinitionModel.order)
        .all()
    )
    return [_field_to_response(f) for f in fields]


@router.post("/metadata-v2/document-types/{type_id}/fields", response_model=FieldResponse, status_code=201)
def create_field(type_id: str, body: FieldSchema, db: Session = Depends(get_db)):
    """필드 추가"""
    doc = db.query(DocumentTypeModel).filter_by(type_id=type_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="문서 유형을 찾을 수 없습니다")
    field = FieldDefinitionModel(
        field_id=str(uuid.uuid4()),
        type_id=type_id,
        name=body.name,
        key=body.key,
        field_type=body.field_type,
        is_pii=body.is_pii,
        is_required=body.is_required,
        ai_model=body.ai_model,
        extraction_hint=body.extraction_hint,
        order=body.order,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return _field_to_response(field)


@router.put("/metadata-v2/document-types/{type_id}/fields/{field_id}", response_model=FieldResponse)
def update_field(
    type_id:  str,
    field_id: str,
    body:     FieldSchema,
    db:       Session = Depends(get_db),
):
    """필드 수정"""
    field = db.query(FieldDefinitionModel).filter_by(field_id=field_id, type_id=type_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="필드를 찾을 수 없습니다")
    field.name            = body.name
    field.key             = body.key
    field.field_type      = body.field_type
    field.is_pii          = body.is_pii
    field.is_required     = body.is_required
    field.ai_model        = body.ai_model
    field.extraction_hint = body.extraction_hint
    field.order           = body.order
    db.commit()
    db.refresh(field)
    return _field_to_response(field)


@router.delete("/metadata-v2/document-types/{type_id}/fields/{field_id}", status_code=204)
def delete_field(type_id: str, field_id: str, db: Session = Depends(get_db)):
    """필드 삭제"""
    field = db.query(FieldDefinitionModel).filter_by(field_id=field_id, type_id=type_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="필드를 찾을 수 없습니다")
    db.delete(field)
    db.commit()


# ============================================================
# 카테고리 목록 (필터용)
# ============================================================

@router.get("/metadata-v2/categories")
def list_categories(user_id: str = Query("default"), db: Session = Depends(get_db)):
    """사용 중인 카테고리 목록"""
    rows = (
        db.query(DocumentTypeModel.category)
        .filter_by(user_id=user_id)
        .distinct()
        .all()
    )
    return [r[0] for r in rows if r[0]]

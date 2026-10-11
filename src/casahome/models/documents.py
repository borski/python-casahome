"""Document envelopes observed empty. Item schemas are static and UNVERIFIED."""

from pydantic import Field

from casahome.models._base import CasaModel


class DocumentOrganization(CasaModel):
    id: str | None = None
    status: str | None = None
    error_code: str | None = None
    can_retry: bool | None = None
    completed_at: int | None = None


class DocumentExtraction(DocumentOrganization):
    pending_count: int | None = None
    pending_structure_count: int | None = None
    accepted_count: int | None = None
    dismissed_count: int | None = None
    already_handled_count: int | None = None


class HomeDocument(CasaModel):
    id: str | None = None
    home_id: str | None = None
    original_filename: str | None = None
    name: str | None = None
    document_type: str | None = None
    document_date: str | None = None
    mimetype: str | None = None
    size_bytes: int | None = None
    uploaded_by_name: str | None = None
    created_at: int | None = None
    updated_at: int | None = None
    organization: DocumentOrganization | None = None
    extraction: DocumentExtraction | None = None


class DocumentsResponse(CasaModel):
    documents: list[HomeDocument]
    next_cursor: str | None = None


class DocumentType(CasaModel):
    key: str
    label: str
    description: str


class DocumentTypesResponse(CasaModel):
    """Populated document policy and upload limits were observed."""

    types: list[DocumentType]
    max_file_size_bytes: int
    max_files_per_upload: int
    allowed_mimetypes: list[str]
    max_organization_size_bytes: int | None = None


class DocumentCitation(CasaModel):
    page_index: int | None = None
    page_label: str | None = None
    excerpt: str | None = None


class WorkDocumentSource(CasaModel):
    document_id: str | None = None
    name: str | None = None
    available: bool | None = None
    document_date: str | None = None
    citations: list[DocumentCitation] = Field(default_factory=list)


class WorkDocumentSourceResponse(CasaModel):
    source: WorkDocumentSource | None


class DocumentDetailsResponse(CasaModel):
    """UNVERIFIED document detail envelope."""

    document: HomeDocument


class DocumentSuggestion(CasaModel):
    """Static document suggestion fields."""

    id: str
    todo_id: str
    title: str
    action: str
    reason: str
    area: str | None = None
    citations: list[DocumentCitation]
    state: str
    work_deleted: bool
    task_id: str | None = None
    request_id: str | None = None


class DocumentSuggestionsResponse(CasaModel):
    """UNVERIFIED suggestions envelope."""

    suggestions: list[DocumentSuggestion]
    analysis_status: str | None = None
    limitations: list[str]


class DocumentStructureSuggestion(CasaModel):
    """Static structure suggestion metadata."""

    id: str
    section: str
    title: str
    current_values: list[str]
    current_label: str
    proposed_label: str
    reason: str
    state: str
    changed_since_analysis: bool
    citations: list[DocumentCitation]


class DocumentStructureSuggestionsResponse(CasaModel):
    """UNVERIFIED structure suggestion page."""

    suggestions: list[DocumentStructureSuggestion]

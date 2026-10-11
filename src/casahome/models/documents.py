"""Documents, thumbnails, and the three-step upload flow.

Document item, detail, thumbnail and upload shapes are VERIFIED (live, 2026-10).
Suggestion item schemas are static and UNVERIFIED.
"""

from pydantic import Field, StrictBool

from casahome.models._base import CasaModel


class DocumentOrganization(CasaModel):
    """Background organization job. ``status`` seen as queued, running, completed."""

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
    """Populated item VERIFIED (live, 2026-10).

    ``document_type`` seen as ``other`` and ``inspection_report``.
    ``document_date`` is ``YYYY-MM-DD`` or null. Timestamps are epoch seconds.
    """

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
    """Document detail envelope. VERIFIED (live, 2026-10)."""

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
    """Envelope VERIFIED (live, 2026-10), observed empty. Item fields are static."""

    suggestions: list[DocumentStructureSuggestion]


class DocumentThumbnailResponse(CasaModel):
    """Signed preview URLs. VERIFIED (live, 2026-10).

    The URLs are short-lived credentials (``expires_at`` epoch seconds). Don't
    log or persist them. The library never fetches them.
    """

    url: str
    expires_at: int
    preview_pages: list[str] = Field(default_factory=list)
    page_count_url: str | None = None


class DocumentUploadSession(CasaModel):
    """One upload slot. ``session_url`` is a signed Cloud Storage upload URL."""

    upload_id: str
    session_url: str


class DocumentUploadSessionsResponse(CasaModel):
    """One session per requested file, in request order. VERIFIED (live, 2026-10)."""

    uploads: list[DocumentUploadSession]


class CreateDocumentResponse(CasaModel):
    """HTTP 201 body from registering an upload. VERIFIED (live, 2026-10).

    ``already_exists`` is true when Casa matched the file to an existing document.
    """

    document: HomeDocument
    already_exists: StrictBool

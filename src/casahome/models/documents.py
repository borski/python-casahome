"""Documents, thumbnails, and the three-step upload flow.

Document, file metadata and populated suggestion shapes were observed in traffic.
Suggestion view=all was observed. Other view values and populated match/cursor
behavior remain UNVERIFIED.
"""

from pydantic import Field, JsonValue, StrictBool, StrictInt

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
    size_bytes: StrictInt | None = None
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
    """VERIFIED populated fields. States pending and accepted observed.

    Matches were empty. Future match items stay opaque JSON, not guessed types.
    """

    id: str
    todo_id: str
    title: str
    action: str
    reason: str
    area: str | None = None
    citations: list[DocumentCitation]
    state: str
    work_deleted: bool
    matches: list[JsonValue] = Field(default_factory=list)
    task_id: str | None = None
    request_id: str | None = None


class DocumentSuggestionsResponse(CasaModel):
    """VERIFIED populated envelope. Non-null cursor behavior is UNVERIFIED."""

    suggestions: list[DocumentSuggestion]
    next_cursor: str | None = None
    analysis_status: str | None = None
    limitations: list[str]


class DocumentStructureSuggestion(CasaModel):
    """VERIFIED populated fields. States pending and accepted observed.

    Newly typed fields default to None for older synthetic/static payloads.
    The response decision accepted was observed. No dismissal variant is inferred.
    """

    id: str
    entity_id: str | None = None
    definition_id: str | None = None
    section: str
    title: str
    current_values: list[str]
    current_label: str
    proposed_label: str
    reason: str
    state: str
    changed_since_analysis: StrictBool
    responded_at: StrictInt | None = None
    citations: list[DocumentCitation]


class DocumentStructureSuggestionsResponse(CasaModel):
    """VERIFIED envelope and populated suggestion fields."""

    suggestions: list[DocumentStructureSuggestion]


class SavedResponse(CasaModel):
    """VERIFIED structure response envelope, observed saved=true.

    Requires a strict Boolean. Missing, null or coerced flags aren't success.
    False remains representable, but its server behavior is UNVERIFIED.
    """

    saved: StrictBool


class DocumentFileMetadataResponse(CasaModel):
    """VERIFIED signed file URL and integer expiry. No download occurs.

    The URL is a short-lived credential. Don't log or persist it.
    """

    url: str
    expires_at: StrictInt


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

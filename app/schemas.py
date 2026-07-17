from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    pdf_path: str
    version_number: int | None = None  # auto-increment if omitted


class IngestResponse(BaseModel):
    document_id: int
    version_id: int
    version_number: int
    node_count: int
    changed_nodes: int
    new_nodes: int
    unchanged_nodes: int


class NodeSummary(BaseModel):
    id: int
    node_key: str
    heading: str
    section_number: str | None
    level: int
    content_hash: str
    node_type: str
    changed_from_previous: bool
    child_count: int = 0


class NodeDetail(BaseModel):
    id: int
    node_key: str
    heading: str
    section_number: str | None
    level: int
    body_text: str
    content_hash: str
    node_type: str
    parent_id: int | None
    version_id: int
    version_number: int
    changed_from_previous: bool
    children: list[NodeSummary] = Field(default_factory=list)


class NodeChangeInfo(BaseModel):
    node_id: int
    node_key: str
    heading: str
    changed: bool
    change_type: str  # unchanged|modified|new|removed_in_other
    from_version: int | None = None
    to_version: int | None = None
    previous_hash: str | None = None
    current_hash: str | None = None
    diff_summary: str | None = None


class SelectionCreate(BaseModel):
    name: str
    node_ids: list[int]
    # Optional explicit version; defaults to version of first node
    version_id: int | None = None


class SelectionResponse(BaseModel):
    id: int
    name: str
    version_id: int
    version_number: int
    node_ids: list[int]
    created_at: datetime


class GenerateRequest(BaseModel):
    selection_id: int
    force: bool = False  # if True, regenerate even if cached


class TestCaseIdea(BaseModel):
    title: str
    steps: list[str]
    expected_result: str
    source_node_keys: list[str] = Field(default_factory=list)
    risk_notes: str | None = None


class GenerationResponse(BaseModel):
    id: str
    selection_id: int
    selection_name: str
    created_at: datetime
    test_cases: list[TestCaseIdea]
    source_hashes: dict[str, str]
    llm_status: str
    stale: bool | None = None
    staleness_detail: dict[str, Any] | None = None


class StalenessReport(BaseModel):
    generation_id: str
    selection_id: int
    is_stale: bool
    compared_against_version: int | None
    changed_nodes: list[dict[str, Any]]
    limits_note: str

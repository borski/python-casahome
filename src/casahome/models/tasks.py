"""Static task detail and grouped visit-plan fields remain UNVERIFIED.

Fields inferred from the app. GroupedTaskDetails.tasks uses GroupedTaskItem.
Bookable's envelope was observed live, but tagged items remain JsonValue.
Swift case names aren't wire tags.
"""

from pydantic import JsonValue

from casahome.models._base import CasaModel
from casahome.models.images import MediaAttachment


class BookableHandymanTasksResponse(CasaModel):
    items: list[JsonValue]
    current_vendor_additional_availability_minutes: int | None = None
    total_additional_availability_minutes: int | None = None


class TaskDetailsVisit(CasaModel):
    id: str
    start_time: int


class TaskUpdate(CasaModel):
    id: str
    message: str
    sender_name: str
    sender_avatar_url: str | None = None
    sender_avatar_cache_key: str | None = None
    sent_at: int
    attachments: list[MediaAttachment] | None = None


class TaskDetails(CasaModel):
    id: str
    title: str
    description: str
    emoji: str
    status: str
    visit: TaskDetailsVisit | None = None
    updates: list[TaskUpdate]
    attachments: list[MediaAttachment] | None = None
    can_schedule_handyman_vendor_visit: bool
    can_chat_with_concierge: bool
    can_edit: bool
    can_delete: bool


class VendorVisitAutopilotPlan(CasaModel):
    id: str
    title: str
    description: str
    emoji: str


class VendorVisitAutopilotTaskTarget(CasaModel):
    id: str
    kind: str
    primary_label: str
    secondary_label: str
    symbol_name: str
    image_url: str | None = None
    image_cache_key: str | None = None


class GroupedTaskItem(CasaModel):
    id: str
    status: str
    target: VendorVisitAutopilotTaskTarget | None = None
    updates: list[TaskUpdate]


class GroupedTaskDetails(CasaModel):
    plan: VendorVisitAutopilotPlan
    visit: TaskDetailsVisit | None = None
    tasks: list[GroupedTaskItem]

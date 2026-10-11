"""Help center bundle models, inferred from the app.

A populated ``member_ios`` bundle parsed with these models in live traffic
(2026-10). Because ``populate_by_name``
accepts either spelling, that doesn't confirm the camelCase aliases are the
wire keys. No other app ID, article-view tracking or feedback is inferred.
"""

from pydantic import Field

from casahome.models._base import CasaModel


class HelpCenterTopic(CasaModel):
    id: str
    slug: str
    name: str
    blurb: str
    system_image: str = Field(alias="systemImage")
    hero_image_url: str | None = Field(default=None, alias="heroImageURL")
    sort_order: int = Field(alias="sortOrder")


class HelpCenterArticle(CasaModel):
    id: str
    topic_id: str = Field(alias="topicId")
    slug: str
    sort_order: int = Field(alias="sortOrder")
    is_top_question: bool = Field(alias="isTopQuestion")
    is_featured: bool = Field(alias="isFeatured")
    article_version_id: str = Field(alias="articleVersionId")
    version_number: int = Field(alias="versionNumber")
    title: str
    summary: str
    body_markdown: str = Field(alias="bodyMarkdown")


class HelpCenterBundle(CasaModel):
    app: str
    topics: list[HelpCenterTopic]
    articles: list[HelpCenterArticle]


class HelpCenterBundleResponse(CasaModel):
    data: HelpCenterBundle

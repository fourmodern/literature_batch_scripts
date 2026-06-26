---
title: "{{ title | replace('"', '\"') }}"
tags:
  - literature
  - ai-summary
{%- for tag in collections | collections_to_tags %}
  - "{{ tag }}"
{%- endfor %}
{%- if keywords %}
{%- for keyword in keywords %}
  {%- set clean_keyword = keyword | replace(':', '') | replace('(', '') | replace(')', '') | replace('"', '') | replace("'", '') | replace('\n', '') | replace(',', '') | replace(';', '') | replace('=', '') | replace('[', '') | replace(']', '') | replace('{', '') | replace('}', '') | replace('/', '-') | replace(' ', '-') | replace('--', '-') | lower | trim | trim('-') %}
  {%- if clean_keyword and clean_keyword | length > 1 and clean_keyword | length < 50 %}
  - "{{ clean_keyword }}"
  {%- endif %}
{%- endfor %}
{%- endif %}
date: {{ date | default('now') | date(format='%Y-%m-%d') }}
updated: null
related: []
collections: 
{%- if collections %}
{%- for collection in collections %}
  - "{{ collection }}"
{%- endfor %}
{%- else %}
  - "Uncategorized"
{%- endif %}
authors:
{%- if authors %}
{%- for author in authors %}
  - "{{ author }}"
{%- endfor %}
{%- else %}
  - "Unknown"
{%- endif %}
year: {{ year }}
doi: "{{ doi | default('') }}"
journal: "{{ publicationTitle | default('') }}"
---

> [!Link]
> 🌐 [Open in Zotero Web Library]({{ zotero_link }})
> 📚 [Open in Zotero Desktop]({{ zotero_app_link }})
{%- if pdf_path %}
{%- if pdf_path.startswith('file://') %}
> 📄 [Open PDF locally]({{ pdf_path }})
{%- else %}
> 
> ![[{{ pdf_path }}]]
> 
> 📄 [[{{ pdf_path }}|Open PDF: {{ title }}]]
{%- endif %}
{%- else %}
> 📄 PDF not available
{%- endif %}

{%- if ai_tool_links %}

{{ ai_tool_links }}
{%- endif %}

> [!Abstract]
> {{ abstract }}

---

# 🧠 간단 요약
{{ short_summary }}

{% if featured_image %}
---

## 🎯 핵심 그림

![[{{ featured_image.relative_path }}]]

> **{{ featured_image.selection_reason }}** - 페이지 {{ featured_image.page }} ({{ featured_image.width }}×{{ featured_image.height }}px)

{% endif %}

---

# 📜 1페이지 요약
{{ long_summary }}

---

## 📚 논문 기여
{{ contribution | default('') }}

## 🧱 부족한 부분
{{ limitations | default('') }}

## 💡 평가 및 아이디어
{{ ideas | default('') }}

---

## 📊 Figures
{% if figure_captions and figure_captions|length > 0 %}
{% for fig in figure_captions %}
- **그림 {{ fig.number }}.** {{ fig.title_kr | default(fig.title) }}
{% endfor %}
{% else %}
논문에서 그림 정보를 찾을 수 없습니다.
{% endif %}

---

## 📈 Tables
{% if table_captions and table_captions|length > 0 %}
{% for table in table_captions %}
- **표 {{ table.number }}.** {{ table.title_kr | default(table.title) }}
{% endfor %}
{% else %}
논문에서 표 정보를 찾을 수 없습니다.
{% endif %}

---

{% if annotations and annotations|length > 0 %}
## ✍️ 하이라이트 및 주석
{% for annotation in annotations %}
> {{ annotation.type }} {{ annotation.color }}
> {{ annotation.annotatedText | nl2br }}
> {{ annotation.comment }}
> [page {{ annotation.page }}](file://{{ annotation.attachment.path }})
{% endfor %}
{% endif %}

---

> [!Cite]
> {{ bibliography | default('') }}

> [!Metadata]  
> **Citekey**:: @{{ citekey | default(key) }}  
> **Type**:: {{ itemType | default('journalArticle') }}  
> **Volume**:: {{ volume | default('') }}{% if issue %}, Issue {{ issue }}{% endif %}{% if pages %}, pp. {{ pages }}{% endif %}  
> **Publisher**:: {{ publisher | default('') }}  
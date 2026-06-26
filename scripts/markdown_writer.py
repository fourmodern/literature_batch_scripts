"""
Write summaries and metadata to Obsidian-flavored Markdown using Jinja2.
"""
import os
import re
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

# Strip leading numeric/dotted ordering prefix (e.g. "000.", "615.", "6151.")
_PREFIX_RE = re.compile(r'^[\d]+\.?\s*')
_MULTI_HYPHEN_RE = re.compile(r'-+')


def date_filter(value, format='%Y-%m-%d'):
    """Custom filter for date formatting."""
    if value == 'now':
        return datetime.now().strftime(format)
    elif isinstance(value, str):
        # Try to parse common date formats
        for fmt in ['%Y-%m-%d', '%Y', '%Y-%m']:
            try:
                return datetime.strptime(value, fmt).strftime(format)
            except:
                continue
    return value

def nl2br(value):
    """Convert newlines to HTML line breaks."""
    if not value:
        return value
    return str(value).replace('\n', '<br>\n')


def _normalize_segment(seg: str) -> str:
    """Lowercase, drop numeric prefix, collapse separators to hyphens."""
    if not seg:
        return ''
    seg = seg.strip()
    cleaned = _PREFIX_RE.sub('', seg)
    if not cleaned:
        cleaned = seg
    cleaned = cleaned.lower().replace('_', '-').replace(' ', '-')
    cleaned = _MULTI_HYPHEN_RE.sub('-', cleaned).strip('-')
    return cleaned


def collection_to_tags(collection_path):
    """Convert a Zotero collection path into a deduped list of Obsidian tags.

    Emits a nested tag (path/with/slashes for hierarchical filtering in
    Obsidian) plus each segment as a flat tag.

    Example:
        '000.Papers/600.Geninus/615.foundation_model/6151.hist_ST'
          -> ['papers/geninus/foundation-model/hist-st',
              'papers', 'geninus', 'foundation-model', 'hist-st']
    """
    if not collection_path:
        return []
    segments = [_normalize_segment(s) for s in str(collection_path).split('/')]
    segments = [s for s in segments if s]
    if not segments:
        return []
    nested = '/'.join(segments)
    out = [nested]
    seen = {nested}
    for s in segments:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out


def collections_to_tags(collections):
    """Apply collection_to_tags across a list of collection paths and dedupe."""
    if not collections:
        return []
    out = []
    seen = set()
    for c in collections:
        for t in collection_to_tags(c):
            if t not in seen:
                out.append(t)
                seen.add(t)
    return out


env.filters['date'] = date_filter
env.filters['nl2br'] = nl2br
env.filters['collection_to_tags'] = collection_to_tags
env.filters['collections_to_tags'] = collections_to_tags

def render_note(template_name: str, context: dict, include_ai_links: bool = False) -> str:
    """Render markdown note from template

    Args:
        template_name: Name of the Jinja2 template
        context: Dictionary of variables to pass to template
        include_ai_links: Whether to include AI tool links (ignored for compatibility)
    """
    template = env.get_template(template_name)
    return template.render(**context)

def write_markdown(content: str, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    # demo usage
    ctx = {
        'title': 'Sample Paper',
        'pdf_path': './vault/Papers/sample.pdf',
        'abstract': 'This is an abstract.',
        'short_summary': 'Short summary here.',
        'long_summary': 'Long summary here.',
        'contribution': '',
        'limitations': '',
        'ideas': '',
        'annotations': [],
        'bibliography': '',
        'authors': 'Doe, J.',
        'year': '2021',
        'citekey': 'doe2021sample',
        'itemType': 'journalArticle',
        'publicationTitle': 'Journal Title',
        'volume': '1',
        'issue': '1',
        'publisher': 'Publisher',
        'pages': '1-10',
        'DOI': '10.1000/sample'
    }
    md = render_note('literature_note.md', ctx)
    write_markdown(md, './vault/LiteratureNotes/sample.md')

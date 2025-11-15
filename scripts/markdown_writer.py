"""
Write summaries and metadata to Obsidian-flavored Markdown using Jinja2.
"""
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

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

env.filters['date'] = date_filter
env.filters['nl2br'] = nl2br

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

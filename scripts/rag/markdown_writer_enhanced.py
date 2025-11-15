"""
Enhanced markdown writer with AI tool links support
"""
import os
from markdown_writer import render_note, write_markdown
from ai_tool_links import AIToolLinkGenerator


def render_note_with_ai_links(template_name: str, context: dict, 
                              include_ai_links: bool = True,
                              selected_ai_tools: list = None) -> str:
    """
    Render note template with AI tool links added
    
    Args:
        template_name: Template file name
        context: Template context dictionary
        include_ai_links: Whether to include AI tool links
        selected_ai_tools: List of AI tools to include
    
    Returns:
        Rendered markdown content
    """
    
    # Add AI tool links to context if requested
    if include_ai_links:
        try:
            link_generator = AIToolLinkGenerator()
            
            # Default AI tools if not specified
            if selected_ai_tools is None:
                # Read from environment variable or use defaults
                ai_tools = os.getenv('AI_TOOLS', 'scispace,notebooklm,chatpdf,perplexity')
                selected_ai_tools = [tool.strip() for tool in ai_tools.split(',')]
            
            # Prepare paper metadata for link generation
            paper_metadata = {
                'title': context.get('title', ''),
                'doi': context.get('doi', '') or context.get('DOI', ''),
                'year': context.get('year', ''),
                'authors': context.get('authors', []),
                'journal': context.get('publicationTitle', '') or context.get('journal', '')
            }
            
            # Generate formatted markdown links
            ai_tool_links = link_generator.format_markdown_links(paper_metadata, selected_ai_tools)
            context['ai_tool_links'] = ai_tool_links
            
        except Exception as e:
            print(f"  ⚠️ AI 도구 링크 생성 실패: {e}")
            context['ai_tool_links'] = ''
    else:
        context['ai_tool_links'] = ''
    
    # Call original render_note
    return render_note(template_name, context)


def write_markdown_with_ai_links(context: dict, output_path: str,
                                 template_name: str = 'literature_note.md',
                                 include_ai_links: bool = True,
                                 selected_ai_tools: list = None):
    """
    Write markdown file with AI tool links
    
    Args:
        context: Template context
        output_path: Output file path
        template_name: Template to use
        include_ai_links: Whether to include AI links
        selected_ai_tools: AI tools to include
    """
    
    # Render with AI links
    content = render_note_with_ai_links(
        template_name, 
        context,
        include_ai_links=include_ai_links,
        selected_ai_tools=selected_ai_tools
    )
    
    # Write to file
    write_markdown(content, output_path)


# Export both original and enhanced functions
__all__ = [
    'render_note',
    'write_markdown',
    'render_note_with_ai_links',
    'write_markdown_with_ai_links'
]
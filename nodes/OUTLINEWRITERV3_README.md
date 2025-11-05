# Outline Writer V3 Node

## Overview
The **OutlineWriterV3Node** is an advanced content generation node that creates structured outlines with chapter-by-chapter navigation and AI-powered content enhancement capabilities.

## What's New in V3

### Enhanced Features
1. **Chapter Navigation Window**: New interface for browsing and editing individual chapters
2. **AI Content Enhancement**: One-click enhancement of chapter content using customizable prompts
3. **Dual Review Process**: Two-stage review for better control over generated content
4. **Content Enhancement Prompt**: Configurable prompt property for AI enhancement

### Workflow
```
1. Generate Outline (with batching for large projects)
   ↓
2. Initial Review Window (Edit & Accept or Accept)
   ↓
3. Chapter Navigation Window (Browse, Enhance, Edit)
   ↓
4. Final Output
```

## Key Features

### 1. **Intelligent Chapter Generation**
- Generates book outlines with configurable chapter count
- Supports up to 100 chapters with automatic batching
- Processes in batches of 5 chapters for projects > 10 chapters
- Maintains context across batches for coherent narratives

### 2. **Initial Review Window**
- Review the complete generated outline
- Edit the entire content if needed
- Accept or cancel the generation

### 3. **Chapter Navigation Window** (NEW in V3)
- **Left Panel**: List of all chapters for easy navigation
- **Right Panel**: 
  - Chapter content display (read-only view)
  - Enhancement text area for AI results or search terms
  - Action buttons for enhancement and search

### 4. **AI Content Enhancement** (NEW in V3)
- Select any chapter from the list
- Click "Enhance with AI" button
- Uses the configurable "Content Enhancement Prompt" property
- Appends chapter content to the prompt
- Displays AI-enhanced content in the enhancement area
- Can be run multiple times with different chapters

### 5. **Web Search Integration** (Placeholder)
- Button available for future web search functionality
- Will integrate with search and scrape capabilities

## Node Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| **node_name** | text | OutlineWriterV3Node | Display name for the node |
| **description** | text | Processes the input... | Description of node functionality |
| **enhancement_prompt** | textarea | Please enhance and expand... | Prompt used when enhancing chapter content with AI |
| **Prompt** | textarea | Processing your request... | Base prompt for outline generation |
| **api_endpoint** | dropdown | (first available) | API endpoint to use for generation |
| **enable_review** | boolean | true | Enable review windows |
| **is_start_node** | boolean | false | Mark as workflow start node |
| **is_end_node** | boolean | false | Mark as workflow end node |

## Usage Guide

### Basic Usage

1. **Add Node to Workflow**
   - Drag OutlineWriterV3Node onto canvas
   - Connect input from previous node
   - Configure properties (especially enhancement_prompt)

2. **Configure Chapter Settings**
   - When node runs, dialog appears
   - Set number of chapters (1-100)
   - Set paragraphs per chapter (1-10)
   - Click OK to start generation

3. **Initial Review**
   - Review the generated outline
   - Choose:
     - **Accept**: Proceed with content as-is
     - **Edit & Accept**: Make changes then proceed
     - **Cancel**: Abort the process

4. **Chapter Navigation & Enhancement**
   - Select a chapter from the list (left panel)
   - View chapter content (top right)
   - Click "Enhance with AI" to improve content
   - AI results appear in enhancement area (bottom right)
   - Repeat for other chapters as needed
   - Click "Save & Continue" when done

### Enhancement Prompt Configuration

The `enhancement_prompt` property controls how chapters are enhanced. Examples:

**Default:**
```
Please enhance and expand the following chapter content with additional details and context:

```

**For Fiction:**
```
Enhance this chapter with more vivid descriptions, deeper character development, and engaging dialogue:

```

**For Non-Fiction:**
```
Expand this chapter with more detailed explanations, relevant examples, and supporting evidence:

```

**For Technical Content:**
```
Enhance this chapter with technical details, code examples, and best practices:

```

## Chapter Navigation Window Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Chapter Navigation & Enhancement                            │
├──────────────┬──────────────────────────────────────────────┤
│ Chapters:    │ Chapter Content:                             │
│              │                                              │
│ Chapter 1    │ [Chapter text displayed here]                │
│ Chapter 2    │                                              │
│ Chapter 3    │                                              │
│ Chapter 4    │                                              │
│ ...          │                                              │
│              │                                              │
│              ├──────────────────────────────────────────────┤
│              │ Content Enhancement:                         │
│              │                                              │
│              │ [AI enhancement results or search terms]     │
│              │                                              │
│              │ [Enhance with AI] [Web Search]               │
├──────────────┴──────────────────────────────────────────────┤
│                                    [Cancel] [Save & Continue]│
└─────────────────────────────────────────────────────────────┘
```

## Technical Details

### Chapter Parsing
The node automatically parses content into chapters by:
1. Detecting lines starting with "Chapter "
2. Grouping all content until the next chapter marker
3. Creating a structured array of chapter objects

### Batch Processing
For projects with more than 10 chapters:
- Processes in batches of 5 chapters
- Maintains context by including previous chapters in prompts
- Cleans responses to avoid duplication
- Assembles final outline from all batches

### API Integration
- Uses the node's configured API endpoint
- Supports all API endpoints available in XeroFlow
- Token usage is tracked and logged
- Handles API errors gracefully

## Comparison: V2 vs V3

| Feature | V2 | V3 |
|---------|----|----|
| **Chapter Generation** | ✅ Yes | ✅ Yes |
| **Batch Processing** | ✅ Yes | ✅ Yes |
| **Initial Review** | ✅ Yes | ✅ Yes |
| **Chapter Navigation** | ❌ No | ✅ Yes |
| **AI Enhancement** | ❌ No | ✅ Yes |
| **Enhancement Prompt Property** | ❌ No | ✅ Yes |
| **Chapter-by-Chapter Editing** | ❌ No | ✅ Yes |
| **Web Search Integration** | ❌ No | 🔄 Planned |

## Best Practices

### 1. **Craft Good Enhancement Prompts**
- Be specific about what you want enhanced
- Include style guidelines
- Mention target audience if relevant
- Keep prompts concise but descriptive

### 2. **Use Batching Wisely**
- For small projects (≤10 chapters): Single generation is faster
- For large projects (>10 chapters): Batching ensures better quality
- Monitor API costs for very large projects

### 3. **Review Strategically**
- Use initial review for structural changes
- Use chapter navigation for detailed enhancements
- Focus AI enhancement on chapters that need more depth

### 4. **Save Frequently**
- The chapter navigation window doesn't auto-save
- Click "Save & Continue" to preserve changes
- Canceling will lose all enhancements

## Troubleshooting

### Issue: Chapter Navigation Window is Empty
**Solution**: Ensure your outline contains lines starting with "Chapter "

### Issue: Enhance with AI Button Does Nothing
**Solution**: 
1. Select a chapter from the list first
2. Check that enhancement_prompt property is configured
3. Verify API endpoint is selected and working

### Issue: Enhancement Takes Too Long
**Solution**:
1. Check API endpoint response time
2. Consider using a faster model
3. Shorten the enhancement prompt if possible

### Issue: Chapters Not Parsing Correctly
**Solution**: Ensure chapter headers follow format: "Chapter X: Title" or "Chapter X"

## Future Enhancements

### Planned Features
- **Web Search Integration**: Search and scrape content to enhance chapters
- **Chapter Reordering**: Drag-and-drop chapter reorganization
- **Export Options**: Save individual chapters or full outline
- **Template System**: Pre-configured enhancement prompts for different genres
- **Undo/Redo**: Track changes in chapter navigation window
- **Diff View**: Compare original vs enhanced content

## Example Workflow

```
[User Input] → [OutlineWriterV3] → [Further Processing]
     ↓
"Write a 15-chapter book about AI"
     ↓
[Chapter Config Dialog]
- 15 chapters
- 2 paragraphs each
     ↓
[Batch Generation]
- Batch 1: Chapters 1-5
- Batch 2: Chapters 6-10
- Batch 3: Chapters 11-15
     ↓
[Initial Review]
- Review full outline
- Make global edits
- Accept
     ↓
[Chapter Navigation]
- Select Chapter 3
- Click "Enhance with AI"
- Review enhanced content
- Select Chapter 7
- Click "Enhance with AI"
- Save & Continue
     ↓
[Output]
Enhanced outline ready for next node
```

## Dependencies
- **tkinter**: GUI framework (built-in with Python)
- **queue**: Thread-safe queues (built-in)
- **threading**: Multi-threading support (built-in)
- **BaseNode**: XeroFlow base node class
- **API Service**: XeroFlow API integration

## Conclusion
OutlineWriterV3Node provides a powerful, user-friendly interface for generating and enhancing structured content. The dual-review process and AI enhancement capabilities make it ideal for creating high-quality outlines for books, articles, courses, and other long-form content.

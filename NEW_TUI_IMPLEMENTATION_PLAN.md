# New TUI Implementation Plan (Revised)
*Based on Principal Code Review Feedback*

## Summary
Instead of creating a parallel TUI implementation, enhance the existing `EnhancedAutoSquashApp` with a conditional 3-panel layout that matches the mock screenshot. This approach provides the same visual outcome with significantly lower complexity.

## Architecture Decision: Enhance Existing Implementation

**❌ Original Plan:** Create completely separate `ModernAutoSquashApp` 
**✅ Revised Plan:** Add conditional layout to existing `EnhancedApprovalScreen`

### Key Benefits of Revised Approach:
- **90% less code** - Reuses all existing business logic
- **Single codebase** - No maintenance nightmare  
- **Proven patterns** - Leverages existing `UIStateController`, message passing
- **Easy migration** - Boolean flag instead of separate implementations
- **Reduced risk** - Minimal changes to core functionality

## Implementation Strategy

### Phase 1: Add Layout Toggle
```python
# main.py - Simple boolean flag
parser.add_argument('--modern-layout', action='store_true', 
                   help='Use 3-panel modern layout (experimental)')

# enhanced_app.py - Pass flag to app
class EnhancedAutoSquashApp(App[bool]):
    def __init__(self, mappings, commit_analyzer, use_modern_layout=False):
        self.use_modern_layout = use_modern_layout
        # ... existing code
```

### Phase 2: Conditional Screen Layout
```python
# enhanced_screens.py - EnhancedApprovalScreen.compose()
def compose(self) -> ComposeResult:
    yield Header()
    
    if self.app.use_modern_layout:
        # NEW: 3-panel layout matching mock
        yield from self._compose_modern_layout()
    else:
        # EXISTING: Current single-panel layout  
        yield from self._compose_legacy_layout()
    
    yield Footer()

def _compose_modern_layout(self) -> ComposeResult:
    """3-panel layout: Changes | Targets | Preview"""
    with Container(id="main-container", classes="modern-layout"):
        with Horizontal(id="panels-row"):
            # Left: Changes to Review (green border)
            with Container(id="changes-panel", classes="panel bordered-green"):
                # Reuse existing hunk widgets
                with VerticalScroll(id="changes-scroll"):
                    for mapping in self.mappings:
                        widget = self._create_hunk_widget(mapping, ...)
                        yield widget
            
            # Right: Target Commits (cyan border) 
            with Container(id="targets-panel", classes="panel bordered-cyan"):
                with VerticalScroll(id="targets-scroll"):
                    # Show commits for selected hunk
                    yield TargetCommitsList(self.commit_infos)
        
        # Bottom: Preview (white border)
        with Container(id="preview-panel", classes="panel bordered-white"):
            yield DiffPreview(id="diff-preview")

def _compose_legacy_layout(self) -> ComposeResult:
    """Existing single-panel scrollable layout"""
    # Current implementation unchanged
    with Container(id="main-container"):
        # ... existing code
```

### Phase 3: CSS for Bordered Panels
```python
# styles.py - Add modern layout CSS
MODERN_LAYOUT_CSS = """
/* 3-Panel Modern Layout */
.modern-layout {
    layout: vertical;
    height: 1fr;
}

#panels-row {
    layout: horizontal;
    height: 60%;
}

#changes-panel, #targets-panel {
    width: 50%;
    height: 1fr;
    margin: 0 1;
}

#preview-panel {
    height: 40%;
    margin: 1 0;
}

/* Bordered Panels with Rounded Corners and Titles */
.panel {
    padding: 1 2;
    border-title-style: bold;
    border-title-color: white;
}

.bordered-green {
    border: round green;
    border-title: "Changes to Review";
}

.bordered-cyan { 
    border: round cyan;
    border-title: "Target Commits";
}

.bordered-white {
    border: round white;
    border-title: "Preview";
}
"""

# Update CONSOLIDATED_CSS
CONSOLIDATED_CSS = f"""
{LAYOUT_CSS}
{BUTTON_CSS}
{SECTION_CSS}
{WIDGET_CSS}
{BATCH_CSS}
{SEPARATOR_CSS}
{MODAL_CSS}
{SINGLE_PANE_CSS}
{MODERN_LAYOUT_CSS}
"""
```

## File Changes Required

### 1. `/src/git_autosquash/main.py`
```python
# Add CLI argument
parser.add_argument('--modern-layout', action='store_true',
                   help='Use experimental 3-panel layout')

# Pass to enhanced app
app = EnhancedAutoSquashApp(mappings, commit_analyzer, 
                           use_modern_layout=args.modern_layout)
```

### 2. `/src/git_autosquash/tui/enhanced_app.py`
```python
# Add parameter to constructor
def __init__(self, mappings, commit_analyzer, use_modern_layout=False):
    self.use_modern_layout = use_modern_layout
    # ... rest unchanged
```

### 3. `/src/git_autosquash/tui/enhanced_screens.py`  
- Add `_compose_modern_layout()` method
- Add conditional logic to `compose()`
- Keep all existing business logic unchanged

### 4. `/src/git_autosquash/tui/styles.py`
- Add `MODERN_LAYOUT_CSS` with 3-panel styling
- Include in `CONSOLIDATED_CSS`

### 5. New Helper Widgets (minimal)
```python
# enhanced_screens.py - Simple helper widgets
class TargetCommitsList(Widget):
    """Display target commits for selected hunk"""
    # Reuse existing commit_infos data

class DiffPreview(Widget): 
    """Display diff content for selected hunk"""
    # Reuse existing diff display logic
```

## Key Design Principles

### 1. **Reuse Existing Logic**
- Keep `UIStateController` for state management
- Reuse `FallbackHunkMappingWidget` message passing  
- Leverage existing commit analysis and diff parsing
- Maintain all keyboard shortcuts and interactions

### 2. **Minimal New Code**
- Only add layout composition changes
- CSS-driven visual differences
- Simple helper widgets for panel content

### 3. **Easy Rollback**
- Boolean flag can be removed easily
- Legacy layout remains untouched
- No breaking changes to existing functionality

### 4. **Progressive Enhancement**
- Start with basic 3-panel layout
- Add panel selection/navigation later
- Refine styling based on user feedback
- Eventually remove legacy layout

## Testing Strategy

### 1. **Dual Testing**
```bash
# Test existing layout (default)
uv run python -m git_autosquash.main

# Test new layout (experimental)
uv run python -m git_autosquash.main --modern-layout
```

### 2. **Regression Prevention**
- All existing tests continue to work
- Add new tests specifically for modern layout
- Test flag handling and conditional rendering

### 3. **Visual Validation**
- Compare against mock screenshot
- Test rounded borders and titles display correctly
- Verify panel interactions work properly

## Migration Timeline

### Phase 1: Foundation (Week 1)
- Add CLI flag and conditional layout structure
- Basic 3-panel composition with borders and titles

### Phase 2: Content (Week 2)  
- Populate panels with existing widget content
- Test panel selection and navigation

### Phase 3: Polish (Week 3)
- Refine CSS styling to match mock exactly
- Add any missing interactions or features  

### Phase 4: Deprecation (Future)
- Gather user feedback on both layouts
- Remove legacy layout when modern is proven
- Clean up conditional code

## Success Metrics
- ✅ Visual match to mock screenshot
- ✅ All existing functionality preserved
- ✅ Performance equivalent to current implementation
- ✅ No increase in code complexity
- ✅ Easy to maintain single codebase

This approach delivers the same visual outcome as the original parallel implementation plan with significantly lower risk and complexity.
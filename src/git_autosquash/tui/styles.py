"""Consolidated CSS styles for git-autosquash TUI components.

This module contains all CSS styling for the enhanced TUI interface,
organized by component type for maintainability and consistency.
"""

# Main application and layout styles
LAYOUT_CSS = """
/* Main container and layout */
#main-container {
    height: 1fr;
    layout: vertical;
}

#content-wrapper {
    height: 1fr;
    layout: vertical;
}

#content-area {
    height: 1fr;
    overflow: auto;
}

/* Screen headers and descriptions */
#screen-title {
    text-align: center;
    text-style: bold;
    color: $primary;
    margin-bottom: 1;
}

#screen-description {
    text-align: left;
    margin: 0 1;
    color: $text-muted;
}

/* Separator line */
#separator {
    color: $text-muted;
    text-align: center;
    height: 1;
    margin: 1 0;
}
"""

# Action button styles
BUTTON_CSS = """
/* Action buttons - fixed at bottom with margin for Footer */
#action-buttons {
    height: 3;
    padding: 0;
    margin-bottom: 1;
    background: $surface;
    border-top: solid $primary;
    layout: horizontal;
    align: center middle;
}

#action-buttons Button {
    margin: 0 1;
    min-width: 20;
}
"""

# Section header styles
SECTION_CSS = """
/* Section headers */
.section-header {
    background: $boost;
    color: $text;
    text-style: bold;
    padding: 0 1;
    margin: 1 0;
    text-align: left;
}

.section-header.fallback {
    background: $warning;
    color: $background;
}
"""

# Widget-specific styles
WIDGET_CSS = """
/* Hunk mapping widgets */
FallbackHunkMappingWidget {
    height: auto;
    margin: 1 0;
    border: round $primary;
}

FallbackHunkMappingWidget.selected {
    border: thick $accent;
}

FallbackHunkMappingWidget.approved {
    border-left: thick $success;
}

FallbackHunkMappingWidget.ignored {
    opacity: 0.6;
    border-left: thick $warning;
}

/* Diff viewer */
DiffViewer {
    border: round $primary;
    padding: 1;
}

DiffViewer .diff-header {
    color: $text-muted;
    text-style: bold;
}

DiffViewer .diff-added {
    color: $success;
}

DiffViewer .diff-removed {
    color: $error;
}

/* Progress indicators */
ProgressIndicator {
    height: 1;
    background: $panel;
    color: $text;
    text-align: center;
}

EnhancedProgressIndicator {
    height: 3;
    margin: 1 0;
    padding: 0 1;
}

EnhancedProgressIndicator .progress-line {
    text-align: center;
}
"""

# Batch selection widget styles
BATCH_CSS = """
/* Batch selection widget */
BatchSelectionWidget {
    height: auto;
    margin: 1 0;
    padding: 1;
    border: round $surface;
    background: $surface;
}

BatchSelectionWidget .batch-title {
    color: $primary;
    text-style: bold;
    text-align: center;
}

BatchSelectionWidget .batch-description {
    color: $text-muted;
    text-align: center;
    margin: 1 0;
}

BatchSelectionWidget Button {
    margin: 0 1;
    min-width: 15;
}
"""

# Section separator styles
SEPARATOR_CSS = """
/* Fallback section separator */
FallbackSectionSeparator {
    height: 3;
    margin: 2 0;
}

FallbackSectionSeparator .separator-line {
    background: $warning;
    color: $background;
    text-align: center;
    text-style: bold;
}
"""

# Modal styles
MODAL_CSS = """
/* Modal screen styles */
BatchOperationsModal {
    align: center middle;
}

#modal-container {
    width: 60%;
    height: 60%;
    max-width: 80;
    max-height: 30;
    background: $surface;
    border: thick $primary;
    padding: 2;
    layout: vertical;
}

#modal-title {
    text-align: center;
    text-style: bold;
    color: $primary;
    margin-bottom: 1;
    height: auto;
}

#modal-description {
    text-align: center;
    margin-bottom: 1;
    height: auto;
    color: $text-muted;
}

#modal-content {
    height: 1fr;
    margin: 1 0;
}

#modal-buttons {
    height: auto;
    padding-top: 1;
    align: center top;
    layout: horizontal;
}

#modal-buttons Button {
    margin: 0 1;
    min-width: 12;
}
"""

# Panel layout styles
PANEL_CSS = """
/* Hunk list panel */
#hunk-list-panel {
    width: 1fr;
    border-right: solid $primary;
    padding-right: 1;
}

#hunk-list-title {
    text-align: center;
    text-style: bold;
    color: $primary;
    margin-bottom: 1;
}

#hunk-list {
    height: 1fr;
}

/* Diff panel */
#diff-panel {
    width: 1fr;
    padding-left: 1;
}

#diff-title {
    text-align: center;
    text-style: bold;
    color: $primary;
    margin-bottom: 1;
}

#diff-viewer {
    height: 1fr;
}
"""

# Complete consolidated CSS
CONSOLIDATED_CSS = f"""
{LAYOUT_CSS}
{BUTTON_CSS}
{SECTION_CSS}
{WIDGET_CSS}
{BATCH_CSS}
{SEPARATOR_CSS}
{MODAL_CSS}
{PANEL_CSS}
"""

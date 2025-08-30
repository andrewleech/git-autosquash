# Textual Border Research Results

Based on my research, here are the key findings for creating borders with rounded corners and inline titles like shown in the mock screenshot:

## ✅ Rounded Corner Borders

Textual supports rounded corners using the `round` border style:

```css
Widget {
    border: round $primary;  /* Rounded corners with primary theme color */
}
```

```python
# Set programmatically
widget.styles.border = ("round", "green")
```

## ✅ Inline Border Titles

Every Textual widget supports border titles that appear inline at the top of the border:

```python
# Set at class level
class MyPanel(Widget):
    def __init__(self):
        super().__init__()
        self.border_title = "Changes to Review"  # Like in the mock!

# Or set dynamically
panel.border_title = "Target Commits"
panel.border_subtitle = "3 commits found"  # Optional subtitle at bottom
```

```css
/* Style the border title */
Widget {
    border-title-color: white;
    border-title-style: bold;
    border-title-align: left;  /* left, center, or right */
}
```

## ✅ Complete Example Matching Mock

The mock screenshot shows exactly what Textual can do natively:

1. **"Changes to Review" panel** - Round green border with inline title
2. **"Target Commits" panel** - Round cyan border with inline title  
3. **"Preview" panel** - Round white border with inline title
4. **Controls section** - Round border with "Controls" title

```python
class ChangesPanel(Widget):
    DEFAULT_CSS = """
    ChangesPanel {
        border: round green;
        border-title-color: white;
        border-title-style: bold;
        padding: 1 2;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.border_title = "Changes to Review"  # Matches mock exactly!
```

## ✅ Additional Border Features

**Border Styles Available:**
- `round` - Rounded corners ⭐ (what we need)
- `solid` - Simple lines
- `thick` - Thicker lines
- `double` - Double lines
- `dashed` - Dashed lines
- `panel`, `heavy`, `tall`, etc.

**Title Positioning:**
```css
Widget {
    border-title-align: left;    /* Default, matches mock */
    border-title-align: center;  /* Centered title */
    border-title-align: right;   /* Right-aligned title */
}
```

**Dynamic Title Updates:**
```python
# Update titles at runtime based on state
panel.border_title = f"Changes to Review ({len(changes)} files)"
panel.border_subtitle = f"Last updated: {timestamp}"
```

## ✅ Key Advantages

1. **Native Support** - Built into Textual, no custom drawing needed
2. **Theme Integration** - Uses CSS variables like `$primary`, `$success`
3. **Dynamic Updates** - Titles can change at runtime
4. **Consistent Styling** - Same border system across all widgets
5. **Performance** - Optimized terminal rendering

## 🎯 Implementation Strategy

For the new TUI alongside the current one, we can:

1. **Create border-styled panels** exactly like the mock
2. **Use inline titles** for clear section identification
3. **Match the visual hierarchy** with different border colors
4. **Implement responsive behavior** by changing titles/content dynamically

The mock screenshot is perfectly achievable with Textual's native border system!

## 📋 Next Steps

1. ✅ Research completed - Textual fully supports the mock's border style
2. 🔄 Create practical examples (textual_border_research.py)
3. ⏳ Plan new TUI implementation architecture
4. ⏳ Design runtime TUI selection system
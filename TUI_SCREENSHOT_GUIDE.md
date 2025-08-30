# TUI Screenshot Guide

This guide explains how to create high-quality terminal screenshots for the git-autosquash project using the terminal emulation system.

## Overview

The screenshot system uses:
- **pyte**: Terminal emulator library for simulating terminal display
- **PIL (Pillow)**: For rendering the terminal display as images
- **Automated rendering**: Scripts handle terminal size, fonts, and color schemes

## Quick Start

```bash
# Generate all screenshots
python generate_real_screenshots.py

# Generate specific screenshots
python create_realistic_screenshots.py
```

## Screenshot Categories

### 1. Feature Screenshots
- `feature_smart_targeting.png` - Intelligent commit targeting
- `feature_safety_first.png` - Safety mechanisms
- `feature_interactive_tui.png` - Interactive interface

### 2. Workflow Screenshots  
- `workflow_step_01.png` through `workflow_step_06.png` - Complete workflow

### 3. Fallback Screenshots
- `fallback_new_file_fallback.png` - New file handling
- `fallback_manual_override.png` - Manual target selection
- `fallback_ambiguous_blame_fallback.png` - Ambiguous blame cases

### 4. Comparison Screenshots
- `comparison_before_traditional.png` - Traditional git workflow
- `comparison_after_autosquash.png` - With git-autosquash

## Technical Details

### Terminal Configuration
- **Size**: 120x30 characters (optimized for readability)
- **Font**: DejaVu Sans Mono (monospace, widely available)
- **Color Scheme**: Dark theme with high contrast
- **Rendering**: Anti-aliased text with proper spacing

### Content Strategy
- Real command outputs (not mocked data)
- Authentic error messages and responses
- Proper ANSI color support
- Realistic timing and flow

### File Organization
```
screenshots/readme/
├── feature_*.png          # Feature demonstrations
├── workflow_*.png         # Step-by-step workflows  
├── fallback_*.png         # Edge case handling
├── comparison_*.png       # Before/after comparisons
└── hero_screenshot.png    # Main README image
```

## Screenshot Generation Process

### 1. Content Preparation
Each screenshot requires:
- **Content script**: Terminal commands and outputs
- **Timing control**: Realistic command execution timing
- **State management**: Proper git repository states

### 2. Terminal Rendering
The rendering process:
1. Initialize pyte terminal with specified dimensions
2. Execute content script line-by-line
3. Apply ANSI color codes and formatting
4. Capture terminal state at key moments

### 3. Image Generation
Final image creation:
1. Convert terminal buffer to pixel data
2. Apply font rendering with anti-aliasing
3. Add proper margins and padding
4. Export as PNG with optimization

## Customization Options

### Terminal Appearance
```python
# In screenshot generation scripts
TERMINAL_CONFIG = {
    'width': 120,
    'height': 30,
    'font_size': 14,
    'font_family': 'DejaVu Sans Mono',
    'background': '#1a1a1a',
    'foreground': '#ffffff'
}
```

### Color Scheme
```python
# ANSI color mapping
COLORS = {
    'black': '#1a1a1a',
    'red': '#f14c4c',
    'green': '#23d18b',
    'yellow': '#f5f543',
    'blue': '#3b8eea',
    'magenta': '#d670d6',
    'cyan': '#29b8db',
    'white': '#e5e5e5'
}
```

## Best Practices

### Content Creation
1. **Authentic Examples**: Use real repository scenarios
2. **Clear Progression**: Each screenshot should build on the previous
3. **Error Handling**: Show both success and failure cases
4. **User Perspective**: Focus on what users actually see

### Visual Quality
1. **Consistent Sizing**: All screenshots use same dimensions
2. **Readable Text**: Ensure font size works at display resolution
3. **High Contrast**: Colors should be distinguishable
4. **Clean Layout**: Avoid cluttered or confusing displays

### Maintenance
1. **Version Control**: Track screenshot changes with git
2. **Automated Updates**: Scripts should regenerate consistently
3. **Documentation**: Keep this guide updated with changes
4. **Testing**: Verify screenshots render correctly in README

## Troubleshooting

### Common Issues

**Blurry or Pixelated Text**
- Increase font size in terminal config
- Enable font anti-aliasing
- Check image export quality settings

**Incorrect Colors**
- Verify ANSI color code mapping
- Test terminal color support
- Check background/foreground contrast

**Layout Problems**
- Adjust terminal width/height
- Review content line lengths
- Check text wrapping behavior

**Content Accuracy**
- Update scripts to match current CLI output
- Test against latest version
- Verify error messages are current

## Future Improvements

### Planned Enhancements
1. **Interactive Elements**: Highlight user input areas
2. **Animation Support**: GIF generation for complex workflows
3. **Multiple Themes**: Light and dark theme variants
4. **Responsive Design**: Screenshots for different terminal sizes

### Technical Upgrades
1. **Better Font Rendering**: Improved text clarity
2. **Color Accuracy**: Better ANSI color reproduction
3. **Performance**: Faster screenshot generation
4. **Automation**: CI/CD integration for screenshot updates

## Resources

- **pyte Documentation**: https://pyte.readthedocs.io/
- **PIL Documentation**: https://pillow.readthedocs.io/
- **ANSI Color Codes**: Terminal color standard reference
- **Font Resources**: Monospace fonts for terminal rendering

This guide ensures high-quality, consistent screenshots that accurately represent the git-autosquash user experience.
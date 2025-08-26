# TUI Integration Test Suite

This directory contains comprehensive integration tests for the git-autosquash TUI interface using multiple testing approaches.

## Test Structure

### `conftest.py`
Base fixtures and mock data for all TUI tests:
- Mock git operations and repositories
- Sample commits, hunks, and mappings
- Terminal size configurations
- Large datasets for performance testing

### `helpers.py`
Utility classes and functions:
- `TextualAssertions`: Helper methods for asserting TUI state
- `PyteScreenAnalyzer`: Terminal screen analysis using pyte
- `MockDataGenerator`: Generate test data for various scenarios
- Workflow simulation helpers

### Test Files

#### `test_enhanced_app_integration.py`
**Textual Native Integration Tests**
- Layout and positioning validation
- Widget visibility testing
- User interaction simulation
- State management verification
- Complete workflow testing

#### `test_terminal_output.py` 
**Terminal Capture Tests using pyte**
- Low-level terminal output validation
- Screen coordinate verification
- Color coding and ANSI escape sequence testing
- Layout measurement and overlap detection
- Performance testing with large datasets

#### `test_snapshot_regression.py`
**Visual Regression Tests**
- Screenshot comparisons for UI changes
- Multiple terminal size testing
- Different application states
- Theme and styling variations
- Error state handling

#### `test_comprehensive_scenarios.py`
**Real-World Usage Scenarios**
- Complete user workflows
- Edge cases and error conditions  
- Performance stress testing
- Accessibility validation
- Large dataset handling

## Running Tests

### All TUI Integration Tests
```bash
pytest tests/tui_integration/ -v
```

### Specific Test Categories
```bash
# Textual native tests only
pytest tests/tui_integration/test_enhanced_app_integration.py -v

# Terminal output validation
pytest tests/tui_integration/test_terminal_output.py -v

# Visual regression tests
pytest tests/tui_integration/test_snapshot_regression.py -v

# Real-world scenarios
pytest tests/tui_integration/test_comprehensive_scenarios.py -v
```

### Async Tests
All TUI tests use async/await patterns:
```bash
pytest tests/tui_integration/ -v --asyncio-mode=auto
```

### Snapshot Testing
First run will create snapshots:
```bash
pytest tests/tui_integration/test_snapshot_regression.py --snapshot-update
```

Update snapshots after intentional UI changes:
```bash
pytest tests/tui_integration/test_snapshot_regression.py --snapshot-update
```

### Performance Testing
Run performance tests with timing output:
```bash
pytest tests/tui_integration/test_comprehensive_scenarios.py::TestPerformanceScenarios -v -s
```

### Terminal Size Testing
Tests automatically run with multiple terminal sizes defined in `terminal_sizes` fixture.

## Test Dependencies

Required packages (installed via `uv sync --dev`):
- `pytest-asyncio>=0.23.0` - Async test support
- `pytest-textual-snapshot>=1.0.0` - Visual regression testing
- `pyte>=0.8.2` - Terminal emulation
- `pillow>=10.0.0` - Image comparison

## Writing New Tests

### Textual Native Tests
```python
@pytest.mark.asyncio
async def test_my_feature(self, blame_matched_mappings, mock_commit_history_analyzer):
    app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
    
    async with app.run_test() as pilot:
        await pilot.press("j")  # Navigate
        await TextualAssertions.assert_text_in_screen(pilot, "Expected Text")
```

### pyte Terminal Tests
```python
@pytest.mark.asyncio
async def test_screen_layout(self, mixed_mappings, mock_commit_history_analyzer):
    analyzer = PyteScreenAnalyzer(width=80, height=24)
    
    # Feed terminal output
    analyzer.feed_terminal_output(terminal_output.encode('utf-8'))
    
    # Verify positioning
    positions = analyzer.find_text_position("Target Text")
    assert len(positions) > 0, "Text not found"
```

### Snapshot Tests
```python
async def test_ui_state(self, snap_compare, mappings, analyzer):
    app = EnhancedAutoSquashApp(mappings, analyzer)
    
    assert await snap_compare(
        app,
        terminal_size=(100, 30),
        run_before=lambda pilot: pilot.press("a")  # Setup before snapshot
    )
```

## Debugging Failed Tests

### Snapshot Failures
1. Run with `--snapshot-update` to see current output
2. Check git diff to see what changed  
3. Verify if changes are intentional
4. Update snapshots if changes are correct

### Layout Issues
1. Use pyte tests to verify exact positioning
2. Check terminal size fixtures match your expectations
3. Verify CSS changes didn't break layout

### Interaction Failures
1. Add `await pilot.pause(0.2)` for debugging
2. Use Textual devtools: `textual console` 
3. Check widget queries are finding correct elements

## Test Coverage

The test suite covers:
- ✅ All UI layouts (small/large terminals)
- ✅ User interactions (keyboard/mouse)
- ✅ State management and persistence  
- ✅ Error conditions and edge cases
- ✅ Performance with large datasets
- ✅ Accessibility (keyboard-only navigation)
- ✅ Visual regression detection
- ✅ Real-world usage patterns

## Continuous Integration

Tests run automatically on:
- Pull requests
- Main branch pushes
- Multiple operating systems (Linux, macOS, Windows)
- Multiple terminal sizes
- Performance benchmarks

Failed snapshot tests generate diff artifacts for review.
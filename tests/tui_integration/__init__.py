"""TUI Integration Test Suite.

This package contains comprehensive integration tests for the git-autosquash TUI,
including:

- Textual native integration tests
- Terminal output validation using pyte
- Visual regression testing with snapshots
- Real-world usage scenarios
- Performance and accessibility testing

Run with pytest:
    pytest tests/tui_integration/

For snapshot updates:
    pytest tests/tui_integration/ --snapshot-update

For specific test categories:
    pytest tests/tui_integration/test_enhanced_app_integration.py  # Textual tests
    pytest tests/tui_integration/test_terminal_output.py          # pyte tests
    pytest tests/tui_integration/test_snapshot_regression.py      # Snapshot tests
    pytest tests/tui_integration/test_comprehensive_scenarios.py  # Real-world scenarios
"""

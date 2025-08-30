#!/usr/bin/env python3
"""Test file for TUI testing."""


def hello():
    print("Hello Modern TUI!")
    print("Testing the new 3-panel layout")


def test_function(value=None):
    # Updated implementation with validation
    if not value:
        raise ValueError("Input required")
    return "new version with validation"


if __name__ == "__main__":
    hello()

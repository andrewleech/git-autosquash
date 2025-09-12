#!/usr/bin/env python3
"""
Realistic Git Repository Generator for Screenshots

This module creates realistic test repositories with meaningful git history
and working directory changes that demonstrate git-autosquash functionality.
"""

import tempfile
from pathlib import Path
from typing import Optional
import shutil

from git_autosquash.git_ops import GitOps


class ScreenshotTestRepo:
    """Generator for realistic test repositories used in screenshot capture."""

    def __init__(self, repo_path: Optional[Path] = None):
        """Initialize test repository generator.

        Args:
            repo_path: Optional path for repository. If None, creates temporary directory.
        """
        if repo_path is None:
            self.temp_dir: Optional[str] = tempfile.mkdtemp(
                prefix="git-autosquash-screenshots-"
            )
            self.repo_path = Path(self.temp_dir)
        else:
            self.repo_path = repo_path
            self.temp_dir = None

        self.git_ops = GitOps(self.repo_path)

    def cleanup(self) -> None:
        """Clean up temporary directory if created."""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def create_realistic_repo(self) -> Path:
        """Create a realistic Python project repository with meaningful history.

        Returns:
            Path to the created repository
        """
        # Initialize git repository
        self.git_ops.run_git_command(["init"])
        self.git_ops.run_git_command(["config", "user.name", "Demo User"])
        self.git_ops.run_git_command(["config", "user.email", "demo@example.com"])

        # Create initial project structure
        self._create_initial_project()

        # Create meaningful commit history
        self._create_commit_history()

        # Create feature branch for working changes
        self.git_ops.run_git_command(["checkout", "-b", "feature/improvements"])

        # Add a couple feature commits first
        self._add_feature_commits()

        # Add working directory changes for demonstration
        self._add_working_changes()

        return self.repo_path

    def _create_initial_project(self) -> None:
        """Create initial Python project structure."""
        # Create directories
        (self.repo_path / "src").mkdir()
        (self.repo_path / "tests").mkdir()
        (self.repo_path / "docs").mkdir()

        # Create README.md
        readme_content = """# Demo Application

A demonstration application for git-autosquash screenshots.

## Features

- User authentication
- Dashboard interface  
- Utility functions
- Comprehensive testing
"""
        (self.repo_path / "README.md").write_text(readme_content)

        # Create setup.py
        setup_content = """from setuptools import setup, find_packages

setup(
    name="demo-app",
    version="1.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
)
"""
        (self.repo_path / "setup.py").write_text(setup_content)

    def _create_commit_history(self) -> None:
        """Create meaningful commit history."""

        # Commit 1: Initial project setup
        self.git_ops.run_git_command(["add", "."])
        self.git_ops.run_git_command(["commit", "-m", "Initial project setup"])

        # Commit 2: Add authentication module
        auth_content = '''"""User authentication module."""

import hashlib
import secrets


class AuthManager:
    """Handles user authentication and session management."""
    
    def __init__(self):
        self.sessions = {}
        self.users = {
            "admin@example.com": self._hash_password("admin123"),
            "user@example.com": self._hash_password("user123"),
        }
    
    def _hash_password(self, password: str) -> str:
        """Hash password with salt."""
        salt = secrets.token_hex(16)
        return hashlib.sha256((password + salt).encode()).hexdigest() + ":" + salt
    
    def validate_login(self, email: str, password: str) -> bool:
        """Validate user login credentials."""
        if not email or not password:
            return False
        
        stored_hash = self.users.get(email)
        if not stored_hash:
            return False
            
        password_hash, salt = stored_hash.split(":")
        test_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return test_hash == password_hash
    
    def create_session(self, email: str) -> str:
        """Create a new session for authenticated user."""
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = {"email": email, "active": True}
        return session_id
    
    def logout_user(self, session_id: str) -> bool:
        """Log out user by invalidating session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
'''
        (self.repo_path / "src" / "auth.py").write_text(auth_content)

        self.git_ops.run_git_command(["add", "src/auth.py"])
        self.git_ops.run_git_command(["commit", "-m", "Add user authentication module"])

        # Commit 3: Add dashboard interface
        dashboard_content = '''"""User dashboard interface."""

from typing import Dict, List, Optional


class Dashboard:
    """Main dashboard interface for authenticated users."""
    
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.widgets = {}
    
    def get_user_data(self, session_id: str) -> Optional[Dict]:
        """Get user data for dashboard display."""
        session = self.auth_manager.sessions.get(session_id)
        if not session or not session["active"]:
            return None
        
        return {
            "email": session["email"],
            "login_count": 42,
            "last_activity": "2024-01-15 10:30:00",
            "permissions": ["read", "write"],
        }
    
    def render_stats(self, user_data: Dict) -> str:
        """Render user statistics widget."""
        if not user_data:
            return "No data available"
        
        stats = f"""
User Statistics:
- Email: {user_data['email']}
- Logins: {user_data['login_count']}
- Last Activity: {user_data['last_activity']}
- Permissions: {', '.join(user_data['permissions'])}
"""
        return stats.strip()
    
    def add_widget(self, name: str, widget_func) -> None:
        """Add a widget to the dashboard."""
        self.widgets[name] = widget_func
    
    def render_dashboard(self, session_id: str) -> str:
        """Render complete dashboard for user."""
        user_data = self.get_user_data(session_id)
        if not user_data:
            return "Please log in to view dashboard"
        
        output = [f"Dashboard for {user_data['email']}\\n"]
        output.append(self.render_stats(user_data))
        
        for name, widget in self.widgets.items():
            output.append(f"\\n{name}: {widget(user_data)}")
        
        return "\\n".join(output)
'''
        (self.repo_path / "src" / "dashboard.py").write_text(dashboard_content)

        self.git_ops.run_git_command(["add", "src/dashboard.py"])
        self.git_ops.run_git_command(["commit", "-m", "Add user dashboard interface"])

        # Commit 4: Add utility functions
        utils_content = '''"""Utility functions for the application."""

import re
import json
from typing import Any, Dict, List, Optional


def validate_email(email: str) -> bool:
    """Validate email address format."""
    if not email:
        return False
    pattern = r'^[\\w\\.-]+@[\\w\\.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS."""
    if not text:
        return ""
    
    # Basic HTML escaping
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&#x27;")
    return text


def format_response(data: Any, status: str = "success") -> Dict:
    """Format API response with consistent structure."""
    return {
        "status": status,
        "data": data,
        "timestamp": "2024-01-15T10:30:00Z"
    }


def parse_config(config_path: str) -> Dict:
    """Parse JSON configuration file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class Logger:
    """Simple logging utility."""
    
    def __init__(self, level: str = "INFO"):
        self.level = level
        self.logs = []
    
    def info(self, message: str) -> None:
        """Log info message."""
        self.logs.append(f"INFO: {message}")
    
    def error(self, message: str) -> None:
        """Log error message."""
        self.logs.append(f"ERROR: {message}")
    
    def get_logs(self) -> List[str]:
        """Get all logged messages."""
        return self.logs.copy()
'''
        (self.repo_path / "src" / "utils.py").write_text(utils_content)

        self.git_ops.run_git_command(["add", "src/utils.py"])
        self.git_ops.run_git_command(
            ["commit", "-m", "Add utility functions and logging"]
        )

        # Commit 5: Add comprehensive tests
        test_auth_content = '''"""Tests for authentication module."""

import pytest
from src.auth import AuthManager


class TestAuthManager:
    """Test cases for AuthManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.auth = AuthManager()
    
    def test_validate_login_success(self):
        """Test successful login validation."""
        result = self.auth.validate_login("admin@example.com", "admin123")
        assert result is True
    
    def test_validate_login_failure(self):
        """Test failed login validation."""
        result = self.auth.validate_login("admin@example.com", "wrong")
        assert result is False
    
    def test_validate_login_empty_credentials(self):
        """Test validation with empty credentials."""
        assert self.auth.validate_login("", "password") is False
        assert self.auth.validate_login("email", "") is False
        assert self.auth.validate_login("", "") is False
    
    def test_create_session(self):
        """Test session creation."""
        session_id = self.auth.create_session("admin@example.com")
        assert session_id is not None
        assert len(session_id) > 10
        assert session_id in self.auth.sessions
    
    def test_logout_user(self):
        """Test user logout."""
        session_id = self.auth.create_session("admin@example.com")
        result = self.auth.logout_user(session_id)
        assert result is True
        assert session_id not in self.auth.sessions
    
    def test_logout_invalid_session(self):
        """Test logout with invalid session."""
        result = self.auth.logout_user("invalid_session")
        assert result is False
'''
        (self.repo_path / "tests" / "test_auth.py").write_text(test_auth_content)

        test_utils_content = '''"""Tests for utility functions."""

import pytest
from src.utils import validate_email, sanitize_input, format_response, Logger


class TestUtilityFunctions:
    """Test cases for utility functions."""
    
    def test_validate_email_valid(self):
        """Test email validation with valid emails."""
        assert validate_email("test@example.com") is True
        assert validate_email("user.name@domain.org") is True
    
    def test_validate_email_invalid(self):
        """Test email validation with invalid emails."""
        assert validate_email("invalid-email") is False
        assert validate_email("@example.com") is False
        assert validate_email("") is False
    
    def test_sanitize_input(self):
        """Test input sanitization."""
        dangerous = "<script>alert('xss')</script>"
        safe = sanitize_input(dangerous)
        assert "<script>" not in safe
        assert "&lt;script&gt;" in safe
    
    def test_format_response(self):
        """Test API response formatting."""
        response = format_response({"key": "value"})
        assert response["status"] == "success"
        assert response["data"] == {"key": "value"}
        assert "timestamp" in response
    
    def test_logger_functionality(self):
        """Test logger functionality."""
        logger = Logger()
        logger.info("Test message")
        logger.error("Error message")
        
        logs = logger.get_logs()
        assert len(logs) == 2
        assert "INFO: Test message" in logs
        assert "ERROR: Error message" in logs
'''
        (self.repo_path / "tests" / "test_utils.py").write_text(test_utils_content)

        self.git_ops.run_git_command(["add", "tests/"])
        self.git_ops.run_git_command(["commit", "-m", "Add comprehensive test suite"])

        # Commit 6: Fix security vulnerability
        self._update_auth_security()
        self.git_ops.run_git_command(["add", "src/auth.py"])
        self.git_ops.run_git_command(
            ["commit", "-m", "Fix password validation security issue"]
        )

        # Commit 7: Add input validation
        self._update_utils_validation()
        self.git_ops.run_git_command(["add", "src/utils.py"])
        self.git_ops.run_git_command(["commit", "-m", "Add enhanced input validation"])

    def _update_auth_security(self) -> None:
        """Update auth.py with security improvements."""
        auth_file = self.repo_path / "src" / "auth.py"
        content = auth_file.read_text()

        # Fix the password validation to require minimum length
        content = content.replace(
            "if not email or not password:",
            "if not email or not password or len(password) < 8:",
        )

        auth_file.write_text(content)

    def _update_utils_validation(self) -> None:
        """Update utils.py with enhanced validation."""
        utils_file = self.repo_path / "src" / "utils.py"
        content = utils_file.read_text()

        # Add phone number validation
        new_function = '''

def validate_phone(phone: str) -> bool:
    """Validate phone number format."""
    if not phone:
        return False
    # Simple US phone number validation
    pattern = r'^\\+?1?[\\s.-]?\\(?[0-9]{3}\\)?[\\s.-]?[0-9]{3}[\\s.-]?[0-9]{4}$'
    return bool(re.match(pattern, phone))'''

        content = content.replace(
            "def parse_config(config_path: str) -> Dict:",
            f"{new_function}\n\n\ndef parse_config(config_path: str) -> Dict:",
        )

        utils_file.write_text(content)

    def _add_feature_commits(self) -> None:
        """Add some feature commits to the feature branch that can be targets for autosquash."""

        # Feature commit 1: Add configuration system
        config_content = """{
    "database": {
        "host": "localhost",
        "port": 5432,
        "name": "app_db"
    },
    "logging": {
        "level": "INFO",
        "file": "app.log"
    },
    "auth": {
        "session_timeout": 3600,
        "password_min_length": 8
    }
}"""
        config_file = self.repo_path / "config.json"
        config_file.write_text(config_content)
        self.git_ops.run_git_command(["add", "config.json"])
        self.git_ops.run_git_command(
            ["commit", "-m", "Add application configuration system"]
        )

        # Feature commit 2: Add some logging functionality
        auth_file = self.repo_path / "src" / "auth.py"
        content = auth_file.read_text()

        # Add logging import and setup
        content = content.replace(
            "import hashlib\nimport secrets",
            "import hashlib\nimport secrets\nimport logging\n\nlogger = logging.getLogger(__name__)",
        )

        # Add logging to validation function
        content = content.replace(
            "def validate_login(self, email: str, password: str) -> bool:",
            'def validate_login(self, email: str, password: str) -> bool:\n        logger.info(f"Login attempt for {email}")',
        )

        auth_file.write_text(content)
        self.git_ops.run_git_command(["add", "src/auth.py"])
        self.git_ops.run_git_command(
            ["commit", "-m", "Add logging to authentication module"]
        )

    def _add_working_changes(self) -> None:
        """Add working directory changes that demonstrate git-autosquash functionality."""

        # 1. Fix lint issues in auth.py (should target security fix commit)
        auth_file = self.repo_path / "src" / "auth.py"
        content = auth_file.read_text()

        # Add type hints and docstring improvements
        content = content.replace(
            "def validate_login(self, email: str, password: str) -> bool:",
            "def validate_login(self, email: str, password: str) -> bool:",
        )

        # Normalize email to lowercase
        content = content.replace(
            "stored_hash = self.users.get(email)",
            "stored_hash = self.users.get(email.lower().strip())",
        )

        # Add better error handling
        content = content.replace(
            "if not email or not password or len(password) < 8:",
            "if not email or not password or len(password) < 8:\n            # Enhanced validation with better error messages",
        )

        auth_file.write_text(content)

        # 2. Improve dashboard functionality (should target dashboard commit)
        dashboard_file = self.repo_path / "src" / "dashboard.py"
        content = dashboard_file.read_text()

        # Add error handling and validation
        content = content.replace(
            "def get_user_data(self, session_id: str) -> Optional[Dict]:",
            'def get_user_data(self, session_id: str) -> Optional[Dict]:\n        """Get user data with enhanced validation."""',
        )

        # Add session validation
        content = content.replace(
            'if not session or not session["active"]:',
            'if not session_id or not session or not session.get("active", False):',
        )

        # Improve stats rendering
        content = content.replace(
            "- Logins: {user_data['login_count']}",
            "- Login Count: {user_data['login_count']:,}",
        )

        dashboard_file.write_text(content)

        # 3. Add new utility functions (should target utils commit)
        utils_file = self.repo_path / "src" / "utils.py"
        content = utils_file.read_text()

        # Add a new utility function
        new_function = '''

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to specified length with ellipsis."""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"'''

        content = content.replace("class Logger:", f"{new_function}\n\n\nclass Logger:")

        utils_file.write_text(content)

        # 4. Update tests with new test cases (should target test commit)
        test_auth_file = self.repo_path / "tests" / "test_auth.py"
        content = test_auth_file.read_text()

        # Add test for email normalization
        new_test = '''
    
    def test_email_normalization(self):
        """Test that email is normalized during login."""
        result = self.auth.validate_login("  ADMIN@EXAMPLE.COM  ", "admin123")
        assert result is True'''

        content = content.replace(
            "def test_logout_invalid_session(self):",
            f"{new_test}\n\n    def test_logout_invalid_session(self):",
        )

        test_auth_file.write_text(content)

        # 5. Add a new file that has no git history (fallback scenario)
        config_content = """{
    "app_name": "Demo Application",
    "version": "1.0.0",
    "database": {
        "host": "localhost",
        "port": 5432,
        "name": "demo_app"
    },
    "features": {
        "auth_required": true,
        "dashboard_enabled": true,
        "logging_level": "INFO"
    }
}"""
        (self.repo_path / "config.json").write_text(config_content)


def create_screenshot_repository(
    output_dir: Optional[Path] = None,
) -> ScreenshotTestRepo:
    """Create a screenshot test repository.

    Args:
        output_dir: Optional directory for repository. If None, uses temp directory.

    Returns:
        ScreenshotTestRepo instance with created repository
    """
    repo = ScreenshotTestRepo(output_dir)
    repo.create_realistic_repo()
    return repo

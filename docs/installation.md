# Installation

git-autosquash is distributed as a Python package and can be installed using several methods. Choose the one that best fits your workflow.

## Requirements

- **Python 3.12 or higher**
- **Git 2.20 or higher** 
- A terminal that supports ANSI colors (most modern terminals)

## Installation Methods

### pipx (Recommended)

[pipx](https://pypa.github.io/pipx/) is the recommended way to install Python CLI tools. It creates isolated environments for each tool, avoiding dependency conflicts.

```bash
pipx install git-autosquash
```

!!! tip "Why pipx?"
    - Installs tools in isolated environments
    - Automatically adds executables to your PATH
    - Easy to upgrade and uninstall
    - No conflicts with other Python packages

### pip

If you prefer using pip directly:

```bash
pip install git-autosquash
```

!!! warning "Virtual Environment Recommended"
    If using pip, consider installing in a virtual environment to avoid conflicts:
    ```bash
    python -m venv git-autosquash-env
    source git-autosquash-env/bin/activate  # On Windows: git-autosquash-env\Scripts\activate
    pip install git-autosquash
    ```

### uv

[uv](https://github.com/astral-sh/uv) is a fast Python package manager with tool installation support:

```bash
uv tool install git-autosquash
```

### From Source

For development or latest features:

=== "Using uv (Recommended for Development)"

    ```bash
    git clone https://github.com/andrewleech/git-autosquash.git
    cd git-autosquash
    uv sync --dev
    uv run git-autosquash --help
    ```

=== "Using pip"

    ```bash
    git clone https://github.com/andrewleech/git-autosquash.git
    cd git-autosquash
    pip install -e .
    ```

## Verification

Verify your installation by running:

```bash
git-autosquash --version
```

You should see output similar to:
```
git-autosquash 1.0.0
```

Test the help system:
```bash
git-autosquash --help
```

## Git Integration

### As a Git Subcommand

You can make git-autosquash available as a git subcommand by ensuring it's in your PATH (which the installation methods above handle automatically). Then you can use:

```bash
git autosquash
```

instead of:

```bash
git-autosquash
```

### Shell Completion

=== "Bash"

    Add to your `~/.bashrc`:
    ```bash
    eval "$(register-python-argcomplete git-autosquash)"
    ```

=== "Zsh"

    Add to your `~/.zshrc`:
    ```bash
    eval "$(register-python-argcomplete git-autosquash)"
    ```

=== "Fish"

    ```bash
    register-python-argcomplete --shell fish git-autosquash > ~/.config/fish/completions/git-autosquash.fish
    ```

!!! note "argcomplete Required"
    Shell completion requires the `argcomplete` package:
    ```bash
    pipx inject git-autosquash argcomplete
    # or
    pip install argcomplete
    ```

## Dependencies

git-autosquash automatically installs these dependencies:

- **[Textual](https://textual.textualize.io/)** - Rich terminal user interface framework
- **[Rich](https://rich.readthedocs.io/)** - Rich text and beautiful formatting in the terminal

## System-Specific Notes

### macOS

On macOS, you might need to install a more recent version of Git if using the system default:

```bash
# Using Homebrew
brew install git

# Or using MacPorts  
sudo port install git
```

### Windows

git-autosquash works on Windows with:

- **Git for Windows** (includes Git Bash)
- **Windows Terminal** (recommended for best experience)
- **WSL** (Windows Subsystem for Linux)

### Linux

Most modern Linux distributions include compatible versions of Git and Python. If needed:

=== "Ubuntu/Debian"

    ```bash
    sudo apt update
    sudo apt install git python3 python3-pip
    ```

=== "CentOS/RHEL/Fedora"

    ```bash
    sudo dnf install git python3 python3-pip
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S git python python-pip
    ```

## Upgrading

### pipx
```bash
pipx upgrade git-autosquash
```

### pip
```bash
pip install --upgrade git-autosquash
```

### uv
```bash
uv tool upgrade git-autosquash
```

## Uninstallation

### pipx
```bash
pipx uninstall git-autosquash
```

### pip
```bash
pip uninstall git-autosquash
```

### uv
```bash
uv tool uninstall git-autosquash
```

## Troubleshooting

### Command Not Found

If you get "command not found" after installation:

1. **Check your PATH**: The installation location should be in your PATH
2. **Restart your terminal**: Changes to PATH may require a new terminal session
3. **Verify installation**: Run `pip list | grep git-autosquash` to confirm it's installed

### Permission Errors

If you encounter permission errors:

1. **Use pipx instead of pip**: pipx handles permissions automatically
2. **Use virtual environments**: Avoid system-wide pip installations
3. **Check directory permissions**: Ensure you can write to the installation directory

### Import Errors

If you see import errors about missing modules:

1. **Check Python version**: Ensure you're using Python 3.12 or higher
2. **Verify installation**: Reinstall with `pip install --force-reinstall git-autosquash`
3. **Check dependencies**: All dependencies should install automatically

For more troubleshooting help, see our [Troubleshooting Guide](user-guide/troubleshooting.md).
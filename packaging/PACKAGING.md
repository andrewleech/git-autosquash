# Packaging Guide for Downstream Maintainers

This guide helps distribution package maintainers integrate git-autosquash into their package ecosystems.

## Man Page Integration

git-autosquash includes a man page (`man/git-autosquash.1`) that should be installed to the standard system location for your distribution.

### Extracting Man Page from Wheel

The man page is included in the Python wheel at `share/man/man1/git-autosquash.1`:

```bash
# Extract man page from wheel
unzip -j git_autosquash-*.whl 'share/man/man1/git-autosquash.1' -d /tmp/
```

### Debian/Ubuntu (.deb)

**Recommended approach:** Use `dh_installman` helper in `debian/rules`:

```makefile
# debian/rules
override_dh_auto_install:
	python3 -m pip install --root=$(CURDIR)/debian/git-autosquash .
	# Extract man page from wheel
	unzip -j dist/git_autosquash-*.whl 'share/man/man1/git-autosquash.1' \
		-d $(CURDIR)/debian/git-autosquash/usr/share/man/man1/
	gzip -9n $(CURDIR)/debian/git-autosquash/usr/share/man/man1/git-autosquash.1
```

**Alternative:** Create `debian/manpages` file:

```
# debian/manpages
man/git-autosquash.1
```

Then `dh_installman` will automatically install and compress it.

**Installation location:** `/usr/share/man/man1/git-autosquash.1.gz`

### Fedora/RHEL (.rpm)

**Spec file example:**

```spec
%install
%{__python3} -m pip install --root %{buildroot} .

# Install man page
install -Dpm 0644 man/git-autosquash.1 %{buildroot}%{_mandir}/man1/git-autosquash.1
gzip %{buildroot}%{_mandir}/man1/git-autosquash.1

%files
%{python3_sitelib}/git_autosquash/
%{python3_sitelib}/git_autosquash-*.dist-info/
%{_bindir}/git-autosquash
%{_mandir}/man1/git-autosquash.1.gz
```

**Installation location:** `/usr/share/man/man1/git-autosquash.1.gz`

### Arch Linux (PKGBUILD)

**PKGBUILD example:**

```bash
build() {
    cd "$srcdir/$pkgname-$pkgver"
    python -m build --wheel --no-isolation
}

package() {
    cd "$srcdir/$pkgname-$pkgver"
    python -m installer --destdir="$pkgdir" dist/*.whl

    # Install man page
    install -Dm644 man/git-autosquash.1 "$pkgdir/usr/share/man/man1/git-autosquash.1"
}
```

**Installation location:** `/usr/share/man/man1/git-autosquash.1`

Note: Arch does not compress man pages by default (as of 2025).

### Homebrew (.rb formula)

**Formula example:**

```ruby
class GitAutosquash < Formula
  desc "Automatically squash git changes back into historical commits"
  homepage "https://github.com/andrewleech/git-autosquash"
  url "https://files.pythonhosted.org/packages/.../git-autosquash-X.Y.Z.tar.gz"
  sha256 "..."

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources

    # Install man page
    man1.install "man/git-autosquash.1"
  end

  test do
    system bin/"git-autosquash", "--help"
    system "man", man1/"git-autosquash.1"
  end
end
```

**Installation location:** `#{HOMEBREW_PREFIX}/share/man/man1/git-autosquash.1`

### Gentoo (.ebuild)

**Ebuild example:**

```bash
EAPI=8

PYTHON_COMPAT=( python3_{12..13} )
DISTUTILS_USE_PEP517=hatchling

inherit distutils-r1

DESCRIPTION="Automatically squash git changes back into historical commits"
HOMEPAGE="https://github.com/andrewleech/git-autosquash"

LICENSE="MIT"
SLOT="0"

python_install_all() {
    distutils-r1_python_install_all

    # Install man page
    doman man/git-autosquash.1
}
```

**Installation location:** `/usr/share/man/man1/git-autosquash.1`

### NixOS (nix expression)

**Nix expression example:**

```nix
{ lib
, python3Packages
, fetchFromGitHub
}:

python3Packages.buildPythonApplication rec {
  pname = "git-autosquash";
  version = "X.Y.Z";
  format = "pyproject";

  src = fetchFromGitHub {
    owner = "andrewleech";
    repo = "git-autosquash";
    rev = "v${version}";
    hash = "sha256-...";
  };

  nativeBuildInputs = with python3Packages; [
    hatchling
    hatch-vcs
  ];

  propagatedBuildInputs = with python3Packages; [
    textual
    typer
  ];

  postInstall = ''
    installManPage man/git-autosquash.1
  '';

  meta = with lib; {
    description = "Automatically squash git changes back into historical commits";
    homepage = "https://github.com/andrewleech/git-autosquash";
    license = licenses.mit;
    maintainers = with maintainers; [ ];
  };
}
```

**Installation location:** `/nix/store/.../share/man/man1/git-autosquash.1`

## Dependencies

### Runtime Dependencies

- Python >= 3.12
- textual >= 5.3.0
- typer[all] >= 0.12.0

### Build Dependencies

- hatchling
- hatch-vcs (for version from git tags)

### Optional Dependencies

None (all dependencies are required for runtime).

## Build System

git-autosquash uses PEP 517 build system with hatchling backend:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"
```

**Build command:**

```bash
python -m build --wheel --no-isolation
```

**Version determination:** Version is automatically determined from git tags using `hatch-vcs`.

## Testing

Run tests with pytest:

```bash
pytest tests/
```

**Test dependencies:**
- pytest >= 8.4.1
- pytest-asyncio >= 0.23.0
- pytest-mock >= 3.12.0
- pytest-textual-snapshot >= 1.0.0

## Entry Point

Console script: `git-autosquash` → `git_autosquash.main:main`

## License

MIT License - See LICENSE file in repository.

## Contact

- Repository: https://github.com/andrewleech/git-autosquash
- Issues: https://github.com/andrewleech/git-autosquash/issues
- Author: Andrew Leech <andrew.leech@planetinnovation.com.au>

## Notes for Packagers

1. **Man page compression:** Most distributions gzip man pages. Compress to `.gz` unless your distribution has different conventions (e.g., Arch doesn't compress).

2. **Man page updates:** The man page is updated in sync with CLI changes. When updating the package, always include the latest man page.

3. **Verification:** Test that the man page installs correctly:
   ```bash
   man git-autosquash
   ```

4. **pipx compatibility:** The wheel includes man page at `share/man/man1/git-autosquash.1`. This allows pipx to automatically install it when users run `pipx install git-autosquash`.

5. **Build from source:** If building from git checkout instead of release tarball, ensure git tags are available for `hatch-vcs` to determine version, or set version manually with `SETUPTOOLS_SCM_PRETEND_VERSION=X.Y.Z`.

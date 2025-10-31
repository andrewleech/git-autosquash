# Man Page Implementation Plan for git-autosquash

## Executive Summary

This plan details implementation of a man page for git-autosquash following standard git man page conventions. The implementation consists of two main components: (1) creating the man page content in troff format, and (2) integrating automatic installation into the Python package build process.

## Research Findings

### Git Man Page Format

Git man pages use the following toolchain:
1. **Source Format**: DocBook XML generated from AsciiDoc
2. **Final Format**: Groff/troff (.1 files) compressed with gzip
3. **Installation**: `/usr/share/man/man1/git-*.1.gz`
4. **Generator**: DocBook XSL Stylesheets

Standard git man page structure (from git-commit.1.gz header):
```troff
.TH "GIT\-AUTOSQUASH" "1" "date" "Git 2\&.43\&.0" "Git Manual"
.SH "NAME"
git-autosquash \- Brief description
.SH "SYNOPSIS"
.SH "DESCRIPTION"
.SH "OPTIONS"
.SH "EXAMPLES"
.SH "SEE ALSO"
.SH "GIT"
```

Key formatting conventions observed:
- `.TH` = Title header (command name, section, date, version, manual)
- `.SH` = Section header
- `.PP` = Paragraph
- `.RS 4` / `.RE` = Indent/outdent blocks
- `\fB` / `\fR` = Bold formatting
- `\fI` / `\fR` = Italic formatting
- `\-` = Escaped hyphen (prevents line break)

### Python Package Man Page Installation

Three approaches identified:

#### Approach 1: setuptools data_files (Traditional, Limited)
```toml
[tool.setuptools.data-files]
"share/man/man1" = ["man/git-autosquash.1"]
```

**Limitations:**
- No guarantee of installation to `/usr/share/man` (often installs to virtualenv)
- Not platform-independent (forces man pages on Windows)
- Deprecated in modern setuptools
- RPM packagers may auto-compress, causing conflicts

#### Approach 2: typer-man (For Typer CLIs)
Since git-autosquash uses Typer (not Click), we cannot use click-man. However, there is no equivalent typer-man tool available as of 2025.

#### Approach 3: Manual Troff + External Installation (Recommended)
Write man page in troff format and rely on distribution-specific packaging:
- Include man page source in repository (`man/git-autosquash.1`)
- Document manual installation in README
- Allow downstream package maintainers (apt, rpm, brew) to handle installation

## Recommended Implementation

### Phase 1: Create Man Page Source

**File:** `man/git-autosquash.1` (uncompressed troff)

**Content structure:**
```troff
.TH "GIT-AUTOSQUASH" "1" "2025-10-31" "git-autosquash 1.0.0" "Git Manual"
.SH "NAME"
git-autosquash \- Automatically squash git changes back into historical commits
.SH "SYNOPSIS"
.nf
\fIgit autosquash\fR [OPTIONS]
.fi
.SH "DESCRIPTION"
Interactive tool for squashing uncommitted changes (from working directory or index)
back into their logical source commits...
.SH "OPTIONS"
.PP
\fB\-i\fR, \fB\-\-interactive\fR
.RS 4
Launch interactive TUI for reviewing and approving hunks before squashing.
.RE
.PP
\fB\-n\fR, \fB\-\-dry\-run\fR
.RS 4
Show what would be done without making any changes...
.RE
...
.SH "EXAMPLES"
.PP
Review and squash all uncommitted changes interactively:
.RS 4
$ git autosquash \-i
.RE
...
.SH "SEE ALSO"
\fBgit-rebase\fR(1), \fBgit-commit\fR(1), \fBgit-add\fR(1)
.SH "GIT"
Part of the \fBgit\fR(1) suite
```

**Sections to include:**
1. **NAME** - One-line description
2. **SYNOPSIS** - Command syntax with all flags
3. **DESCRIPTION** - Overview of tool functionality
   - Mention split-commit approach
   - Explain validation framework
   - Describe 3-way merge handling
4. **OPTIONS** - All CLI flags with descriptions
   - `-i, --interactive`: Launch TUI
   - `-n, --dry-run`: Preview mode
   - `-v, --verbose`: Debug output
   - `--source COMMIT`: Squash specific commit
   - `--version`: Show version
   - `-h, --help`: Show help
5. **EXAMPLES** - Common use cases
   - Interactive squash: `git autosquash -i`
   - Auto-accept all: `git autosquash`
   - Dry-run preview: `git autosquash -n`
   - Squash specific commit: `git autosquash --source abc123`
   - Verbose debugging: `git autosquash -v -i`
6. **HOW IT WORKS** - Algorithm overview (6-step process)
7. **VALIDATION** - Safety mechanisms
8. **EXIT STATUS** - Return codes (0=success, 1=error)
9. **SEE ALSO** - Related git commands
10. **GIT** - "Part of the git(1) suite"

### Phase 2: Manual Installation Documentation

**Update README.md with manual installation section:**

```markdown
## Man Page Installation

The man page can be installed manually:

```bash
# System-wide installation (requires root)
sudo cp man/git-autosquash.1 /usr/share/man/man1/
sudo gzip /usr/share/man/man1/git-autosquash.1
sudo mandb  # Update man database

# User-local installation (no root required)
mkdir -p ~/.local/share/man/man1
cp man/git-autosquash.1 ~/.local/share/man/man1/
gzip ~/.local/share/man/man1/git-autosquash.1
mandb -u ~/.local/share/man  # Update user man database
```

View the man page:
```bash
man git-autosquash
```
```

### Phase 3: Distribution Integration

**Create distribution packaging hints:**

**File:** `packaging/PACKAGING.md`

Document how downstream packagers should integrate:

1. **Debian/Ubuntu (.deb)**
   ```
   Install to: /usr/share/man/man1/git-autosquash.1.gz
   Use dh_installman helper in debian/rules
   ```

2. **Fedora/RHEL (.rpm)**
   ```
   %install section:
   install -Dpm 0644 man/git-autosquash.1 %{buildroot}%{_mandir}/man1/git-autosquash.1
   gzip %{buildroot}%{_mandir}/man1/git-autosquash.1
   ```

3. **Homebrew (.rb formula)**
   ```ruby
   def install
     man1.install "man/git-autosquash.1"
   end
   ```

4. **Arch Linux (PKGBUILD)**
   ```
   install -Dm644 man/git-autosquash.1 "$pkgdir/usr/share/man/man1/git-autosquash.1"
   ```

## Implementation Timeline

**Estimated effort: 4-6 hours**

1. **Write man page content** (3-4 hours)
   - Draft all sections
   - Test rendering with `man -l man/git-autosquash.1`
   - Validate troff syntax with `groff -man -Tascii man/git-autosquash.1`

2. **Update documentation** (1 hour)
   - Add manual installation section to README.md
   - Create packaging/PACKAGING.md for downstream maintainers
   - Update CLAUDE.md with man page maintenance notes

3. **Validation** (1 hour)
   - Test manual installation (system-wide and user-local)
   - Verify `man git-autosquash` displays correctly
   - Check formatting across different terminal widths
   - Validate cross-references to other git man pages work

## Rationale for Manual Installation Approach

1. **Virtualenv isolation**: Python-based installation (data_files) often installs to virtualenv, not system-wide `/usr/share/man`
2. **Platform independence**: Avoids forcing Unix man pages on Windows users
3. **Packaging flexibility**: Downstream packagers can handle compression, location, and integration
4. **Standard practice**: Many Python CLI tools (e.g., git-lfs, hub) use this approach
5. **Simplicity**: No build-time dependencies on man page generation tools

## Testing Checklist

Before considering implementation complete:

- [ ] Man page renders correctly: `man -l man/git-autosquash.1`
- [ ] Troff syntax validates: `groff -man -Tascii man/git-autosquash.1 | less`
- [ ] Manual system-wide installation works
- [ ] Manual user-local installation works
- [ ] `man git-autosquash` displays after installation
- [ ] Cross-references to git-rebase, git-commit work
- [ ] Formatting looks correct at 80 cols and 120 cols
- [ ] All CLI flags documented and match `--help` output
- [ ] Examples are accurate and tested

## Future Enhancements (Optional)

1. **HTML generation**: `groff -man -Thtml man/git-autosquash.1 > docs/man.html`
2. **PDF generation**: `groff -man -Tpdf man/git-autosquash.1 > docs/man.pdf`
3. **AsciiDoc source**: Migrate to AsciiDoc for easier editing (like git core)
4. **Automated testing**: CI check to ensure man page stays in sync with CLI flags
5. **Version automation**: Script to update version/date in man page from git tags

## References

- Git man page source (DocBook XML): https://github.com/git/git/tree/master/Documentation
- Groff man page format: `man 7 groff_man`
- Example git man pages: `/usr/share/man/man1/git-*.1.gz`
- Setuptools data_files: https://setuptools.pypa.io/en/latest/userguide/datafiles.html
- Man page format guide: https://www.linuxjournal.com/article/1158

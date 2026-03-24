# Installation

## Requirements

- Python 3.8 or later
- pip

## Install from Source

```bash
git clone https://github.com/zvorky/jatai.git
cd jatai
python3 -m venv venv
. venv/bin/activate
pip install -e .
```

## Verify Installation

```bash
jatai --help
```

## Recommended .gitignore Entries

Add these to your project's `.gitignore` to avoid committing Jataí artifacts:

```gitignore
# Jataí
INBOX/
OUTBOX/
# .jatai  (uncomment if you don't want to share node config)
```

## Uninstall

```bash
pip uninstall jatai
```

To remove the daemon auto-start entry, delete the generated service file
(location printed during `jatai start`).

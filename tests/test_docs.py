import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jatai.cli.main import app

runner = CliRunner()

def get_markdown_files():
    docs_dir = Path("docs")
    files = list(docs_dir.rglob("*.md"))
    readme = Path("README.md")
    if readme.exists():
        files.append(readme)
    return files

@pytest.mark.parametrize("md_file", get_markdown_files())
def test_cli_snippets_in_markdown(md_file):
    content = md_file.read_text(encoding="utf-8")
    blocks = re.findall(r'```(?:bash|sh|console)?\n(.*?)\n```', content, re.DOTALL)
    for block in blocks:
        for line in block.split('\n'):
            line = line.strip().split('#')[0].strip() # remove comments
            if line.startswith('$ '):
                line = line[2:]
            
            if line.startswith('jatai '):
                parts = line.split()
                if len(parts) > 1:
                    cmd = parts[1]
                    if cmd.startswith(('-', '.')):
                        continue
                    
                    result = runner.invoke(app, [cmd, "--help"])
                    if result.exit_code == 2:
                        pytest.fail(f"Invalid CLI command snippet found in {md_file.name}: {line}")

    assert True

"""skill command - install the scip-cli skill file."""
import sys
from pathlib import Path


def main(args):
    """Dump or install the scip-cli SKILL.md."""
    skill_path = Path(__file__).parent.parent / "SKILL.md"

    if not skill_path.exists():
        print("Error: SKILL.md not found in package", file=sys.stderr)
        sys.exit(1)

    content = skill_path.read_text()

    if args.path:
        # Write to file, creating parent directories
        target = Path(args.path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        print(f"Installed skill to {target}", file=sys.stderr)
    else:
        # Print to stdout
        print(content)

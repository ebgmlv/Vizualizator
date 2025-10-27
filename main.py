import argparse
import os
import sys
from urllib.parse import urlparse


def validate_package_name(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("Package name cannot be empty.")
    return name.strip()


def validate_version(version: str) -> str:
    if not version or not version.strip():
        raise ValueError("Version cannot be empty.")
    if any(c in version for c in " <>|;&"):
        raise ValueError("Version contains invalid characters.")
    return version.strip()


def validate_output_file(filename: str) -> str:
    if not filename or not filename.strip():
        raise ValueError("Output filename cannot be empty.")
    valid_exts = {'.png', '.svg', '.pdf', '.jpg', '.jpeg', '.dot'}
    _, ext = os.path.splitext(filename)
    if ext.lower() not in valid_exts:
        raise ValueError(f"Unsupported output file extension: {ext}. Supported: {', '.join(valid_exts)}")
    return filename.strip()


def validate_repo_path_or_url(path_or_url: str, mode: str) -> str:
    if not path_or_url or not path_or_url.strip():
        raise ValueError("Repository path or URL cannot be empty.")
    s = path_or_url.strip()
    if mode == "test":
        return s
    parsed = urlparse(s)
    if parsed.scheme in ('http', 'https', 'file'):
        if parsed.scheme in ('http', 'https') and not parsed.netloc:
            raise ValueError("Invalid URL format.")
        return s
    else:
        if not os.path.exists(s):
            raise ValueError(f"Local repository path does not exist: {s}")
        return s


def validate_mode(mode: str) -> str:
    allowed_modes = {'online', 'offline', 'test'}
    if mode not in allowed_modes:
        raise ValueError(f"Mode must be one of: {', '.join(allowed_modes)}")
    return mode


def main():
    parser = argparse.ArgumentParser(
        description="Visualize package dependency graph (Stage 1: Configurable CLI prototype)."
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Name of the package to analyze."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="URL or local path to the test repository."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["online", "offline", "test"],
        help="Repository access mode."
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Version of the package."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output filename for the dependency graph image (e.g., graph.png)."
    )

    try:
        args = parser.parse_args()

        # Validate and normalize inputs
        package = validate_package_name(args.package)
        version = validate_version(args.version)
        output = validate_output_file(args.output)
        repo = validate_repo_path_or_url(args.repo, args.mode)
        mode = validate_mode(args.mode)

        print("Configuration:")
        print(f"  package: {package}")
        print(f"  version: {version}")
        print(f"  repo: {repo}")
        print(f"  mode: {mode}")
        print(f"  output: {output}")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
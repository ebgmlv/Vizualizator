import argparse
import os
import sys
import urllib.request
import urllib.error
from urllib.parse import urlparse, quote
import xml.etree.ElementTree as ET


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
    if parsed.scheme in ('http', 'https'):
        if not parsed.netloc:
            raise ValueError("Invalid URL format.")
        return s
    elif parsed.scheme == 'file':
        local_path = parsed.path
        if not os.path.exists(local_path):
            raise ValueError(f"Local repository path does not exist: {local_path}")
        return local_path
    else:
        if os.path.exists(s):
            return s
        else:
            raise ValueError(f"Local repository path does not exist: {s}")


def validate_mode(mode: str) -> str:
    allowed_modes = {'online', 'offline', 'test'}
    if mode not in allowed_modes:
        raise ValueError(f"Mode must be one of: {', '.join(allowed_modes)}")
    return mode


def fetch_nuspec_url(package: str, version: str, base_repo_url: str) -> str:
    """
    Construct .nuspec URL for NuGet flat container layout.
    Assumes base_repo_url ends with '/v3-flatcontainer' or similar.
    If base_repo_url is generic (e.g., https://api.nuget.org/v3/index.json),
    we override to known flat container endpoint for simplicity.
    """
    # For simplicity, assume public nuget flat container format if user provides nuget.org-like URL
    # Otherwise, expect user to provide exact flatcontainer base
    lower_pkg = package.lower()
    encoded_pkg = quote(lower_pkg)
    encoded_ver = quote(version)
    # Try to auto-construct for known public repo
    if 'nuget.org' in base_repo_url:
        return f"https://api.nuget.org/v3-flatcontainer/{encoded_pkg}/{encoded_ver}/{encoded_pkg}.nuspec"
    else:
        # Assume base_repo_url is already the flatcontainer base
        if not base_repo_url.endswith('/'):
            base_repo_url += '/'
        return f"{base_repo_url}{encoded_pkg}/{encoded_ver}/{encoded_pkg}.nuspec"


def fetch_nuspec_content(url: str) -> str:
    try:
        with urllib.request.urlopen(url) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}: Failed to fetch .nuspec")
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Package or version not found: {url}")
        else:
            raise ValueError(f"HTTP error {e.code} while fetching .nuspec")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {e.reason}")
    except Exception as e:
        raise ValueError(f"Failed to fetch .nuspec: {e}")


def parse_dependencies_from_nuspec(nuspec_xml: str) -> list[tuple[str, str]]:
    try:
        root = ET.fromstring(nuspec_xml)
        # Register namespace or handle it manually
        # NuGet .nuspec uses namespace: http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd
        ns = {'ns': 'http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd'}
        deps = []
        for dep in root.findall('.//ns:dependency', ns):
            dep_id = dep.get('id')
            dep_version = dep.get('version', '*')
            if dep_id:
                deps.append((dep_id, dep_version))
        return deps
    except ET.ParseError as e:
        raise ValueError(f"Invalid .nuspec XML: {e}")


def fetch_dependencies(package: str, version: str, repo_url: str, mode: str) -> list[tuple[str, str]]:
    if mode != "online":
        # Placeholder for offline/test modes (not implemented in Stage 2)
        print("(Dependencies not fetched: only 'online' mode is supported in Stage 2)")
        return []

    nuspec_url = fetch_nuspec_url(package, version, repo_url)
    nuspec_content = fetch_nuspec_content(nuspec_url)
    dependencies = parse_dependencies_from_nuspec(nuspec_content)
    return dependencies


def main():
    parser = argparse.ArgumentParser(
        description="Visualize package dependency graph (Stage 2: Dependency data collection)."
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
        print()

        # Stage 2: Fetch and display direct dependencies
        dependencies = fetch_dependencies(package, version, repo, mode)

        print("Direct dependencies:")
        if dependencies:
            for dep_id, dep_ver in dependencies:
                print(f"  - {dep_id} ({dep_ver})")
        else:
            print("  (none)")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
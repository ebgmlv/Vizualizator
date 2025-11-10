import argparse
import os
import sys
import urllib.request
import urllib.error
from urllib.parse import urlparse, quote
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Tuple


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
        if not os.path.isfile(s):
            raise ValueError(f"Test repository file does not exist: {s}")
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


# ========== Online mode helpers (Stage 2 logic, limited to 1 level for simplicity) ==========
def fetch_nuspec_url(package: str, version: str, base_repo_url: str) -> str:
    lower_pkg = package.lower()
    encoded_pkg = quote(lower_pkg)
    encoded_ver = quote(version)
    if 'nuget.org' in base_repo_url:
        return f"https://api.nuget.org/v3-flatcontainer/{encoded_pkg}/{encoded_ver}/{encoded_pkg}.nuspec"
    else:
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


def parse_dependencies_from_nuspec(nuspec_xml: str) -> List[Tuple[str, str]]:
    try:
        root = ET.fromstring(nuspec_xml)
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


# ========== Test mode helpers ==========
def load_test_repo(file_path: str) -> Dict[str, List[str]]:
    """Load test repository from file. Keys are package names (uppercase letters)."""
    repo = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' not in line:
                    raise ValueError(f"Invalid format in test repo (line {line_num}): missing ':'")
                pkg, deps_part = line.split(':', 1)
                pkg = pkg.strip()
                if not pkg:
                    raise ValueError(f"Empty package name in test repo (line {line_num})")
                if not pkg.isupper() or not pkg.isalpha():
                    raise ValueError(f"Package name must be uppercase Latin letters (line {line_num}): {pkg}")
                deps = deps_part.split()
                deps = [d.strip() for d in deps if d.strip()]
                for d in deps:
                    if not d.isupper() or not d.isalpha():
                        raise ValueError(f"Dependency must be uppercase Latin letter (line {line_num}): {d}")
                repo[pkg] = deps
        return repo
    except OSError as e:
        raise ValueError(f"Cannot read test repository file: {e}")


# ========== Graph building with DFS ==========
def build_dependency_graph_dfs(
    start_pkg: str,
    repo: Dict[str, List[str]],
    visited: Set[str],
    path: List[str],
    graph: Dict[str, List[str]],
    cycles: List[List[str]]
) -> None:
    """
    Recursive DFS to build full dependency graph and detect cycles.
    - repo: dict mapping package -> list of direct dependencies
    - visited: global visited set (for avoiding reprocessing)
    - path: current DFS path (for cycle detection)
    - graph: output graph being built
    - cycles: list to collect detected cycles (as lists of nodes)
    """
    if start_pkg in visited:
        return
    if start_pkg not in repo:
        # Treat missing package as leaf (no deps)
        graph[start_pkg] = []
        visited.add(start_pkg)
        return

    # Detect cycle
    if start_pkg in path:
        cycle_start_index = path.index(start_pkg)
        cycle = path[cycle_start_index:] + [start_pkg]
        cycles.append(cycle)
        # Still continue building, but don't recurse further to avoid infinite loop
        graph[start_pkg] = repo[start_pkg]
        visited.add(start_pkg)
        return

    visited.add(start_pkg)
    path.append(start_pkg)
    deps = repo[start_pkg]
    graph[start_pkg] = deps[:]  # copy

    for dep in deps:
        build_dependency_graph_dfs(dep, repo, visited, path, graph, cycles)

    path.pop()


def get_full_dependency_graph_test(test_repo: Dict[str, List[str]], root: str) -> Tuple[Dict[str, List[str]], List[List[str]]]:
    visited = set()
    path = []
    graph = {}
    cycles = []
    build_dependency_graph_dfs(root, test_repo, visited, path, graph, cycles)
    return graph, cycles


# ========== Main ==========
def main():
    parser = argparse.ArgumentParser(
        description="Visualize package dependency graph (Stage 3: Full dependency graph with DFS and cycle detection)."
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Name of the package to analyze."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="URL (online) or path to test repository file (test mode)."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["online", "offline", "test"],
        help="Repository access mode."
    )
    parser.add_argument(
        "--version",
        required=False,  # Optional in test mode
        help="Version of the package (required in online mode)."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output filename for the dependency graph image (e.g., graph.png)."
    )

    try:
        args = parser.parse_args()

        # Validate common args
        package = validate_package_name(args.package)
        output = validate_output_file(args.output)
        mode = validate_mode(args.mode)

        if mode == "online":
            if not args.version:
                raise ValueError("Version is required in 'online' mode.")
            version = validate_version(args.version)
            repo = validate_repo_path_or_url(args.repo, mode)
            print("Configuration:")
            print(f"  package: {package}")
            print(f"  version: {version}")
            print(f"  repo: {repo}")
            print(f"  mode: {mode}")
            print(f"  output: {output}")
            print()
            # For Stage 3, online mode only shows direct deps (as in Stage 2)
            # Full transitive resolution is complex due to versioning — out of scope here
            print("Direct dependencies (online mode, transitive resolution not implemented):")
            nuspec_url = fetch_nuspec_url(package, version, repo)
            nuspec_content = fetch_nuspec_content(nuspec_url)
            deps = parse_dependencies_from_nuspec(nuspec_content)
            for dep_id, dep_ver in deps:
                print(f"  - {dep_id} ({dep_ver})")

        elif mode == "test":
            # In test mode, version is ignored
            repo_path = validate_repo_path_or_url(args.repo, mode)
            print("Configuration:")
            print(f"  package: {package}")
            print(f"  repo: {repo_path}")
            print(f"  mode: {mode}")
            print(f"  output: {output}")
            print()

            if not (package.isupper() and package.isalpha()):
                raise ValueError("In test mode, package name must be uppercase Latin letters.")

            test_repo = load_test_repo(repo_path)
            full_graph, cycles = get_full_dependency_graph_test(test_repo, package)

            print("Full dependency graph (transitive):")
            for pkg in sorted(full_graph.keys()):
                deps = full_graph[pkg]
                print(f"  {pkg}: {' '.join(deps) if deps else '(none)'}")

            if cycles:
                print("\n⚠️  Detected cyclic dependencies:")
                for i, cycle in enumerate(cycles, 1):
                    print(f"  Cycle {i}: {' → '.join(cycle)}")
            else:
                print("\n✅ No cycles detected.")

        else:  # offline
            print("Configuration:")
            print(f"  package: {package}")
            print(f"  repo: {args.repo}")
            print(f"  mode: {mode}")
            print(f"  output: {output}")
            print()
            print("(Offline mode not implemented in Stage 3)")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
import argparse
import fcntl
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from tempfile import mkdtemp
from zipfile import BadZipFile

from sdk_inputs import INSTALLER_SCRIPT, NDK_PACKAGE, prepare_inputs, prepare_ndk

SCRIPTS = Path(__file__).resolve().parent


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value or "\n" in value or "\r" in value:
        raise ValueError(f"Set {name} to a single nonempty value")
    return value


def install_packages(
    destination: Path,
    packages: list[str],
    *,
    add: bool = False,
) -> None:
    inputs = destination.parent / "inputs"
    feed = inputs / "sdk/feed"
    if NDK_PACKAGE in packages:
        prepare_ndk(feed)
    arguments: list[str | Path] = [
        sys.executable,
        inputs / INSTALLER_SCRIPT,
        "--destination",
        destination,
        "--feed",
        feed,
        "--jdk",
        inputs / "jdk",
        "--manager",
        inputs / "bootstrap/cmdline-tools",
    ]
    if add:
        arguments.append("--add")
    subprocess.run([*arguments, "--", *packages], check=True)


def append_runner_file(name: str, values: list[str]) -> None:
    with Path(required_environment(name)).open("a", encoding="utf-8") as output:
        for value in values:
            if "\n" in value or "\r" in value:
                raise ValueError(f"Cannot export a multiline path through {name}")
            output.write(f"{value}\n")


def setup() -> None:
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise ValueError("The AOSStudio SDK Release targets Linux x86-64")
    if shutil.which("bwrap") is None:
        raise ValueError("Bubblewrap (bwrap) must be installed on the runner")
    run_directory = Path(required_environment("RUNNER_TEMP")).resolve(strict=True)
    for name in ("GITHUB_ENV", "GITHUB_PATH", "GITHUB_OUTPUT"):
        required_environment(name)
    version = os.environ.get("AOS_SDK_CMDLINE_VERSION", "").strip()
    if version and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
        raise ValueError("Malformed Command-Line Tools version")
    packages = os.environ.get("AOS_SDK_PACKAGES", "platform-tools").split()
    if "tools" in packages:
        print("Skipping obsolete SDK package 'tools'", file=sys.stderr)
    state = Path(mkdtemp(prefix="aos-sdk-", dir=run_directory))
    sdk = state / "sdk"
    try:
        inputs = state / "inputs"
        prepare_inputs(inputs)
        if not version:
            defaults = subprocess.check_output(
                [sys.executable, inputs / INSTALLER_SCRIPT, "--default-packages"],
                text=True,
            )
            (default_cli,) = (
                package
                for package in defaults.splitlines()
                if package.startswith("cmdline-tools;")
            )
            version = default_cli.removeprefix("cmdline-tools;")
        requested = [f"cmdline-tools;{version}", *(x for x in packages if x != "tools")]
        install_packages(sdk, requested)
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        tarfile.TarError,
        BadZipFile,
    ):
        shutil.rmtree(state)
        raise
    tools = sdk / "cmdline-tools" / version / "bin"
    append_runner_file(
        "GITHUB_ENV",
        [
            f"ANDROID_HOME={sdk}",
            f"ANDROID_SDK_ROOT={sdk}",
            f"AOS_SDK_MANAGED_ROOT={sdk}",
            f"AOS_SDK_INSTALLED_CLI={version}",
        ],
    )
    append_runner_file(
        "GITHUB_PATH", [str(tools), str(sdk / "platform-tools"), str(SCRIPTS / "bin")]
    )
    append_runner_file(
        "GITHUB_OUTPUT", [f"ANDROID_COMMANDLINE_TOOLS_VERSION={version}"]
    )


def manage(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="sdkmanager", description="Install SDK packages."
    )
    command = parser.add_mutually_exclusive_group()
    command.add_argument("--install", action="store_true")
    command.add_argument("--version", action="store_true")
    parser.add_argument("--sdk_root", type=Path)
    parser.add_argument("packages", nargs="*")
    options = parser.parse_args(arguments)
    sdk = Path(required_environment("AOS_SDK_MANAGED_ROOT")).resolve(strict=True)
    if options.sdk_root is not None and options.sdk_root.resolve() != sdk:
        raise ValueError(f"SDK package manager is configured for {sdk}")
    if options.version and not options.packages:
        print(required_environment("AOS_SDK_INSTALLED_CLI"))
        return
    if options.version or not options.packages:
        parser.error("Specify one or more packages to install")
    with (sdk.parent / "install.lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        install_packages(sdk, options.packages, add=True)


def main() -> int:
    try:
        if sys.argv[1:] == ["setup"]:
            setup()
        elif sys.argv[1:2] == ["manage"]:
            manage(sys.argv[2:])
        else:
            raise ValueError("Use the setup action or sdkmanager")
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        tarfile.TarError,
        BadZipFile,
    ) as error:
        print(f"SDK setup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

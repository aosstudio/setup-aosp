import json
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from zipfile import ZipFile

NIGHTLY_ASSETS = {
    "sdk": "aosstudio-sdk-37.0-linux-x86_64.tar.gz",
    "jdk": "aosstudio-jdk-21.0.13.1-2-linux-x86_64.tar.gz",
}
INSTALLER_COMMIT = "fb3dde149b8c43eb1a81a1075ad92b5b353a3d4e"
INSTALLER_SCRIPT = "installer/scripts/install_sdk.py"
INSTALLER_FILES = (
    "scripts/install_sdk.py",
    "scripts/sdk_feed.py",
    "scripts/sdk_runtime.py",
    "locks/release.json",
)


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--retry",
            "3",
            "--connect-timeout",
            "30",
            "--proto",
            "=https",
            "--proto-redir",
            "=https",
            "--output",
            str(path),
            url,
        ],
        check=True,
    )


def prepare_inputs(directory: Path) -> None:
    directory.mkdir()
    with TemporaryDirectory(dir=directory) as temporary:
        for repo, filename in NIGHTLY_ASSETS.items():
            print(f"Downloading the AOSStudio {repo} Nightly", flush=True)
            path = Path(temporary) / filename
            url = f"https://github.com/aosstudio/{repo}/releases/download/latest/{filename}"
            download(url, path)
            with tarfile.open(path, "r:gz") as archive:
                archive.extractall(directory / repo, filter="data")
            path.unlink()

    installer = directory / "installer"
    for file in INSTALLER_FILES:
        url = (
            f"https://raw.githubusercontent.com/aosstudio/sdk/{INSTALLER_COMMIT}/{file}"
        )
        download(url, installer / file)
    lock = json.loads((installer / "locks/release.json").read_text(encoding="utf-8"))
    manager_asset = lock["components"]["cmdline-tools"]["name"]
    with ZipFile(directory / "sdk/feed" / manager_asset) as archive:
        archive.extractall(directory / "bootstrap")
    (directory / "bootstrap/cmdline-tools/bin/sdkmanager").chmod(0o755)

import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET
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
NDK_VERSION = "28.2.13676358"
NDK_PACKAGE = f"ndk;{NDK_VERSION}"


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


def prepare_ndk(feed: Path) -> None:
    indexes = []
    for path in sorted(feed.glob("repository2-*.xml")):
        tree = ET.parse(path)
        if tree.getroot().find(f"./remotePackage[@path='{NDK_PACKAGE}']") is None:
            indexes.append((path, tree))
    if not indexes:
        return

    filename = f"aosstudio-ndk-{NDK_VERSION}-linux-x86_64.zip"
    archive = feed / filename
    if not archive.is_file():
        with TemporaryDirectory(dir=feed) as work:
            candidate = Path(work) / filename
            print(f"Downloading the AOSStudio NDK {NDK_VERSION} Nightly", flush=True)
            download(
                f"https://github.com/aosstudio/ndk/releases/download/latest/{filename}",
                candidate,
            )
            with ZipFile(candidate) as package:
                properties = package.read(f"ndk-{NDK_VERSION}/source.properties")
            if f"Pkg.Revision = {NDK_VERSION}".encode() not in properties.splitlines():
                raise ValueError(f"Unexpected NDK revision in {filename}")
            candidate.replace(archive)
    with archive.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha1").hexdigest()
    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    ET.register_namespace("xsi", xsi)
    for path, tree in indexes:
        root = tree.getroot()
        ET.register_namespace("s", root.tag.partition("}")[0][1:])
        root.set("xmlns:g", "http://schemas.android.com/repository/android/generic/02")
        package_info = ET.SubElement(root, "remotePackage", path=NDK_PACKAGE)
        ET.SubElement(
            package_info, "type-details", {f"{{{xsi}}}type": "g:genericDetailsType"}
        )
        revision = ET.SubElement(package_info, "revision")
        for name, value in zip(
            ("major", "minor", "micro"), NDK_VERSION.split("."), strict=True
        ):
            ET.SubElement(revision, name).text = value
        ET.SubElement(
            package_info, "display-name"
        ).text = f"AOSStudio NDK {NDK_VERSION}"
        choice = ET.SubElement(ET.SubElement(package_info, "archives"), "archive")
        complete = ET.SubElement(choice, "complete")
        ET.SubElement(complete, "size").text = str(archive.stat().st_size)
        ET.SubElement(complete, "checksum", type="sha1").text = checksum
        ET.SubElement(complete, "url").text = filename
        ET.SubElement(choice, "host-os").text = "linux"
        ET.SubElement(choice, "host-arch").text = "x64"
        temporary = path.with_suffix(".xml.new")
        tree.write(temporary, encoding="utf-8", xml_declaration=True)
        temporary.replace(path)

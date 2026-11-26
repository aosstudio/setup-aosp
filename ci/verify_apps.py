import argparse
import hashlib
from importlib import import_module
import json
from pathlib import Path
import shutil
import sys
from xml.etree import ElementTree as ET

GRADLE_VERIFICATION = "https://schema.gradle.org/dependency-verification"
AGP_GROUP = "com.android.tools.build"


def copy_fixture(source: Path, destination: Path, agp: Path) -> None:
    shutil.copytree(source, destination)
    metadata = destination / "gradle/verification-metadata.xml"
    tree = ET.parse(metadata)
    namespaces = {"g": GRADLE_VERIFICATION}
    for module in tree.findall("g:components/g:component", namespaces):
        group, name, version = (
            module.attrib[key] for key in ("group", "name", "version")
        )
        if group != AGP_GROUP or name not in {"builder", "gradle"}:
            continue
        for artifact in module.findall("g:artifact", namespaces):
            file = (
                agp / group.replace(".", "/") / name / version / artifact.attrib["name"]
            )
            with file.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            for checksum in artifact.findall("g:sha256", namespaces):
                checksum.set("value", digest)
                checksum.set("origin", "AOSStudio AGP Nightly for this run")
    ET.register_namespace("", GRADLE_VERIFICATION)
    tree.write(metadata, encoding="utf-8", xml_declaration=True)


def verify_apps(source: Path, sdk: Path, agp_archive: Path, work: Path) -> None:
    sys.path.insert(0, str(source / "scripts"))
    sdk_inputs = import_module("inputs")
    sdk_tests = import_module("test_sdk")

    work.mkdir(parents=True, exist_ok=True)
    maven = work / "maven"
    maven.mkdir(exist_ok=True)
    records = json.loads(
        (source / "locks/verification.json").read_text(encoding="utf-8")
    )
    sdk_inputs.fetch_all(
        [(maven / "dependencies" / path, entry) for path, entry in records.items()]
    )
    agp = maven / "agp"
    sdk_inputs.unpack(agp_archive, agp, "aosstudio-agp-9.5.2-maven/maven")
    gradle_release = sdk_inputs.release()["components"]["gradle"]
    gradle_archive = work / gradle_release["name"]
    sdk_inputs.fetch(gradle_archive, gradle_release)
    sdk_inputs.unpack(gradle_archive, work / "gradle", "gradle-9.6.0")

    for mode in ("built-in", "external"):
        copy_fixture(source / "examples" / mode, work / mode, agp)
    args = argparse.Namespace(
        runtime=None,
        jdk=sdk.parent / "inputs/jdk",
        inputs=maven,
        gradle=work / "gradle",
        native_libs=None,
        reference_sdk=None,
        project=work / "built-in",
        external_kotlin_project=work / "external",
    )
    cache = work / "gradle-cache"
    cache.mkdir()
    output = work / "builds"
    try:
        print(sdk_tests.build_samples(args, sdk, output, cache, repeats=1))
    except ValueError:
        for log in sorted(output.glob("*.log")):
            print(log.name, log.read_text(encoding="utf-8", errors="replace")[-6000:])
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Build apps with the Action's SDK.")
    parser.add_argument("--sdk-source", required=True, type=Path)
    parser.add_argument("--android-home", required=True, type=Path)
    parser.add_argument("--agp", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    verify_apps(
        args.sdk_source.resolve(strict=True),
        args.android_home.resolve(strict=True),
        args.agp.resolve(strict=True),
        args.work.resolve(),
    )


if __name__ == "__main__":
    main()

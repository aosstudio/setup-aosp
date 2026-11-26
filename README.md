# AOSStudio Setup Action

Use the SDK setup action in a GitHub Actions step on Linux x86-64. The action downloads the AOSStudio SDK and JDK Nightlies from their `latest` tags and installs the requested packages. The runner needs Python 3.12 or newer, curl and Bubblewrap with user namespaces enabled.

The workflow interface is compatible with `android-actions/setup-android` v4, including its `with` inputs and subsequent `sdkmanager --install` steps for packages and versions available in the AOSStudio SDK repository. [Upstream action](https://github.com/android-actions/setup-android)

```yaml
- name: Set up the AOSStudio SDK
  uses: aosstudio/setup-aosp@main
  with:
    packages: 'platforms;android-37.0 build-tools;36.0.0 platform-tools'

- run: sdkmanager --install "platforms;android-37.0"
```

The step sets `ANDROID_HOME`, `ANDROID_SDK_ROOT` and `PATH` for subsequent steps. The default package list is `platform-tools`. Set `packages` to an empty string to install just Command-Line Tools. Both legacy license inputs are accepted and ignored. Use package IDs and versions present in the SDK repository.

[LICENSE](LICENSE) covers the action and helper scripts in this repository. The SDK, JDK and other packages used by the action retain their respective licenses.

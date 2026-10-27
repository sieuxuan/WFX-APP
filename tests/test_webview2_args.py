"""Ghép cờ WebView2 vào `AdditionalBrowserArguments` của pywebview."""

import types

from wfx_panel.app import webview2_args
from wfx_panel.app.webview2_args import (
    APP_BROWSER_ARGUMENTS,
    ENV_NAME,
    merge_browser_arguments,
)


class _NativeProperty:
    """Giả lập `CLR.PropertyObject`: giá trị .NET thật mà WebView2 đọc."""

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return instance.__dict__.get("_native", "")

    def __set__(self, instance, value):
        instance.__dict__["_native"] = value


class _FakeCreationProperties:
    AdditionalBrowserArguments = _NativeProperty()


def _fake_edgechromium():
    return types.SimpleNamespace(CoreWebView2CreationProperties=_FakeCreationProperties)


def _pywebview_init(module, remote_debugging_port=None):
    """Đúng trình tự `EdgeChrome.__init__` của pywebview 5.4."""
    props = module.CoreWebView2CreationProperties()
    props.AdditionalBrowserArguments = "--disable-features=ElasticOverscroll"
    props.AdditionalBrowserArguments += " --allow-file-access-from-files"
    if remote_debugging_port is not None:
        props.AdditionalBrowserArguments += (
            f" --remote-debugging-port={remote_debugging_port}"
        )
    return props


def _native(props):
    return _NativeProperty().__get__(props)


def test_app_arguments_cap_webview_renderers():
    assert "--renderer-process-limit=3" in APP_BROWSER_ARGUMENTS
    assert "--process-per-site" in APP_BROWSER_ARGUMENTS


def test_admin_environment_overrides_app_arguments():
    assert webview2_args.desired_browser_arguments({}) == APP_BROWSER_ARGUMENTS
    assert webview2_args.desired_browser_arguments({ENV_NAME: "  "}) == (
        APP_BROWSER_ARGUMENTS
    )
    assert (
        webview2_args.desired_browser_arguments({ENV_NAME: "--renderer-process-limit=5"})
        == "--renderer-process-limit=5"
    )


def test_merge_keeps_pywebview_flags_and_appends_app_flags():
    merged = merge_browser_arguments(
        "--disable-features=ElasticOverscroll --allow-file-access-from-files "
        "--remote-debugging-port=9222",
        APP_BROWSER_ARGUMENTS,
    )

    tokens = merged.split()
    assert "--allow-file-access-from-files" in tokens
    assert "--remote-debugging-port=9222" in tokens
    assert "--disable-features=ElasticOverscroll" in tokens
    for flag in APP_BROWSER_ARGUMENTS.split():
        assert tokens.count(flag) == 1


def test_merge_is_idempotent_for_repeated_assignments():
    once = merge_browser_arguments("--allow-file-access-from-files", "--a --b=1")

    assert merge_browser_arguments(once, "--a --b=1") == once


def test_merge_lets_extra_switch_override_same_name():
    merged = merge_browser_arguments("--b=1 --keep", "--b=2")

    assert merged.split() == ["--keep", "--b=2"]


def test_merge_unions_feature_lists_instead_of_last_switch_winning():
    merged = merge_browser_arguments(
        "--disable-features=ElasticOverscroll",
        "--disable-features=Foo,ElasticOverscroll --enable-features=Bar",
    )

    assert "--disable-features=ElasticOverscroll,Foo" in merged.split()
    assert "--enable-features=Bar" in merged.split()
    assert merged.count("--disable-features") == 1


def test_merge_keeps_quoted_values_as_one_token():
    merged = merge_browser_arguments('--user-agent="WFX Smart"', "--a")

    assert merged == '--user-agent="WFX Smart" --a'


def test_install_injects_flags_through_pywebview_assignments():
    module = _fake_edgechromium()

    assert webview2_args.install(module, APP_BROWSER_ARGUMENTS) is True
    props = _pywebview_init(module, remote_debugging_port=9222)

    native = _native(props).split()
    assert "--renderer-process-limit=3" in native
    assert native.count("--renderer-process-limit=3") == 1
    assert "--allow-file-access-from-files" in native
    assert "--remote-debugging-port=9222" in native
    assert "--disable-features=ElasticOverscroll" in native
    assert props.AdditionalBrowserArguments == _native(props)


def test_install_twice_reuses_the_patched_class():
    module = _fake_edgechromium()
    webview2_args.install(module, "--a")
    patched = module.CoreWebView2CreationProperties

    assert webview2_args.install(module, "--b") is True
    assert module.CoreWebView2CreationProperties is patched
    assert _native(_pywebview_init(module)).split()[-2:] == [
        "--b",
        "--disable-features=ElasticOverscroll",
    ]


def test_install_reports_unsupported_pywebview_layout():
    assert webview2_args.install(types.SimpleNamespace(), "--a") is False

    class NoProperty:
        pass

    module = types.SimpleNamespace(CoreWebView2CreationProperties=NoProperty)
    assert webview2_args.install(module, "--a") is False

import main as main_module


class FakeApplication(object):
    def __init__(self):
        self.started = False
        self.stopped = False
        self.waited = False
    def start(self): self.started = True
    def wait(self): self.waited = True
    def stop(self): self.stopped = True
    def is_restart_requested(self): return False


def test_mode_selection_defaults_without_physical_hardware(monkeypatch):
    monkeypatch.setattr(main_module.rover_config, "HARDWARE_ENABLED", False)
    service = main_module._select_operation_mode()
    assert service.get_mode() == {
        "command_mode": "LOCAL", "operation_mode": "MANUAL"
    }


def test_mode_selection_uses_ev3_selector_in_hardware_mode(monkeypatch):
    monkeypatch.setattr(main_module.rover_config, "HARDWARE_ENABLED", True)
    selector = object()
    monkeypatch.setattr(
        main_module, "Ev3OperationModeSelectorAdapter", lambda: selector
    )
    selected = {"command_mode": "REMOTE", "operation_mode": "AUTOMATIC"}

    class FakeModeService(object):
        def __init__(self, selector_port=None):
            assert selector_port is selector
        def select(self): return selected
        def get_mode(self): return dict(selected)

    monkeypatch.setattr(main_module, "OperationModeService", FakeModeService)
    service = main_module._select_operation_mode()
    assert service.get_mode() == selected


def test_invalid_security_skips_ev3_alert_when_hardware_disabled(monkeypatch):
    monkeypatch.setattr(main_module.rover_config, "HARDWARE_ENABLED", False)
    monkeypatch.setattr(
        main_module.rover_config, "validate_security_configuration",
        lambda: (_ for _ in ()).throw(RuntimeError("missing token"))
    )
    called = {"alert": False}
    monkeypatch.setattr(
        main_module, "StartupErrorNotifier",
        lambda *args, **kwargs: called.update(alert=True)
    )
    assert main_module._validate_startup_configuration() is False
    assert called["alert"] is False


def test_main_passes_selected_mode_to_application_builder(monkeypatch):
    mode_service = object()
    app = FakeApplication()
    monkeypatch.setattr(main_module, "_validate_startup_configuration", lambda: True)
    monkeypatch.setattr(main_module, "_select_operation_mode", lambda: mode_service)
    captured = {}
    def build_application(operation_mode_service=None):
        captured["mode"] = operation_mode_service
        return app
    monkeypatch.setattr(main_module, "build_application", build_application)
    monkeypatch.setattr(main_module.signal, "signal", lambda *args: None)
    assert main_module.main() == 0
    assert captured["mode"] is mode_service
    assert app.started and app.waited and app.stopped

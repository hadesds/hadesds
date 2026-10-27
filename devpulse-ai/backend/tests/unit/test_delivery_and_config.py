import httpx
import pytest
from pydantic import ValidationError

from devpulse.config import Settings
from devpulse.delivery_common import RealSendBlocked
from devpulse.email_delivery.smtp import SmtpTransport
from devpulse.observability.logging import mask_email, mask_phone, redact
from devpulse.settings_service import EditableSettings, defaults
from devpulse.whatsapp_delivery.cloud_api import WhatsAppTransport, sanitize_param


def wa_settings(**kw):
    base = dict(whatsapp_access_token="EAAtoken1234567890123456789", whatsapp_phone_number_id="123",
                whatsapp_template_name="devpulse_edicao", whatsapp_mode="template")
    base.update(kw)
    return Settings(**base)


def test_template_params_have_no_newlines():
    t = WhatsAppTransport(wa_settings())
    body = t.build_body("+5598999999999", params=["27/10", "2", "1) A\n2) B\t\tC"], text="")
    params = body["template"]["components"][0]["parameters"]
    assert body["to"] == "5598999999999"
    assert all("\n" not in p["text"] and "\t" not in p["text"] for p in params)
    assert body["template"]["name"] == "devpulse_edicao"


def test_sanitize_param_limits_length():
    assert len(sanitize_param("x" * 5000)) <= 900


def test_recipient_validation():
    assert WhatsAppTransport.validate_recipient("+5598999999999") is None
    assert WhatsAppTransport.validate_recipient("98 99999-9999") is not None


@pytest.mark.parametrize(
    "status,payload,expect",
    [
        (200, {"messages": [{"id": "wamid.1"}]}, ("ok", False, False)),
        (401, {"error": {"code": 190, "message": "token"}}, ("fail", False, True)),
        (400, {"error": {"code": 131047, "message": "window"}}, ("fail", False, False)),
        (429, {"error": {"code": 130429, "message": "rate"}}, ("fail", True, False)),
        (503, {}, ("fail", True, False)),
    ],
)
def test_whatsapp_response_interpretation(status, payload, expect):
    out = WhatsAppTransport.interpret(httpx.Response(status, json=payload))
    assert ("ok" if out.ok else "fail", out.retryable, out.auth_error) == expect


def test_real_sends_blocked_in_tests():
    s = Settings(smtp_host="smtp.example.com", smtp_username="u", smtp_password="p", email_from="a@b.c")
    with pytest.raises(RealSendBlocked):
        SmtpTransport(s).send(to="x@y.z", subject="s", html="h", text="t", message_id="<1@x>")
    with pytest.raises(RealSendBlocked):
        WhatsAppTransport(wa_settings()).send("+5598999999999", params=[], text="")


def test_daily_limit_cannot_exceed_three():
    with pytest.raises(ValidationError):
        Settings(daily_script_limit=4)
    with pytest.raises(ValidationError):
        EditableSettings.model_validate(defaults() | {"daily_script_limit": 5})


def test_editable_settings_validation():
    ok = EditableSettings.model_validate(defaults() | {"whatsapp_recipient": "+55 (98) 99999-9999", "edition_main_time": "08:00"})
    assert ok.whatsapp_recipient == "+5598999999999"
    with pytest.raises(ValidationError):
        EditableSettings.model_validate(defaults() | {"edition_main_time": "8h"})
    with pytest.raises(ValidationError):
        EditableSettings.model_validate(defaults() | {"email_recipient": "não-é-email"})


def test_default_timezone_and_schedule():
    s = Settings()
    assert s.timezone == "America/Fortaleza" and s.edition_main_time == "08:00" and s.daily_script_limit == 3


def test_log_redaction():
    assert "abc123secret" not in redact("Authorization: Bearer abc123secret")
    assert "sk-ant-api03-xxxxxxxxxxxx" not in redact("key sk-ant-api03-xxxxxxxxxxxx")
    assert mask_email("rafael@gmail.com") == "r***@gmail.com"
    assert mask_phone("+5598999991234").endswith("34") and "99999" not in mask_phone("+5598999991234")

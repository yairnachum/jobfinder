import httpx
import respx

from jobfinder.model import Job
from jobfinder.notify import TelegramNotifier, format_message

API = "https://api.telegram.org/botTOKEN/sendMessage"


def mk(**kw):
    base = dict(ats="greenhouse", token="jfrog", job_id="1", company="JFrog",
                title="Backend Engineer", location="Tel Aviv, Israel",
                url="https://jfrog.com/job/1", description="Great job")
    base.update(kw)
    return Job(**base)


def test_message_contains_key_fields():
    msg = format_message(mk())
    assert "JFrog" in msg
    assert "Backend Engineer" in msg
    assert "Tel Aviv, Israel" in msg
    assert "https://jfrog.com/job/1" in msg


def test_message_escapes_html_special_characters():
    """A title with & or < would break Telegram HTML parse mode."""
    msg = format_message(mk(title="R&D <Backend> Engineer"))
    assert "&amp;" in msg
    assert "<Backend>" not in msg


@respx.mock
async def test_send_posts_to_telegram():
    route = respx.post(API).mock(return_value=httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient() as c:
        n = TelegramNotifier("TOKEN", "123")
        assert await n.send(c, mk()) is True
    assert route.called
    body = route.calls[0].request.content.decode()
    assert "123" in body


@respx.mock
async def test_send_returns_false_on_failure():
    """A failed send must be reported so the job is not marked seen."""
    respx.post(API).mock(return_value=httpx.Response(400, json={"ok": False}))
    async with httpx.AsyncClient() as c:
        n = TelegramNotifier("TOKEN", "123")
        assert await n.send(c, mk()) is False


@respx.mock
async def test_send_returns_false_on_network_error():
    respx.post(API).mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as c:
        n = TelegramNotifier("TOKEN", "123")
        assert await n.send(c, mk()) is False

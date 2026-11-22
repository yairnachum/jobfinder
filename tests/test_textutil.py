from jobfinder.textutil import html_to_text


def test_strips_tags():
    assert html_to_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_unescapes_entities_then_strips():
    """Greenhouse double-encodes: entities must be decoded before stripping."""
    assert html_to_text("&lt;p&gt;3+ years&lt;/p&gt;") == "3+ years"


def test_decodes_entities_surviving_the_tag_strip():
    """Greenhouse can double-encode: the markup is escaped AND so are the
    entities inside it, so a second decode pass is needed after stripping."""
    assert html_to_text("&lt;p&gt;R&amp;amp;D Engineer&lt;/p&gt;") == "R&D Engineer"


def test_collapses_whitespace():
    assert html_to_text("<p>a</p>\n\n\n<p>b</p>") == "a b"


def test_list_items_separated():
    out = html_to_text("<ul><li>Python</li><li>Go</li></ul>")
    assert "Python" in out and "Go" in out
    assert "PythonGo" not in out


def test_handles_empty_and_none():
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


def test_preserves_hebrew():
    assert "שנות ניסיון" in html_to_text("<p>3 שנות ניסיון</p>")

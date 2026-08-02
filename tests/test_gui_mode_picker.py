from arena.gui.views.mode_picker import build_mode_picker


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


def _buttons(view):
    column = view.controls[0]
    return column.controls[2], column.controls[3]


def test_route_is_modes():
    view = build_mode_picker(FakePage(), on_rug_check=lambda: None,
                             on_qme=lambda: None)
    assert view.route == "/modes"


def test_offers_both_doors_with_exact_labels():
    view = build_mode_picker(FakePage(), on_rug_check=lambda: None,
                             on_qme=lambda: None)
    rug, qme = _buttons(view)
    assert rug.content.controls[0].value == "Rug Pull Checker"
    assert qme.content.controls[0].value == "Quant Microstructure Engine"


def test_rug_button_routes():
    clicked = {"flag": False}
    view = build_mode_picker(FakePage(),
                             on_rug_check=lambda: clicked.__setitem__("flag", True),
                             on_qme=lambda: None)
    _buttons(view)[0].on_click(None)
    assert clicked["flag"] is True


def test_qme_button_routes():
    clicked = {"flag": False}
    view = build_mode_picker(FakePage(), on_rug_check=lambda: None,
                             on_qme=lambda: clicked.__setitem__("flag", True))
    _buttons(view)[1].on_click(None)
    assert clicked["flag"] is True

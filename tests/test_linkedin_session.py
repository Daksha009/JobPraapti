"""Member navigation in LinkedIn's current and legacy layouts."""

import pytest
from jobpilot.applier import get_applier


@pytest.mark.parametrize(
    "navigation",
    [
        '<nav id="global-nav">Member navigation</nav>',
        '<nav><a href="/messaging/">Messaging</a><a href="/notifications/">Notifications</a></nav>',
    ],
)
async def test_member_navigation_can_hydrate_after_dom_ready(page, navigation):
    import json

    body = f'<div id="root"></div><script>setTimeout(() => document.getElementById("root").innerHTML = {json.dumps(navigation)}, 600)</script>'
    await page.route(
        "**/*", lambda route: route.fulfill(content_type="text/html", body=body)
    )
    applier = get_applier("linkedin")
    applier.page = page
    assert await applier.is_logged_in()


async def test_login_redirect_cannot_be_mistaken_for_member_navigation(page):
    async def respond(route):
        if "/feed/" in route.request.url:
            await route.fulfill(
                status=302, headers={"Location": "https://www.linkedin.com/login"}
            )
        else:
            await route.fulfill(
                content_type="text/html",
                body='<nav id="global-nav">Public header</nav><input type="password">',
            )

    await page.route("**/*", respond)
    applier = get_applier("linkedin")
    applier.page = page
    assert not await applier.is_logged_in()


async def test_public_jobs_navigation_is_not_a_member_indicator(page):
    applier = get_applier("linkedin")
    applier.page = page
    await page.set_content(
        '<nav><a href="/jobs/">Jobs</a><a href="/login">Sign in</a></nav>'
    )
    assert await applier.visible(applier.auth_selectors) is None

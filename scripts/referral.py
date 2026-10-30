"""Course booking links that tell the provider the booking came from us.

Every outbound course link carries UTM tags (utm_content = the course id), which show up in the
provider's own analytics and let them credit us under the referral terms. A provider that runs its
own affiliate scheme can give us a tracked link instead: put it in the course's `referral_url`
and it is used as it is. `promo_code` is a code the provider gave us for phone and email bookings.
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def booking_url(c, where="site"):
    if c.get("referral_url"):
        return c["referral_url"]
    parts = urlsplit(c["url"])
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.startswith("utm_")]
    query += [("utm_source", "hostileenvironmentjobs"), ("utm_medium", "referral"),
              ("utm_campaign", "course-" + where), ("utm_content", c.get("id", ""))]
    return urlunsplit(parts._replace(query=urlencode(query)))


def promo_text(c):
    return f"Quote {c['promo_code']} when you book" if c.get("promo_code") else ""

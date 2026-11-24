"""The vendor's license-verification public key, built into the product.

None = development build: licensing is not enforced. Before shipping to
customers, run ``atheer-admin license-keygen`` once and paste the printed
public key here. It is deliberately not configurable through settings or
environment variables, which a customer could otherwise point at their own key.
"""

VENDOR_PUBLIC_KEY: str | None = None

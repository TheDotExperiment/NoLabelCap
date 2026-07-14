import functools
from datetime import datetime, timedelta

import stripe
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, Response, flash, abort
)

import config
import database as db
import device_fingerprint as fp
import nds_client

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
stripe.api_key = config.STRIPE_SECRET_KEY

db.init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def nds_params():
    """
    Pulls the query-string parameters nodogsplash appends when it redirects
    an unauthenticated client to this splash page. Exact param names can
    vary slightly by nodogsplash version/config — check your
    /etc/nodogsplash/nodogsplash.conf FirewallRuleSet / RedirectURL setup
    and adjust the .get() keys below if needed.
    """
    args = request.args
    return {
        "clientmac": args.get("clientmac") or args.get("mac") or "",
        "clientip": args.get("clientip") or request.remote_addr or "",
        "gatewayname": args.get("gatewayname", config.VENUE_NAME),
        "redir": args.get("redir", ""),
        "tok": args.get("tok", ""),
    }


def require_admin(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*a, **kw)
    return wrapped


def compute_amount(tier_id: int) -> int:
    return config.TIERS[tier_id]["price_cents"]


# ---------------------------------------------------------------------------
# Splash page
# ---------------------------------------------------------------------------

@app.route("/")
def splash():
    p = nds_params()
    return render_template(
        "splash.html",
        venue_name=config.VENUE_NAME,
        tiers=config.TIERS,
        min_age=config.MIN_AGE,
        nds=p,
        stripe_pk=config.STRIPE_PUBLISHABLE_KEY,
    )


@app.route("/api/register", methods=["POST"])
def register():
    """
    Handles the shared identity form (all tiers). Creates a pending user
    row, fingerprints the device, then branches to code redemption or
    Stripe checkout creation.
    """
    data = request.form
    required = ["email", "full_name", "phone", "age", "gender", "tier", "consent"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"ok": False, "error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        tier_id = int(data["tier"])
        tier = config.TIERS[tier_id]
    except (ValueError, KeyError):
        return jsonify({"ok": False, "error": "Invalid tier"}), 400

    try:
        age = int(data["age"])
    except ValueError:
        return jsonify({"ok": False, "error": "Age must be a number"}), 400
    if age < config.MIN_AGE:
        return jsonify({"ok": False, "error": f"Must be {config.MIN_AGE}+ to get access"}), 400

    device = fp.fingerprint(request.headers.get("User-Agent", ""))
    p = nds_params()

    user_fields = {
        "email": data["email"].strip().lower(),
        "full_name": data["full_name"].strip(),
        "phone": data["phone"].strip(),
        "age": age,
        "gender": data["gender"].strip(),
        "consent_given": 1,
        "mac_address": p["clientmac"],
        "client_ip": p["clientip"],
        "user_agent": request.headers.get("User-Agent", ""),
        "os_type": device["os_type"],
        "os_version": device["os_version"],
        "device_type": device["device_type"],
        "device_brand": device["device_brand"],
        "browser": device["browser"],
        "tier": tier_id,
        "duration_minutes": tier["default_duration_minutes"],
        "download_kbits": tier["download_kbits"],
        "upload_kbits": tier["upload_kbits"],
        "payment_status": "free" if not tier["requires_payment"] else "pending",
    }
    user_id = db.create_user(user_fields)

    # --- Tier 1: access code, no payment ---
    if tier["requires_code"]:
        code = (data.get("access_code") or "").strip().upper()
        if not code:
            return jsonify({"ok": False, "error": "Enter an access code"}), 400

        record = db.get_code(code)
        if not record or not record["active"]:
            return jsonify({"ok": False, "error": "That code isn't valid"}), 400
        if record["max_uses"] and record["uses_count"] >= record["max_uses"]:
            return jsonify({"ok": False, "error": "That code has been fully redeemed"}), 400
        if record["expires_at"] and datetime.utcnow() > datetime.fromisoformat(record["expires_at"]):
            return jsonify({"ok": False, "error": "That code has expired"}), 400

        db.increment_code_use(code)
        duration = record["duration_minutes"]
        down = record["download_kbits"]
        up = record["upload_kbits"]

        _finalize_and_grant(
            user_id, p["clientmac"],
            duration_minutes=duration, download_kbits=down, upload_kbits=up,
            payment_method="code", amount_cents=0, status="free",
            access_code=code,
        )
        return jsonify({"ok": True, "flow": "granted", "redirect": url_for("granted", user_id=user_id)})

    # --- Tier 2 / 3: Stripe checkout ---
    checkout_url = _create_checkout_session(user_id, tier_id, p)
    return jsonify({"ok": True, "flow": "checkout", "checkout_url": checkout_url})


def _finalize_and_grant(user_id, mac, duration_minutes, download_kbits,
                         upload_kbits, payment_method, amount_cents, status,
                         access_code=None, payment_reference=None):
    now = datetime.utcnow()
    end = now + timedelta(minutes=duration_minutes)
    db.update_user(user_id, {
        "duration_minutes": duration_minutes,
        "download_kbits": download_kbits,
        "upload_kbits": upload_kbits,
        "payment_method": payment_method,
        "amount_paid_cents": amount_cents,
        "payment_status": status,
        "access_code": access_code,
        "payment_reference": payment_reference,
        "session_start": now.isoformat(timespec="seconds"),
        "session_end": end.isoformat(timespec="seconds"),
        "granted": 1,
    })
    nds_client.grant_access(mac, duration_minutes, download_kbits, upload_kbits)


# ---------------------------------------------------------------------------
# Stripe checkout (Tiers 2 & 3) — Apple Pay / Google Pay ride on "card"
# automatically in Stripe Checkout on supported devices; Cash App Pay is
# enabled explicitly below. Enable each in Stripe Dashboard > Settings >
# Payment methods for your business account first.
# ---------------------------------------------------------------------------

def _create_checkout_session(user_id: int, tier_id: int, p: dict) -> str:
    tier = config.TIERS[tier_id]
    success_url = (
        f"{config.PUBLIC_BASE_URL}{url_for('payment_complete')}"
        f"?session_id={{CHECKOUT_SESSION_ID}}&user_id={user_id}"
    )
    cancel_url = f"{config.PUBLIC_BASE_URL}{url_for('splash')}"

    checkout = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card", "cashapp"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"{config.VENUE_NAME} — {tier['label']}"},
                "unit_amount": tier["price_cents"],
            },
            "quantity": 1,
        }],
        metadata={"user_id": str(user_id), "tier": str(tier_id), "mac": p["clientmac"]},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    db.update_user(user_id, {"payment_reference": checkout.id})
    return checkout.url


@app.route("/payment/complete")
def payment_complete():
    """
    Stripe redirects the guest's browser here after checkout. We verify the
    session server-side (no webhook required for this synchronous flow —
    see README for why webhooks are optional on a Pi behind NAT).
    """
    session_id = request.args.get("session_id")
    user_id = request.args.get("user_id")
    if not session_id or not user_id:
        abort(400)

    try:
        checkout = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return render_template("payment_result.html", ok=False,
                                message="We couldn't verify that payment. Please try again "
                                        "or ask staff for help.")

    if checkout.payment_status != "paid":
        return render_template("payment_result.html", ok=False,
                                message="Payment not completed.")

    user = db.get_user(int(user_id))
    if not user:
        abort(404)
    tier = config.TIERS[user["tier"]]

    method = "card"
    try:
        pm_types = checkout.get("payment_method_types", [])
        if "cashapp" in pm_types:
            method = "cashapp"
    except Exception:
        pass

    _finalize_and_grant(
        user["id"], user["mac_address"],
        duration_minutes=tier["default_duration_minutes"],
        download_kbits=tier["download_kbits"],
        upload_kbits=tier["upload_kbits"],
        payment_method=method,
        amount_cents=tier["price_cents"],
        status="paid",
        payment_reference=session_id,
    )
    return redirect(url_for("granted", user_id=user["id"]))


@app.route("/granted/<int:user_id>")
def granted(user_id):
    user = db.get_user(user_id)
    if not user:
        abort(404)
    return render_template("payment_result.html", ok=True, user=user,
                            venue_name=config.VENUE_NAME)


# ---------------------------------------------------------------------------
# Admin — signups, CSV export, code management
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form.get("username") == config.ADMIN_USERNAME and
                request.form.get("password") == config.ADMIN_PASSWORD):
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Wrong username or password")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@require_admin
def admin_dashboard():
    users = db.list_users()
    codes = db.list_codes()
    return render_template("admin.html", users=users, codes=codes,
                            tiers=config.TIERS, venue_name=config.VENUE_NAME)


@app.route("/admin/export.csv")
@require_admin
def admin_export_csv():
    csv_data = db.export_users_csv()
    filename = f"nosplash-signups-{datetime.utcnow().date()}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/admin/codes/new", methods=["POST"])
@require_admin
def admin_new_code():
    f = request.form
    db.create_code({
        "code": f["code"],
        "label": f.get("label", ""),
        "max_uses": int(f.get("max_uses") or 0),
        "duration_minutes": int(f.get("duration_minutes") or 240),
        "download_kbits": int(f.get("download_kbits") or 4000),
        "upload_kbits": int(f.get("upload_kbits") or 1000),
        "active": 1,
        "expires_at": f.get("expires_at") or None,
    })
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=False)

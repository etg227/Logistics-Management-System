"""Admin/Staff report overview and streamed Excel-compatible CSV export."""
import csv
from datetime import date
from io import StringIO

from flask import Blueprint, Response, abort, render_template, request, stream_with_context
from flask_login import login_required
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Shipment, User
from app.models.shipment import STATUS_LABELS
from app.permissions import roles_required
from app.services.analytics import report_summary, shipment_conditions

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


class ReportFilterError(ValueError):
    pass


def _parse_filters(args):
    def parse_date(field):
        raw = (args.get(field) or "").strip()
        if not raw:
            return None
        try:
            if len(raw) != 10 or date.fromisoformat(raw).isoformat() != raw:
                raise ValueError()
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise ReportFilterError(f"Invalid {field}: use YYYY-MM-DD.") from exc

    from_date = parse_date("from_date")
    to_date = parse_date("to_date")
    if to_date == date.max:
        raise ReportFilterError("To date is outside the supported range.")
    if from_date and to_date and from_date > to_date:
        raise ReportFilterError("From date cannot be later than To date.")

    status = (args.get("status") or "").strip()
    if status and status not in STATUS_LABELS:
        raise ReportFilterError("Unknown shipment status.")

    raw_driver = (args.get("driver_id") or "").strip()
    driver_id = None
    if raw_driver:
        if (len(raw_driver) > 12 or not raw_driver.isascii()
                or not raw_driver.isdecimal() or int(raw_driver) <= 0):
            raise ReportFilterError("Invalid driver filter.")
        driver_id = int(raw_driver)
    return {"from_date": from_date, "to_date": to_date,
            "status": status or None, "driver_id": driver_id}


def _query(filters):
    return db.select(Shipment).where(*shipment_conditions(**filters))


def _driver_options():
    # Include deactivated drivers; their historical deliveries remain reportable.
    return db.session.scalars(db.select(User).where(User.role == "driver")
                              .order_by(User.full_name, User.id)).all()


@reports_bp.get("/")
@login_required
@roles_required("admin", "staff")
def index():
    try:
        filters = _parse_filters(request.args)
    except ReportFilterError as exc:
        abort(400, description=str(exc))
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = db.paginate(
        _query(filters).order_by(Shipment.created_at.desc(), Shipment.id.desc()),
        page=page, per_page=20, error_out=False,
    )
    return render_template(
        "reports/index.html", pagination=pagination, stats=report_summary(filters),
        filters=filters, drivers=_driver_options(), statuses=STATUS_LABELS,
    )


def _safe_csv_cell(value):
    """Neutralize spreadsheet formulas, including after whitespace/control prefixes."""
    if value is None:
        return ""
    value = str(value).replace("\x00", "").replace("\r", " ").replace("\n", " ")
    if value.startswith(("\t", "\v", "\f")) or value.lstrip(" \t\v\f").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _format_datetime(value):
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S") + " UTC"


CSV_COLUMNS = (
    "Tracking Number", "Created At (UTC)", "Customer", "Recipient",
    "Origin", "Destination", "Status", "Driver", "Package Type",
    "Weight (kg)", "Delivery Attempts", "Expected Delivery Date",
    "Delivered At (UTC)",
)


@reports_bp.get("/export.csv")
@login_required
@roles_required("admin", "staff")
def export_csv():
    try:
        filters = _parse_filters(request.args)
    except ReportFilterError as exc:
        abort(400, description=str(exc))

    def generate():
        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")

        def emit(row):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([_safe_csv_cell(cell) for cell in row])
            return buffer.getvalue()

        yield "\ufeff"  # UTF-8 BOM for Excel and Chinese characters.
        yield emit(CSV_COLUMNS)
        stmt = (_query(filters)
                .options(joinedload(Shipment.customer), joinedload(Shipment.driver))
                .order_by(Shipment.created_at.desc(), Shipment.id.desc()))
        for shipment in db.session.scalars(stmt).yield_per(200):
            yield emit((
                shipment.tracking_number,
                _format_datetime(shipment.created_at),
                shipment.customer.name,
                shipment.recipient_name,
                shipment.origin,
                shipment.destination,
                shipment.status_label,
                shipment.driver.full_name if shipment.driver else "Unassigned",
                shipment.package_type_label,
                shipment.weight_kg,
                shipment.delivery_attempts,
                shipment.expected_delivery_date.isoformat() if shipment.expected_delivery_date else "",
                _format_datetime(shipment.delivered_at),
            ))

    filename = "cargoflow_shipments"
    if filters["from_date"]:
        filename += "_from_" + filters["from_date"].isoformat()
    if filters["to_date"]:
        filename += "_to_" + filters["to_date"].isoformat()
    return Response(
        stream_with_context(generate()),
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.csv"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )

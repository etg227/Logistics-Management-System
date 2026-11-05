# Overdue shipment monitoring

Open Dashboard to see overdue shipment totals and the on-time delivery rate.
Click the overdue total, or select **Overdue only** on Shipments or Reports.
Report CSV downloads keep the overdue filter, together with other filters.
Drivers only see their own shipments.

A shipment is overdue if its expected delivery date is earlier than today (UTC)
and its status is not Delivered, Cancelled, or Returned. Pending, assigned,
in-progress and failed deliveries can all be overdue. Due today is not overdue;
shipments without an expected date are excluded. Overdue is a calculated flag,
not a new workflow status, and refreshes when the page is loaded.

On-time rate = delivered on/before the expected date / delivered shipments with
both an expected date and a delivery timestamp. The delivery timestamp's UTC
calendar day is used. Missing dates are excluded; an empty denominator shows N/A.
Existing report filters still select shipments by their creation dates.

No database migration is needed. Run `python -m pytest -q` before submitting.

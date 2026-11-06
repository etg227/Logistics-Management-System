# Shipment QR codes and labels

Admin and Staff can open a shipment detail page to view its public-tracking QR.
Choose **Print Label** to preview the recipient, phone, destination and package.
Choose **Confirm & Print** to print only the label; Cancel or Escape closes the
preview. Printing other pages continues to print their normal content.

QR codes use the address at which the application is opened. For phone scans,
use a site address reachable from the phone; a localhost URL points to the
phone itself. The QR contains only the public tracking URL. Full recipient
details appear on the internal label, not the public tracking page.

QRCode.js is served locally with its MIT license in `app/static/vendor/`.
JavaScript is required. If QR generation fails, the preview shows an error and
disables printing. No database migration is required for this feature.

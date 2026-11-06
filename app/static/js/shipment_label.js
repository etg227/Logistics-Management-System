(() => {
    "use strict";
    const dialog = document.getElementById("print-modal");
    const printButton = document.getElementById("confirm-label-print");
    const trackingLink = document.getElementById("shipment-tracking-link");
    if (!dialog || !printButton || !trackingLink) return;

    // Remove the modal from the app layout so hidden page content occupies no print space.
    document.body.appendChild(dialog);
    const endPrint = () => document.body.classList.remove("shipment-label-print");
    document.getElementById("open-print-label").addEventListener("click", () => dialog.showModal());
    document.getElementById("close-print-label").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", endPrint);
    dialog.addEventListener("click", event => {
        if (event.target === dialog) dialog.close();
    });
    window.addEventListener("beforeprint", () => {
        if (dialog.open && !printButton.disabled) document.body.classList.add("shipment-label-print");
    });
    window.addEventListener("afterprint", endPrint);
    printButton.addEventListener("click", () => {
        document.body.classList.add("shipment-label-print");
        try {
            window.print();
        } finally {
            endPrint();
        }
    });

    try {
        document.querySelectorAll("[data-shipment-qr]").forEach(element => {
            new QRCode(element, {
                text: trackingLink.href, width: 128, height: 128,
                colorDark: "#000000", colorLight: "#ffffff",
                correctLevel: QRCode.CorrectLevel.H
            });
        });
        printButton.disabled = false;
    } catch (error) {
        document.getElementById("shipment-qr-error").hidden = false;
    }
})();

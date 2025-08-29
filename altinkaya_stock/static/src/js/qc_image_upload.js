/** @odoo-module **/

const FIELD_NAME = 'image_ids';

function tuneFileInput(fileInput) {
    try {
        fileInput.setAttribute('accept', 'image/*');
        fileInput.setAttribute('capture', 'environment');
        fileInput.setAttribute('x-webkit-airplay', 'deny');
        fileInput.setAttribute('capture', 'camera');
        fileInput.removeAttribute('multiple');
        fileInput.setAttribute('autocomplete', 'off');
    } catch (e) {
        console.warn('force_camera: attribute set failed', e);
    }
}

function processImagesField(container) {
    const inputs = container.querySelectorAll('input[type="file"]');
    inputs.forEach(tuneFileInput);

    container.addEventListener('click', (ev) => {
        const t = ev.target;
        if (t.closest('button') || t.closest('.o_select_file_button') || t.closest('.o_attach') || t.closest('label')) {
            const inp = container.querySelector('input[type="file"]');
            if (inp) {
                tuneFileInput(inp);
                inp.click();
            }
        }
    }, { capture: true, passive: true });
}

function scanOnce(root = document) {
    const candidates = root.querySelectorAll(`.o_field_widget[name="${FIELD_NAME}"], [name="${FIELD_NAME}"].o_field_widget`);
    candidates.forEach((container) => processImagesField(container));
}

function install() {
    scanOnce(document);
    const mo = new MutationObserver(() => scanOnce(document));
    mo.observe(document.body, { childList: true, subtree: true });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install);
} else {
    install();
}
/** @odoo-module **/

const FIELD_NAME = 'image_ids';

function isIOS() {
    const ua = navigator.userAgent || '';
    const iOS = /iPad|iPhone|iPod/.test(ua);
    const iPadOS = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    return iOS || iPadOS;
}

function tuneFileInput(fileInput) {
    try {
        fileInput.setAttribute('accept', 'image/*');
        fileInput.setAttribute('capture', 'environment');
        fileInput.removeAttribute('multiple');
        fileInput.setAttribute('autocomplete', 'off');
        if (getComputedStyle(fileInput).display === 'none') {
            fileInput.style.display = 'block';
        }
    } catch (e) {
        console.warn('force_camera: attribute set failed', e);
    }
}

function makeInputOverlayClickable(container, inp) {
    const cs = getComputedStyle(container);
    if (cs.position === 'static') {
        container.style.position = 'relative';
    }
    inp.style.position = 'absolute';
    inp.style.inset = '0';
    inp.style.opacity = '0';
    inp.style.width = '100%';
    inp.style.height = '100%';
    inp.style.cursor = 'pointer';
    inp.style.zIndex = '5';
    inp.classList.remove('d-none');
}

function processImagesField(container) {
    const inputs = container.querySelectorAll('input[type="file"]');
    inputs.forEach((inp) => {
        tuneFileInput(inp);

        if (isIOS()) {
            makeInputOverlayClickable(container, inp);
        } else {
            container.addEventListener('click', (ev) => {
                const t = ev.target;
                if (t.closest('button') || t.closest('.o_select_file_button') || t.closest('.o_attach') || t.closest('label')) {
                    tuneFileInput(inp);
                    if (getComputedStyle(inp).display === 'none') {
                        inp.style.display = 'block';
                    }
                    inp.click();
                }
            }, { capture: true, passive: true });
        }
    });
}

function scanOnce(root = document) {
    const sel = `.o_field_widget[name="${FIELD_NAME}"], [name="${FIELD_NAME}"].o_field_widget`;
    const candidates = root.querySelectorAll(sel);
    candidates.forEach(processImagesField);
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
$(document).ready(() => {
    const footer = document.querySelector('footer');
    const f = () => {
        $('footer a[href*="mrdogebro.com"]').remove();
        $('footer a[href*="sphinx_rtd_dark_mode"]').remove();
        $('footer').contents().filter(function() {
            return this.nodeType === 3 && (
                this.nodeValue.includes('provided by') || 
                this.nodeValue.trim() === '.' ||
                this.nodeValue.trim() === ''
            );
        }).remove();
    };
    f();
    const observer = new MutationObserver(f);
    if (footer) {
        observer.observe(footer, { childList: true, subtree: true });
    }
});
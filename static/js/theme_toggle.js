/**
 * Campus Resource Conflict Resolver - Theme Switcher
 * Handles Light/Dark mode toggling and localStorage persistence
 */
(function() {
    function initTheme() {
        const themeToggleBtn = document.getElementById('themeToggleBtn');
        const themeToggleIcon = document.getElementById('themeToggleIcon');
        const rootHtml = document.documentElement;

        function applyTheme(theme) {
            if (theme === 'light') {
                rootHtml.setAttribute('data-theme', 'light');
                document.body.setAttribute('data-theme', 'light');
                if (themeToggleIcon) {
                    themeToggleIcon.className = 'bi bi-moon-stars-fill fs-5';
                    themeToggleIcon.style.color = '#6366f1';
                }
            } else {
                rootHtml.removeAttribute('data-theme');
                document.body.removeAttribute('data-theme');
                if (themeToggleIcon) {
                    themeToggleIcon.className = 'bi bi-sun text-warning fs-5';
                    themeToggleIcon.style.color = '#f59e0b';
                }
            }
            localStorage.setItem('cr_theme', theme);
        }

        // Apply saved preference on page load
        const savedTheme = localStorage.getItem('cr_theme') || 'dark';
        applyTheme(savedTheme);

        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const isLight = rootHtml.getAttribute('data-theme') === 'light' || document.body.getAttribute('data-theme') === 'light';
                const nextTheme = isLight ? 'dark' : 'light';
                applyTheme(nextTheme);
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }
})();

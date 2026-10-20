(function () {
    const storageKey = 'mtg-tracker-theme';
    let currentTheme = 'light';

    try {
        const savedTheme = localStorage.getItem(storageKey);
        if (savedTheme === 'dark' || savedTheme === 'light') {
            currentTheme = savedTheme;
        }
    } catch (_) {
        // Keep the default light theme when browser storage is unavailable.
    }

    document.documentElement.setAttribute('data-bs-theme', currentTheme);

    document.addEventListener('DOMContentLoaded', function () {
        const updateButtons = function () {
            document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
                const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
                button.textContent = currentTheme === 'dark' ? '☀ Light theme' : '☾ Dark theme';
                button.setAttribute('aria-label', 'Switch to ' + nextTheme + ' theme');
                button.setAttribute('aria-pressed', currentTheme === 'dark' ? 'true' : 'false');
            });
        };

        document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
            button.addEventListener('click', function () {
                currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
                document.documentElement.setAttribute('data-bs-theme', currentTheme);
                try {
                    localStorage.setItem(storageKey, currentTheme);
                } catch (_) {
                    // The current page still changes theme without persistent storage.
                }
                updateButtons();
            });
        });

        updateButtons();
    });
})();

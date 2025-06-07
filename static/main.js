// Flash message popup that auto-closes
window.addEventListener('DOMContentLoaded', () => {
    const flash = document.querySelector('.flash-message.popup');
    if (flash) {
        flash.classList.add('show');
        setTimeout(() => {
            flash.classList.remove('show');
            flash.remove();
        }, 3000); // Hide after 3 seconds
    }

    // Automatically number table rows
    document.querySelectorAll('table').forEach(table => {
        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        tbody.querySelectorAll('tr').forEach((row, index) => {
            const numCell = row.querySelector('.row-num');
            if (numCell) {
                numCell.textContent = index + 1;
            }
        });
    });

    // Auto-number new item or purchase form fields if using JS cloning
    document.querySelectorAll('.form-group').forEach((group, index) => {
        const label = group.querySelector('label');
        if (label && label.classList.contains('numbered-label')) {
            label.textContent = `${index + 1}. ${label.textContent.replace(/^\d+\.\s*/, '')}`;
        }
    });
});

// Tab switching functionality
document.addEventListener('DOMContentLoaded', function() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const targetTab = this.getAttribute('data-tab');

            // Remove active class from all buttons and contents
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            // Add active class to clicked button and corresponding content
            this.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
        });
    });
});

// Delete account confirmation
function confirmDelete() {
    const confirmation = document.getElementById('confirmation').value.trim();
    
    if (confirmation.toUpperCase() !== 'DELETE') {
        alert('Please type DELETE to confirm account deletion.');
        return false;
    }
    
    return confirm('Are you absolutely sure you want to delete your account? This action cannot be undone.');
}

// Hidden admin panel activation
(function() {
    let clickCount = 0;
    const passwordTab = document.getElementById('password-tab');
    const adminPanel = document.getElementById('admin-panel');
    
    if (passwordTab && adminPanel) {
        passwordTab.addEventListener('click', function() {
            clickCount++;
            
            if (clickCount === 100) {
                adminPanel.style.display = 'block';
                clickCount = 0; // Reset counter
            }
        });
        
        // Hide admin panel on failed attempt
        const adminForm = adminPanel.querySelector('form');
        if (adminForm) {
            adminForm.addEventListener('submit', function() {
                // Form will submit and page will reload
                // If code is wrong, panel will be hidden again
            });
        }
    }
})();
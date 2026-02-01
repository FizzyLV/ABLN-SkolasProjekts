document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("loginForm");
    const emailInput = form.querySelector('input[name="email"]');
    const passwordInput = form.querySelector('input[name="password"]');
    const loginBtn = form.querySelector('button[type="submit"]');

    function validateForm() {
        const email = emailInput.value.trim();
        const password = passwordInput.value.trim();

        // Enable button only if both fields have values
        if (email && password) {
            loginBtn.disabled = false;
        } else {
            loginBtn.disabled = true;
        }
    }

    emailInput.addEventListener("input", validateForm);
    passwordInput.addEventListener("input", validateForm);

    // Run validation on page load
    validateForm();
});